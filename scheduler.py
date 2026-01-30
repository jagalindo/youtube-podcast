import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import CHECK_INTERVAL_HOURS
from models import Channel, Episode
from downloader import fetch_channel_videos, get_video_metadata, download_audio

logger = logging.getLogger(__name__)


def refresh_channel(channel: dict):
    """
    Check a channel for new videos and download them.
    """
    logger.info(f"Refreshing channel: {channel['name']}")

    try:
        videos = fetch_channel_videos(channel['youtube_channel_id'])

        for video in videos:
            video_id = video['video_id']

            # Skip if already downloaded
            existing = Episode.get_by_video_id(video_id)
            if existing and existing.get('audio_path'):
                continue

            logger.info(f"Processing new video: {video['title']}")

            try:
                # Get full metadata
                metadata = get_video_metadata(video_id)

                # Download audio
                audio_filename, _ = download_audio(video_id)

                # Create or update episode
                if existing:
                    Episode.update_audio_path(existing['id'], audio_filename)
                else:
                    Episode.create(
                        channel_id=channel['id'],
                        video_id=video_id,
                        title=metadata['title'],
                        description=metadata.get('description'),
                        duration=metadata.get('duration'),
                        published_at=metadata.get('published_at'),
                        audio_path=audio_filename,
                        thumbnail_url=metadata.get('thumbnail_url')
                    )

                logger.info(f"Downloaded: {metadata['title']}")

            except Exception as e:
                logger.error(f"Failed to process video {video_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Failed to refresh channel {channel['name']}: {e}")


def refresh_all_channels():
    """
    Refresh all channels - called by scheduler.
    """
    logger.info("Starting scheduled refresh of all channels")
    channels = Channel.get_all()

    for channel in channels:
        refresh_channel(channel)

    logger.info("Finished scheduled refresh")


def create_scheduler() -> BackgroundScheduler:
    """
    Create and configure the background scheduler.
    """
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        func=refresh_all_channels,
        trigger=IntervalTrigger(hours=CHECK_INTERVAL_HOURS),
        id='refresh_channels',
        name='Refresh all YouTube channels',
        replace_existing=True
    )

    return scheduler
