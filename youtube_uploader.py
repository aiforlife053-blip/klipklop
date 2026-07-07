from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from social_auth import get_youtube_credentials


VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".avi"}


def delete_youtube_video(video_id):
    if not video_id:
        raise ValueError("Video ID tidak valid")
    youtube = build("youtube", "v3", credentials=get_youtube_credentials())
    youtube.videos().delete(id=video_id).execute()
    return {"video_id": video_id}


def list_existing_youtube_videos(video_ids):
    ids = [video_id for video_id in video_ids if video_id]
    if not ids:
        return []
    youtube = build("youtube", "v3", credentials=get_youtube_credentials())
    response = youtube.videos().list(part="id", id=",".join(ids)).execute()
    return [item["id"] for item in response.get("items", [])]


def upload_youtube_video(file_path, title, description="", privacy="private"):
    path = Path(file_path).resolve()
    if not path.exists() or path.suffix.lower() not in VIDEO_EXTS:
        raise ValueError("File video tidak valid")
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Privacy tidak valid")

    youtube = build("youtube", "v3", credentials=get_youtube_credentials())
    media = MediaFileUpload(str(path), chunksize=-1, resumable=True)
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
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    return {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}
