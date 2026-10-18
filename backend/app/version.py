"""Single product version loaded from the repository/container VERSION file."""
from pathlib import Path
import re


def _load_version() -> str:
    candidates = (Path(__file__).resolve().parents[2] / "VERSION", Path("/app/VERSION"))
    for path in candidates:
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if re.fullmatch(r"\d+\.\d+\.\d+", value):
                return value
    raise RuntimeError("Missing or invalid product VERSION")


APP_VERSION = _load_version()
