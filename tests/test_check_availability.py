"""Tests for check_availability() and the retry behavior."""
from unittest.mock import MagicMock, patch

import pytest
import requests

import check_permits
from check_permits import check_availability


def _ok_response(payload=None):
    resp = MagicMock()
    resp.json.return_value = payload or {"payload": {}}
    resp.raise_for_status.return_value = None
    return resp


def test_builds_correct_url_and_params():
    resp = _ok_response()
    with patch("check_permits.requests.get", return_value=resp) as mock_get:
        check_availability("2026", "07")

    args, kwargs = mock_get.call_args
    assert args[0] == check_permits.BASE_URL
    assert kwargs["params"] == {"year": "2026", "month": "07", "inventoryBucket": "FIT"}
    assert kwargs["timeout"] == 15
    assert "User-Agent" in kwargs["headers"]


def test_retries_then_succeeds():
    failing = requests.ConnectionError("boom")
    good = _ok_response({"ok": True})
    with patch("check_permits.requests.get", side_effect=[failing, good]) as mock_get, patch(
        "check_permits.time.sleep"
    ):
        result = check_availability("2026", "07")

    assert mock_get.call_count == 2
    assert result == {"ok": True}


def test_raises_after_exhausting_retries():
    with patch(
        "check_permits.requests.get", side_effect=requests.ConnectionError("boom")
    ) as mock_get, patch("check_permits.time.sleep"):
        with pytest.raises(requests.RequestException):
            check_availability("2026", "07")

    assert mock_get.call_count == check_permits.MAX_RETRIES
