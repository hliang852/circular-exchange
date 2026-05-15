#!/usr/bin/env python3
"""
HKEX Disclosure of Interest scraper.
Fetches daily filings and updates data/filings.json.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import sys
import time
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

BASE_URL = "https://di.hkex.com.hk/di/"
DATA_FILE = Path(__file__).parent.parent / "data" / "filings.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_request(session, url, method="GET", data=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            if method == "POST":
                resp = session.post(url, data=data, headers=HEADERS, timeout=30)
            else:
                resp = session.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            time.sleep(1.2)
            return resp
        except requests.RequestException as exc:
            log.warning("Request failed (attempt %d/%d): %s", attempt + 1, max_retries, exc)
            if attempt < max_retries - 1:
                time.sleep(4 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# List-page parser
# ---------------------------------------------------------------------------

def find_table(soup):
    """Return the best-candidate table from the results page."""
    # Try by known id/class first
    for attrs in [
        {"id": "tbResult"},
        {"class": "table_gray"},
        {"class": "result_table"},
    ]:
        t = soup.find("table", attrs)
        if t:
            return t

    # Fallback: any table whose headers mention stock/corporation
    for t in soup.find_all("table"):
        headers_text = " ".join(
            th.get_text(strip=True).lower() for th in t.find_all("th")
        )
        if any(k in headers_text for k in ("stock", "corporation", "filer", "capacity")):
            return t
    return None


def parse_filings_list(html):
    soup = BeautifulSoup(html, "lxml")
    table = find_table(soup)
    if not table:
        log.warning("Could not find filings table in list page")
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    # Build column-name -> index map from header row
    header_cells = rows[0].find_all(["th", "td"])
    col_map = {}
    for i, cell in enumerate(header_cells):
        text = cell.get_text(strip=True).lower()
        col_map[text] = i
    log.info("List-page columns: %s", list(col_map.keys()))

    results = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells:
            continue

        entry = {}
        texts = [c.get_text(strip=True) for c in cells]

        # --- extract link / serial ---
        for cell in cells[:6]:
            a = cell.find("a")
            if a and a.get("href"):
                href = a["href"]
                if any(k in href for k in ("NSForm", "fn=", ".aspx")):
                    entry["serial"] = a.get_text(strip=True) or re.search(r"fn=(\w+)", href, re.I) and re.search(r"fn=(\w+)", href, re.I).group(1) or ""
                    entry["url"] = href if href.startswith("http") else BASE_URL + href.lstrip("/")
                    break

        if not entry.get("url"):
            continue

        # --- map well-known columns ---
        def col_val(keys):
            for k in keys:
                for col_name, idx in col_map.items():
                    if k in col_name and idx < len(texts):
                        return texts[idx]
            return ""

        entry["filing_date"] = col_val(["date", "form date"])
        entry["stock_code"]  = col_val(["stock code", "share code"])
        entry["company_name"] = col_val(["corporation", "listed company", "issuer"])
        entry["person_entity"] = col_val(["filer", "substantial", "director", "name of"])
        entry["capacity"]    = col_val(["capacity"])

        # --- positional fallback for dates ---
        if not entry["filing_date"]:
            for t in texts:
                if re.match(r"\d{2}/\d{2}/\d{4}", t):
                    entry["filing_date"] = t
                    break

        # --- positional fallback for stock code ---
        if not entry["stock_code"]:
            for t in texts:
                if re.match(r"^\d{4,5}$", t.strip()):
                    entry["stock_code"] = t.strip().zfill(4)
                    break

        results.append(entry)

    log.info("Parsed %d filings from list", len(results))
    return results


# ---------------------------------------------------------------------------
# Individual filing page parser
# ---------------------------------------------------------------------------

def clean_number(text):
    """Parse a number like '1,234,567' or '(500,000)' (negative)."""
    text = text.strip().replace(",", "").replace(" ", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        val = int(text)
        return -val if negative else val
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return 0


def parse_filing_detail(html, serial, url):
    soup = BeautifulSoup(html, "lxml")
    d = {
        "serial":                  serial,
        "url":                     url,
        "event_date":              "",
        "stock_code":              "",
        "company_name":            "",
        "person_entity":           "",
        "capacity":                "",
        "nature_of_interest":      "",
        "shares_held_before":      0,
        "shares_acquired_disposed": 0,
        "shares_held_after":       0,
        "percentage_held":         0.0,
        "is_disposal":             False,
        "form_type":               "",
    }

    # Page title sometimes has form type
    h2 = soup.find(["h2", "h3", "h1"])
    if h2:
        d["form_type"] = h2.get_text(strip=True)

    # Walk all label->value pairs in tables
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(separator=" ", strip=True).lower()
            value = cells[-1].get_text(separator=" ", strip=True)

            if not value:
                continue

            if any(k in label for k in ("name of listed", "listed corporation", "issuer name")):
                d["company_name"] = value
            elif any(k in label for k in ("stock code", "share code", "stock / share code")):
                raw = re.sub(r"\s+", "", value)
                d["stock_code"] = raw.zfill(4) if re.match(r"^\d+$", raw) else raw
            elif any(k in label for k in ("date of relevant", "event date", "date of event")):
                d["event_date"] = value
            elif any(k in label for k in ("name of substantial", "name of director", "declarer", "filer", "name of person")):
                d["person_entity"] = value
            elif label.strip() in ("capacity", "capacity of declarer") or "capacity" == label.strip():
                d["capacity"] = value
            elif "nature of interest" in label:
                d["nature_of_interest"] = value

    # Share holdings table: look for rows with (before, change, after, %)
    share_rows_found = False
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            texts = [c.get_text(strip=True) for c in cells]

            # Look for numeric values
            nums = []
            for t in texts:
                n = clean_number(t)
                if n != 0:
                    nums.append(n)

            if len(nums) >= 3 and not share_rows_found:
                # Candidate share row: before, change, after at minimum
                big = [n for n in nums if abs(n) > 100]
                if len(big) >= 2:
                    d["shares_held_before"]      = big[0]
                    d["shares_acquired_disposed"] = big[1] if len(big) >= 3 else 0
                    d["shares_held_after"]        = big[-1]
                    share_rows_found = True

            # Percentage
            for t in texts:
                m = re.search(r"(\d+\.\d+)\s*%", t)
                if m and not d["percentage_held"]:
                    d["percentage_held"] = float(m.group(1))

    # Disposal flag
    if d["shares_acquired_disposed"] < 0:
        d["is_disposal"] = True
    elif d["shares_held_before"] > 0 and d["shares_held_after"] > 0:
        d["is_disposal"] = d["shares_held_after"] < d["shares_held_before"]

    return d


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"filings": [], "last_updated": "", "entity_latest": {}}


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved %d filings to %s", len(data["filings"]), DATA_FILE)


# ---------------------------------------------------------------------------
# Change calculation
# ---------------------------------------------------------------------------

def entity_key(stock_code, person):
    return f"{stock_code}|||{person}".lower().strip()


def pct_change(current, previous):
    if not previous:
        return None, None
    prev = previous.get("shares_held_after") or previous.get("shares_held_before") or 0
    curr = current.get("shares_held_after") or current.get("shares_held_before") or 0
    if prev == 0:
        return None, curr
    delta = curr - prev
    return round(delta / prev * 100, 4), delta


# ---------------------------------------------------------------------------
# Scrape a single date
# ---------------------------------------------------------------------------

def scrape_date(session, date_str):
    """date_str in DD/MM/YYYY"""
    url = (
        f"{BASE_URL}NSAllFormDateList.aspx"
        f"?sa1=da&scsd={date_str}&sced={date_str}&src=MAIN&lang=EN&g_lang=en"
    )
    log.info("Fetching list: %s", url)
    resp = make_request(session, url)
    if not resp:
        log.error("Failed to fetch list for %s", date_str)
        return []

    summaries = parse_filings_list(resp.content)

    details = []
    for i, s in enumerate(summaries):
        if not s.get("url"):
            continue
        log.info("  [%d/%d] %s  %s", i + 1, len(summaries), s.get("serial", "?"), s.get("url", ""))
        r = make_request(session, s["url"])
        if not r:
            details.append(s)
            continue

        detail = parse_filing_detail(r.content, s.get("serial", ""), s["url"])
        # Merge – summary wins for fields like filing_date, stock_code if detail missed them
        for k, v in s.items():
            if not detail.get(k):
                detail[k] = v
        detail["filing_date"] = date_str
        detail["scraped_at"] = datetime.now(timezone.utc).isoformat()
        details.append(detail)
        time.sleep(0.8)

    return details


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1:
        dates = sys.argv[1:]
    else:
        hk_now = datetime.now(timezone.utc) + timedelta(hours=8)
        # Scrape yesterday (filings are usually published same or next day)
        dates = [(hk_now - timedelta(days=1)).strftime("%d/%m/%Y")]

    log.info("Dates to scrape: %s", dates)
    store = load_data()
    known = {f["serial"] for f in store["filings"] if f.get("serial")}
    entity_latest = store.get("entity_latest", {})

    session = requests.Session()
    added = 0

    for date_str in dates:
        filings = scrape_date(session, date_str)
        for f in filings:
            if f.get("serial") and f["serial"] in known:
                continue
            key = entity_key(f.get("stock_code", ""), f.get("person_entity", ""))
            prev = entity_latest.get(key)
            f["pct_change_from_previous"], f["share_change_from_previous"] = pct_change(f, prev)
            f["previous_serial"] = prev.get("serial") if prev else None
            entity_latest[key] = {
                "serial":           f.get("serial"),
                "shares_held_after": f.get("shares_held_after", 0),
                "shares_held_before": f.get("shares_held_before", 0),
                "filing_date":      f.get("filing_date"),
            }
            store["filings"].append(f)
            if f.get("serial"):
                known.add(f["serial"])
            added += 1

    store["filings"].sort(key=lambda x: x.get("filing_date", ""), reverse=True)
    store["entity_latest"] = entity_latest
    store["last_updated"] = datetime.now(timezone.utc).isoformat()
    save_data(store)
    log.info("Done — added %d new filings", added)


if __name__ == "__main__":
    main()
