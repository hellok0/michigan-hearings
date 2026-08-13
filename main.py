import json
import logging
import os
import time
from datetime import date, timedelta

import downloader
from mi_scrapers.house_scraper import fetch_page, extract_committees, VIDEO_ARCHIVE_URL
from mi_scrapers import senate_scraper
from speakers.legislators import parse_hearing_filename
from speakers.pipeline import identify_speakers
from storage import create_table, is_new, add_meeting, save_identification
from transcriber import transcribe
from retry import with_retry

logger = logging.getLogger(__name__)

# use absolute paths, cwd isn't guaranteed to be the repo root (cron etc)
TRANSCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcripts")
LOOKBACK_DAYS = 60

DOWNLOADERS = {
    'house': (downloader.build_dest_path, downloader.download_video),
    'senate': (senate_scraper.build_dest_path, senate_scraper.download_video),
}

# lockfile so two overlapping cron runs don't both grab the same "new" hearing
_LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pipeline.lock")
LOCK_STALE_SECONDS = 3 * 60 * 60  # reclaim if a previous run crashed and left this behind


def _acquire_lock() -> bool:
    try:
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        age = time.time() - os.path.getmtime(_LOCK_PATH)
        if age > LOCK_STALE_SECONDS:
            logger.warning(f"Lock is {age / 60:.0f} min old - treating as abandoned by a crashed run, reclaiming it.")
            os.remove(_LOCK_PATH)
            return _acquire_lock()
        logger.warning("Another run is already in progress, skipping this invocation.")
        return False


def _release_lock() -> None:
    try:
        os.remove(_LOCK_PATH)
    except FileNotFoundError:
        pass


def save_transcript(dest_path, transcript) -> None:
    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(dest_path))[0]

    with open(os.path.join(TRANSCRIPT_DIR, stem + ".json"), "w") as f:
        json.dump(transcript, f, indent=2)

    text = transcript["results"]["channels"][0]["alternatives"][0]["transcript"]
    with open(os.path.join(TRANSCRIPT_DIR, stem + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)


def process_hearing(hearing) -> None:
    logger.info(f"Processing: {hearing['committee']} - {hearing['meeting_date']}")

    build_dest_path, download_video = DOWNLOADERS[hearing['source']]
    dest_path = build_dest_path(hearing['url'])
    stem = os.path.splitext(os.path.basename(dest_path))[0]
    transcript_path = os.path.join(TRANSCRIPT_DIR, stem + ".json")

    # a prior run may have downloaded+transcribed this one and then died
    # before add_meeting() (crash, killed process, etc) - is_new() would
    # still call it new, so resume from the transcript instead of paying
    # for another multi-GB download + Deepgram pass.
    if os.path.exists(transcript_path):
        logger.info(f"Transcript already on disk for {stem}, resuming from it instead of re-downloading/re-transcribing.")
        with open(transcript_path, encoding="utf-8") as f:
            transcript = json.load(f)
    else:
        with_retry(download_video, hearing['url'], dest_path)
        transcript = with_retry(transcribe, dest_path)
        save_transcript(dest_path, transcript)

    try:
        committee_code = hearing.get('committee_code') or parse_hearing_filename(stem)[0]
        result = identify_speakers(transcript, committee_code)
        counts = save_identification(
            result, hearing['url'], hearing['committee'], hearing['meeting_date'].isoformat())
        logger.info(f"Speaker ID: {counts['mentions']} mentions, {counts['testimony']} testimony rows")
    except Exception:
        logger.exception(f"Speaker identification failed for {hearing['url']}, continuing.")

    add_meeting(hearing['committee'], hearing['meeting_date'].isoformat(), hearing['url'])
    os.remove(dest_path)
    logger.info(f"Done: {hearing['url']}")


def fetch_all_hearings(cutoff) -> list:
    page = with_retry(fetch_page, VIDEO_ARCHIVE_URL)
    house_hearings = extract_committees(page)
    for hearing in house_hearings:
        hearing['source'] = 'house'

    senate_hearings = with_retry(senate_scraper.extract_hearings, cutoff)
    for hearing in senate_hearings:
        hearing['source'] = 'senate'

    return house_hearings + senate_hearings


def main() -> int:
    """Exit code 0 if every new hearing processed ok, 1 if any failed."""
    create_table()

    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    hearings = fetch_all_hearings(cutoff)

    new_hearings = [
        h for h in hearings
        if is_new(h['url']) and h['meeting_date'] >= cutoff
    ]
    logger.info(
        f"Found {len(hearings)} hearings across House and Senate, "
        f"{len(new_hearings)} are new and within the last {LOOKBACK_DAYS} days."
    )

    failures = 0
    for hearing in new_hearings:
        try:
            process_hearing(hearing)
        except Exception:
            logger.exception(f"Giving up on {hearing['url']} after retries, moving to next hearing.")
            failures += 1

    succeeded = len(new_hearings) - failures
    if failures:
        logger.warning(f"Run complete: {succeeded}/{len(new_hearings)} hearings succeeded, {failures} failed.")
    else:
        logger.info(f"Run complete: {succeeded}/{len(new_hearings)} hearings succeeded.")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    if not _acquire_lock():
        sys.exit(0)  # another run already has it - not a failure, just a skip
    try:
        sys.exit(main())
    finally:
        _release_lock()
