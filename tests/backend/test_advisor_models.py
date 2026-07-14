import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from advisor import fetch_advisor_models


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_fetch_advisor_models_reads_openai_compatible_data():
    payload = {"data": [{"id": "model-b"}, {"id": "model-a"}, {"id": "model-a"}]}
    with patch("advisor.urlopen", return_value=FakeResponse(payload)) as mocked:
        result = fetch_advisor_models({"baseUrl": "https://example.test/v1/", "apiKey": "secret"})

    assert result["models"] == ["model-a", "model-b"]
    assert result["endpoint"] == "https://example.test/v1/models"
    assert mocked.call_args.args[0].headers["Authorization"] == "Bearer secret"


def test_fetch_advisor_models_accepts_models_array():
    with patch("advisor.urlopen", return_value=FakeResponse({"models": ["local-a", {"name": "local-b"}]})):
        result = fetch_advisor_models({"base_url": "http://127.0.0.1:4000/v1", "api_key": "secret"})
    assert result["models"] == ["local-a", "local-b"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [({"baseUrl": "", "apiKey": "key"}, "Base URL"), ({"baseUrl": "https://example.test/v1", "apiKey": ""}, "API Key")],
)
def test_fetch_advisor_models_requires_connection_details(monkeypatch, payload, message):
    monkeypatch.setattr("advisor.load_advisor_config", lambda: {"base_url": "", "api_key": ""})
    with pytest.raises(RuntimeError, match=message):
        fetch_advisor_models(payload)
