#!/usr/bin/env python3
"""
Upload a Shorts MP4 to YouTube Studio as PRIVATE (draft) via YouTube Data API v3,
so the creator only needs to review and click Publish in YouTube Studio.

Supports BOTH:
  1. GitHub Actions / headless env vars:
     YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN
  2. Local PC OAuth flow:
     scripts/client_secret.json -> scripts/youtube_token.json
"""

import argparse
import os
import re
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
    cid = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    rtok = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

    if cid and csec and rtok:
        creds = Credentials(
            token=None,
            refresh_token=rtok,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=cid,
            client_secret=csec,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return build("youtube", "v3", credentials=creds)

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                raise FileNotFoundError(
                    "Set YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN env vars "
                    f"or place OAuth Desktop credentials at {CLIENT_SECRET}."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def parse_metadata_file(path: Path):
    text = path.read_text(encoding="utf-8")
    sections = {}
    current = None
    lines = []
    for line in text.splitlines():
        m = re.match(r"^\[(.+)\]$", line.strip())
        if m:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = m.group(1)
            lines = []
        else:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()

    title = sections.get("YouTube Shorts タイトル", "").splitlines()[0].strip() if "YouTube Shorts タイトル" in sections else ""
    desc = sections.get("YouTube Shorts 説明文", "")
    tags_raw = sections.get("タグ（カンマ区切り）", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    return title, desc, tags


def main():
    parser = argparse.ArgumentParser(description="Upload Short as Private Draft to YouTube Studio")
    parser.add_argument("--video", required=True, help="Path to MP4 file")
    parser.add_argument("--metadata-file", help="Path to youtube_metadata.txt")
    parser.add_argument("--title", default="", help="Video title (<= 100 chars)")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--description-file", help="Path to text file for description")
    parser.add_argument("--tags", default="Shorts,ミニゲーム,ブラウザゲーム,個人開発", help="Comma-separated tags")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    args = parser.parse_args()

    title = args.title
    desc = args.description
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    if args.metadata_file:
        m_title, m_desc, m_tags = parse_metadata_file(Path(args.metadata_file))
        if not title and m_title:
            title = m_title
        if not desc and m_desc:
            desc = m_desc
        if m_tags:
            tags = m_tags

    if args.description_file:
        desc = Path(args.description_file).read_text(encoding="utf-8")

    if not title:
        raise ValueError("Video title is required via --title or --metadata-file")

    youtube = get_youtube_service()
    body = {
        "snippet": {
            "title": title[:100],
            "description": desc,
            "tags": tags,
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
