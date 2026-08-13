# Bootstraps data/committee_rosters.json from the roll call at the start of
# most House hearings in transcripts/. One-time/occasional build step, not
# part of the live pipeline - run it, skim the output for obviously-wrong
# names (STT mangles surnames inconsistently), then commit. Senate isn't
# covered here (no committee-level id in older transcripts); anything not
# matching '<CODE>-MMDDYY' gets skipped.
#
# usage: python build_committee_rosters.py
import glob
import json
import logging
import os
from collections import Counter, defaultdict

from speakers.legislators import extract_roll_call_candidates, parse_hearing_filename
from speakers.transcript import turns_from_deepgram

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TRANSCRIPT_DIR = "transcripts"
OUT_PATH = os.path.join("data", "committee_rosters.json")


def main():
    hearings_seen = defaultdict(int)
    chair_votes = defaultdict(Counter)
    member_counts = defaultdict(Counter)

    for path in sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.json"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        code, _ = parse_hearing_filename(stem)
        if not code:
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

    rosters = {}
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
    logger.info(f"wrote {len(rosters)} committee roster(s) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
