"""Dev launcher with hot reload.

Run once, then edit files — browser auto-refreshes in under a second. No
process-kill, no manual restart, no curl smoke tests needed while iterating.

    python scripts/dev.py

Stops when you Ctrl+C. Production (Render) still uses `src/dashboard/app.py`
directly with gunicorn, no reloader — this entry point is local-only.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dashboard.app import app   # noqa: E402

if __name__ == "__main__":
    # debug=True enables auto-reload on save, shows in-browser error page,
    # and adds the Dash dev-tools panel. Safe only for local use.
    app.run_server(
        debug=True,
        host="127.0.0.1",
        port=8050,
        use_reloader=True,
        dev_tools_hot_reload=True,
        dev_tools_ui=True,
    )
