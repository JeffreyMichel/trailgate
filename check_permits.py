#!/usr/bin/env python3
import os
import smtplib
import sys
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
import yaml

FACILITY_ID = "300009"
BASE_URL = f"https://www.recreation.gov/api/ticket/availability/facility/{FACILITY_ID}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def load_config(path="config.yml"):
    with open(path) as f:
        return yaml.safe_load(f)


def check_availability(tour_id: str, year: str, month: str) -> dict:
    url = f"{BASE_URL}/{tour_id}/monthlyAvailabilitySummaryView"
    resp = requests.get(url, params={"year": year, "month": month}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def find_available(config: dict) -> dict[str, list[str]]:
    """Returns {trailhead_name: [available_date, ...]}"""
    target_dates = list(dict.fromkeys(config["dates"]))  # deduplicate, preserve order

    # Group dates by year-month to minimize API calls
    by_month: dict[str, list[str]] = defaultdict(list)
    for d in target_dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        by_month[dt.strftime("%Y-%m")].append(d)

    found: dict[str, list[str]] = defaultdict(list)

    for trailhead in config["trailheads"]:
        name = trailhead["name"]
        tour_id = trailhead["tour_id"]

        for ym, dates_in_month in by_month.items():
            year, month = ym.split("-")
            try:
                data = check_availability(tour_id, year, month)
            except requests.HTTPError as e:
                print(f"  HTTP error for {name} ({ym}): {e}", file=sys.stderr)
                continue

            daily = (
                data.get("payload", {})
                .get("facility_availability_summary_view_by_local_date", {})
            )

            for date_str in dates_in_month:
                date_data = daily.get(date_str)
                if not date_data:
                    continue
                tours = date_data.get("tour_availability_summary_view_by_tour_id", {})
                tour = tours.get(tour_id, {})
                reservable = tour.get("reservable", 0)
                if reservable > 0:
                    print(f"  AVAILABLE: {name} on {date_str} ({reservable} spots)")
                    found[name].append(date_str)
                else:
                    print(f"  unavailable: {name} on {date_str}")

    return found


def send_email(available: dict[str, list[str]], config: dict, trailhead_map: dict):
    gmail_address = os.environ["GMAIL_ADDRESS"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    notify_address = os.environ.get("NOTIFY_EMAIL", gmail_address)

    lines = ["Permit availability found for your dates!\n"]
    for name, dates in available.items():
        url = trailhead_map[name]
        for d in sorted(dates):
            lines.append(f"  {name} — {d}")
            lines.append(f"  Book now: {url}\n")

    body = "\n".join(lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Trailgate: Permits Available!"
    msg["From"] = gmail_address
    msg["To"] = notify_address
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, notify_address, msg.as_string())

    print(f"Email sent to {notify_address}")


def main():
    config = load_config()
    trailhead_map = {t["name"]: t["url"] for t in config["trailheads"]}

    print(f"Checking {len(config['trailheads'])} trailhead(s) across {len(config['dates'])} date(s)...")
    available = find_available(config)

    if available:
        send_email(available, config, trailhead_map)
    else:
        print("No availability found. No email sent.")


if __name__ == "__main__":
    main()
