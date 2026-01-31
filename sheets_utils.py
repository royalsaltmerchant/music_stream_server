"""Utilities for fetching CSV data from Google Sheets or local files."""

import csv
import io
import re
import urllib.request
import urllib.error

# Regex to detect Google Sheets URL and extract sheet ID and gid
_GSHEET_PATTERN = re.compile(
    r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)(?:/edit)?(?:\?.*gid=(\d+))?"
)


def get_csv_export_url(sheets_url: str) -> str | None:
    """Convert a Google Sheets URL to its CSV export URL."""
    match = _GSHEET_PATTERN.match(sheets_url)
    if not match:
        return None
    sheet_id = match.group(1)
    gid = match.group(2) or "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_csv_from_url(url: str) -> str:
    """Fetch CSV content from a URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def read_csv(path: str) -> csv.DictReader:
    """Read CSV from a Google Sheets URL or local file path.

    Returns a tuple of (DictReader, file_handle_or_None).
    Caller must close the file handle if not None.
    """
    export_url = get_csv_export_url(path)

    if export_url:
        csv_content = fetch_csv_from_url(export_url)
        return csv.DictReader(io.StringIO(csv_content)), None
    else:
        f = open(path, "r", encoding="utf-8")
        return csv.DictReader(f), f
