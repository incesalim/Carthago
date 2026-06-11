"""Unit tests for TEFAS per-day aggregation (AUM weighting, top-N, residuals)."""
from __future__ import annotations

from src.tefas.aggregate import TOP_N, aggregate_day


def info_row(kodu, unvan, aum, investors=10, price=1.0):
    return {
        "fonKodu": kodu, "fonUnvan": unvan, "tarih": "2026-06-09",
        "fiyat": price, "portfoyBuyukluk": aum, "kisiSayisi": investors,
        "tedPaySayisi": 1000, "borsaBultenFiyat": None, "rn": 1,
    }


def alloc_row(kodu, **pcts):
    row = {"fonKodu": kodu, "fonUnvan": "X", "tarih": "2026-06-09", "bilFiyat": 99.0}
    row.update(pcts)
    return row


class TestManagerAndCategory:
    def test_manager_grouping(self):
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("AAA", "AK PORTFÖY PARA PİYASASI FONU", 100.0, investors=5),
            info_row("BBB", "AK PORTFÖY HİSSE SENEDİ FONU", 200.0, investors=7),
            info_row("CCC", "İŞ PORTFÖY PARA PİYASASI FONU", 50.0, investors=3),
        ], [])
        rows = {r[2]: r for r in out["tefas_manager_daily"]}
        assert rows["AK PORTFÖY"] == ("2026-06-09", "YAT", "AK PORTFÖY", 300.0, 2, 12)
        assert rows["İŞ PORTFÖY"] == ("2026-06-09", "YAT", "İŞ PORTFÖY", 50.0, 1, 3)

    def test_null_aum_counts_fund_but_not_aum(self):
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("AAA", "AK PORTFÖY PARA PİYASASI FONU", None, investors=5),
            info_row("BBB", "AK PORTFÖY PARA PİYASASI FONU", 100.0, investors=2),
        ], [])
        (row,) = out["tefas_manager_daily"]
        assert row == ("2026-06-09", "YAT", "AK PORTFÖY", 100.0, 2, 7)

    def test_category_grouping(self):
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("AAA", "AK PORTFÖY PARA PİYASASI FONU", 100.0),
            info_row("BBB", "İŞ PORTFÖY PARA PİYASASI FONU", 300.0),
        ], [])
        (row,) = out["tefas_category_daily"]
        assert row[2] == "money_market"
        assert row[3] == 400.0


class TestAllocationWeighting:
    def test_aum_weighted_mix(self):
        # fund A: 100 TL, 100% equity; fund B: 300 TL, 100% gov debt
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("A", "X PORTFÖY HİSSE SENEDİ FONU", 100.0),
            info_row("B", "Y PORTFÖY BORÇLANMA ARAÇLARI FONU", 300.0),
        ], [
            alloc_row("A", hs=100.0),
            alloc_row("B", dt=100.0),
        ])
        rows = {r[2]: r for r in out["tefas_allocation_daily"]}
        assert rows["equity_tr"][3] == 25.0
        assert rows["gov_debt_tr"][3] == 75.0
        assert rows["equity_tr"][4] == 400.0  # covered AUM base

    def test_residual_clamped_to_other(self):
        # only 90% mapped → 10% residual lands in other; negative residual
        # (repo borrowing pushing the sum past 100) must NOT be subtracted.
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("A", "X PORTFÖY FONU", 100.0),
            info_row("B", "Y PORTFÖY FONU", 100.0),
        ], [
            alloc_row("A", hs=90.0),
            alloc_row("B", hs=120.0, r=-20.0),  # leveraged: sums to 100
        ])
        rows = {r[2]: r for r in out["tefas_allocation_daily"]}
        assert rows["other"][3] == 5.0          # 10% of half the base
        assert rows["equity_tr"][3] == 105.0    # (90+120)/2
        assert rows["money_market"][3] == -10.0

    def test_unknown_key_rolls_to_other(self):
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("A", "X PORTFÖY FONU", 100.0),
        ], [
            alloc_row("A", hs=60.0, zzz_new_field=40.0),
        ])
        rows = {r[2]: r for r in out["tefas_allocation_daily"]}
        assert rows["other"][3] == 40.0

    def test_fund_without_info_aum_excluded(self):
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("A", "X PORTFÖY FONU", 100.0),
        ], [
            alloc_row("A", hs=100.0),
            alloc_row("GHOST", dt=100.0),  # no info row → no weight
        ])
        rows = {r[2]: r for r in out["tefas_allocation_daily"]}
        assert "gov_debt_tr" not in rows
        assert rows["equity_tr"][3] == 100.0

    def test_no_alloc_rows_yields_empty(self):
        out = aggregate_day("YAT", "2026-06-09", [info_row("A", "X PORTFÖY FONU", 1.0)], [])
        assert out["tefas_allocation_daily"] == []


class TestTopFunds:
    def test_ranking_and_cutoff(self):
        infos = [
            info_row(f"F{i:02d}", f"M{i} PORTFÖY FONU", float(i)) for i in range(1, 21)
        ]
        out = aggregate_day("YAT", "2026-06-09", infos, [])
        top = out["tefas_top_funds"]
        assert len(top) == TOP_N
        assert top[0][2] == "F20" and top[0][5] == 1   # biggest AUM is rank 1
        assert top[-1][2] == "F06" and top[-1][5] == TOP_N

    def test_null_aum_excluded_from_top(self):
        out = aggregate_day("YAT", "2026-06-09", [
            info_row("A", "X PORTFÖY FONU", None),
            info_row("B", "Y PORTFÖY FONU", 5.0),
        ], [])
        assert [r[2] for r in out["tefas_top_funds"]] == ["B"]
