import pytest
import yaml

from check_permits import load_config


def _facility(dates, trailheads, facility_id="300009", name="Test Facility"):
    return {
        "name": name,
        "facility_id": facility_id,
        "dates": dates,
        "trailheads": trailheads,
    }


def test_valid_config_loads_expected_keys(tmp_path):
    config_data = {
        "facilities": [
            _facility(
                dates=["2026-07-04", "2026-07-05"],
                trailheads=[
                    {
                        "name": "Half Dome",
                        "tour_id": "10085052",
                        "url": "https://www.recreation.gov/ticket/facility/300009",
                    }
                ],
            )
        ],
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    assert "facilities" in config
    facility = config["facilities"][0]
    assert "facility_id" in facility
    assert "dates" in facility
    assert "trailheads" in facility


def test_valid_config_dates_values(tmp_path):
    config_data = {
        "facilities": [
            _facility(
                dates=["2026-07-04", "2026-07-05"],
                trailheads=[
                    {
                        "name": "Half Dome",
                        "tour_id": "10085052",
                        "url": "https://www.recreation.gov/ticket/facility/300009",
                    }
                ],
            )
        ],
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    assert config["facilities"][0]["dates"] == ["2026-07-04", "2026-07-05"]


def test_trailhead_entries_have_required_keys(tmp_path):
    config_data = {
        "facilities": [
            _facility(
                dates=["2026-07-04"],
                trailheads=[
                    {
                        "name": "Half Dome",
                        "tour_id": "10085052",
                        "url": "https://www.recreation.gov/ticket/facility/300009",
                    },
                    {
                        "name": "Snow Creek",
                        "tour_id": "10085053",
                        "url": "https://www.recreation.gov/ticket/facility/300009/tour/10085053",
                    },
                ],
            )
        ],
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    for facility in config["facilities"]:
        for trailhead in facility["trailheads"]:
            assert "name" in trailhead
            assert "tour_id" in trailhead
            assert "url" in trailhead


def test_missing_file_raises_file_not_found(tmp_path):
    missing = tmp_path / "nonexistent.yml"

    with pytest.raises(FileNotFoundError):
        load_config(str(missing))


def test_empty_file_raises_error(tmp_path):
    config_file = tmp_path / "config.yml"
    config_file.write_text("")

    # yaml.safe_load returns None for an empty file; accessing keys on None
    # raises TypeError when the caller (or we) try to use the result.
    result = load_config(str(config_file))
    assert result is None  # load_config itself succeeds ...

    # ... but using the result as a dict raises TypeError
    with pytest.raises(TypeError):
        _ = result["facilities"]


def test_config_missing_facilities_key(tmp_path):
    config_data = {
        "dates": ["2026-07-04"],  # no top-level facilities key
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    # The config loads successfully but "facilities" is absent; accessing it raises KeyError.
    assert "facilities" not in config
    with pytest.raises(KeyError):
        _ = config["facilities"]
