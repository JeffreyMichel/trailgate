# Trailgate

Checks [Recreation.gov](https://www.recreation.gov) daily for Central Cascades Wilderness permit availability on your available dates and emails you when spots open up.

## How it works

A GitHub Action runs daily in the early morning Pacific time (twice, at ~6 and ~7 AM, to cover the PST/PDT shift). It reads your available dates and target trailheads from `config.yml`, queries the Recreation.gov API, and sends you an email with a direct booking link if any permits are available. If every request fails (e.g. recreation.gov blocks the checker), the job exits non-zero and emails you a failure alert.

## Setup

### 1. Configure your dates and trailheads

Edit `config.yml`. List the dates you're available and the trailheads to watch:

```yaml
dates:
  - "2026-07-04"
  - "2026-07-12"

trailheads:
  - name: "Green Lakes / Soda Creek"
    tour_id: "2003"
    url: "https://www.recreation.gov/ticket/300009/ticket/2003"
  - name: "Devils Lake / South Sister"
    tour_id: "10088687"
    url: "https://www.recreation.gov/ticket/300009/ticket/10088687"
```

The repo ships with all Central Cascades trailheads pre-populated — trim the list to the ones you care about.

#### Scoping a trailhead to specific dates

By default every trailhead is checked against the global `dates`. To watch a
trailhead only on certain dates, give it its own `dates` list:

```yaml
trailheads:
  - name: "Devils Lake / South Sister"
    tour_id: "10088687"
    url: "https://www.recreation.gov/ticket/300009/ticket/10088687"
    dates:               # overrides the global dates for this trailhead only
      - "2026-07-04"
```

### 2. Add GitHub Secrets

In your repo go to **Settings → Secrets and variables → Actions** and add:

| Secret | Required | Value |
|---|---|---|
| `GMAIL_ADDRESS` | Yes | Your Gmail address (used to send the mail) |
| `GMAIL_APP_PASSWORD` | Yes | 16-character app password from [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |
| `NOTIFY_EMAIL` | No | Where to send alerts. Defaults to `GMAIL_ADDRESS` if unset. |

### 3. Trigger manually to test

Go to **Actions → Check Permit Availability → Run workflow** to run it immediately and confirm the email works before waiting for the daily schedule.

## Adding trailheads

Find the trailhead on Recreation.gov. The URL will look like:
```
https://www.recreation.gov/ticket/300009/ticket/{tour_id}
```
Copy the `tour_id` from the URL and add a new entry to `config.yml`.

## Running locally

```bash
pip install -r requirements.txt
GMAIL_ADDRESS=you@gmail.com GMAIL_APP_PASSWORD=xxxx NOTIFY_EMAIL=you@gmail.com python check_permits.py
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## Linting

This repo uses [ruff](https://docs.astral.sh/ruff/) and
[pre-commit](https://pre-commit.com/). After installing dev dependencies:

```bash
ruff check .          # lint
ruff format .         # format
pre-commit install    # run the hooks automatically on every commit
```
