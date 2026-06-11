"""Make tests run against the current sources in src/, regardless of what is
installed in site-packages (the install is non-editable — see pyproject.toml)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
