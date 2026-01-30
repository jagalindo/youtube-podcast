import os
import re
import yt_dlp
from datetime import datetime
from pathlib import Path
from config import AUDIO_DIR, AUDIO_FORMAT, AUDIO_BITRATE, INITIAL_FETCH_COUNT


def extract_channel_id(url_or_id: str) -> tuple[str, str]:
    """
    Extract channel ID and name from various YouTube URL formats.
    Returns (channel_id, channel_name).
    """
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'no_warnings': True,
    }

    # Normalize the input
    url = url_or_id.strip()

    # If it looks like just a channel ID
    if re.match(r'^UC[\w-]{22}$', url):
        url = f"https://www.youtube.com/channel/{url}"
    # If it's a handle without URL
    elif url.startswith('@'):
        url = f"https://www.youtube.com/{url}"
    # If it doesn't look like a URL, try as handle
    elif not url.startswith('http'):
        url = f"https://www.youtube.com/@{url}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        channel_id = info.get('channel_id') or info.get('id')
        channel_name = info.get('channel') or info.get('uploader') or info.get('title', 'Unknown Channel')
        return channel_id, channel_name


def fetch_channel_videos(channel_id: str, max_videos: int = INITIAL_FETCH_COUNT) -> list[dict]:
    """
    Fetch video list from a YouTube channel.
    Returns list of video metadata dicts.
    """
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'no_warnings': True,
        'playlistend': max_videos,
    }

    url = f"https://www.youtube.com/channel/{channel_id}/videos"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        videos = []
        entries = info.get('entries', [])

        for entry in entries[:max_videos]:
            if entry is None:
                continue
            videos.append({
                'video_id': entry.get('id'),
                'title': entry.get('title'),
                'url': entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}",
            })

        return videos


def get_video_metadata(video_id: str) -> dict:
    """
    Get detailed metadata for a video.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }

    url = f"https://www.youtube.com/watch?v={video_id}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        # Parse upload date
        upload_date = info.get('upload_date')
        published_at = None
        if upload_date:
            try:
                published_at = datetime.strptime(upload_date, '%Y%m%d')
            except ValueError:
                pass

        return {
            'video_id': video_id,
            'title': info.get('title', 'Untitled'),
            'description': info.get('description', ''),
            'duration': info.get('duration', 0),
            'published_at': published_at,
            'thumbnail_url': info.get('thumbnail'),
        }


def download_audio(video_id: str) -> tuple[str, int]:
    """
    Download video as audio file.
    Returns (audio_filename, file_size).
    """
    output_template = str(AUDIO_DIR / f"{video_id}.%(ext)s")
    final_path = AUDIO_DIR / f"{video_id}.{AUDIO_FORMAT}"

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': AUDIO_FORMAT,
            'preferredquality': AUDIO_BITRATE,
        }],
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }

    url = f"https://www.youtube.com/watch?v={video_id}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if final_path.exists():
        file_size = final_path.stat().st_size
        return f"{video_id}.{AUDIO_FORMAT}", file_size

    raise FileNotFoundError(f"Downloaded audio file not found: {final_path}")


def get_audio_file_size(filename: str) -> int:
    """Get the size of an audio file in bytes."""
    path = AUDIO_DIR / filename
    if path.exists():
        return path.stat().st_size
    return 0
