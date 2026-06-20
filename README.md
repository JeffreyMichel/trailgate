# Trailgate

Checks [Recreation.gov](https://www.recreation.gov) daily for Central Cascades Wilderness permit availability on your available dates and emails you when spots open up.

## How it works

A GitHub Action runs every day at 8am Pacific. It reads your available dates and target trailheads from `config.yml`, queries the Recreation.gov API, and sends you an email with a direct booking link if any permits are available.

## Setup

### 1. Configure your dates and trailheads

Edit `config.yml`:

```yaml
dates:
  - "2026-07-04"
  - "2026-07-12"

trailheads:
  - name: "Devils Lake / South Sister"
    tour_id: "10088687"
    url: "https://www.recreation.gov/ticket/300009/ticket/10088687"
  - name: "Green Lakes / Soda Creek"
    tour_id: "2003"
    url: "https://www.recreation.gov/ticket/300009/ticket/2003"
```

### 2. Add GitHub Secrets

In your repo go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | 16-character app password from [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) |
| `NOTIFY_EMAIL` | Where to send alerts (can be same as `GMAIL_ADDRESS`) |

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
