import random
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from social_auth import get_youtube_credentials


VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".avi"}
THUMBNAIL_EXTS = {".jpg", ".jpeg", ".png"}


def delete_youtube_video(video_id, user_key=None):
    if not video_id:
        raise ValueError("Video ID tidak valid")
    youtube = build("youtube", "v3", credentials=get_youtube_credentials(user_key))
    youtube.videos().delete(id=video_id).execute()
    return {"video_id": video_id}


def list_existing_youtube_videos(video_ids, user_key=None):
    ids = [video_id for video_id in video_ids if video_id]
    if not ids:
        return []
    youtube = build("youtube", "v3", credentials=get_youtube_credentials(user_key))
    response = youtube.videos().list(part="id", id=",".join(ids)).execute()
    return [item["id"] for item in response.get("items", [])]


def upload_youtube_video(file_path, title, description="", privacy="private", user_key=None, thumbnail_path=None):
    path = Path(file_path).resolve()
    if not path.exists() or path.suffix.lower() not in VIDEO_EXTS:
        raise ValueError("File video tidak valid")
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Privacy tidak valid")

    youtube = build("youtube", "v3", credentials=get_youtube_credentials(user_key))
    media = MediaFileUpload(str(path), chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": (title or path.stem)[:100],
                "description": description or "",
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=media,
    )

    response = None
    failures = 0
    while response is None:
        try:
            _, response = request.next_chunk(num_retries=1)
            failures = 0
        except (HttpError, OSError) as exc:
            retryable = not isinstance(exc, HttpError) or exc.resp.status in {408, 429, 500, 502, 503, 504}
            if not retryable or failures >= 4:
                raise
            time.sleep(min(30, 2 ** failures) + random.random())
            failures += 1

    video_id = response["id"]
    thumbnail = Path(thumbnail_path).resolve() if thumbnail_path else None
    thumbnail_set = False
    thumbnail_error = ""
    if thumbnail and thumbnail.is_file() and thumbnail.suffix.lower() in THUMBNAIL_EXTS:
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail), resumable=False),
            ).execute()
            thumbnail_set = True
        except (HttpError, OSError) as exc:
            # Video sudah berhasil diunggah; jangan memicu retry yang membuat duplikat.
            thumbnail_error = f"Thumbnail YouTube gagal dipasang ({type(exc).__name__})"
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail_set": thumbnail_set,
        "thumbnail_error": thumbnail_error,
    }
