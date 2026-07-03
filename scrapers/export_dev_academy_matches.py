"""
export_dev_academy_matches.py
------------------------------
Pulls all rows from tca_db_match_info where the series column contains
"development league" or "academy league" (case-insensitive) AND the
match_date falls in 2026, then exports them to an Excel file.

Setup:
    pip install supabase python-dotenv openpyxl pandas

Environment variables (.env or shell):
    SUPABASE_URL
    SUPABASE_KEY
"""

import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLE = "tca_db_match_info"
OUTPUT_FILE = "dev_academy_league_matches_2026.xlsx"
PAGE_SIZE = 1000


def fetch_all_rows() -> list[dict]:
    """Paginate through the table since Supabase caps results per request."""
    all_rows = []
    start = 0
    while True:
        res = (
            supabase.table(TABLE)
            .select("*")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        batch = res.data
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return all_rows


def main():
    print("Fetching all rows from Supabase...")
    rows = fetch_all_rows()
    print(f"Fetched {len(rows)} total rows.")

    df = pd.DataFrame(rows)

    # Filter: series contains "development league" or "academy league" (case-insensitive)
    series_mask = df["series"].str.contains(
        r"development league|academy league", case=False, na=False, regex=True
    )

    # Filter: match_date is in 2026
    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
    year_mask = df["match_date"].dt.year == 2026

    filtered = df[series_mask & year_mask].copy()
    filtered = filtered.sort_values("match_date")

    print(f"Filtered down to {len(filtered)} rows matching criteria.")

    filtered.to_excel(OUTPUT_FILE, index=False)
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()