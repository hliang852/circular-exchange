# HKEX Disclosure of Interest Tracker

A GitHub Pages site that tracks HKEX substantial shareholder and director
dealings, updated automatically every day via GitHub Actions.

## Columns

| Column | Source |
|---|---|
| Serial # | Link to the HKEX filing |
| Filed | Date the form was filed |
| Event Date | Date the transaction occurred |
| Ticker | HKEX stock code |
| Company | Name of listed corporation |
| Person / Entity | Filer name |
| Capacity | Director, Substantial Shareholder, etc. |
| Shares Held | Post-transaction balance |
| Change (#) | Absolute change vs previous filing |
| Change (%) | Percentage change vs previous filing |
| Nature / Relationship | Nature of interest + search link |
| Report | News link for disposals |

## Setup

### 1. Push to GitHub

```bash
cd hkex-tracker
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/hliang852/hkex-tracker.git
git push -u origin main
```

### 2. Enable GitHub Pages

Go to **Settings → Pages → Source** and select **`main` branch, `/` (root)**.

### 3. Bootstrap historical data (optional, run locally)

```bash
pip install -r scraper/requirements.txt
python scraper/bootstrap.py 30     # scrape last 30 days
```

Then commit and push `data/filings.json`.

### 4. Daily automation

The GitHub Actions workflow (`.github/workflows/daily.yml`) runs automatically
at **01:00 HK time** every day. You can also trigger it manually from the
Actions tab with a custom date range.

## Manual scrape

```bash
# Specific date
python scraper/scrape.py 14/05/2026

# Multiple dates
python scraper/scrape.py 12/05/2026 13/05/2026 14/05/2026
```
