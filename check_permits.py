#!/usr/bin/env python3
import os
import smtplib
import sys
import time
from collections import defaultdict
from datetime import datetime
from email.mime.text import MIMEText

import requests
import yaml

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def availability_url(facility_id: str) -> str:
    """Recreation.gov monthly-availability endpoint for a given facility.

    This is the *ticketed* API used for day-use permits. Overnight permits use a
    different API entirely -- see ``overnight_availability_url``.
    """
    return (
        "https://www.recreation.gov/api/ticket/availability/facility/"
        f"{facility_id}/monthlyAvailabilitySummaryView"
    )


def overnight_availability_url(permit_id: str) -> str:
    """Recreation.gov monthly-availability endpoint for an overnight permit.

    The overnight-permit (itinerary) API is keyed by ``division_id`` rather than
    ``tour_id`` and reports ``remaining`` counts per date, so it needs its own
    request and parsing path (``check_overnight_availability`` / ``_find_in_permit``).
    """
    return f"https://www.recreation.gov/api/permits/{permit_id}/availability/month"


# Network retry behavior for recreation.gov, which rate-limits / blocks scrapers.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

REQUIRED_ENV_VARS = ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")


def load_config(path="config.yml"):
    with open(path) as f:
        return yaml.safe_load(f)


def _get_json_with_retries(url: str, params: dict) -> dict:
    """GET ``url`` and return the parsed JSON, retrying on transient errors.

    recreation.gov rate-limits / blocks scrapers, so both availability APIs share
    this behaviour: up to ``MAX_RETRIES`` attempts with a linearly growing
    ``RETRY_BACKOFF_SECONDS`` delay, logging 403/429 responses. Re-raises the last
    error if every attempt fails.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            last_error = e
            status = getattr(e.response, "status_code", None)
            if status in (403, 429):
                print(
                    f"  rate-limited/blocked (HTTP {status}), attempt {attempt}/{MAX_RETRIES}",
                    file=sys.stderr,
                )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise last_error  # type: ignore[misc]


def check_availability(facility_id: str, year: str, month: str) -> dict:
    """Monthly availability for a day-use facility (ticketed API)."""
    return _get_json_with_retries(
        availability_url(facility_id),
        {"year": year, "month": month, "inventoryBucket": "FIT"},
    )


def check_overnight_availability(permit_id: str, year: str, month: str) -> dict:
    """Monthly availability for a recreation.gov overnight permit.

    One call returns the whole month starting at the 1st; the response payload is
    keyed by ``division_id``.
    """
    start = f"{year}-{month}-01T00:00:00.000Z"
    return _get_json_with_retries(overnight_availability_url(permit_id), {"start_date": start})


def _trailhead_dates(trailhead: dict, default_dates: list[str]) -> list[str]:
    """Dates to check for a given trailhead.

    A trailhead may override the global ``dates`` with its own ``dates`` list;
    otherwise it falls back to the config-level default. Order is preserved and
    duplicates removed.
    """
    dates = trailhead.get("dates", default_dates)
    return list(dict.fromkeys(dates))


def _dates_by_month(
    trailheads: list[dict], default_dates: list[str]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Resolve each trailhead's dates and group their union by year-month.

    Shared by the facility and overnight-permit paths. Returns
    ``(dates_by_trailhead, by_month)`` where ``by_month`` maps ``"YYYY-MM"`` to
    the target dates in that month, so callers make one API call per month.
    """
    dates_by_trailhead = {t["name"]: _trailhead_dates(t, default_dates) for t in trailheads}
    all_target_dates = list(
        dict.fromkeys(d for dates in dates_by_trailhead.values() for d in dates)
    )
    by_month: dict[str, list[str]] = defaultdict(list)
    for d in all_target_dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        by_month[dt.strftime("%Y-%m")].append(d)
    return dates_by_trailhead, by_month


def _find_in_facility(facility: dict, found: dict[str, list[str]]) -> tuple[int, int]:
    """Check one facility, recording hits into ``found``.

    Returns ``(attempts, failures)`` for this facility's API calls. Each
    trailhead is checked against the facility's ``dates`` unless it defines its
    own ``dates`` list, which scopes that trailhead to those dates.
    """
    facility_id = facility["facility_id"]
    facility_name = facility.get("name", facility_id)
    default_dates = list(dict.fromkeys(facility.get("dates", [])))
    dates_by_trailhead, by_month = _dates_by_month(facility["trailheads"], default_dates)

    attempts = 0
    failures = 0

    # One API call per month covers all trailheads — response includes every tour_id
    for ym, dates_in_month in by_month.items():
        year, month = ym.split("-")
        attempts += 1
        try:
            data = check_availability(facility_id, year, month)
        except requests.RequestException as e:
            failures += 1
            print(f"  request error ({facility_name} {ym}): {e}", file=sys.stderr)
            continue

        daily = data.get("facility_availability_summary_view_by_local_date", {})

        for date_str in dates_in_month:
            date_data = daily.get(date_str)
            if not date_data:
                continue
            tours = date_data.get("tour_availability_summary_view_by_tour_id", {})
            for trailhead in facility["trailheads"]:
                name = trailhead["name"]
                if date_str not in dates_by_trailhead[name]:
                    continue  # this date isn't in scope for this trailhead
                tour_id = trailhead["tour_id"]
                tour = tours.get(tour_id, {})
                reservable = tour.get("reservable") or 0
                if reservable > 0:
                    print(f"  AVAILABLE: {name} on {date_str} ({reservable} spots)")
                    found[name].append(date_str)
                else:
                    print(f"  unavailable: {name} on {date_str}")

    return attempts, failures


def _find_in_permit(permit: dict, found: dict[str, list[str]]) -> tuple[int, int]:
    """Check one overnight permit, recording hits into ``found``.

    Mirrors ``_find_in_facility`` but against the overnight-permit API, which is
    keyed by ``division_id`` and reports ``remaining`` per
    ``YYYY-MM-DDT00:00:00Z`` date. Per-trailhead ``dates`` overrides work the
    same way. Returns ``(attempts, failures)`` for this permit's API calls.
    """
    permit_id = permit["permit_id"]
    permit_name = permit.get("name", permit_id)
    default_dates = list(dict.fromkeys(permit.get("dates", [])))
    dates_by_trailhead, by_month = _dates_by_month(permit["trailheads"], default_dates)

    attempts = 0
    failures = 0

    # One API call per month returns every division's availability.
    for ym, dates_in_month in by_month.items():
        year, month = ym.split("-")
        attempts += 1
        try:
            data = check_overnight_availability(permit_id, year, month)
        except requests.RequestException as e:
            failures += 1
            print(f"  request error ({permit_name} {ym}): {e}", file=sys.stderr)
            continue

        by_division = (data.get("payload") or {}).get("availability") or {}

        for trailhead in permit["trailheads"]:
            name = trailhead["name"]
            division = by_division.get(trailhead["division_id"]) or {}
            day_avail = division.get("date_availability") or {}
            for date_str in dates_in_month:
                if date_str not in dates_by_trailhead[name]:
                    continue  # this date isn't in scope for this trailhead
                slot = day_avail.get(f"{date_str}T00:00:00Z", {})
                remaining = slot.get("remaining") or 0
                if remaining > 0:
                    print(f"  AVAILABLE: {name} on {date_str} ({remaining} spots)")
                    found[name].append(date_str)
                else:
                    print(f"  unavailable: {name} on {date_str}")

    return attempts, failures


def find_available(config: dict) -> tuple[dict[str, list[str]], bool]:
    """Check availability across every facility/trailhead/date.

    Returns ``(found, all_failed)`` where ``found`` is
    ``{trailhead_name: [available_date, ...]}`` and ``all_failed`` is True when
    every API request errored (so the caller can distinguish a broken checker
    from a genuine "nothing available" result).
    """
    found: dict[str, list[str]] = defaultdict(list)
    attempts = 0
    failures = 0

    for facility in config.get("facilities", []):
        f_attempts, f_failures = _find_in_facility(facility, found)
        attempts += f_attempts
        failures += f_failures

    for permit in config.get("overnight_permits", []):
        p_attempts, p_failures = _find_in_permit(permit, found)
        attempts += p_attempts
        failures += p_failures

    all_failed = attempts > 0 and failures == attempts
    return found, all_failed


def build_email_body(available: dict[str, list[str]], trailhead_map: dict) -> str:
    lines = ["Permit availability found for your dates!\n"]
    for name, dates in available.items():
        url = trailhead_map.get(name, "https://www.recreation.gov")
        for d in sorted(dates):
            lines.append(f"  {name} — {d}")
            lines.append(f"  Book now: {url}?date={d}\n")
    return "\n".join(lines)


def send_email(available: dict[str, list[str]], trailhead_map: dict):
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    notify_address = os.environ.get("NOTIFY_EMAIL", gmail_address)

    body = build_email_body(available, trailhead_map)

    msg = MIMEText(body, "plain")
    msg["Subject"] = "Trailgate: Permits Available!"
    msg["From"] = gmail_address
    msg["To"] = notify_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, notify_address, msg.as_string())

    print(f"Email sent to {notify_address}")


def send_failure_email(reason: str) -> None:
    """Best-effort alert when the checker itself breaks.

    Sent so a silently-failing job (e.g. recreation.gov blocking us) is visible
    without having to watch the GitHub Actions dashboard. Swallows its own
    errors — if we can't even send mail, we still want the original failure to
    surface via the non-zero exit.
    """
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not (gmail_address and gmail_password):
        return
    notify_address = os.environ.get("NOTIFY_EMAIL", gmail_address)

    msg = MIMEText(reason, "plain")
    msg["Subject"] = "Trailgate: Checker FAILED"
    msg["From"] = gmail_address
    msg["To"] = notify_address

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, notify_address, msg.as_string())
        print(f"Failure alert sent to {notify_address}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - alerting is best-effort
        print(f"Could not send failure alert: {e}", file=sys.stderr)


def check_env() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing)}")


def build_trailhead_map(facilities: list[dict], overnight: list[dict]) -> dict[str, str]:
    """Map every trailhead name to its booking ``url``, warning on collisions.

    ``found`` is keyed by trailhead ``name`` across both sections, so a name
    reused between (or within) sections silently merges results in the email.
    Warn to stderr so that stays visible. ``url`` is required on every trailhead
    in both sections.
    """
    trailhead_map: dict[str, str] = {}
    for entry in (*facilities, *overnight):
        for t in entry["trailheads"]:
            name = t["name"]
            if name in trailhead_map:
                print(
                    f"  WARNING: duplicate trailhead name {name!r} — its results will merge",
                    file=sys.stderr,
                )
            trailhead_map[name] = t["url"]
    return trailhead_map


def main():
    check_env()
    config = load_config()
    facilities = config.get("facilities", [])
    overnight = config.get("overnight_permits", [])

    trailhead_map = build_trailhead_map(facilities, overnight)

    trailhead_count = sum(len(f["trailheads"]) for f in facilities) + sum(
        len(p["trailheads"]) for p in overnight
    )
    print(
        f"Checking {trailhead_count} trailhead(s) across "
        f"{len(facilities)} facilit{'y' if len(facilities) == 1 else 'ies'} "
        f"and {len(overnight)} overnight permit(s)..."
    )
    available, all_failed = find_available(config)

    if all_failed:
        # Every request errored — the checker is broken, not the permits sold out.
        # Email an alert and exit non-zero so the scheduled job goes red instead
        # of silently passing.
        reason = (
            "ERROR: all availability requests failed. "
            "recreation.gov may be blocking requests or its API may have changed."
        )
        send_failure_email(reason)
        raise SystemExit(reason)

    if available:
        send_email(available, trailhead_map)
    else:
        print("No availability found. No email sent.")


if __name__ == "__main__":
    main()
