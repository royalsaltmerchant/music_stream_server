import csv
import logging
from config import TRACKS_CSV_PATH

logger = logging.getLogger("radio.tracks")

# Track registry: KEY TITLE -> File Name
_tracks: dict[str, str] = {}


def _load_tracks():
    """Load tracks from CSV file."""
    global _tracks
    try:
        with open(TRACKS_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get("KEY TITLE", "").strip()
                filename = row.get("File Name", "").strip()
                if key and filename:
                    _tracks[key] = filename
        logger.info(f"Loaded {len(_tracks)} tracks from {TRACKS_CSV_PATH}")
    except FileNotFoundError:
        logger.error(f"Tracks CSV not found: {TRACKS_CSV_PATH}")
    except Exception as e:
        logger.error(f"Failed to load tracks CSV: {e}")


def get_track_filename(key: str) -> str | None:
    """Get filename for a track key."""
    if not _tracks:
        _load_tracks()
    return _tracks.get(key)


def get_all_track_keys() -> list[str]:
    """Get all available track keys."""
    if not _tracks:
        _load_tracks()
    return list(_tracks.keys())


def reload_tracks():
    """Force reload tracks from CSV."""
    global _tracks
    _tracks = {}
    _load_tracks()
