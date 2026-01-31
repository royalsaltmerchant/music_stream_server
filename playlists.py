import logging
import urllib.error
from config import PLAYLISTS_CSV_PATH
from sheets_utils import read_csv

logger = logging.getLogger("radio.playlists")

# Playlist registry: Playlist Title -> list of Track Keys
_playlists: dict[str, list[str]] = {}


def _load_playlists():
    """Load playlists from CSV file or Google Sheets URL.

    Expects columns: "Playlist Title", "Track Key"
    Builds playlists by appending each track to its playlist.
    """
    global _playlists
    new_playlists: dict[str, list[str]] = {}

    try:
        logger.info(f"Loading playlists from {PLAYLISTS_CSV_PATH}...")
        reader, file_handle = read_csv(PLAYLISTS_CSV_PATH)

        for row in reader:
            playlist_title = row.get("Playlist Title", "").strip()
            track_key = row.get("Track Key", "").strip()
            if playlist_title and track_key:
                if playlist_title not in new_playlists:
                    new_playlists[playlist_title] = []
                new_playlists[playlist_title].append(track_key)

        if file_handle:
            file_handle.close()

        _playlists = new_playlists
        logger.info(f"Loaded {len(_playlists)} playlists")

    except FileNotFoundError:
        logger.error(f"Playlists CSV not found: {PLAYLISTS_CSV_PATH}")
    except urllib.error.URLError as e:
        logger.error(f"Failed to fetch playlists from URL: {e}")
    except Exception as e:
        logger.error(f"Failed to load playlists CSV: {e}")


def get_playlist(name: str) -> list[str] | None:
    """Get track keys for a playlist."""
    if not _playlists:
        _load_playlists()
    return _playlists.get(name)


def get_all_playlists() -> list[str]:
    """Get all playlist names."""
    if not _playlists:
        _load_playlists()
    return list(_playlists.keys())


def reload_playlists():
    """Force reload playlists from CSV."""
    global _playlists
    _playlists = {}
    _load_playlists()
