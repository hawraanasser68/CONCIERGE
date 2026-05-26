# Owner D — pytest path bootstrap for integration tests.
#
# backend/pyproject.toml has no [build-system] section, so `app` is not installed
# as a package. We add backend/ to sys.path here so `from app.X import Y` resolves
# during integration test collection. conftest.py loads before its sibling test
# modules are imported, so the path is set before any `from app...` line runs.

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
