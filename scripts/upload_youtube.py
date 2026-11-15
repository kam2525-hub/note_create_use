#!/usr/bin/env python3
"""
Upload a Shorts MP4 to YouTube Studio as PRIVATE (draft) via YouTube Data API v3,
so the creator only needs to review and click Publish in YouTube Studio.

Setup:
  pip install google-api-python-client google-auth-oauthlib
  Place OAuth Desktop App credentials at scripts/client_secret.json
Usage:
  python3 scripts/upload_youtube.py \
    --video shorts/day01/output/day01_short.mp4 \
    --title "99%が3回目でミスる鬼ゲー作ったｗ【無料ブラウザゲーム】 #Shorts" \
    --description-file notes/day01/youtube_metadata.txt
"""

import argparse
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SCRIPT_DIR = Path(__file__).resolve().parent
CLIENT_SECRET = SCRIPT_DIR / "client_secret.json"
TOKEN_FILE = SCRIPT_DIR / "youtube_token.json"


def get_youtube_service():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                raise FileNotFoundError(
                    f"Missing {CLIENT_SECRET}. Download OAuth Desktop credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def main():
    parser = argparse.ArgumentParser(description="Upload Short as Private Draft to YouTube Studio")
    parser.add_argument("--video", required=True, help="Path to MP4 file")
    parser.add_argument("--title", required=True, help="Video title (<= 100 chars)")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--description-file", help="Path to text file for description")
    parser.add_argument("--tags", default="Shorts,ミニゲーム,ブラウザゲーム,個人開発", help="Comma-separated tags")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    args = parser.parse_args()

    desc = args.description
    if args.description_file:
        desc = Path(args.description_file).read_text(encoding="utf-8")

    youtube = get_youtube_service()
    body = {
        "snippet": {
            "title": args.title[:100],
            "description": desc,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
            "categoryId": "20",  # Gaming
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(args.video, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    vid = response["id"]
    print(f"Uploaded as '{args.privacy}': https://studio.youtube.com/video/{vid}/edit")


if __name__ == "__main__":
    main()
