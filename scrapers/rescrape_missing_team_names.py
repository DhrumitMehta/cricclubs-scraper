"""
rescrape_missing_team_names.py
-------------------------------
Finds rows in tca_db_match_info where team names (points_team_1 / points_team_2)
are missing, then re-scrapes just those match IDs and upserts the corrected data.

This is meant to be run after the team-name fix in match_info_scraper.py
(team names now sourced from the match-summary block, so it should backfill
knockout/playoff games that previously had no team names).

Usage:
    python rescrape_missing_team_names.py                # find + rescrape all
    python rescrape_missing_team_names.py --dry-run       # just list affected match IDs
    python rescrape_missing_team_names.py --limit 50      # only process first 50
"""

import time
import logging
import argparse

from match_info_scraper import (
    supabase,
    create_driver,
    scrape_match_info,
    flush,
    MATCH_INFO_TABLE,
    CLUB_ID,
    CLUB_SLUG,
    SCRAPE_DELAY,
    CHECKPOINT_EVERY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def get_match_ids_missing_team_names() -> list[int]:
    """
    Return all match_ids where either team name is NULL, ordered ascending.
    Supabase's python client doesn't support OR filters directly, so we
    query each condition separately and merge the results.
    """
    ids: set[int] = set()

    for column in ("points_team_1", "points_team_2"):
        res = (
            supabase.table(MATCH_INFO_TABLE)
            .select("match_id")
            .is_(column, "null")
            .execute()
        )
        ids.update(row["match_id"] for row in res.data)

    sorted_ids = sorted(ids)
    log.info(f"Found {len(sorted_ids)} match(es) missing a team name.")
    return sorted_ids


def rescrape_match_ids(match_ids: list[int], delay: float = SCRAPE_DELAY) -> None:
    """Re-scrape a specific list of match IDs and upsert the results."""
    if not match_ids:
        log.info("Nothing to rescrape.")
        return

    driver = create_driver()
    buf: list[dict] = []
    success_ids, failed_ids, still_missing_ids = [], [], []

    try:
        log.info("Warming up session…")
        driver.get(f"https://www.cricclubs.com/{CLUB_SLUG}/home.do?clubId={CLUB_ID}")
        time.sleep(2)

        for match_id in match_ids:
            record = scrape_match_info(driver, match_id)
            time.sleep(delay)

            if record is None:
                failed_ids.append(match_id)
                continue

            success_ids.append(match_id)
            if not record.get("points_team_1") or not record.get("points_team_2"):
                still_missing_ids.append(match_id)

            buf.append(record)

            if len(success_ids) % CHECKPOINT_EVERY == 0:
                flush(buf, label=f"checkpoint matchId={match_id}")
                buf.clear()

    finally:
        driver.quit()

    if buf:
        flush(buf, label="final flush")

    log.info(f"\nRescraped: {len(success_ids)} succeeded | {len(failed_ids)} skipped/failed")
    if failed_ids:
        log.warning(f"Failed IDs (page didn't load / no info table): {failed_ids}")
    if still_missing_ids:
        log.warning(
            f"Still missing a team name after rescrape (source page likely "
            f"lacks a match-summary block): {still_missing_ids}"
        )
    log.info("Done ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Find and re-scrape matches with missing team names"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only list affected match IDs, don't scrape or write anything",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only process the first N affected match IDs",
    )
    parser.add_argument(
        "--delay", type=float, default=SCRAPE_DELAY,
        help="Seconds between requests",
    )
    args = parser.parse_args()

    ids = get_match_ids_missing_team_names()

    if args.limit:
        ids = ids[: args.limit]

    if args.dry_run:
        log.info(f"[DRY RUN] Match IDs missing team names ({len(ids)}): {ids}")
    else:
        rescrape_match_ids(ids, delay=args.delay)