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

FACILITY_ID = "300009"
BASE_URL = f"https://www.recreation.gov/api/ticket/availability/facility/{FACILITY_ID}/monthlyAvailabilitySummaryView"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Network retry behavior for recreation.gov, which rate-limits / blocks scrapers.
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2

REQUIRED_ENV_VARS = ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")


def load_config(path="config.yml"):
    with open(path) as f:
        return yaml.safe_load(f)


def check_availability(year: str, month: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                BASE_URL,
                params={"year": year, "month": month, "inventoryBucket": "FIT"},
                headers=HEADERS,
                timeout=15,
            )
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


def _trailhead_dates(trailhead: dict, default_dates: list[str]) -> list[str]:
    """Dates to check for a given trailhead.

    A trailhead may override the global ``dates`` with its own ``dates`` list;
    otherwise it falls back to the config-level default. Order is preserved and
    duplicates removed.
    """
    dates = trailhead.get("dates", default_dates)
    return list(dict.fromkeys(dates))


def find_available(config: dict) -> tuple[dict[str, list[str]], bool]:
    """Check availability for every trailhead/date.

    Each trailhead is checked against the global ``config["dates"]`` unless it
    defines its own ``dates`` list, which scopes that trailhead to those dates.

    Returns ``(found, all_failed)`` where ``found`` is
    ``{trailhead_name: [available_date, ...]}`` and ``all_failed`` is True when
    every API request errored (so the caller can distinguish a broken checker
    from a genuine "nothing available" result).
    """
    default_dates = list(dict.fromkeys(config["dates"]))  # deduplicate, preserve order

    # Resolve the set of dates each trailhead actually cares about.
    dates_by_trailhead = {
        t["name"]: _trailhead_dates(t, default_dates) for t in config["trailheads"]
    }

    # Union of every relevant date determines which months we need to query.
    all_target_dates = list(
        dict.fromkeys(d for dates in dates_by_trailhead.values() for d in dates)
    )

    # Group dates by year-month to minimize API calls
    by_month: dict[str, list[str]] = defaultdict(list)
    for d in all_target_dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        by_month[dt.strftime("%Y-%m")].append(d)

    found: dict[str, list[str]] = defaultdict(list)
    attempts = 0
    failures = 0

    # One API call per month covers all trailheads — response includes every tour_id
    for ym, dates_in_month in by_month.items():
        year, month = ym.split("-")
        attempts += 1
        try:
            data = check_availability(year, month)
        except requests.RequestException as e:
            failures += 1
            print(f"  request error ({ym}): {e}", file=sys.stderr)
            continue

        daily = data.get("facility_availability_summary_view_by_local_date", {})

        for date_str in dates_in_month:
            date_data = daily.get(date_str)
            if not date_data:
                continue
            tours = date_data.get("tour_availability_summary_view_by_tour_id", {})
            for trailhead in config["trailheads"]:
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

    all_failed = attempts > 0 and failures == attempts
    return found, all_failed


def build_email_body(available: dict[str, list[str]], trailhead_map: dict) -> str:
    lines = ["Permit availability found for your dates!\n"]
    for name, dates in available.items():
        url = trailhead_map.get(name, "https://www.recreation.gov/ticket/300009")
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


def main():
    check_env()
    config = load_config()
    trailhead_map = {t["name"]: t["url"] for t in config["trailheads"]}

    print(
        f"Checking {len(config['trailheads'])} trailhead(s) "
        f"across {len(config['dates'])} date(s)..."
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
