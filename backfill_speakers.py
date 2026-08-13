# Backfill speaker identification over transcripts already on disk. Walks
# transcripts/*.json, derives committee code + date from the filename (House
# encodes this, Senate ids don't - those get no roster and skip legislator
# name-spotting), writes rows into the same _hearings.db_ the live pipeline uses.
#
# usage: python backfill_speakers.py
import glob
import json
import logging
import os
from datetime import date, timedelta

from mi_scrapers import senate_scraper
from speakers.legislators import parse_hearing_filename
from speakers.pipeline import identify_speakers
from storage import save_identification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TRANSCRIPT_DIR = "transcripts"
# same reach-back as build_senate_committee_rosters.py, for the same reason
SENATE_LOOKBACK_DAYS = 365


def main():
    paths = sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.json")))
    logger.info(f"Found {len(paths)} transcripts to process.")

    senate_codes = None  # fetched lazily, only if a Senate-style stem shows up

    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        committee_code, hearing_date = parse_hearing_filename(stem)
        if committee_code is None:
            if senate_codes is None:
                cutoff = date.today() - timedelta(days=SENATE_LOOKBACK_DAYS)
                senate_codes = senate_scraper.fetch_video_committee_codes(cutoff)
            committee_code = senate_codes.get(stem)
        hearing_id = stem

        try:
            with open(path, encoding="utf-8") as f:
                transcript = json.load(f)
            result = identify_speakers(transcript, committee_code)
            counts = save_identification(
                result, hearing_id, committee=committee_code,
                hearing_date=hearing_date.isoformat() if hearing_date else None,
            )
            logger.info(f"{stem}: {counts['mentions']} mentions, {counts['testimony']} testimony rows")
        except Exception:
            logger.exception(f"Failed on {stem}, continuing.")


if __name__ == "__main__":
    main()
