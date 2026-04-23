"""BDDK Banking Analytics — launcher.

For everyday use, prefer:
    python scripts/dev.py      # dashboard with hot reload
    python scripts/refresh.py  # refresh data from BDDK + EVDS

This file is kept as a simple "just run the dashboard" entry point.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.dashboard.app import app   # noqa: E402


if __name__ == "__main__":
    print("Dashboard at http://localhost:8050  (Ctrl+C to stop)")
    app.run_server(debug=False, host="0.0.0.0", port=8050)
