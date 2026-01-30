import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.absolute()
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
DATABASE_PATH = DATA_DIR / "podcast.db"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)

# Server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")

# Scheduler settings
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", 1))

# Download settings
INITIAL_FETCH_COUNT = int(os.getenv("INITIAL_FETCH_COUNT", 10))
AUDIO_FORMAT = "mp3"
AUDIO_BITRATE = "192"
