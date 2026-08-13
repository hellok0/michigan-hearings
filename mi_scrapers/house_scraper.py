from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import requests
import urllib3

# house.mi.gov's server doesn't send its full cert chain (checked - it's a
# legit DigiCert leaf cert, just misconfigured). Public data, no creds, so
# verify=False is fine here.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VIDEO_ARCHIVE_URL = "https://house.mi.gov/VideoArchive"


def fetch_page(url):
    response = requests.get(url, verify=False)
    return BeautifulSoup(response.text, 'html.parser')


def parse_date(raw_text) -> datetime:
    date_part = raw_text.split(' - ')[0]
    return datetime.strptime(date_part, "%A, %B %d, %Y").date()


def extract_committees(page) -> list:

    all_hearings = []
    committees = page.find_all('li', class_='page-search-container')

    for committee in committees:
        raw_committee_name = committee.find('strong').get_text()
        parts = raw_committee_name.split('|')
        committee_name = parts[0].strip()

        print(committee_name)

        meetings = committee.find_all('div', class_='page-search-object')

        for meeting in meetings:

            href = meeting.find('a').get('href')
            filename = parse_qs(urlparse(href).query)['video'][0]

            all_hearings.append({
                'committee': committee_name,
                'meeting_date': parse_date(meeting.get_text(strip=True)),
                'url': 'https://www.house.mi.gov/ArchiveVideoFiles/' + filename
            })

    print(all_hearings)
    return all_hearings


def main():
    page = fetch_page(VIDEO_ARCHIVE_URL)
    extract_committees(page)

if __name__ == "__main__":
    main()