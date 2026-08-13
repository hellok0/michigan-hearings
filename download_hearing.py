# Download one hearing's video without running the rest of the pipeline
# (no transcription, no speaker ID, no db write).
# usage: python download_hearing.py <house|senate> <url> [dest_path]
import sys

from main import DOWNLOADERS


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    source, url = sys.argv[1], sys.argv[2]
    if source not in DOWNLOADERS:
        print(f"unknown source {source!r}, expected one of: {', '.join(DOWNLOADERS)}")
        return 1

    build_dest_path, download_video = DOWNLOADERS[source]
    dest_path = sys.argv[3] if len(sys.argv) > 3 else build_dest_path(url)

    download_video(url, dest_path)
    print(f"downloaded -> {dest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
