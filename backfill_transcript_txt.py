# Writes a plain-text .txt alongside each transcripts/*.json that's missing
# one - same format main.py writes for new transcripts (raw transcript
# string, no diarization/speaker labels).
#
# usage: python backfill_transcript_txt.py
import glob
import json
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TRANSCRIPT_DIR = "transcripts"


def main():
    written = skipped = failed = 0
    for json_path in sorted(glob.glob(os.path.join(TRANSCRIPT_DIR, "*.json"))):
        txt_path = os.path.splitext(json_path)[0] + ".txt"
        if os.path.exists(txt_path):
            skipped += 1
            continue
        try:
            with open(json_path, encoding="utf-8") as f:
                transcript = json.load(f)
            text = transcript["results"]["channels"][0]["alternatives"][0]["transcript"]
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            written += 1
        except (KeyError, IndexError, TypeError):
            logger.warning(f"{json_path}: no diarized transcript text found, skipping")
            failed += 1

    logger.info(f"wrote {written}, skipped {skipped} (already had .txt), failed {failed}")


if __name__ == "__main__":
    main()
