# YouTube Podcast Generator

A Python local server application that converts YouTube channels into podcast RSS feeds with automatic audio downloading.

## Features

- **Add channels by URL or ID** - Supports youtube.com/c/, @handle, and channel IDs
- **Automatic audio extraction** - Converts videos to MP3 for podcast compatibility
- **Valid podcast RSS** - Works with Apple Podcasts, Overcast, Pocket Casts, etc.
- **Periodic updates** - Automatically checks for new videos every hour
- **Simple web UI** - Add/remove channels via browser

## Requirements

- Python 3.10+
- FFmpeg (required by yt-dlp for audio extraction)

## Installation

1. Clone or download this project:
   ```bash
   cd /Users/jagalindo/Documents/Personal/youtube-podcast
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure FFmpeg is installed:
   ```bash
   # macOS
   brew install ffmpeg

   # Ubuntu/Debian
   sudo apt install ffmpeg

   # Windows
   # Download from https://ffmpeg.org/download.html
   ```

## Usage

### Starting the Server

```bash
python app.py
```

The server starts at `http://localhost:5000` by default.

### Web Interface

Open `http://localhost:5000` in your browser to:
- Add YouTube channels by URL, @handle, or channel ID
- View all added channels
- Copy RSS feed URLs for your podcast app
- Manually refresh channels
- Delete channels

### Adding a Channel

You can add channels using any of these formats:
- Full URL: `https://www.youtube.com/@channelname`
- Handle: `@channelname`
- Channel ID: `UCxxxxxxxxxxxxxxxxxxxxxxxx`
- Legacy URL: `https://www.youtube.com/c/channelname`

### Subscribing in Podcast Apps

1. Add a channel through the web UI
2. Copy the RSS feed URL (shown under each channel)
3. In your podcast app, add a podcast by URL
4. Paste the RSS feed URL

## Authentication

### Global Admin Password

Protect the web interface and management API with a password:

```bash
export ADMIN_PASSWORD="your-secret-password"
python app.py
```

When set, accessing the web UI or any management endpoint requires HTTP Basic authentication. You can use any username - only the password is checked. Feed and audio endpoints remain accessible to podcast apps with their own per-channel auth.

### Per-Channel Feed Authentication

You can protect individual feeds with authentication to prevent unauthorized access. Two methods are available:

### HTTP Basic Authentication

Requires username and password to access the feed. Most podcast apps support this.

1. In the web UI, select "Password (HTTP Basic)" for a channel
2. Enter a username and password, then click Save
3. Use the feed URL format: `http://username:password@yourserver:5000/feed/1`

Supported by: Apple Podcasts, Overcast, Pocket Casts, and most other apps.

### Secret Token URL

Uses a long random token in the URL itself. No password prompt needed.

1. In the web UI, select "Secret Token URL" for a channel
2. Click Save - a new token will be generated
3. Use the token URL shown: `http://yourserver:5000/feed/t/your-secret-token`

The token URL is unguessable, but anyone with the URL can access the feed. Keep it private.

### Disabling Authentication

Select "None (Public)" to make a feed publicly accessible again.

## API Reference

### List Channels
```
GET /channels
```
Returns JSON array of all channels.

### Add Channel
```
POST /channels
Content-Type: application/json

{"url": "https://www.youtube.com/@channelname"}
```
Adds a new channel and downloads initial videos.

### Delete Channel
```
DELETE /channels/<id>
```
Removes a channel and all its downloaded episodes.

### Get RSS Feed
```
GET /feed/<channel_id>
```
Returns the podcast RSS feed XML for a channel.

### Serve Audio
```
GET /audio/<filename>
```
Serves downloaded audio files.

### Refresh All Channels
```
POST /refresh
```
Manually triggers a refresh of all channels.

### Refresh Single Channel
```
POST /refresh/<channel_id>
```
Manually triggers a refresh of a specific channel.

### Get Feed by Token
```
GET /feed/t/<token>
```
Returns the podcast RSS feed using token authentication.

### Serve Audio by Token
```
GET /audio/t/<token>/<filename>
```
Serves audio files using token authentication.

### Update Channel Authentication
```
POST /channels/<id>/auth
Content-Type: application/json

// For no auth:
{"auth_type": "none"}

// For HTTP Basic:
{"auth_type": "basic", "username": "user", "password": "pass"}

// For token:
{"auth_type": "token"}
```
Updates authentication settings for a channel. Token auth returns the generated token.

## Configuration

Configuration is managed in `config.py` or via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `5000` | Server port |
| `BASE_URL` | `http://localhost:5000` | Public URL for feed links |
| `CHECK_INTERVAL_HOURS` | `1` | Hours between automatic refreshes |
| `INITIAL_FETCH_COUNT` | `10` | Number of videos to fetch per channel |
| `ADMIN_PASSWORD` | (none) | Password for admin interface (recommended when exposed) |

### Environment Variables

```bash
export PORT=8080
export BASE_URL="http://myserver.local:8080"
export CHECK_INTERVAL_HOURS=2
export INITIAL_FETCH_COUNT=20
python app.py
```

## Deploying on Proxmox LXC

This section covers deploying the application in an LXC container on Proxmox.

### 1. Create the LXC Container

In Proxmox web UI or via CLI:

```bash
# From Proxmox host
pct create 100 local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst \
  --hostname youtube-podcast \
  --memory 1024 \
  --cores 2 \
  --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 \
  --features nesting=1

pct start 100
```

Or use the GUI: **Create CT** → Debian 12 template, 1GB RAM, 8GB disk.

### 2. Enter Container and Install Dependencies

```bash
# From Proxmox host
pct enter 100

# Inside the container
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv ffmpeg git
```

### 3. Set Up the Application

```bash
# Create app user
useradd -m -s /bin/bash podcast
su - podcast

# Create project directory
mkdir -p ~/youtube-podcast
cd ~/youtube-podcast

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Copy your project files here (via scp, git, or manual copy)
# Then install dependencies
pip install -r requirements.txt
```

### 4. Configure for Network Access

Check the container IP:

```bash
hostname -I
```

Create `/home/podcast/youtube-podcast/.env` (replace `YOUR_CONTAINER_IP` with actual IP):

```
HOST=0.0.0.0
PORT=5000
BASE_URL=http://YOUR_CONTAINER_IP:5000
ADMIN_PASSWORD=your-secret-password
```

### 5. Create Systemd Service

As root in the container:

```bash
cat > /etc/systemd/system/youtube-podcast.service << 'EOF'
[Unit]
Description=YouTube Podcast Generator
After=network.target

[Service]
Type=simple
User=podcast
WorkingDirectory=/home/podcast/youtube-podcast
Environment=PATH=/home/podcast/youtube-podcast/venv/bin
ExecStart=/home/podcast/youtube-podcast/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable youtube-podcast
systemctl start youtube-podcast
```

### 6. Verify It's Running

```bash
systemctl status youtube-podcast
curl http://localhost:5000
```

Access from any device on your network at `http://YOUR_CONTAINER_IP:5000`.

### Copying Files to the Container

To copy files from your local machine to the container:

```bash
# From your local machine - copy to Proxmox host first
scp -r /path/to/youtube-podcast root@PROXMOX_IP:/tmp/

# From Proxmox host - copy into container
pct push 100 /tmp/youtube-podcast /home/podcast/youtube-podcast --recursive

# Fix ownership inside the container
pct enter 100
chown -R podcast:podcast /home/podcast/youtube-podcast
```

### Optional: Nginx Reverse Proxy

For a clean URL or to add SSL, set up nginx inside the container:

```bash
apt install nginx

cat > /etc/nginx/sites-available/podcast << 'EOF'
server {
    listen 80;
    server_name podcast.local;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

ln -s /etc/nginx/sites-available/podcast /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
systemctl restart nginx
```

Then update `BASE_URL` in your `.env` to match your domain/IP.

## Project Structure

```
youtube-podcast/
├── app.py              # Main Flask application & routes
├── config.py           # Configuration settings
├── models.py           # SQLite database models
├── downloader.py       # yt-dlp wrapper for audio extraction
├── feed_generator.py   # RSS/Podcast XML generation
├── scheduler.py        # Background job scheduling
├── requirements.txt    # Python dependencies
├── README.md           # This file
└── data/
    ├── audio/          # Downloaded audio files (*.mp3)
    └── podcast.db      # SQLite database
```

## Database Schema

### Channels Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| youtube_channel_id | TEXT | YouTube's channel ID |
| name | TEXT | Channel name |
| url | TEXT | Channel URL |
| added_at | TIMESTAMP | When the channel was added |
| auth_type | TEXT | Authentication type: 'none', 'basic', or 'token' |
| username | TEXT | Username for HTTP Basic auth |
| password_hash | TEXT | SHA-256 hash of password |
| secret_token | TEXT | Secret token for token-based auth |

### Episodes Table
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| channel_id | INTEGER | Foreign key to channels |
| video_id | TEXT | YouTube video ID |
| title | TEXT | Episode title |
| description | TEXT | Episode description |
| duration | INTEGER | Duration in seconds |
| published_at | TIMESTAMP | Original publish date |
| audio_path | TEXT | Path to downloaded audio |
| downloaded_at | TIMESTAMP | When audio was downloaded |
| thumbnail_url | TEXT | Video thumbnail URL |

## Troubleshooting

### "FFmpeg not found" error
Install FFmpeg using your system's package manager (see Installation).

### Audio files not downloading
- Check that the YouTube video is available in your region
- Some videos may have download restrictions
- Check the console logs for specific error messages

### RSS feed not working in podcast app
- Ensure `BASE_URL` is set correctly and accessible from your podcast app
- If running locally, your phone/device must be on the same network
- Some podcast apps cache feeds; try removing and re-adding

### Database errors
Delete `data/podcast.db` to reset the database (you'll lose channel data).

## License

MIT License
