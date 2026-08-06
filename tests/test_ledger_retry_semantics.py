"""The run ledger and the automatic retry contradicted each other.

`push_to_d1` books its estimate BEFORE calling wrangler, because an import that
dies half way still bills. `audit_d1.replace_partitions` retries any non-terminal
exit, and EXIT_PUSH_FAILED (4) is non-terminal precisely because a transient
wrangler failure leaves D1 untouched.

Put together on one run:

    attempt 1  books 203,799  ->  wrangler blips  ->  exit 4  (retryable)
    attempt 2  cap is now 250,000 - 203,799 = 46,201
               estimate 203,799 > 46,201        ->  exit 3  (TERMINAL)

A service-side blip becomes a permanent budget refusal, and the message a human
reads says "a validation or budget refusal is deterministic … Nothing was
written" — neither half of which is true here.

Whether a failed import bills is not something this repo can observe, so the
retry cannot be made correct: if it billed, retrying spends twice; if it did
not, the ledger has over-booked and the retry is refused for no reason. Under an
active ledger the conservative move is to stop and let a human look.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _db(tmp_path, rows=500):
    p = tmp_path / "s.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE loans (id INTEGER PRIMARY KEY, v REAL, "
              "downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE INDEX ix_loans_v ON loans(v)")
    c.executemany("INSERT INTO loans (id, v) VALUES (?, ?)",
                  [(i, float(i)) for i in range(rows)])
    c.commit()
    return p, c


# --- the reproduction --------------------------------------------------------

def test_a_failed_push_then_a_retry_turns_transient_into_terminal(tmp_path, monkeypatch):
    """The exact sequence, driven through the real main(): exit 4, then exit 3."""
    P = _mod("p2d_seq", "scripts/push_to_d1.py")
    db, _ = _db(tmp_path)
    ledger = tmp_path / "ledger.json"
    monkeypatch.setenv(P.RUN_LEDGER_ENV, str(ledger))
    monkeypatch.setattr(P, "cycle_rows_written", lambda *a, **k: None)
    # wrangler blips — D1 untouched, but the rows may already have been billed.
    monkeypatch.setattr(P, "run_wrangler", lambda *a, **k: 1)
    # 1,500 leaves room for one push of ~1,000 and not for a second.
    monkeypatch.setattr(sys, "argv",
                        ["push_to_d1.py", "--db", str(db), "--hours", "48",
                         "--max-billed-rows", "1500"])

    first = P.main()
    assert first == P.EXIT_PUSH_FAILED, "a wrangler blip is exit 4, retryable"
    booked = P.run_ledger_spent()
    assert booked > 0, "the estimate must be booked before the write"

    second = P.main()
    assert second == P.EXIT_BUDGET, (
        "the retry is refused by the ledger the first attempt filled — this is "
        "the contradiction, reproduced")
    assert P.EXIT_BUDGET in _mod("ad_seq", "scripts/audit_d1.py").TERMINAL_EXITS, \
        "and exit 3 is terminal, so the repair dies permanently"


# --- the resolution ----------------------------------------------------------

def test_push_failed_is_terminal_while_a_ledger_is_active(monkeypatch, tmp_path):
    """Under an active ledger the retry cannot be right either way, so it stops."""
    AD = _mod("ad_active", "scripts/audit_d1.py")
    monkeypatch.setenv("D1_RUN_LEDGER", str(tmp_path / "l.json"))
    terminal = AD.terminal_exits()
    assert AD.EXIT_PUSH_FAILED in terminal
    assert AD.EXIT_BUDGET in terminal and AD.EXIT_VALIDATION in terminal


def test_push_failed_stays_retryable_without_a_ledger(monkeypatch):
    """No ledger, no double-booking risk: a transient failure retries as before,
    which is what every non-audit caller still relies on."""
    AD = _mod("ad_inactive", "scripts/audit_d1.py")
    monkeypatch.delenv("D1_RUN_LEDGER", raising=False)
    terminal = AD.terminal_exits()
    assert AD.EXIT_PUSH_FAILED not in terminal
    assert AD.EXIT_BUDGET in terminal and AD.EXIT_VALIDATION in terminal


def test_the_static_terminal_set_is_still_the_no_ledger_answer(monkeypatch):
    """TERMINAL_EXITS is imported by name elsewhere; it must keep meaning what
    it always meant."""
    AD = _mod("ad_static", "scripts/audit_d1.py")
    monkeypatch.delenv("D1_RUN_LEDGER", raising=False)
    assert set(AD.terminal_exits()) == set(AD.TERMINAL_EXITS)


def _drive(AD, monkeypatch, tmp_path, which, rc):
    """Run one of the two retry loops with a stubbed subprocess; count attempts."""
    monkeypatch.setattr(AD, "ensure_d1_schema", lambda *a, **k: None)
    monkeypatch.setattr(AD, "D1_RETRY_WAIT_S", 0)
    monkeypatch.setattr(AD.time, "sleep", lambda *_: None)
    attempts = {"n": 0}

    class _R:
        returncode = rc

    def _run(cmd, *a, **k):
        attempts["n"] += 1
        return _R()

    monkeypatch.setattr(AD.subprocess, "run", _run)
    with pytest.raises(SystemExit) as e:
        if which == "replace":
            AD.replace_partitions([("TEB", "2026Q2", "consolidated")],
                                  db_path=tmp_path / "x.db",
                                  tables=["bank_audit_balance_sheet"])
        else:
            AD.push_to_d1(tmp_path / "x.db", 24, tables=["bank_audit_balance_sheet"])
    return attempts["n"], str(e.value)


# BOTH loops. The ledger rule first landed in replace_partitions only, and
# push_to_d1 kept retrying exit 4 into a guaranteed budget refusal.
@pytest.mark.parametrize("which", ["replace", "push"])
def test_neither_loop_retries_a_failed_push_under_a_ledger(
        which, tmp_path, monkeypatch):
    AD = _mod(f"ad_{which}_on", "scripts/audit_d1.py")
    monkeypatch.setenv("D1_RUN_LEDGER", str(tmp_path / "l.json"))
    n, msg = _drive(AD, monkeypatch, tmp_path, which, AD.EXIT_PUSH_FAILED)
    assert n == 1, f"{which}: retried {n} times under a ledger"
    assert "ledger" in msg.lower(), \
        f"{which}: the reason must be explained to whoever reads it: {msg}"


@pytest.mark.parametrize("which", ["replace", "push"])
def test_both_loops_still_retry_without_a_ledger(which, tmp_path, monkeypatch):
    """No ledger, no double-booking risk — a transient failure gets its retries
    back, which is what every non-audit caller relies on."""
    AD = _mod(f"ad_{which}_off", "scripts/audit_d1.py")
    monkeypatch.delenv("D1_RUN_LEDGER", raising=False)
    n, msg = _drive(AD, monkeypatch, tmp_path, which, AD.EXIT_PUSH_FAILED)
    assert n == AD.D1_RETRIES, f"{which}: made {n} attempts, expected {AD.D1_RETRIES}"
    assert "ledger" not in msg.lower()


@pytest.mark.parametrize("which", ["replace", "push"])
def test_both_loops_treat_a_budget_refusal_as_terminal_either_way(
        which, tmp_path, monkeypatch):
    AD = _mod(f"ad_{which}_bud", "scripts/audit_d1.py")
    monkeypatch.delenv("D1_RUN_LEDGER", raising=False)
    n, msg = _drive(AD, monkeypatch, tmp_path, which, AD.EXIT_BUDGET)
    assert n == 1 and "deterministic" in msg


# --- what the operator is told after a failed remote call --------------------
#
# Atomicity is not knowledge. The import is all-or-nothing, so D1 either took the
# whole file or none of it — but if wrangler loses the response after submitting
# ("import polling failed" is one of the transients this lane retries), exit 4
# cannot say which happened. Telling an operator "D1 is unchanged" there invites
# them to clear the ledger and re-run on a state nobody has looked at.

_BANNED = ("d1 is unchanged", "content is unchanged", "leaves d1 unchanged",
           "d1 is untouched", "leaves d1 untouched")


@pytest.mark.parametrize("which", ["replace", "push"])
def test_a_failed_remote_call_reports_the_outcome_as_unknown(
        which, tmp_path, monkeypatch):
    """Both the retries-exhausted path and the ledger path."""
    AD = _mod(f"ad_{which}_msg", "scripts/audit_d1.py")
    monkeypatch.delenv("D1_RUN_LEDGER", raising=False)
    _, msg = _drive(AD, monkeypatch, tmp_path, which, AD.EXIT_PUSH_FAILED)
    low = msg.lower()
    assert "outcome is unknown" in low, f"{which}: {msg}"
    assert "verify d1" in low, f"{which}: must tell them to check: {msg}"
    for claim in _BANNED:
        assert claim not in low, f"{which}: still claims {claim!r}: {msg}"


@pytest.mark.parametrize("which", ["replace", "push"])
def test_the_ledger_message_also_reports_the_outcome_as_unknown(
        which, tmp_path, monkeypatch):
    AD = _mod(f"ad_{which}_msg2", "scripts/audit_d1.py")
    monkeypatch.setenv("D1_RUN_LEDGER", str(tmp_path / "l.json"))
    _, msg = _drive(AD, monkeypatch, tmp_path, which, AD.EXIT_PUSH_FAILED)
    low = msg.lower()
    assert "outcome is unknown" in low, f"{which}: {msg}"
    assert "verify d1 before clearing the ledger" in low, (
        f"{which}: clearing the ledger on an unverified state is the specific "
        f"hazard: {msg}")
    for claim in _BANNED:
        assert claim not in low, f"{which}: still claims {claim!r}: {msg}"


@pytest.mark.parametrize("which", ["replace", "push"])
def test_only_a_pre_write_refusal_may_claim_nothing_was_written(
        which, tmp_path, monkeypatch):
    """A validation/budget refusal is decided before wrangler is invoked, so
    there it IS known — and the message says why, so the wording cannot be
    copied to a path that has already called out."""
    AD = _mod(f"ad_{which}_ref", "scripts/audit_d1.py")
    monkeypatch.delenv("D1_RUN_LEDGER", raising=False)
    _, msg = _drive(AD, monkeypatch, tmp_path, which, AD.EXIT_BUDGET)
    low = msg.lower()
    assert "nothing was written" in low
    assert "before any remote call" in low, (
        f"the claim must carry its justification: {msg}")


def test_no_message_in_the_module_claims_d1_is_unchanged():
    """Guards every future message, not just the ones a test drives."""
    src = (REPO / "scripts" / "audit_d1.py").read_text(encoding="utf-8").lower()
    for claim in _BANNED:
        assert claim not in src, f"audit_d1.py still asserts {claim!r}"


def test_the_two_loops_share_one_decision_point():
    """They were separate copies of the same seven lines, which is exactly how
    the rule ended up in one of them. Guard the de-duplication."""
    src = (REPO / "scripts" / "audit_d1.py").read_text(encoding="utf-8")
    assert src.count("def stop_if_terminal") == 1
    assert src.count("stop_if_terminal(rc,") == 2, \
        "both retry loops must go through the shared helper"
