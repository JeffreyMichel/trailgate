"""Tests for the overnight-permit path: check_overnight_availability() and _find_in_permit()."""

from unittest.mock import MagicMock, patch

import pytest
import requests

import check_permits
from check_permits import (
    build_trailhead_map,
    check_overnight_availability,
    find_available,
    main,
)

PERMIT_CONFIG = {
    "overnight_permits": [
        {
            "name": "Central Cascades Overnight",
            "permit_id": "4675311",
            "dates": ["2026-09-02"],
            "trailheads": [
                {"name": "South Sister (overnight)", "division_id": "467531103"},
                {"name": "Green Lake (overnight)", "division_id": "467531108"},
            ],
        }
    ],
}


def _permit_response(availability: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"payload": {"permit_id": "4675311", "availability": availability}}
    resp.raise_for_status.return_value = None
    return resp


def _division(date_to_remaining: dict[str, int]) -> dict:
    return {
        "date_availability": {
            f"{d}T00:00:00Z": {"total": 5, "remaining": r} for d, r in date_to_remaining.items()
        }
    }


# --- check_overnight_availability -----------------------------------------


def test_builds_correct_url_and_params():
    resp = _permit_response({})
    with patch("check_permits.requests.get", return_value=resp) as mock_get:
        check_overnight_availability("4675311", "2026", "09")

    args, kwargs = mock_get.call_args
    assert args[0] == check_permits.overnight_availability_url("4675311")
    assert "4675311" in args[0]
    assert kwargs["params"] == {"start_date": "2026-09-01T00:00:00.000Z"}
    assert kwargs["timeout"] == 15
    assert "User-Agent" in kwargs["headers"]


def test_retries_then_succeeds():
    good = _permit_response({})
    with (
        patch(
            "check_permits.requests.get",
            side_effect=[requests.ConnectionError("boom"), good],
        ) as mock_get,
        patch("check_permits.time.sleep"),
    ):
        check_overnight_availability("4675311", "2026", "09")
    assert mock_get.call_count == 2


def test_raises_after_exhausting_retries():
    with (
        patch(
            "check_permits.requests.get", side_effect=requests.ConnectionError("boom")
        ) as mock_get,
        patch("check_permits.time.sleep"),
    ):
        with pytest.raises(requests.RequestException):
            check_overnight_availability("4675311", "2026", "09")
    assert mock_get.call_count == check_permits.MAX_RETRIES


# --- _find_in_permit via find_available -----------------------------------


def test_reports_division_with_remaining():
    availability = {
        "467531103": _division({"2026-09-02": 2}),
        "467531108": _division({"2026-09-02": 0}),
    }
    with patch("check_permits.requests.get", return_value=_permit_response(availability)):
        found, all_failed = find_available(PERMIT_CONFIG)

    assert all_failed is False
    assert found["South Sister (overnight)"] == ["2026-09-02"]
    assert "Green Lake (overnight)" not in found


def test_missing_division_or_date_is_not_available():
    with patch("check_permits.requests.get", return_value=_permit_response({})):
        found, all_failed = find_available(PERMIT_CONFIG)
    assert found == {}
    assert all_failed is False


def test_null_remaining_treated_as_zero():
    availability = {
        "467531103": {"date_availability": {"2026-09-02T00:00:00Z": {"remaining": None}}}
    }
    with patch("check_permits.requests.get", return_value=_permit_response(availability)):
        found, _ = find_available(PERMIT_CONFIG)
    assert found.get("South Sister (overnight)", []) == []


def test_all_failed_true_when_request_errors():
    with (
        patch("check_permits.requests.get", side_effect=requests.ConnectionError("down")),
        patch("check_permits.time.sleep"),
    ):
        found, all_failed = find_available(PERMIT_CONFIG)
    assert found == {}
    assert all_failed is True


def test_trailhead_date_override_scopes_to_its_own_dates():
    config = {
        "overnight_permits": [
            {
                "name": "Central Cascades Overnight",
                "permit_id": "4675311",
                "dates": ["2026-09-02", "2026-09-03"],
                "trailheads": [
                    {
                        "name": "South Sister (overnight)",
                        "division_id": "467531103",
                        "dates": ["2026-09-03"],  # only the 3rd
                    }
                ],
            }
        ],
    }
    availability = {"467531103": _division({"2026-09-02": 4, "2026-09-03": 4})}
    with patch("check_permits.requests.get", return_value=_permit_response(availability)):
        found, _ = find_available(config)
    assert found["South Sister (overnight)"] == ["2026-09-03"]


def test_dates_across_two_months_make_separate_calls():
    config = {
        "overnight_permits": [
            {
                "name": "Central Cascades Overnight",
                "permit_id": "4675311",
                "dates": ["2026-09-30", "2026-10-01"],
                "trailheads": [{"name": "South Sister (overnight)", "division_id": "467531103"}],
            }
        ],
    }

    def fake_get(url, **kwargs):
        start = kwargs["params"]["start_date"]
        month = "2026-09-30" if start.startswith("2026-09") else "2026-10-01"
        return _permit_response({"467531103": _division({month: 1})})

    with patch("check_permits.requests.get", side_effect=fake_get) as mock_get:
        found, all_failed = find_available(config)

    assert all_failed is False
    assert sorted(found["South Sister (overnight)"]) == ["2026-09-30", "2026-10-01"]
    starts = sorted(c.kwargs["params"]["start_date"] for c in mock_get.call_args_list)
    assert starts == ["2026-09-01T00:00:00.000Z", "2026-10-01T00:00:00.000Z"]


def test_extra_dates_in_response_are_ignored():
    # The API returns the whole month; only the configured date is reported on.
    availability = {"467531103": _division({"2026-09-01": 5, "2026-09-02": 3, "2026-09-09": 5})}
    with patch("check_permits.requests.get", return_value=_permit_response(availability)):
        found, _ = find_available(PERMIT_CONFIG)
    assert found["South Sister (overnight)"] == ["2026-09-02"]


def test_null_payload_does_not_crash():
    resp = MagicMock()
    resp.json.return_value = {"payload": None}
    resp.raise_for_status.return_value = None
    with patch("check_permits.requests.get", return_value=resp):
        found, all_failed = find_available(PERMIT_CONFIG)
    assert found == {}
    assert all_failed is False


def test_build_trailhead_map_warns_on_duplicate_name(capsys):
    facilities = [{"trailheads": [{"name": "South Sister", "url": "https://day-use.example"}]}]
    overnight = [{"trailheads": [{"name": "South Sister", "url": "https://overnight.example"}]}]
    mapping = build_trailhead_map(facilities, overnight)
    assert mapping["South Sister"] == "https://overnight.example"  # last wins
    assert "duplicate trailhead name" in capsys.readouterr().err


def test_overnight_trailhead_url_is_required(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "a@b.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    config = {
        "overnight_permits": [
            {
                "permit_id": "4675311",
                "dates": [],
                "trailheads": [{"name": "no url", "division_id": "467531103"}],
            }
        ],
    }
    with patch("check_permits.load_config", return_value=config):
        with pytest.raises(KeyError):
            main()


def test_day_use_and_overnight_combine_in_one_result():
    config = {
        "facilities": [
            {
                "name": "Day Use",
                "facility_id": "300009",
                "dates": ["2026-09-02"],
                "trailheads": [{"name": "Green Lakes", "tour_id": "2003", "url": "https://a.com"}],
            }
        ],
        "overnight_permits": PERMIT_CONFIG["overnight_permits"],
    }

    def fake_get(url, **kwargs):
        if "permits/4675311" in url:
            return _permit_response({"467531103": _division({"2026-09-02": 1})})
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "facility_availability_summary_view_by_local_date": {
                "2026-09-02": {
                    "tour_availability_summary_view_by_tour_id": {"2003": {"reservable": 3}}
                }
            }
        }
        return resp

    with patch("check_permits.requests.get", side_effect=fake_get):
        found, all_failed = find_available(config)

    assert all_failed is False
    assert found["Green Lakes"] == ["2026-09-02"]
    assert found["South Sister (overnight)"] == ["2026-09-02"]
