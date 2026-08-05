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


def test_the_replace_loop_does_not_retry_a_failed_push_under_a_ledger(
        tmp_path, monkeypatch):
    """Drive the real retry loop: with a ledger active it must exit after ONE
    attempt instead of three."""
    AD = _mod("ad_loop", "scripts/audit_d1.py")
    monkeypatch.setenv("D1_RUN_LEDGER", str(tmp_path / "l.json"))
    monkeypatch.setattr(AD, "ensure_d1_schema", lambda *a, **k: None)
    monkeypatch.setattr(AD, "D1_RETRY_WAIT_S", 0)
    attempts = {"n": 0}

    class _R:
        returncode = AD.EXIT_PUSH_FAILED

    def _run(cmd, *a, **k):
        attempts["n"] += 1
        return _R()

    monkeypatch.setattr(AD.subprocess, "run", _run)
    with pytest.raises(SystemExit) as e:
        AD.replace_partitions([("TEB", "2026Q2", "consolidated")],
                              db_path=tmp_path / "x.db",
                              tables=["bank_audit_balance_sheet"])
    assert attempts["n"] == 1, f"retried {attempts['n']} times under a ledger"
    assert "ledger" in str(e.value).lower(), \
        f"the reason must be explained to whoever reads it: {e.value}"
