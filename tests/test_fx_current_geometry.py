"""ICBC's split currency baselines must retain source row and sign ownership."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

from src.audit_reports import fx_position as fx
from src.audit_reports.validator import check_fx_position


COLS = ["EUR", "USD", "OTHER", "TOTAL"]
VALUES = [
    [17906630, 31688414, 1041939, 50636983],
    [10824925, 35424548, 2443483, 48692956],
    [7081705, -3736134, -1401544, 1944027],
    [-6743612, 4998781, 1413414, -331417],
    [2559643, 9452478, 1976631, 13988752],
    [9303255, 4453697, 563217, 14320169],
]
LABELS = ["Toplam Varlıklar", "Toplam Yükümlülükler", "Net Bilanço Pozisyonu",
          "Net Bilanço Dışı Pozisyon", "Türev Finansal Araçlardan Alacaklar",
          "Türev Finansal Araçlardan Borçlar"]


def source_words():
    words = []
    edges = [377.46, 440.46, 491.73, 544.29]
    for idx, (label, values, y) in enumerate(zip(
            LABELS, VALUES, [304.76, 396.82, 412.90, 428.99, 444.95, 461.03])):
        words.append((58.2, y, 260, y + 9, label))
        for col, (edge, value) in enumerate(zip(edges, values)):
            ny = y + (.60 if idx < 2 else 1.20 if col == 0 else -2.88)
            text = f"{abs(value):,}"
            words.append((edge - 28, ny, edge, ny + 7.7, text))
            if value < 0:
                if idx == 3 and col == 0:
                    # EUR minus occupies its own baseline above the numeral.
                    words.append((edge - 2.3, ny - 8.04, edge, ny - .34, "-"))
                else:
                    words.append((edge - 44, ny, edge - 41.7, ny + 7.7, "-"))
    return words


def test_split_baselines_and_detached_signs_recover_all_source_cells():
    candidate = fx._coordinate_current_block(source_words(), COLS)
    assert [[candidate[c][f] for c in COLS] for f in fx._FIELDS] == VALUES
    rows = []
    for currency, fields in candidate.items():
        row = fx.FxRow("current", currency, **fields)
        row.net_position = row.net_on_balance + row.net_off_balance
        rows.append(asdict(row))
    validation = check_fx_position(rows)
    assert validation.failed == 0
    assert rows[-1]["net_position"] == 1612610


def test_missing_cell_is_not_invented_from_an_identity():
    words = [w for w in source_words() if w[4] != "1,944,027"]
    assert fx._coordinate_current_block(words, COLS) == {}


def test_ambiguous_or_uncorroborated_signs_reject_the_entire_candidate():
    words = [w for w in source_words() if not (w[4] == "-" and w[1] > 420 and w[0] < 400)]
    assert fx._coordinate_current_block(words, COLS) == {}
    words = deepcopy(source_words())
    words.append((375.16, 430.19, 377.46, 437.89, "-"))
    assert fx._coordinate_current_block(words, COLS) == {}


def test_closer_neighbour_label_owns_its_amount_even_when_identities_would_pass():
    words = source_words()
    # The EUR amount lies within 7pt of the net-on row, but a distinct labelled
    # row now owns it. Numerical coincidence cannot override that ownership.
    words = [(w[0], 417.1, w[2], 424.8, w[4]) if w[4] == "7,081,705" else w
             for w in words]
    words.append((58.2, 416.1, 260, 425.1, "Other source disclosure"))
    assert fx._coordinate_current_block(words, COLS) == {}


def test_missing_derivative_disclosure_cannot_use_the_next_non_cash_row():
    words = [w for w in source_words() if w[4] != LABELS[-1]]
    words.append((58.2, 461.03, 260, 470.03, "Non-cash loans"))
    assert fx._coordinate_current_block(words, COLS) == {}


def test_repair_replaces_current_only_and_keeps_prior_source_values(monkeypatch):
    words = source_words()
    lines = []
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        if lines and w[1] - lines[-1][0] <= 3:
            lines[-1][1].append((w[0], w[4]))
        else:
            lines.append((w[1], [(w[0], w[4])]))
    tokens = [[(350, "EUR"), (412, "USD"), (464, "Other"), (516, "Total")],
              *[sorted(ws) for _, ws in lines], [(10, "Prior Period")]]
    prior_values = [[10, 20, 30, 60], [5, 10, 15, 30], [5, 10, 15, 30],
                    [-2, -4, -6, -12], [2, 4, 6, 12], [4, 8, 12, 24]]
    for label, values in zip(LABELS, prior_values):
        tokens.append([(10, label), *[(x, str(v)) for x, v in zip([350, 412, 464, 516], values)]])

    class Document:
        def __getitem__(self, _):
            return SimpleNamespace(get_text=lambda _: words)

        def close(self):
            pass

    monkeypatch.setattr(fx, "_SKIP_PAGES", 0)
    monkeypatch.setattr(fx, "_fitz_word_lines", lambda _: ([(0, tokens)], Document()))
    report = fx.extract_from_pdf(pdf_path="geometry-fixture.pdf")
    by_key = {(r.period_type, r.currency): r for r in report.rows}
    assert by_key["current", "TOTAL"].net_position == 1612610
    assert [[getattr(by_key["prior", c], f) for c in COLS] for f in fx._FIELDS] == prior_values
