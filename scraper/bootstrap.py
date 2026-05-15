#!/usr/bin/env python3
"""
One-time bootstrap: scrape the last N days of HKEX DI filings.
Usage:  python scraper/bootstrap.py [days=30]
"""
import sys
from datetime import datetime, timedelta, timezone
from scrape import main as run_main
import sys as _sys

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30

hk_now = datetime.now(timezone.utc) + timedelta(hours=8)
dates = [
    (hk_now - timedelta(days=i)).strftime("%d/%m/%Y")
    for i in range(days, -1, -1)
]

# Inject into sys.argv so scrape.main picks them up
_sys.argv = ["scrape.py"] + dates
run_main()
