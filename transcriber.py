import os
import requests
from dotenv import load_dotenv

# explicit path - load_dotenv() searching from cwd fails silently under cron
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

DEEPGRAM_API_KEY = os.environ["DEEPGRAM_API_KEY"]
DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


def transcribe(file_path) -> dict:
    with open(file_path, "rb") as f:
        response = requests.post(
            DEEPGRAM_URL,
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "video/mp4",
            },
            params={
                "model": "nova-2",
                "diarize": "true",
                "smart_format": "true",
            },
            data=f,
        )
    response.raise_for_status()
    return response.json()
