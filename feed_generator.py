from datetime import datetime, timezone
from feedgen.feed import FeedGenerator
from config import BASE_URL, AUDIO_FORMAT
from downloader import get_audio_file_size


def generate_feed(channel: dict, episodes: list) -> str:
    """
    Generate a podcast RSS 2.0 feed with iTunes extensions.

    Args:
        channel: Channel dict with id, name, youtube_channel_id, url, auth_type, secret_token
        episodes: List of episode dicts

    Returns:
        RSS XML string
    """
    fg = FeedGenerator()
    fg.load_extension('podcast')

    # Determine feed URL based on auth type
    auth_type = channel.get('auth_type', 'none')
    if auth_type == 'token' and channel.get('secret_token'):
        feed_url = f"{BASE_URL}/feed/t/{channel['secret_token']}"
    else:
        feed_url = f"{BASE_URL}/feed/{channel['id']}"

    # Channel metadata
    fg.title(channel['name'])
    fg.description(f"Podcast feed for YouTube channel: {channel['name']}")
    fg.link(href=channel['url'], rel='alternate')
    fg.link(href=feed_url, rel='self')
    fg.language('en')
    fg.generator('YouTube Podcast Generator')

    # iTunes/Podcast specific
    fg.podcast.itunes_author(channel['name'])
    fg.podcast.itunes_category('Technology')
    fg.podcast.itunes_explicit('no')
    fg.podcast.itunes_owner(name=channel['name'], email='noreply@example.com')
    fg.podcast.itunes_summary(f"Audio from YouTube channel: {channel['name']}")

    # Add episodes
    for ep in episodes:
        if not ep.get('audio_path'):
            continue

        fe = fg.add_entry()
        fe.id(ep['video_id'])
        fe.title(ep['title'])

        # Description
        description = ep.get('description') or ''
        fe.description(description[:4000] if description else ep['title'])

        # Link to original video
        fe.link(href=f"https://www.youtube.com/watch?v={ep['video_id']}")

        # Publication date
        if ep.get('published_at'):
            pub_date = ep['published_at']
            if isinstance(pub_date, str):
                pub_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            fe.published(pub_date)

        # Audio enclosure - use token URL if token auth is enabled
        if auth_type == 'token' and channel.get('secret_token'):
            audio_url = f"{BASE_URL}/audio/t/{channel['secret_token']}/{ep['audio_path']}"
        else:
            audio_url = f"{BASE_URL}/audio/{ep['audio_path']}"
        file_size = get_audio_file_size(ep['audio_path'])
        mime_type = f"audio/{AUDIO_FORMAT}"

        fe.enclosure(audio_url, str(file_size), mime_type)

        # iTunes specific
        fe.podcast.itunes_duration(ep.get('duration', 0))
        if ep.get('thumbnail_url'):
            fe.podcast.itunes_image(ep['thumbnail_url'])

    return fg.rss_str(pretty=True).decode('utf-8')
