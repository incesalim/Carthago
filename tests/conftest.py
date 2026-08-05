"""Suite-wide guards: no live credentials, no network, no subprocesses.

Both escape hatches have already been used by accident here.

Tests once shelled out to ``npx wrangler --remote`` and passed only because this
machine holds Cloudflare credentials — reading live D1 while the run was
reported as an offline verification.

And ``push_to_d1.main()`` reads ``CF_ACCOUNT_TAG`` / ``CLOUDFLARE_API_TOKEN``
straight from the process environment, so on a developer machine four tests made
real HTTPS calls to the Cloudflare usage API. CI never saw it: that job has no
secrets, ``acct and tok`` is falsy there, and the branch is skipped. A guard that
only holds on the machine without credentials is not a guard.

So credentials are scrubbed before every test and both hatches are nailed shut.
A test that needs to exercise a network or subprocess path injects a fake; it
does not reach for the real thing.
"""
from __future__ import annotations

import os
import socket
import subprocess

import pytest

# Anything that could authenticate to a live service. Pattern-matched rather
# than enumerated so a new secret is covered the day it is introduced.
_SECRET_MARKERS = ("TOKEN", "SECRET", "API_KEY", "APIKEY", "ACCESS_KEY",
                   "ACCOUNT_ID", "ACCOUNT_TAG", "PASSWORD", "CREDENTIAL")


@pytest.fixture(autouse=True)
def _no_live_credentials(monkeypatch):
    """Strip every credential-shaped variable from the environment.

    Not a courtesy: it is the only thing standing between a unit test and a
    billed D1 write, because the scripts read os.environ directly at call time.
    """
    for name in list(os.environ):
        if any(m in name.upper() for m in _SECRET_MARKERS):
            monkeypatch.delenv(name, raising=False)


def _blocked(what: str):
    def _raise(*args, **kwargs):
        raise RuntimeError(
            f"{what} is blocked in the test suite. A test must not touch the "
            f"network or spawn a process — inject a fake instead. (Called with "
            f"{args[1:2] if len(args) > 1 else args!r}.)")
    return _raise


@pytest.fixture(autouse=True, scope="session")
def _no_network_no_subprocess():
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_popen = subprocess.Popen.__init__
    socket.socket.connect = _blocked("outbound network")
    socket.socket.connect_ex = _blocked("outbound network")
    subprocess.Popen.__init__ = _blocked("subprocess")
    try:
        yield
    finally:
        socket.socket.connect = real_connect
        socket.socket.connect_ex = real_connect_ex
        subprocess.Popen.__init__ = real_popen
