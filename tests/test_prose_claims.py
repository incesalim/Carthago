"""The prose-claims guard must catch the shapes it was built for.

Thin pytest wrapper around scripts/check_prose_claims.py. Sibling of
tests/test_docs_sync.py and tests/test_pipeline_graph_sync.py.

The repo-wide assertion (zero unguarded claims) lands with C6, once the 41 sites
the 2026-07 audit found are computed. Until then the guard runs in `--warn` mode
in CI and these tests hold the *scanner* honest — a checker that quietly stops
matching is worse than no checker.
"""

from check_prose_claims import _files, scan, scan_text

# Every line here is a real defect the audit found, reduced to its shape.
CAUGHT = {
    "R1": [
        'net <b className="text-negative">+{fmtBn(rollNow.net)}</b>.',
        "<>+{mobYoY.toFixed(0)}% y/y</>",
    ],
    "R2": [
        'title="Gearing keeps climbing — the state banks lean hardest"',
        'title="The margin rebuilt as deposits repriced down"',
        'title={"Every deposit-taking group funds its book below the line"}',
    ],
    "R3": [
        'description: "32 banks\' audited BRSA financials, BDDK aggregates",',
    ],
}

# Legitimate lines that must NOT trip the guard — the ~300 timeless strings the
# site is mostly made of, plus the computed idioms that are the fix.
IGNORED = [
    'description="tl loans ÷ tl deposits, %, weekly · public vs private"',
    'title="Capital adequacy — by group"',
    'title="Largest funds"',  # a topic label, not a claim
    'title={seriesFinding(s, { noun: "Loan growth" }) ?? "Loan growth YoY (%)"}',
    "title={claim(everyOf(g, (x) => x < 100), 'Every group is below the line') ?? 'Loan / deposit'}",
    "<b>{signed(rollNow.net, fmtBn)}</b>",
    "const total = base + {};",  # not a JSX sign
    " * The audited universe is ~32 banks ≈ 98% of the sector.",  # a comment
]


def test_catches_every_defect_shape():
    for rule, lines in CAUGHT.items():
        for line in lines:
            hits, _ = scan_text("web/app/x/page.tsx", line)
            assert rule in {h.rule for h in hits}, f"{rule} missed: {line}"


def test_leaves_legitimate_lines_alone():
    for line in IGNORED:
        hits, _ = scan_text("web/app/x/page.tsx", line)
        assert not hits, f"false positive on: {line} → {[h.rule for h in hits]}"


def test_suppression_covers_its_line_and_the_next():
    text = "\n".join(
        [
            "// prose-ok: the corridor's lending leg is above policy by construction",
            "+{Math.round(spread * 100)}bp",
        ]
    )
    hits, sups = scan_text("web/app/x/page.tsx", text)
    assert not hits
    assert len(sups) == 1
    assert "by construction" in sups[0].reason


def test_the_universe_count_is_allowed_where_it_is_derived():
    line = "{rows.length} banks · audited BRSA quarterly filings"
    assert not scan_text("web/app/banks/page.tsx", line)[0]
    # …but not anywhere else.
    assert scan_text("web/app/page.tsx", "32 banks' audited financials")[0]


def test_there_is_something_to_scan():
    # Guard against the check passing because a glob found no files.
    assert len(_files()) > 50, "no page files discovered — check APP_DIR"
    scan()  # must not raise
