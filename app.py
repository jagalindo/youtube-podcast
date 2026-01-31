import os
import logging
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, Response
from config import HOST, PORT, AUDIO_DIR, BASE_URL, ADMIN_PASSWORD
from models import init_db, Channel, Episode
from downloader import extract_channel_id, fetch_channel_videos, get_video_metadata, download_audio
from feed_generator import generate_feed
from scheduler import create_scheduler, refresh_channel, refresh_all_channels


def check_auth(channel):
    """Check if request is authorized for the given channel."""
    auth_type = channel.get('auth_type', 'none')

    if auth_type == 'none':
        return True

    if auth_type == 'basic':
        auth = request.authorization
        if not auth:
            return False
        return Channel.verify_basic_auth(channel['id'], auth.username, auth.password)

    if auth_type == 'token':
        # Token auth is handled by separate route
        return False

    return False


def require_auth(f):
    """Decorator to require authentication for a route."""
    @wraps(f)
    def decorated(channel_id, *args, **kwargs):
        channel = Channel.get_by_id(channel_id)
        if not channel:
            return jsonify({'error': 'Channel not found'}), 404

        if not check_auth(channel):
            if channel.get('auth_type') == 'token':
                return jsonify({'error': 'This feed requires token access. Use the token URL.'}), 401
            return Response(
                'Authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="Podcast Feed"'}
            )

        return f(channel_id, channel=channel, *args, **kwargs)
    return decorated


def require_admin_auth(f):
    """Decorator to require admin authentication for management routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ADMIN_PASSWORD:
            # No password set, allow access
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or auth.password != ADMIN_PASSWORD:
            return Response(
                'Admin authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="Admin"'}
            )

        return f(*args, **kwargs)
    return decorated

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
        input[type="text"], input[type="password"], select {
            padding: 8px; font-size: 14px; border: 1px solid #ddd; border-radius: 4px; margin: 2px; }
        input.url-input { width: 70%; }
        button { padding: 10px 20px; font-size: 16px; background: #ff0000; color: white; border: none;
                 border-radius: 4px; cursor: pointer; margin-left: 10px; }
        button:hover { background: #cc0000; }
        button.secondary { background: #666; }
        button.secondary:hover { background: #444; }
        button.danger { background: #dc3545; }
        button.danger:hover { background: #c82333; }
        button.small { padding: 5px 10px; font-size: 12px; margin-left: 5px; }
        .channel { padding: 15px; border-bottom: 1px solid #eee; }
        .channel:last-child { border-bottom: none; }
        .channel-header { display: flex; justify-content: space-between; align-items: center; }
        .channel-name { font-weight: bold; font-size: 18px; }
        .channel-actions { display: flex; gap: 10px; }
        .feed-url { font-size: 12px; color: #666; word-break: break-all; margin: 8px 0; }
        .feed-url a { color: #0066cc; }
        .feed-url code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; }
        .auth-section { margin-top: 10px; padding: 10px; background: #f9f9f9; border-radius: 4px; font-size: 13px; }
        .auth-badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 10px; }
        .auth-badge.none { background: #e9ecef; color: #495057; }
        .auth-badge.basic { background: #cce5ff; color: #004085; }
        .auth-badge.token { background: #d4edda; color: #155724; }
        .auth-form { margin-top: 8px; }
        .auth-form input { margin-right: 5px; }
        .loading { display: none; color: #666; font-style: italic; }
        .message { padding: 10px; margin: 10px 0; border-radius: 4px; }
        .message.success { background: #d4edda; color: #155724; }
        .message.error { background: #f8d7da; color: #721c24; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <h1>YouTube Podcast Generator</h1>

    <div class="card">
        <h2>Add YouTube Channel</h2>
        <form id="add-form">
            <input type="text" id="channel-url" class="url-input" placeholder="YouTube channel URL, @handle, or channel ID" required>
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

        function getAuthBadge(authType) {
            const labels = { none: 'Public', basic: 'Password', token: 'Token' };
            return `<span class="auth-badge ${authType}">${labels[authType] || 'Public'}</span>`;
        }

        function getFeedUrl(ch) {
            if (ch.auth_type === 'token' && ch.secret_token) {
                return `${BASE_URL}/feed/t/${ch.secret_token}`;
            } else if (ch.auth_type === 'basic' && ch.username) {
                return `${BASE_URL.replace('://', '://' + ch.username + ':PASSWORD@')}/feed/${ch.id}`;
            }
            return `${BASE_URL}/feed/${ch.id}`;
        }

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
                    <div class="channel-header">
                        <div>
                            <span class="channel-name">${ch.name}</span>
                            ${getAuthBadge(ch.auth_type || 'none')}
                        </div>
                        <div class="channel-actions">
                            <button class="secondary small" onclick="refreshChannel(${ch.id})">Refresh</button>
                            <button class="danger small" onclick="deleteChannel(${ch.id})">Delete</button>
                        </div>
                    </div>
                    <div class="feed-url">
                        RSS Feed: <code>${getFeedUrl(ch)}</code>
                        <a href="${ch.auth_type === 'token' ? getFeedUrl(ch) : '/feed/' + ch.id}" target="_blank">(open)</a>
                    </div>
                    <div class="auth-section">
                        <strong>Authentication:</strong>
                        <select id="auth-type-${ch.id}" onchange="toggleAuthForm(${ch.id})">
                            <option value="none" ${ch.auth_type === 'none' ? 'selected' : ''}>None (Public)</option>
                            <option value="basic" ${ch.auth_type === 'basic' ? 'selected' : ''}>Password (HTTP Basic)</option>
                            <option value="token" ${ch.auth_type === 'token' ? 'selected' : ''}>Secret Token URL</option>
                        </select>
                        <div id="auth-form-${ch.id}" class="auth-form">
                            <span id="basic-fields-${ch.id}" class="${ch.auth_type === 'basic' ? '' : 'hidden'}">
                                <input type="text" id="username-${ch.id}" placeholder="Username" value="${ch.username || ''}">
                                <input type="password" id="password-${ch.id}" placeholder="Password">
                            </span>
                            <button class="secondary small" onclick="saveAuth(${ch.id})">Save</button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function toggleAuthForm(id) {
            const authType = document.getElementById(`auth-type-${id}`).value;
            const basicFields = document.getElementById(`basic-fields-${id}`);
            basicFields.classList.toggle('hidden', authType !== 'basic');
        }

        async function saveAuth(id) {
            const authType = document.getElementById(`auth-type-${id}`).value;
            const username = document.getElementById(`username-${id}`)?.value;
            const password = document.getElementById(`password-${id}`)?.value;

            const body = { auth_type: authType };
            if (authType === 'basic') {
                if (!username || !password) {
                    alert('Username and password are required');
                    return;
                }
                body.username = username;
                body.password = password;
            }

            const response = await fetch(`/channels/${id}/auth`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            const data = await response.json();
            if (response.ok) {
                if (data.token) {
                    alert('Token generated! Your feed URL has been updated.');
                }
                loadChannels();
            } else {
                alert('Error: ' + data.error);
            }
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
@require_admin_auth
def index():
    """Serve the web UI."""
    return HTML_TEMPLATE


@app.route('/channels', methods=['GET'])
@require_admin_auth
def list_channels():
    """List all channels."""
    channels = Channel.get_all()
    return jsonify(channels)


@app.route('/channels', methods=['POST'])
@require_admin_auth
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
@require_admin_auth
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
@require_auth
def get_feed(channel_id, channel=None):
    """Get RSS feed for a channel (with auth check)."""
    episodes = Episode.get_by_channel(channel_id)
    rss = generate_feed(channel, episodes)
    return Response(rss, mimetype='application/rss+xml')


@app.route('/feed/t/<token>')
def get_feed_by_token(token):
    """Get RSS feed using secret token."""
    channel = Channel.get_by_token(token)
    if not channel:
        return jsonify({'error': 'Invalid token'}), 404

    if channel.get('auth_type') != 'token':
        return jsonify({'error': 'Token access not enabled for this channel'}), 403

    episodes = Episode.get_by_channel(channel['id'])
    rss = generate_feed(channel, episodes)
    return Response(rss, mimetype='application/rss+xml')


@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serve audio files (with auth check based on episode's channel)."""
    # Extract video_id from filename (format: video_id.mp3)
    video_id = filename.rsplit('.', 1)[0] if '.' in filename else filename

    episode = Episode.get_by_video_id(video_id)
    if not episode:
        return jsonify({'error': 'Audio not found'}), 404

    channel = Channel.get_by_id(episode['channel_id'])
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    # Check authentication
    if not check_auth(channel):
        if channel.get('auth_type') == 'token':
            # For token auth, check if token is in query string
            token = request.args.get('token')
            if token != channel.get('secret_token'):
                return jsonify({'error': 'Authentication required'}), 401
        else:
            return Response(
                'Authentication required',
                401,
                {'WWW-Authenticate': 'Basic realm="Podcast Audio"'}
            )

    return send_from_directory(AUDIO_DIR, filename)


@app.route('/audio/t/<token>/<filename>')
def serve_audio_by_token(token, filename):
    """Serve audio files using token authentication."""
    channel = Channel.get_by_token(token)
    if not channel:
        return jsonify({'error': 'Invalid token'}), 404

    # Verify the audio belongs to this channel
    video_id = filename.rsplit('.', 1)[0] if '.' in filename else filename
    episode = Episode.get_by_video_id(video_id)

    if not episode or episode['channel_id'] != channel['id']:
        return jsonify({'error': 'Audio not found'}), 404

    return send_from_directory(AUDIO_DIR, filename)


@app.route('/channels/<int:channel_id>/auth', methods=['POST'])
@require_admin_auth
def update_channel_auth(channel_id):
    """Update authentication settings for a channel."""
    channel = Channel.get_by_id(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404

    data = request.get_json()
    auth_type = data.get('auth_type', 'none')

    try:
        if auth_type == 'basic':
            username = data.get('username')
            password = data.get('password')
            if not username or not password:
                return jsonify({'error': 'Username and password required'}), 400
            Channel.update_auth(channel_id, 'basic', username=username, password=password)
            return jsonify({'success': True, 'auth_type': 'basic'})

        elif auth_type == 'token':
            token = Channel.update_auth(channel_id, 'token')
            return jsonify({'success': True, 'auth_type': 'token', 'token': token})

        else:
            Channel.update_auth(channel_id, 'none')
            return jsonify({'success': True, 'auth_type': 'none'})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/refresh', methods=['POST'])
@require_admin_auth
def refresh_all():
    """Manually trigger refresh of all channels."""
    refresh_all_channels()
    return jsonify({'success': True})


@app.route('/refresh/<int:channel_id>', methods=['POST'])
@require_admin_auth
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
