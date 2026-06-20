import pytest
import yaml

from check_permits import load_config


def test_valid_config_loads_expected_keys(tmp_path):
    config_data = {
        "dates": ["2026-07-04", "2026-07-05"],
        "trailheads": [
            {
                "name": "Half Dome",
                "tour_id": "10085052",
                "url": "https://www.recreation.gov/ticket/facility/300009",
            }
        ],
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    assert "dates" in config
    assert "trailheads" in config


def test_valid_config_dates_values(tmp_path):
    config_data = {
        "dates": ["2026-07-04", "2026-07-05"],
        "trailheads": [
            {
                "name": "Half Dome",
                "tour_id": "10085052",
                "url": "https://www.recreation.gov/ticket/facility/300009",
            }
        ],
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    assert config["dates"] == ["2026-07-04", "2026-07-05"]


def test_trailhead_entries_have_required_keys(tmp_path):
    config_data = {
        "dates": ["2026-07-04"],
        "trailheads": [
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
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    for trailhead in config["trailheads"]:
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
        _ = result["dates"]


def test_config_missing_dates_key(tmp_path):
    config_data = {
        "trailheads": [
            {
                "name": "Half Dome",
                "tour_id": "10085052",
                "url": "https://www.recreation.gov/ticket/facility/300009",
            }
        ]
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(yaml.dump(config_data))

    config = load_config(str(config_file))

    # The config loads successfully but "dates" is absent; accessing it raises KeyError.
    assert "dates" not in config
    with pytest.raises(KeyError):
        _ = config["dates"]
