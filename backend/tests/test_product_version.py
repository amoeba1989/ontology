import re

from app.main import app
from app.version import APP_VERSION


def test_product_version_is_semver_and_exposed_by_fastapi():
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)
    assert app.version == APP_VERSION
