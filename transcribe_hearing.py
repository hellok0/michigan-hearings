# Download (if needed) + transcribe a single hearing, skipping speaker ID
# and the db write. Writes the same transcripts/<stem>.json + .txt the full
# pipeline would.
#
# usage: python transcribe_hearing.py <house|senate> <url> [dest_path]
#        python transcribe_hearing.py --file <path_to_already_downloaded_mp4>
import os
import sys

from main import DOWNLOADERS, save_transcript
from retry import with_retry
from transcriber import transcribe


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    if sys.argv[1] == "--file":
        if len(sys.argv) < 3:
            print(__doc__)
            return 1
        dest_path = sys.argv[2]
    else:
        if len(sys.argv) < 3:
            print(__doc__)
            return 1
        source, url = sys.argv[1], sys.argv[2]
        if source not in DOWNLOADERS:
            print(f"unknown source {source!r}, expected one of: {', '.join(DOWNLOADERS)}")
            return 1
        build_dest_path, download_video = DOWNLOADERS[source]
        dest_path = sys.argv[3] if len(sys.argv) > 3 else build_dest_path(url)
        print(f"downloading -> {dest_path}")
        with_retry(download_video, url, dest_path)

    print(f"transcribing {dest_path} ...")
    transcript = with_retry(transcribe, dest_path)
    save_transcript(dest_path, transcript)

    stem = os.path.splitext(os.path.basename(dest_path))[0]
    print(f"transcript saved -> transcripts/{stem}.json, transcripts/{stem}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
