# Bootstraps Senate entries in data/committee_rosters.json, same idea as
# build_committee_rosters.py but for House. Senate filenames are opaque
# Castus ids with no embedded committee code, so this re-fetches the live
# Castus hearing list to get each video id's stable 'parent' folder id, then
# matches that against whatever video ids already have a transcript on disk.
#
# One-time/occasional build step - run it, skim the output, commit. Merges
# into the existing rosters file rather than overwriting it.
#
# usage: python build_senate_committee_rosters.py
import glob
import json
import logging
import os
from collections import Counter, defaultdict
from datetime import date, timedelta

from mi_scrapers import senate_scraper
from speakers.legislators import extract_roll_call_candidates, load_rosters, parse_hearing_filename
from speakers.transcript import turns_from_deepgram

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TRANSCRIPT_DIR = "transcripts"
OUT_PATH = os.path.join("data", "committee_rosters.json")
# main.py's LOOKBACK_DAYS=60 only needs new hearings; this needs to reach
# back far enough to cover whatever old Senate transcripts are on disk
LOOKBACK_DAYS = 365


def main():
    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    video_codes = senate_scraper.fetch_video_committee_codes(cutoff)
    logger.info(f"fetched {len(video_codes)} Senate hearing(s) from Castus (last {LOOKBACK_DAYS} days)")

    hearings_seen = defaultdict(int)
    chair_votes = defaultdict(Counter)
    member_counts = defaultdict(Counter)

    for path in sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.json"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        if parse_hearing_filename(stem)[0] is not None:
            continue  # House-style filename, not a Senate video id

        code = video_codes.get(stem)
        if not code:
            logger.info(f"{stem}: not in the current {LOOKBACK_DAYS}-day Castus listing, skipping")
            continue

        with open(path, encoding="utf-8") as f:
            transcript = json.load(f)
        candidates = extract_roll_call_candidates(turns_from_deepgram(transcript))
        if not candidates:
            logger.warning(f"{stem}: no roll call found, skipping")
            continue

        hearings_seen[code] += 1
        chair_votes[code][candidates[0]] += 1
        for name in candidates[1:]:
            member_counts[code][name] += 1

    rosters = load_rosters()
    for code in sorted(hearings_seen):
        chair = chair_votes[code].most_common(1)[0][0] if chair_votes[code] else None
        members = [name for name, _ in member_counts[code].most_common() if name != chair]
        roster = ([{"name": chair, "role": "chair"}] if chair else []) + \
                 [{"name": name, "role": "member"} for name in members]
        rosters[code] = roster
        logger.info(f"{code}: chair={chair}, {len(members)} member(s) from {hearings_seen[code]} hearing(s)")

    os.makedirs("data", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rosters, f, indent=2)
    logger.info(f"wrote {len(rosters)} total committee roster(s) ({len(hearings_seen)} Senate) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
