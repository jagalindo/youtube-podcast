import sqlite3
import secrets
import hashlib
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH


def get_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token() -> str:
    """Generate a secure random token."""
    return secrets.token_urlsafe(32)


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Initialize the database with required tables."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_channel_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                auth_type TEXT DEFAULT 'none',
                username TEXT,
                password_hash TEXT,
                secret_token TEXT
            )
        """)

        # Migration: add auth columns if they don't exist
        cursor = conn.execute("PRAGMA table_info(channels)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'auth_type' not in columns:
            conn.execute("ALTER TABLE channels ADD COLUMN auth_type TEXT DEFAULT 'none'")
        if 'username' not in columns:
            conn.execute("ALTER TABLE channels ADD COLUMN username TEXT")
        if 'password_hash' not in columns:
            conn.execute("ALTER TABLE channels ADD COLUMN password_hash TEXT")
        if 'secret_token' not in columns:
            conn.execute("ALTER TABLE channels ADD COLUMN secret_token TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                video_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                duration INTEGER,
                published_at TIMESTAMP,
                audio_path TEXT,
                downloaded_at TIMESTAMP,
                thumbnail_url TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels (id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_channel ON episodes(channel_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_video ON episodes(video_id)")


class Channel:
    """Channel model for managing YouTube channels."""

    @staticmethod
    def create(youtube_channel_id: str, name: str, url: str) -> int:
        """Create a new channel and return its ID."""
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO channels (youtube_channel_id, name, url) VALUES (?, ?, ?)",
                (youtube_channel_id, name, url)
            )
            return cursor.lastrowid

    @staticmethod
    def get_all() -> list:
        """Get all channels."""
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM channels ORDER BY added_at DESC").fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def get_by_id(channel_id: int) -> dict | None:
        """Get a channel by its ID."""
        with get_db() as conn:
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_by_youtube_id(youtube_channel_id: str) -> dict | None:
        """Get a channel by its YouTube channel ID."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE youtube_channel_id = ?",
                (youtube_channel_id,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def delete(channel_id: int) -> bool:
        """Delete a channel and its episodes."""
        with get_db() as conn:
            cursor = conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
            return cursor.rowcount > 0

    @staticmethod
    def get_by_token(token: str) -> dict | None:
        """Get a channel by its secret token."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM channels WHERE secret_token = ?",
                (token,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_auth(channel_id: int, auth_type: str, username: str = None,
                    password: str = None) -> str | None:
        """
        Update authentication settings for a channel.
        Returns the secret token if auth_type is 'token'.
        """
        with get_db() as conn:
            if auth_type == 'none':
                conn.execute(
                    """UPDATE channels SET auth_type = 'none',
                       username = NULL, password_hash = NULL, secret_token = NULL
                       WHERE id = ?""",
                    (channel_id,)
                )
                return None

            elif auth_type == 'basic':
                if not username or not password:
                    raise ValueError("Username and password required for basic auth")
                conn.execute(
                    """UPDATE channels SET auth_type = 'basic',
                       username = ?, password_hash = ?, secret_token = NULL
                       WHERE id = ?""",
                    (username, hash_password(password), channel_id)
                )
                return None

            elif auth_type == 'token':
                token = generate_token()
                conn.execute(
                    """UPDATE channels SET auth_type = 'token',
                       username = NULL, password_hash = NULL, secret_token = ?
                       WHERE id = ?""",
                    (token, channel_id)
                )
                return token

            else:
                raise ValueError(f"Invalid auth type: {auth_type}")

    @staticmethod
    def verify_basic_auth(channel_id: int, username: str, password: str) -> bool:
        """Verify basic auth credentials for a channel."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT username, password_hash FROM channels WHERE id = ?",
                (channel_id,)
            ).fetchone()
            if not row:
                return False
            return row['username'] == username and row['password_hash'] == hash_password(password)


class Episode:
    """Episode model for managing podcast episodes."""

    @staticmethod
    def create(channel_id: int, video_id: str, title: str, description: str = None,
               duration: int = None, published_at: datetime = None,
               audio_path: str = None, thumbnail_url: str = None) -> int:
        """Create a new episode and return its ID."""
        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO episodes
                (channel_id, video_id, title, description, duration, published_at, audio_path, thumbnail_url, downloaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                channel_id, video_id, title, description, duration,
                published_at, audio_path, thumbnail_url,
                datetime.now() if audio_path else None
            ))
            return cursor.lastrowid

    @staticmethod
    def get_by_channel(channel_id: int) -> list:
        """Get all episodes for a channel, ordered by publish date."""
        with get_db() as conn:
            rows = conn.execute(
                """SELECT * FROM episodes
                   WHERE channel_id = ? AND audio_path IS NOT NULL
                   ORDER BY published_at DESC""",
                (channel_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def get_by_video_id(video_id: str) -> dict | None:
        """Get an episode by its video ID."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM episodes WHERE video_id = ?",
                (video_id,)
            ).fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_audio_path(episode_id: int, audio_path: str):
        """Update the audio path for an episode."""
        with get_db() as conn:
            conn.execute(
                "UPDATE episodes SET audio_path = ?, downloaded_at = ? WHERE id = ?",
                (audio_path, datetime.now(), episode_id)
            )

    @staticmethod
    def delete_by_channel(channel_id: int):
        """Delete all episodes for a channel."""
        with get_db() as conn:
            conn.execute("DELETE FROM episodes WHERE channel_id = ?", (channel_id,))
