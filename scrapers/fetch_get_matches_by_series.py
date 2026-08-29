"""
Fetches getMatches responses by iterating seriesId from 1 to SERIES_ID_END,
saving each series' batch to responses_matches/matches_series{seriesId}.json.

Resume logic (series-level, using the real API signal):
  - Before touching getMatches, we check getSeriesDetails for every already
    -saved series. That endpoint returns an explicit `data.status` field:
    "COMPLETED" or "ONGOING" (there may be other values too - anything not
    recognized as completed is treated as still-open, to be safe).
  - A saved series whose status is "COMPLETED" is skipped - no getMatches
    call, since no new matches are expected.
  - A saved series whose status is anything else (e.g. "ONGOING", or an
    unrecognized value) is RE-fetched via getMatches, since more matches
    may have been added since we last saved it.
  - A series with no file yet is fetched fresh via getMatches (no need to
    check getSeriesDetails first for these - we don't have anything to
    decide about).

This checking step costs one lightweight getSeriesDetails call per already
-saved series (cheap payload), which is far less wasteful than blindly
re-pulling every series' full getMatches payload "just in case."

getMatches doesn't support matchId filtering or an offset param, so paging
by seriesId is the way to get full historical coverage instead of just
"most recent N".

Usage:
    python fetch_get_matches_by_series.py
    python fetch_get_matches_by_series.py --inspect-status
        # prints the getSeriesDetails status for every already-saved
        # series, without fetching any getMatches data. Useful for a
        # dry-run / sanity check before doing a real run.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import requests

MATCHES_URL = "https://core-prod-origin.cricclubs.com/core/match/getMatches"
SERIES_DETAILS_URL = "https://core-prod-origin.cricclubs.com/core/series/getSeriesDetails"

CLUB_ID = "7605"
X_API_KEY = "Tan@!75za"          # <-- same key as your scorecard fetcher
X_CONSUMER_KEY = "Tan#$72za5"    # <-- same key as your scorecard fetcher

OUT_DIR = "responses_matches"

SERIES_ID_START = 1
SERIES_ID_END = 400  # inclusive

LIMIT = 500  # per-series match cap; a series is unlikely to have more than this

DELAY_BETWEEN_REQUESTS_SECONDS = 1

HEADERS = {
    "x-api-key": X_API_KEY,
    "x-consumer-key": X_CONSUMER_KEY,
}

# Confirmed via getSeriesDetails: data.status == "COMPLETED" for finished
# series, "ONGOING" for active ones. Anything not in this "closed" set is
# treated as still-open (conservative default: re-fetch rather than miss
# new matches) - UNLESS the age override below kicks in.
CLOSED_STATUS_VALUES = {"COMPLETED"}

# Fallback override: if a series isn't marked "COMPLETED" but its
# startDate/endDate (whichever is more recent / present) is older than this,
# treat it as closed anyway. Catches stale "ONGOING" data-entry (e.g. a
# series someone forgot to mark finished) without relying on status alone.
STALE_SERIES_AGE = timedelta(days=365)

DATE_FORMATS = ["%m/%d/%Y", "%Y-%m-%d"]


def parse_series_date(value):
    """Best-effort parse of startDate/endDate strings like '10/21/2018'."""
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def series_is_stale_by_date(details_data):
    """
    Returns True if the series' most relevant date (endDate if present,
    else startDate) is older than STALE_SERIES_AGE. Returns False if no
    usable date is found (so the status field remains the deciding factor).
    """
    end_date = parse_series_date(details_data.get("endDate"))
    start_date = parse_series_date(details_data.get("startDate"))
    reference_date = end_date or start_date
    if reference_date is None:
        return False
    return (datetime.now() - reference_date) > STALE_SERIES_AGE

os.makedirs(OUT_DIR, exist_ok=True)

FILENAME_RE = re.compile(r"^matches_series(\d+)\.json$")


def get_saved_series_ids():
    """Return the sorted set of seriesIds we already have a matches file for."""
    ids = set()
    for fname in os.listdir(OUT_DIR):
        m = FILENAME_RE.match(fname)
        if m:
            ids.add(int(m.group(1)))
    return ids


def fetch_series_details(series_id):
    """
    Calls getSeriesDetails for a series and returns the `data` dict (which
    includes "status", "startDate", "endDate", etc.), or None if the call
    failed / response malformed (treated as "unknown -> re-fetch to be
    safe" by the caller).
    """
    params = {
        "clubId": CLUB_ID,
        "seriesId": str(series_id),
        "X-Auth-Token": "",  # required empty param, confirmed via testing
    }
    try:
        r = requests.get(SERIES_DETAILS_URL, params=params, headers=HEADERS, timeout=10)
    except requests.RequestException as e:
        print(f"[series {series_id}] getSeriesDetails request error: {e}")
        return None

    if r.status_code != 200:
        print(f"[series {series_id}] getSeriesDetails status={r.status_code}")
        return None

    try:
        data = r.json()
    except ValueError:
        print(f"[series {series_id}] getSeriesDetails returned non-JSON")
        return None

    if data.get("responseState") is False or data.get("errorMessage"):
        print(f"[series {series_id}] getSeriesDetails error: {data.get('errorMessage')}")
        return None

    return data.get("data", {})


def classify_saved_series(saved_ids):
    """
    For every already-saved series, check getSeriesDetails and classify as
    "closed" (skip, no getMatches call) or "open" (re-fetch via getMatches).

    Decision order:
      1. status == "COMPLETED" -> closed.
      2. Otherwise, if the series' start/end date is older than
         STALE_SERIES_AGE -> closed anyway (catches stale "ONGOING" entries
         that were probably just never marked finished).
      3. Otherwise -> open (status is "ONGOING"/unknown and it's recent).
      4. If the details call itself failed (details is None) -> open, to
         be safe (we can't confirm it's closed, so don't risk skipping it).

    Returns dict {series_id: "closed"|"open"}.
    """
    result = {}
    for series_id in sorted(saved_ids):
        details = fetch_series_details(series_id)

        if details is None:
            result[series_id] = "open"
            print(f"[series {series_id}] details unavailable -> will re-fetch matches")
            time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)
            continue

        status = details.get("status")

        if status in CLOSED_STATUS_VALUES:
            result[series_id] = "closed"
        elif series_is_stale_by_date(details):
            result[series_id] = "closed"
            print(f"[series {series_id}] status={status!r} but dates are >1yr old "
                  f"(start={details.get('startDate')!r}, end={details.get('endDate')!r}) "
                  f"-> treating as closed anyway")
        else:
            result[series_id] = "open"
            print(f"[series {series_id}] status={status!r} -> will re-fetch matches")

        time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)
    return result


def inspect_status():
    """Dry-run: print getSeriesDetails status for every saved series, no getMatches calls."""
    saved_ids = get_saved_series_ids()
    if not saved_ids:
        print("No saved series files found.")
        return
    print(f"Checking getSeriesDetails status for {len(saved_ids)} saved series...")
    classification = classify_saved_series(saved_ids)
    closed = [sid for sid, s in classification.items() if s == "closed"]
    open_ = [sid for sid, s in classification.items() if s == "open"]
    print("---")
    print(f"Closed (would skip): {len(closed)}")
    print(f"Open/unknown (would re-fetch): {len(open_)}")
    if open_:
        print(f"Open/unknown series IDs: {sorted(open_)}")


def fetch_matches(series_id):
    params = {
        "clubId": CLUB_ID,
        "seriesId": str(series_id),
        "limit": LIMIT,
    }
    r = requests.get(MATCHES_URL, params=params, headers=HEADERS, timeout=10)
    return r


def main():
    if "--inspect-status" in sys.argv:
        inspect_status()
        return

    saved_ids = get_saved_series_ids()

    if saved_ids:
        print(f"Found {len(saved_ids)} existing series files. "
              f"Checking getSeriesDetails to see which need re-fetching...")
        scraped_status = classify_saved_series(saved_ids)
        closed_count = sum(1 for v in scraped_status.values() if v == "closed")
        open_count = sum(1 for v in scraped_status.values() if v == "open")
        print(f"-> {closed_count} closed (will skip), {open_count} open/unknown (will re-fetch).")
    else:
        print("No existing series files found. Starting fresh.")
        scraped_status = {}

    fetched = 0
    skipped = 0
    refetched = 0
    empty = []
    failed = []

    for series_id in range(SERIES_ID_START, SERIES_ID_END + 1):
        status = scraped_status.get(series_id)  # "closed" | "open" | None (never saved)

        if status == "closed":
            skipped += 1
            continue

        is_refetch = status == "open"

        try:
            r = fetch_matches(series_id)
        except requests.RequestException as e:
            print(f"[series {series_id}] request error: {e}")
            failed.append(series_id)
            continue

        if r.status_code != 200:
            print(f"[series {series_id}] status={r.status_code} (skipping, not saved)")
            failed.append(series_id)
            continue

        data = r.json()

        if data.get("responseState") is False or data.get("errorMessage"):
            print(f"[series {series_id}] error: {data.get('errorMessage')}")
            failed.append(series_id)
            continue

        matches = data.get("data", [])
        if not matches:
            # Not necessarily a problem - series IDs may not be contiguous
            # or some may belong to other clubs. Track it but don't treat
            # as a failure.
            empty.append(series_id)
            print(f"[series {series_id}] 0 matches")
            time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)
            continue

        out_path = f"{OUT_DIR}/matches_series{series_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        fetched += 1
        if is_refetch:
            refetched += 1
            print(f"[series {series_id}] RE-fetched (was open/ongoing), saved {len(matches)} matches")
        else:
            print(f"[series {series_id}] saved {len(matches)} matches ({fetched} series fetched so far)")

        if len(matches) == LIMIT:
            print(
                f"  WARNING: series {series_id} returned exactly LIMIT "
                f"({LIMIT}) matches - this series may have more than we "
                f"captured. Consider raising LIMIT if this happens often."
            )

        time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    print("---")
    print(f"Fetched: {fetched} (of which re-fetched open series: {refetched}), "
          f"skipped (closed): {skipped}, empty: {len(empty)}, failed: {len(failed)}")
    if empty:
        print(f"Empty series IDs: {empty}")
    if failed:
        print(f"Failed series IDs: {failed}")


if __name__ == "__main__":
    main()