"""P&L repairs need complete identities and must preserve physical row ownership."""
from test_audit_validator import _clean_pl

from src.audit_reports.extractor import (
    _fitz_merge_rows, _parse_rows, _parse_with_chain, _split_label,
)
from src.audit_reports.validator import check_profit_loss


def _statement(*, trading=30):
    # Keep every mandatory roman and a complete, reconciling income chain.
    gross = 185 + trading
    net_op = gross - 55
    changes = {"VI.": trading, "VIII.": gross, "XIII.": net_op,
               "XVII.": net_op, "XIX.": net_op - 30, "XXV.": net_op - 30}
    return "\n".join(
        f"{r['hierarchy']} {r['item_name']} "
        f"{changes.get(r['hierarchy'], r['amount'] / 1000):,.0f} 108 77 66"
        for r in _clean_pl())


def _original(text):
    return _parse_rows(_fitz_merge_rows(text, 4), 4)


def _parsed(text):
    return _parse_with_chain(text, 4, "profit_loss")


def _rows(parsed):
    return {_split_label(label)[0]: (" ".join(_split_label(label)[1].split()), values)
            for label, values in parsed}


def _validation(parsed):
    return check_profit_loss([
        {"hierarchy": _split_label(label)[0], "item_name": _split_label(label)[1],
         "amount": values[0]} for label, values in parsed])


def test_ungrouped_prior_integer_does_not_displace_current_fee_income():
    # ZIRAATK: 2061 is a single prior-period cell, not the two cells 206 + 1.
    text = _statement() + "\n" + "\n".join([
        "4.1 Alınan Ücret ve Komisyonlar 3.649 2.626 1.941 1.500",
        "4.1.1 Gayri Nakdi Kredilerden 802 565 410 299",
        "4.1.2 Diğer 2.847 2061 1.531 1.201",
    ])
    before, after = _original(text), _parsed(text)
    assert _validation(before).failed > 0
    assert _validation(after).failed == 0
    assert _rows(after)["4.1.2"][1] == [2847, 2061, 1531, 1201]
    # A partial statement cannot authorize the candidate just because its fee
    # subtree happens to add up; the full roman chain must also be present.
    partial = "\n".join(text.splitlines()[-3:])
    assert _parsed(partial) == _original(partial)
    broken = text.replace("XXV. DÖNEM NET KÂR/ZARARI 130", "XXV. DÖNEM NET KÂR/ZARARI 999")
    assert _parsed(broken) == _original(broken)


def test_split_trading_minus_and_duplicated_merger_marker_require_full_chain():
    text = _statement(trading=-185)
    text = text.replace("-185 108 77 66", "- 185 108 -155 187")
    text = text.replace("XIV. BİRLEŞME İŞLEMİ SONRASI GELİR",
                        "XIII. BİRLEŞME İŞLEMİ SONRASINDA GELİR OLARAK KAYDEDİLEN FAZLALIK TUTARI")
    # An unrelated four-cell row with two genuine nils must remain unchanged.
    text += "\n2.6 Diğer faiz giderleri - 70 - 70"
    after = _parsed(text)
    rows = _rows(after)
    assert rows["VI."][1] == [-185, 108, -155, 187]
    assert rows["XIII."][1][0] == -55
    assert rows["XIV."][1] == [0, 108, 77, 66]
    assert rows["2.6"][1] == [0, 70, 0, 70]
    assert _validation(after).failed == 0
    bad_role = text.replace("FAZLALIK TUTARI", "UNRELATED ROW")
    assert "XIV." not in _rows(_parsed(bad_role))
    broken = text.replace("XXV. DÖNEM NET KÂR/ZARARI -85", "XXV. DÖNEM NET KÂR/ZARARI -500")
    assert _parsed(broken) == _original(broken)


def test_label_and_values_above_decimal_and_roman_markers_recover_all_columns():
    # ODEA: both decimals and XIII have figures ABOVE the hierarchy marker.
    text = _statement().replace(
        "XIII. NET FAALİYET KÂRI/ZARARI 160 108 77 66",
        "NET FAALİYET KÂRI/ZARARI 160 108 77 66\nXIII. (VIII-IX-X-XI-XII)")
    text += "\n" + "\n".join([
        "1.5 Menkul değerlerden faiz 120 70 65 20",
        "Gerçeğe uygun değer farkı kar zarara 20 10 15 5",
        "1.5.1 Yansıtılanlar",
        "Gerçeğe uygun değer farkı diğer gelire 40 20 25 5",
        "1.5.2 Yansıtılanlar",
        "1.5.3 İtfa edilmiş maliyet 60 40 25 10",
    ])
    before, after = _original(text), _parsed(text)
    assert _validation(before).failed > 0
    assert _validation(after).failed == 0
    rows = _rows(after)
    assert rows["1.5.1"] == ("Gerçeğe uygun değer farkı kar zarara Yansıtılanlar", [20, 10, 15, 5])
    assert rows["1.5.2"] == ("Gerçeğe uygun değer farkı diğer gelire Yansıtılanlar", [40, 20, 25, 5])
    assert rows["XIII."][1] == [160, 108, 77, 66]


def test_three_line_continuation_is_not_stolen_when_a_different_row_repairs():
    text = _statement(trading=-185).replace("-185 108 77 66", "- 185 108 -155 187")
    text += "\n" + "\n".join([
        "1.5 Interest 50 30 20 10",
        "1.5.1 Income from",
        "securities measured",
        "at fair value 20 10 10 5",
        "1.5.2 Other income",
        "1.5.3 Amortised cost 30 20 10 5",
    ])
    # Reassigning 20 from 1.5.1 to 1.5.2 would still satisfy every identity.
    # The preceding three-line label establishes ownership independently.
    after = _parsed(text)
    rows = _rows(after)
    assert rows["VI."][1][0] == -185
    assert rows["1.5.1"] == ("Income from securities measured at fair value", [20, 10, 10, 5])
    assert "1.5.2" not in rows
    assert _validation(after).failed == 0


def test_clean_multiperiod_income_statement_is_unchanged():
    text = _statement()
    assert _parsed(text) == _original(text)


def test_standalone_value_fallback_cannot_bypass_continuation_ownership():
    text = _statement().replace("XVII. VERGİ ÖNCESİ KÂR/ZARAR 160", "XVII. VERGİ ÖNCESİ KÂR/ZARAR 180")
    text = text.replace("NET K/Z 130", "NET K/Z 150").replace("NET KÂR/ZARARI 130", "NET KÂR/ZARARI 150")
    text = text.replace("XIV. BİRLEŞME İŞLEMİ SONRASI GELİR 0 108 77 66", "\n".join([
        "1.5 Interest 50 30 20 10",
        "1.5.2 Other interest 30 20 10 5",
        "1.5.1 Income from",
        "securities",
        "20 10 10 5",
        "XIV. BİRLEŞME İŞLEMİ SONRASI GELİR",
    ]))
    # Moving the bare 20 into missing XIV would enable an extra, passing chain
    # identity while dropping its owner's child-sum check. Do not manufacture it.
    assert _parsed(text) == _original(text)
    assert _rows(_parsed(text))["1.5.1"][1] == [20, 10, 10, 5]


def test_short_negative_prior_net_cannot_append_earnings_per_share():
    # HAYATK's (76) was counted as a note, so the last row swallowed EPS and
    # stored 9 from 0.0091 in place of its printed current net profit.
    text = _statement().replace("XXV. DÖNEM NET KÂR/ZARARI 130 108 77 66",
                                "XXV. DÖNEM NET KÂR/ZARARI (4.12.) 130 (76) 55 20")
    text += "\nHisse Başına Kâr / Zarar 0.0149 (0.0220) 0.0091 0.0051"
    rows = _rows(_parsed(text))
    assert rows["XXV."][1] == [130, -76, 55, 20]
    assert "Hisse" not in rows["XXV."][0]
    assert _validation(_parsed(text)).failed == 0
