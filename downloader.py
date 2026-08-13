import os
import requests
from urllib.parse import urlparse

from tls_bundle import house_mi_gov_ca_bundle

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")


def build_dest_path(url) -> str:
    filename = os.path.basename(urlparse(url).path)
    return os.path.join(DOWNLOAD_DIR, filename)


def download_video(url, dest_path) -> None:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    temp_path = dest_path + ".part"

    response = requests.get(url, stream=True, verify=house_mi_gov_ca_bundle())
    response.raise_for_status()

    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    os.replace(temp_path, dest_path)
