"""The regulation briefing's hand-verified fact checklist, importable.

Extracted from scripts/check_briefing_facts.py (which keeps its CLI and imports
this) so the GENERATOR can gate on the same instrument the checker scores with.
Until 2026-08-16 the checklist ran only after the store, alert-only — so the
2026-08-16 briefing shipped at 69% while the alert said so on Telegram. The
history of that afternoon's diagnosis is in docs/regulation_followups.md (E).

Two verdict-shaping details learned from real briefings:

- A fact is matched on its NUMBER plus context keywords, never phrasing — the
  LLM words bullets freely and this must not become a style test.
- CONTRADICTED is judged PER BULLET: "reduced from 2% to 1%" is correct
  reporting and necessarily carries both numbers; a SEPARATE bullet asserting a
  bare superseded value is the defect. (That separate bullet is exactly what
  `stale_bare_indexes` finds, so the generator can strip it deterministically.)
"""

from __future__ import annotations

import re

# Each fact: (id, section it belongs to, the number that must appear, keywords
# that must co-occur, the source that published it, and — where the rule was
# revised — the superseded value, so a STALE answer is distinguishable from a
# missing one. `hint` is the rule's identity in words, used when asking the
# model to repair an omission: it names the rule and WHERE it is published but
# NEVER the value, so the checklist keeps measuring extraction, not echo.
#
# ⚠️ Keyword regexes are matched against model prose — write them for the ways
# the rule is actually worded. `\bSME\b` missed "SMEs" (plural) and scored a
# correct 4.5% bullet MISSING; a bare `FX` keyword matched an RR bullet's
# "up to 1 month" and scored a correct briefing CONTRADICTED. Tie the keyword
# to the rule's full identity, and test against real bullets.
FACTS: list[dict] = [
    # --- 2026-05-23 loan growth limits (the table that was missing entirely) ---
    dict(id="loan_general", section="Loan Growth Caps", value="3",
         keywords=[r"general[- ]purpose|general purpose"], stale="4",
         source="tcmb:ANO2026-21 (2026-05-23)",
         hint="the 8-week growth cap for general-purpose consumer loans "
              "(tcmb:ANO2026-21, 2026-05-23, limits table)"),
    dict(id="loan_vehicle", section="Loan Growth Caps", value="3",
         keywords=[r"vehicle|auto"], stale="4",
         source="tcmb:ANO2026-21 (2026-05-23)",
         hint="the 8-week growth cap for vehicle loans "
              "(tcmb:ANO2026-21, 2026-05-23, limits table)"),
    dict(id="loan_overdraft", section="Loan Growth Caps", value="1",
         keywords=[r"overdraft"], stale="2",
         source="tcmb:ANO2026-21 (2026-05-23)",
         hint="the 8-week growth cap for consumer overdraft account limits "
              "(tcmb:ANO2026-21, 2026-05-23 — the latest revision)"),
    dict(id="loan_sme", section="Loan Growth Caps", value="4.5",
         keywords=[r"\bSMEs?\b"], stale="5",
         source="tcmb:ANO2026-21 (2026-05-23)",
         hint="the 8-week growth cap for TL loans to SMEs "
              "(tcmb:ANO2026-21, 2026-05-23, limits table)"),
    dict(id="loan_nonsme", section="Loan Growth Caps", value="2",
         keywords=[r"non-?SME"], stale="3",
         source="tcmb:ANO2026-21 (2026-05-23)",
         hint="the 8-week growth cap for TL loans to non-SME enterprises "
              "(tcmb:ANO2026-21, 2026-05-23, limits table)"),
    # --- 2026-01-31 FX loan cap. The keyword must bind FX to LOANS: a bare
    # `FX` matched "foreign currency deposits … up to 1 month" in an RR bullet
    # and read its "1" as a superseded FX-loan cap (false CONTRADICTED,
    # 2026-08-16). Same shape as briefing_validate's loan:fx subject. ---
    dict(id="loan_fx", section="Loan Growth Caps", value="0.5",
         keywords=[r"(?:foreign[- ]currency|\bFX\b|\bFC\b)[^.;]{0,40}?loans?"],
         stale="1",
         source="tcmb:ANO2026-06 (2026-01-31)",
         hint="the 8-week growth cap for foreign-currency loans "
              "(tcmb:ANO2026-06, 2026-01-31)"),
    # --- 2026-07-01 FX reserve requirements (post-fix release, table present) ---
    # ⚠️ These MUST exclude precious metal. The 2026-07-01 release revised only
    # "foreign currency deposits/participation funds"; precious metal accounts
    # stay at 30%/26% from 2025-12-02 and are CORRECT at those values. Without
    # not_keywords, a correct precious-metal bullet ("30% for demand … 26% for
    # longer") matched on the bare maturity words and was scored a stale FX
    # ratio — the same liability-blindness that made three versions of the gate
    # unusable, reproduced here in the hand-written list.
    # `all_keywords` = every pattern must match the SAME line, because an RR rule
    # is identified by liability AND maturity together. Matching maturity alone
    # read a correct "precious metal … 30% demand, 26% longer" bullet as a stale
    # FX ratio. Excluding any line mentioning precious metal then failed the
    # other way: the real bullets combine the two liabilities ("for foreign
    # currency deposits/participation funds and precious metal deposit accounts
    # … 32% … 28%"), so the exclusion discarded the FX evidence and the facts
    # read MISSING. Requiring both dimensions handles the combined bullet and
    # the precious-metal-only bullet correctly.
    dict(id="rr_fx_short", section="Regulations on RRs", value="32",
         all_keywords=[r"(?:foreign[- ]currency|FX)[^.;]{0,60}"
                       r"(?:deposits|participation funds)",
                       r"demand|up to 1 month|up to one month"],
         stale="30", source="tcmb (2026-07-01)",
         hint="the reserve requirement ratio for FX deposits/participation "
              "funds at demand and up-to-1-month maturities (TCMB press "
              "release of 2026-07-01)"),
    dict(id="rr_fx_long", section="Regulations on RRs", value="28",
         all_keywords=[r"(?:foreign[- ]currency|FX)[^.;]{0,60}"
                       r"(?:deposits|participation funds)",
                       r"longer maturit"],
         stale="26", source="tcmb (2026-07-01)",
         hint="the reserve requirement ratio for FX deposits/participation "
              "funds at longer maturities (TCMB press release of 2026-07-01)"),
    dict(id="rr_addl_tl", section="Regulations on RRs", value="2.5",
         keywords=[r"additional|terminated|abolish"], stale=None,
         source="tcmb (2026-07-01) — the 2.5% additional TL RR was TERMINATED",
         hint="the fate of the additional Turkish lira reserve requirement on "
              "FX deposits/participation funds (TCMB press release of "
              "2026-07-01)"),
    # --- policy rates (prose releases; unaffected by the table bug — the control) ---
    dict(id="policy_rate", section="Monetary Policy Stance", value="37",
         keywords=[r"policy rate|one-week repo|week repo"], stale="38",
         source="tcmb:ANO2026-24 (2026-06-11)",
         hint="the current policy rate (one-week repo auction rate) "
              "(latest Press Release on Interest Rates)"),
    dict(id="on_lending", section="Monetary Policy Stance", value="40",
         keywords=[r"lending"], stale="41",
         source="tcmb:ANO2026-24 (2026-06-11)",
         hint="the overnight lending rate of the corridor "
              "(latest Press Release on Interest Rates)"),
    dict(id="on_borrowing", section="Monetary Policy Stance", value="35.5",
         keywords=[r"borrowing"], stale="36.5",
         source="tcmb:ANO2026-24 (2026-06-11)",
         hint="the overnight borrowing rate of the corridor "
              "(latest Press Release on Interest Rates)"),
    # --- 2026-03-01 repo auction suspension (a fact with no number). The
    # keyword accepts the ways a suspension is actually worded — "suspend"
    # alone would score a correct "auctions remain halted" bullet MISSING. ---
    dict(id="repo_suspended", section="Monetary Policy Stance", value=None,
         keywords=[r"suspend|halted|paused|not (?:be )?(?:conduct|held)|"
                   r"no longer (?:be )?(?:conduct|held)|ceased"],
         stale=None,
         source="tcmb:ANO2026-11 (2026-03-01) — one-week repo auctions suspended",
         hint="the CURRENT status of one-week repo auctions (tcmb:ANO2026-11, "
              "2026-03-01, and any later release that changes it)"),
]


# The sections a healthy briefing produces. UNSOURCED_CATEGORIES (CARs, Credit
# Cards) are deliberately skipped upstream and are not expected here.
EXPECTED_SECTIONS = [
    "Monetary Policy Stance",
    "Regulations for TL Deposit Share",
    "Loan Growth Caps",
    "Regulations on RRs",
    "Other Regulatory Actions",
]


# Tokenise numbers and compare NUMERICALLY. The first version matched the value
# as text with a lookahead, so "37.0%" did not satisfy "37" — the model writing a
# trailing zero scored the fact MISSING while the briefing was correct. Textual
# matching also cannot see that 4.50 and 4.5 are one value.
_NUM_TOKEN_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)")


def _num_present(text: str, value: str) -> bool:
    """True if `value` appears as a standalone number, compared by magnitude.
    Still anchored on token boundaries so 3 does not match inside 37 or 0.35."""
    want = float(value)
    return any(abs(float(tok) - want) < 1e-9 for tok in _NUM_TOKEN_RE.findall(text))


def _relevance(fact: dict):
    """A line-relevance predicate for one fact (keywords OR / all_keywords AND)."""
    alls = [re.compile(p, re.I) for p in fact.get("all_keywords", [])]
    kw_re = re.compile("|".join(fact["keywords"]), re.I) if fact.get("keywords") else None

    def _relevant(line: str) -> bool:
        if alls:
            return all(rx.search(line) for rx in alls)
        return bool(kw_re and kw_re.search(line))

    return _relevant


def _is_stale_bare(fact: dict, bullet_text: str) -> bool:
    """A bullet asserting the superseded value WITHOUT the current one — the
    defect shape. A transition bullet ("reduced from 2% to 1%") carries both
    numbers and is fine."""
    if not fact.get("stale"):
        return False
    relevant = _relevance(fact)
    for line in bullet_text.splitlines() or [bullet_text]:
        if not relevant(line):
            continue
        if _num_present(line, fact["stale"]) and not _num_present(line, fact["value"] or "\0"):
            return True
    return False


def score(payload: dict) -> dict:
    """Score a full briefing payload ({"categories": [{name, bullets}]}).
    Returns results per fact, counts, score, missing sections. Verbatim the
    checker's semantics — the CLI in scripts/check_briefing_facts.py and the
    generator's gate both call THIS, so they can never disagree."""
    cats = {c.get("name", ""): c for c in payload.get("categories", [])}
    all_bullets = [b.get("text", "")
                   for c in payload.get("categories", []) for b in c.get("bullets", [])]
    all_text = "\n".join(all_bullets)
    results = []
    for f in FACTS:
        # Prefer the fact's own section, but fall back to the whole briefing:
        # a correct figure filed under a neighbouring heading is a categorisation
        # problem, not a missing fact, and the two deserve different verdicts.
        sect = cats.get(f["section"])
        sect_text = "\n".join(b.get("text", "") for b in sect.get("bullets", [])) if sect else ""
        relevant = _relevance(f)

        def hit(text: str, val: str | None, _rel=relevant) -> bool:
            if not text:
                return False
            lines = [ln for ln in text.splitlines() if _rel(ln)]
            if not lines:
                return False
            return True if val is None else any(_num_present(ln, val) for ln in lines)

        current = hit(sect_text, f["value"]) or hit(all_text, f["value"])
        superseded = any(_is_stale_bare(f, b) for b in all_bullets)

        if current and superseded:
            verdict = "CONTRADICTED"
        elif hit(sect_text, f["value"]):
            verdict = "PASS"
        elif current:
            verdict = "MISFILED"
        elif superseded:
            verdict = "STALE"
        else:
            verdict = "MISSING"
        results.append({**{k: f[k] for k in ("id", "section", "value", "stale", "source")},
                        "verdict": verdict})
    # Section coverage is scored separately from facts, because the two failures
    # are independent and the checklist is blind to one of them: a change can
    # raise the fact score while deleting an entire section whose rules the
    # checklist happens not to assert.
    missing_sections = [s for s in EXPECTED_SECTIONS if not cats.get(s, {}).get("bullets")]

    order = ("PASS", "MISFILED", "CONTRADICTED", "STALE", "MISSING")
    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in order}
    # Only PASS/MISFILED are correct: the figure reached the page and nothing
    # contradicts it. CONTRADICTED is scored as wrong — a reader cannot tell
    # which of two printed caps applies, which is worse than a missing bullet.
    good = counts["PASS"] + counts["MISFILED"]
    return {"results": results, "counts": counts,
            "score": good / len(FACTS) if FACTS else 0.0,
            "missing_sections": missing_sections,
            "sections": {n: len(c.get("bullets", [])) for n, c in cats.items()}}


# --- the generator's gate ----------------------------------------------------

def stale_bare_indexes(bullets: list[dict]) -> list[int]:
    """Indexes of bullets that assert a superseded value for a curated fact
    without its current value. Deterministically strippable: the checker would
    score each one CONTRADICTED (or STALE) — a reader cannot tell which cap
    applies, so a wrong bullet must not ship, whichever section it sits in."""
    out: list[int] = []
    for i, b in enumerate(bullets):
        text = b.get("text", "")
        if any(_is_stale_bare(f, text) for f in FACTS):
            out.append(i)
    return out


def section_missing_facts(section_name: str, bullets: list[dict]) -> list[dict]:
    """Curated facts belonging to `section_name` whose current value does not
    appear in these bullets — the omissions a pointed retry should repair."""
    text = "\n".join(b.get("text", "") for b in bullets)
    out: list[dict] = []
    for f in FACTS:
        if f["section"] != section_name:
            continue
        relevant = _relevance(f)
        lines = [ln for ln in text.splitlines() if relevant(ln)]
        present = bool(lines) and (f["value"] is None
                                   or any(_num_present(ln, f["value"]) for ln in lines))
        if not present:
            out.append(f)
    return out


def retry_addendum(missing: list[dict], attempt: int = 1) -> str:
    """The repair message for a pointed regeneration: name each omitted rule
    and the release that states it — NEVER the value. The checklist stays an
    independent measurement only if the model still has to read the source.

    `attempt` exists because the calls are deterministic (temperature 0, fixed
    seed): a second try with the identical addendum returns the identical
    draft, so the second attempt escalates the wording instead — a changed
    input is the only thing that can change the output."""
    lines = [
        "REVISION — your draft of this section omitted rules that are in force.",
        "Add a bullet for each of the following, reading the CURRENT value from",
        "the named source (and any later release that revises it). Keep every",
        "other rule of your draft unchanged; do not drop existing bullets.",
        "",
    ]
    for f in missing:
        lines.append(f"  - {f['hint']}")
    if attempt > 1:
        lines += [
            "",
            "THIS REVISION IS REQUIRED. Your previous revision still omitted the",
            "item(s) above. Return the COMPLETE section again, and it MUST contain",
            "one bullet for each listed item, cited to the named source. An item",
            "genuinely absent from the provided sources is the only acceptable",
            "reason to leave one out.",
        ]
    return "\n".join(lines)
