import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data_understanding"))

import llm  # noqa: E402


@pytest.fixture(autouse=True)
def no_env_file(monkeypatch):
    """A local .env must not change the tests or leak into the environment."""
    monkeypatch.setattr(llm, "load_env", lambda *args: None)
