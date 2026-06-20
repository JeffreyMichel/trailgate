"""Tests for error handling: all-failed detection, reservable=null, env checks, main() wiring."""
from unittest.mock import MagicMock, patch

import pytest
import requests

import check_permits
from check_permits import check_env, find_available, main


CONFIG = {
    "dates": ["2026-07-04"],
    "trailheads": [{"name": "Green Lakes", "tour_id": "2003", "url": "https://example.com"}],
}


def _make_response(daily: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "payload": {"facility_availability_summary_view_by_local_date": daily}
    }
    resp.raise_for_status.return_value = None
    return resp


# --- all_failed flag --------------------------------------------------------

def test_all_failed_true_when_every_request_errors():
    with patch(
        "check_permits.requests.get", side_effect=requests.ConnectionError("down")
    ), patch("check_permits.time.sleep"):
        found, all_failed = find_available(CONFIG)

    assert found == {}
    assert all_failed is True


def test_all_failed_false_on_success():
    payload = {
        "2026-07-04": {
            "tour_availability_summary_view_by_tour_id": {"2003": {"reservable": 1}}
        }
    }
    with patch("check_permits.requests.get", return_value=_make_response(payload)):
        found, all_failed = find_available(CONFIG)

    assert all_failed is False
    assert "2026-07-04" in found["Green Lakes"]


# --- reservable is null -----------------------------------------------------

def test_null_reservable_is_treated_as_zero():
    payload = {
        "2026-07-04": {
            "tour_availability_summary_view_by_tour_id": {"2003": {"reservable": None}}
        }
    }
    with patch("check_permits.requests.get", return_value=_make_response(payload)):
        found, all_failed = find_available(CONFIG)

    assert found.get("Green Lakes", []) == []
    assert all_failed is False


# --- env validation ---------------------------------------------------------

def test_check_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    with pytest.raises(SystemExit):
        check_env()


def test_check_env_passes_when_present(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "a@b.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    check_env()  # should not raise


# --- main() wiring ----------------------------------------------------------

def test_main_exits_nonzero_when_all_failed(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "a@b.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    with patch("check_permits.load_config", return_value=CONFIG), patch(
        "check_permits.find_available", return_value=({}, True)
    ), patch("check_permits.send_email") as mock_send:
        with pytest.raises(SystemExit):
            main()
    mock_send.assert_not_called()


def test_main_sends_email_when_available(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "a@b.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    available = {"Green Lakes": ["2026-07-04"]}
    with patch("check_permits.load_config", return_value=CONFIG), patch(
        "check_permits.find_available", return_value=(available, False)
    ), patch("check_permits.send_email") as mock_send:
        main()
    mock_send.assert_called_once()


def test_main_no_email_when_nothing_available(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "a@b.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    with patch("check_permits.load_config", return_value=CONFIG), patch(
        "check_permits.find_available", return_value=({}, False)
    ), patch("check_permits.send_email") as mock_send:
        main()
    mock_send.assert_not_called()
