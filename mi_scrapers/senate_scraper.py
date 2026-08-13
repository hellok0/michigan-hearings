import os
import re
import subprocess
from datetime import date, datetime
from urllib.parse import urlparse

import requests

# Senate video lives on Castus (cloud.castus.tv/vod/misenate), a JS SPA with
# no server-rendered page to scrape - this is the JSON API its frontend calls
# to list videos for the "misenate" station. Undocumented but this is the
# real data source.
API_URL = "https://tf4pr3wftk.execute-api.us-west-2.amazonaws.com/default/api/all"
STATION_ID = "61b3adc8124d7d000891ca5c"
DOWNLOAD_URL_TEMPLATE = "https://dlttx48mxf9m3.cloudfront.net/outputs/{video_id}/Default/HLS/out.m3u8"
RESULTS_PER_PAGE = 20
# repo root, so this lands in the same downloads/ folder downloader.py uses
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "downloads")

# metadata.filename is like "Labor 26-06-18" - committee name + YY-MM-DD date
_TRAILING_DATE_RE = re.compile(r"\s+\d{2}-\d{2}-\d{2}$")


def parse_date(raw_date) -> date:
    return datetime.fromisoformat(raw_date.replace('Z', '+00:00')).date()


def fetch_hearings_page(page_num) -> dict:
    response = requests.post(
        API_URL,
        json={'_id': STATION_ID, 'page': page_num, 'results': RESULTS_PER_PAGE},
    )
    response.raise_for_status()
    return response.json()


def _committee_name(file) -> str:
    meta = file.get('metadata') or {}
    label = meta.get('filename') or os.path.splitext(meta.get('original filename') or '')[0]
    return _TRAILING_DATE_RE.sub('', label).strip() or 'Senate'


def _is_floor_session(committee_name) -> bool:
    return committee_name.lower().startswith('senate session')


def extract_hearings(cutoff_date) -> list:
    """Committee hearings only - skips full floor "Senate Session" recordings,
    no testimony in those and no point transcribing them."""
    all_hearings = []
    page_num = 1

    while True:
        data = fetch_hearings_page(page_num)
        files = data.get('allFiles', [])
        if not files:
            break

        for file in files:
            hearing_date = parse_date(file['date'])

            # newest-first, so once we're past the cutoff we can stop
            if hearing_date < cutoff_date:
                return all_hearings

            committee = _committee_name(file)
            if _is_floor_session(committee):
                continue

            all_hearings.append({
                'committee': committee,
                # Castus' stable folder id - used to key committee rosters
                # instead of `committee`, which varies in spelling/punctuation
                'committee_code': file.get('parent'),
                'meeting_date': hearing_date,
                'url': DOWNLOAD_URL_TEMPLATE.format(video_id=file['_id']),
            })

        page_num += 1

    return all_hearings


def fetch_video_committee_codes(cutoff) -> dict:
    """{video_id: committee_code} for every Senate hearing Castus lists back
    to cutoff. Includes floor sessions too (unlike extract_hearings) since a
    transcript might predate that filter - harmless, they have no roll call
    anyway."""
    codes = {}
    page_num = 1
    while True:
        data = fetch_hearings_page(page_num)
        files = data.get('allFiles', [])
        if not files:
            break
        stop = False
        for file in files:
            if parse_date(file['date']) < cutoff:
                stop = True
                break
            codes[file['_id']] = file.get('parent')
        if stop:
            break
        page_num += 1
    return codes


def build_dest_path(url) -> str:
    parts = urlparse(url).path.split('/')
    video_id = parts[parts.index('outputs') + 1]
    return os.path.join(DOWNLOAD_DIR, video_id + '.mp4')


def download_video(url, dest_path) -> None:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    temp_path = dest_path + ".part"

    # Senate video is an HLS stream (.m3u8), so ffmpeg pulls + muxes it into
    # one mp4. -f mp4 is explicit since ffmpeg can't guess format from ".part"
    subprocess.run(
        ['ffmpeg', '-y', '-i', url, '-c', 'copy', '-f', 'mp4', temp_path],
        check=True,
        capture_output=True,
    )

    os.replace(temp_path, dest_path)
