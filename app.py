import os
import logging
from flask import Flask, request, jsonify, send_from_directory, Response
from config import HOST, PORT, AUDIO_DIR, BASE_URL
from models import init_db, Channel, Episode
from downloader import extract_channel_id, fetch_channel_videos, get_video_metadata, download_audio
from feed_generator import generate_feed
from scheduler import create_scheduler, refresh_channel, refresh_all_channels

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize database
init_db()

# HTML template for the web UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>YouTube Podcast Generator</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 50px auto; padding: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .card { background: white; padding: 20px; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        input[type="text"] { width: 70%; padding: 10px; font-size: 16px; border: 1px solid #ddd; border-radius: 4px; }
        button { padding: 10px 20px; font-size: 16px; background: #ff0000; color: white; border: none;
                 border-radius: 4px; cursor: pointer; margin-left: 10px; }
        button:hover { background: #cc0000; }
        button.secondary { background: #666; }
        button.secondary:hover { background: #444; }
        button.danger { background: #dc3545; }
        button.danger:hover { background: #c82333; }
        .channel { display: flex; justify-content: space-between; align-items: center;
                   padding: 15px; border-bottom: 1px solid #eee; }
        .channel:last-child { border-bottom: none; }
        .channel-name { font-weight: bold; font-size: 18px; }
        .channel-actions { display: flex; gap: 10px; }
        .feed-url { font-size: 12px; color: #666; word-break: break-all; }
        .feed-url a { color: #0066cc; }
        .loading { display: none; color: #666; font-style: italic; }
        .message { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .message.success { background: #d4edda; color: #155724; }
        .message.error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>🎙️ YouTube Podcast Generator</h1>

    <div class="card">
        <h2>Add YouTube Channel</h2>
        <form id="add-form">
            <input type="text" id="channel-url" placeholder="YouTube channel URL, @handle, or channel ID" required>
            <button type="submit">Add Channel</button>
        </form>
        <p class="loading" id="add-loading">Adding channel and downloading videos...</p>
        <div id="add-message"></div>
    </div>

    <div class="card">
        <h2>Your Channels</h2>
        <button class="secondary" onclick="refreshAll()">Refresh All Channels</button>
        <div id="channels-list"></div>
    </div>

    <script>
        const BASE_URL = '""" + BASE_URL + """';

        async function loadChannels() {
            const response = await fetch('/channels');
            const channels = await response.json();
            const list = document.getElementById('channels-list');

            if (channels.length === 0) {
                list.innerHTML = '<p>No channels added yet.</p>';
                return;
            }

            list.innerHTML = channels.map(ch => `
                <div class="channel">
                    <div>
                        <div class="channel-name">${ch.name}</div>
                        <div class="feed-url">
                            RSS Feed: <a href="/feed/${ch.id}" target="_blank">${BASE_URL}/feed/${ch.id}</a>
                        </div>
                    </div>
                    <div class="channel-actions">
                        <button class="secondary" onclick="refreshChannel(${ch.id})">Refresh</button>
                        <button class="danger" onclick="deleteChannel(${ch.id})">Delete</button>
                    </div>
                </div>
            `).join('');
        }

        document.getElementById('add-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const url = document.getElementById('channel-url').value;
            const loading = document.getElementById('add-loading');
            const message = document.getElementById('add-message');

            loading.style.display = 'block';
            message.innerHTML = '';

            try {
                const response = await fetch('/channels', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });

                const data = await response.json();

                if (response.ok) {
                    message.innerHTML = `<div class="message success">Added "${data.name}" successfully!</div>`;
                    document.getElementById('channel-url').value = '';
                    loadChannels();
                } else {
                    message.innerHTML = `<div class="message error">${data.error}</div>`;
                }
            } catch (err) {
                message.innerHTML = `<div class="message error">Error: ${err.message}</div>`;
            }

            loading.style.display = 'none';
        });

        async function deleteChannel(id) {
            if (!confirm('Are you sure? This will delete all downloaded episodes.')) return;

            await fetch(`/channels/${id}`, { method: 'DELETE' });
            loadChannels();
        }

        async function refreshChannel(id) {
            alert('Refresh started. This may take a while.');
            await fetch(`/refresh/${id}`, { method: 'POST' });
            alert('Refresh complete!');
            loadChannels();
        }

        async function refreshAll() {
            alert('Refreshing all channels. This may take a while.');
            await fetch('/refresh', { method: 'POST' });
            alert('Refresh complete!');
            loadChannels();
        }

        loadChannels();
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serve the web UI."""
    return HTML_TEMPLATE


@app.route('/channels', methods=['GET'])
def list_channels():
    """List all channels."""
    channels = Channel.get_all()
    return jsonify(channels)


@app.route('/channels', methods=['POST'])
def add_channel():
    """Add a new YouTube channel."""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        # Extract channel info
        channel_id, channel_name = extract_channel_id(url)

        # Check if already exists
        existing = Channel.get_by_youtube_id(channel_id)
        if existing:
            return jsonify({'error': 'Channel already added'}), 400

        # Create channel
        channel_db_id = Channel.create(
            youtube_channel_id=channel_id,
            name=channel_name,
            url=f"https://www.youtube.com/channel/{channel_id}"
        )

        # Fetch and download initial videos
        channel = Channel.get_by_id(channel_db_id)
        refresh_channel(channel)

        return jsonify({
            'id': channel_db_id,
            'name': channel_name,
            'youtube_channel_id': channel_id
        }), 201

    except Exception as e:
        logger.error(f"Failed to add channel: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/channels/<int:channel_id>', methods=['DELETE'])
def delete_channel(channel_id):
    """Delete a channel and its episodes."""
    channel = Channel.get_by_id(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    # Delete audio files
    episodes = Episode.get_by_channel(channel_id)
    for ep in episodes:
        if ep.get('audio_path'):
            audio_file = AUDIO_DIR / ep['audio_path']
            if audio_file.exists():
                audio_file.unlink()

    # Delete from database
    Episode.delete_by_channel(channel_id)
    Channel.delete(channel_id)

    return jsonify({'success': True})


@app.route('/feed/<int:channel_id>')
def get_feed(channel_id):
    """Get RSS feed for a channel."""
    channel = Channel.get_by_id(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    episodes = Episode.get_by_channel(channel_id)
    rss = generate_feed(channel, episodes)

    return Response(rss, mimetype='application/rss+xml')


@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serve audio files."""
    return send_from_directory(AUDIO_DIR, filename)


@app.route('/refresh', methods=['POST'])
def refresh_all():
    """Manually trigger refresh of all channels."""
    refresh_all_channels()
    return jsonify({'success': True})


@app.route('/refresh/<int:channel_id>', methods=['POST'])
def refresh_single(channel_id):
    """Manually trigger refresh of a single channel."""
    channel = Channel.get_by_id(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    refresh_channel(channel)
    return jsonify({'success': True})


if __name__ == '__main__':
    # Start the scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info(f"Scheduler started. Checking for new videos every {scheduler.get_job('refresh_channels').trigger} hours")

    # Run the Flask app
    logger.info(f"Starting server at {BASE_URL}")
    app.run(host=HOST, port=PORT, debug=False)
