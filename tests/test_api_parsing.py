"""Tests for find_available() in check_permits.py."""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Ensure the project root is on the path so check_permits can be imported.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from check_permits import find_available


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(payload: dict) -> MagicMock:
    """Return a mock requests.Response whose .json() returns the given payload."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"payload": {"facility_availability_summary_view_by_local_date": payload}}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _daily(date_str: str, tour_id: str, reservable: int) -> dict:
    """Build the daily availability dict for a single date / tour."""
    return {
        date_str: {
            "tour_availability_summary_view_by_tour_id": {
                tour_id: {
                    "reservable": reservable,
                    "availability_level": "Available" if reservable > 0 else "Not Available",
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFindAvailable:
    CONFIG_DATE = "2026-07-04"
    TOUR_ID = "2003"
    NAME = "Green Lakes"

    @property
    def _base_config(self):
        return {
            "dates": [self.CONFIG_DATE],
            "trailheads": [
                {"name": self.NAME, "tour_id": self.TOUR_ID, "url": "https://example.com"}
            ],
        }

    def test_date_with_reservable_spots_is_included(self):
        """A date whose reservable count is > 0 should appear in the result."""
        payload = _daily(self.CONFIG_DATE, self.TOUR_ID, reservable=5)

        with patch("check_permits.requests.get", return_value=_make_response(payload)):
            result, _ = find_available(self._base_config)

        assert self.NAME in result
        assert self.CONFIG_DATE in result[self.NAME]

    def test_date_with_zero_reservable_is_excluded(self):
        """A date present in the API response but with reservable == 0 must not appear."""
        payload = _daily(self.CONFIG_DATE, self.TOUR_ID, reservable=0)

        with patch("check_permits.requests.get", return_value=_make_response(payload)):
            result, _ = find_available(self._base_config)

        # Key may be absent or the list may be empty — either is correct.
        assert result.get(self.NAME, []) == []

    def test_date_absent_from_api_response_is_excluded(self):
        """If the API response contains no entry for a requested date, skip it."""
        # Return an empty daily payload — the date simply isn't present.
        with patch("check_permits.requests.get", return_value=_make_response({})):
            result, _ = find_available(self._base_config)

        assert result.get(self.NAME, []) == []

    def test_only_requested_dates_are_returned(self):
        """Extra dates in the API response that were not requested should be ignored."""
        extra_date = "2026-07-05"
        payload = {
            **_daily(self.CONFIG_DATE, self.TOUR_ID, reservable=3),
            **_daily(extra_date, self.TOUR_ID, reservable=10),
        }

        with patch("check_permits.requests.get", return_value=_make_response(payload)):
            result, _ = find_available(self._base_config)

        assert extra_date not in result.get(self.NAME, [])
        assert self.CONFIG_DATE in result[self.NAME]

    def test_multiple_trailheads_each_get_own_key(self):
        """When config lists multiple trailheads, each appears as its own key."""
        tour_a, tour_b = "2003", "2004"
        name_a, name_b = "Green Lakes", "Broken Top"
        date = "2026-07-04"

        payload = {
            date: {
                "tour_availability_summary_view_by_tour_id": {
                    tour_a: {"reservable": 5, "availability_level": "Available"},
                    tour_b: {"reservable": 2, "availability_level": "Available"},
                }
            }
        }

        config = {
            "dates": [date],
            "trailheads": [
                {"name": name_a, "tour_id": tour_a, "url": "https://example.com/a"},
                {"name": name_b, "tour_id": tour_b, "url": "https://example.com/b"},
            ],
        }

        with patch("check_permits.requests.get", return_value=_make_response(payload)):
            result, _ = find_available(config)

        assert date in result[name_a]
        assert date in result[name_b]
        # The two trailheads must be separate keys, not merged.
        assert name_a in result
        assert name_b in result
        assert name_a != name_b

    def test_multiple_trailheads_independent_availability(self):
        """One trailhead available, the other not — results reflect each independently."""
        tour_a, tour_b = "2003", "2004"
        name_a, name_b = "Green Lakes", "Broken Top"
        date = "2026-07-04"

        payload = {
            date: {
                "tour_availability_summary_view_by_tour_id": {
                    tour_a: {"reservable": 5, "availability_level": "Available"},
                    tour_b: {"reservable": 0, "availability_level": "Not Available"},
                }
            }
        }

        config = {
            "dates": [date],
            "trailheads": [
                {"name": name_a, "tour_id": tour_a, "url": "https://example.com/a"},
                {"name": name_b, "tour_id": tour_b, "url": "https://example.com/b"},
            ],
        }

        with patch("check_permits.requests.get", return_value=_make_response(payload)):
            result, _ = find_available(config)

        assert date in result.get(name_a, [])
        assert result.get(name_b, []) == []

    def test_multiple_dates_across_same_month(self):
        """Multiple requested dates in the same month are all evaluated in one API call."""
        date1 = "2026-07-04"
        date2 = "2026-07-11"
        tour_id = self.TOUR_ID

        payload = {
            **_daily(date1, tour_id, reservable=3),
            **_daily(date2, tour_id, reservable=0),
        }

        config = {
            "dates": [date1, date2],
            "trailheads": [{"name": self.NAME, "tour_id": tour_id, "url": "https://example.com"}],
        }

        with patch("check_permits.requests.get", return_value=_make_response(payload)) as mock_get:
            result, _ = find_available(config)

        # Only one API call should have been made (same year-month).
        assert mock_get.call_count == 1

        assert date1 in result[self.NAME]
        assert date2 not in result.get(self.NAME, [])

    def test_dates_across_different_months_make_separate_api_calls(self):
        """Dates in different months each trigger their own API call."""
        date_jul = "2026-07-04"
        date_aug = "2026-08-01"
        tour_id = self.TOUR_ID

        # Both months return availability.
        payload_jul = _daily(date_jul, tour_id, reservable=1)
        payload_aug = _daily(date_aug, tour_id, reservable=2)

        responses = [_make_response(payload_jul), _make_response(payload_aug)]

        config = {
            "dates": [date_jul, date_aug],
            "trailheads": [{"name": self.NAME, "tour_id": tour_id, "url": "https://example.com"}],
        }

        with patch("check_permits.requests.get", side_effect=responses) as mock_get:
            result, _ = find_available(config)

        assert mock_get.call_count == 2
        assert date_jul in result[self.NAME]
        assert date_aug in result[self.NAME]
