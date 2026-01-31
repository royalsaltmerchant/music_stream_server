import base64
import hashlib
import hmac
import queue
import os
import re
import signal
import time
import random
import threading
import subprocess
import urllib.parse
import logging
import psycopg2
import uvicorn

from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware


from config import (
    CHUNK_SIZE,
    LISTENER_QUEUE_MAXSIZE,
    IDLE_TIMEOUT,
    SILENT_BUFFER,
    SESSION_COOKIE_NAME,
    SESSION_SECRET,
    SESSION_DB_DSN,
    HOST,
    PORT,
    LOGIN_URL,
    ADMIN_EMAILS,
    DEV_MODE,
    DEV_USER_EMAIL,
)
from tracks import get_track_filename, reload_tracks
from playlists import get_playlist, get_all_playlists, reload_playlists
from cloudfront import get_signed_url

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("radio")
logger.level = logging.INFO


# === AudioStreamer ===
class AudioStreamer:
    def __init__(self, playlist_name: str):
        self.playlist_name = playlist_name
        self.listener_queues = {}  # key: channel_name, value: set of queues
        self.listener_queues_lock = threading.Lock()
        self.command_queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self.thread.is_alive():
            self.thread.start()

    def add_listener(self, channel_name, q):
        with self.listener_queues_lock:
            if channel_name not in self.listener_queues:
                self.listener_queues[channel_name] = set()
            self.listener_queues[channel_name].add(q)

    def remove_listener(self, channel_name, q):
        with self.listener_queues_lock:
            if channel_name in self.listener_queues:
                self.listener_queues[channel_name].discard(q)
                if not self.listener_queues[channel_name]:
                    del self.listener_queues[channel_name]

    def put_command(self, cmd: str):
        self.command_queue.put(cmd)

    def _run(self):
        last_listener_time = time.time()
        while True:
            track_keys = get_playlist(self.playlist_name)
            if not track_keys:
                logger.warning(f"[!] Playlist '{self.playlist_name}' not found or empty.")
                time.sleep(5)
                continue

            # Resolve track keys to filenames, skip any that don't exist
            tracks = []
            for key in track_keys:
                filename = get_track_filename(key)
                if filename:
                    tracks.append((key, filename))
                else:
                    logger.warning(f"[!] Track key '{key}' not found in registry.")

            if not tracks:
                logger.warning("[!] No valid tracks found. Waiting...")
                time.sleep(5)
                continue

            random.shuffle(tracks)

            for track_key, track_filename in tracks:
                # Generate signed CloudFront URL for this track
                track_url = get_signed_url(track_filename)
                logger.info(f"Now playing: {track_key} ({track_filename})")

                try:
                    proc = subprocess.Popen(
                        [
                            "ffmpeg",
                            "-hide_banner",
                            "-loglevel",
                            "quiet",
                            "-re",
                            "-i",
                            track_url,
                            "-vn",
                            "-acodec",
                            "libmp3lame",
                            "-ar",
                            "44100",
                            "-b:a",
                            "128k",
                            "-f",
                            "mp3",
                            "-",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except FileNotFoundError:
                    logger.error("FFmpeg not found in PATH")
                    time.sleep(5)
                    continue
                except Exception as e:
                    logger.error(f"Failed to start FFmpeg: {e}")
                    time.sleep(5)
                    continue

                try:
                    while True:
                        try:
                            cmd = self.command_queue.get_nowait()
                            if cmd == "stop":
                                logger.info("[Streamer] Stopped.")
                                return
                            elif cmd == "next":
                                logger.info("[Streamer] Skipping track.")
                                break
                            # Removed "change" command - playlist changes handled via Channel.play_playlist()
                        except queue.Empty:
                            pass

                        assert proc.stdout is not None
                        chunk = proc.stdout.read(CHUNK_SIZE)
                        if chunk:
                            with self.listener_queues_lock:
                                if any(self.listener_queues.values()):
                                    last_listener_time = time.time()
                                for listeners in list(self.listener_queues.values()):
                                    for q in listeners:
                                        try:
                                            q.put_nowait(chunk)
                                        except queue.Full:
                                            pass
                        else:
                            logger.info("[Streamer] End of track reached.")
                            break

                        if time.time() - last_listener_time > IDLE_TIMEOUT:
                            logger.info(
                                f"[Streamer] No listeners for {IDLE_TIMEOUT} seconds. Exiting."
                            )
                            return
                finally:
                    # Ensure FFmpeg process is properly cleaned up
                    if proc.poll() is None:
                        proc.kill()
                    if proc.stdout:
                        proc.stdout.close()
                    proc.wait()


# === Channel ===
class Channel:
    def __init__(self, name: str):
        self.name = name
        self.current_playlist = None

    def play_playlist(self, playlist_name: str, streamers: dict):
        if self.current_playlist == playlist_name:
            return

        old_playlist = self.current_playlist
        self.current_playlist = playlist_name

        if (
            playlist_name not in streamers
            or not streamers[playlist_name].thread.is_alive()
        ):
            streamer = AudioStreamer(playlist_name=playlist_name)
            streamers[playlist_name] = streamer
            streamer.start()

        if old_playlist and old_playlist in streamers:
            old_streamer = streamers[old_playlist]
            new_streamer = streamers[playlist_name]

            if self.name in old_streamer.listener_queues:
                for q in list(old_streamer.listener_queues[self.name]):
                    old_streamer.remove_listener(self.name, q)
                    new_streamer.add_listener(self.name, q)

    def send_command(self, cmd: str, streamers: dict):
        if self.current_playlist and self.current_playlist in streamers:
            streamers[self.current_playlist].put_command(cmd)


# === Radio Web Service ===
class RadioWebService:
    MAX_CHANNEL_NAME_LENGTH = 256

    def __init__(self):
        self.app = FastAPI()
        self.channels = {}
        self.streamers = {}
        self.app.add_middleware(
            BaseHTTPMiddleware, dispatch=self.create_session_middleware()
        )
        self.app.mount("/static", StaticFiles(directory="static"), name="static")
        self._define_routes()

    def _validate_channel_name(self, name: str) -> tuple[bool, str]:
        """Validate channel name format and length."""
        if not name or not isinstance(name, str):
            return False, "Channel name required"

        name = name.strip()
        if len(name) > self.MAX_CHANNEL_NAME_LENGTH:
            return False, "Channel name too long"

        # Whitelist allowed characters
        if not re.match(r'^[a-zA-Z0-9_-]+$', name):
            return False, "Channel name contains invalid characters"

        return True, name

    def _get_channel(self, name: str) -> Channel:
        if name not in self.channels:
            logger.info(f"[Channel] Creating new channel: {name}")
            self.channels[name] = Channel(name)
        return self.channels[name]

    def create_session_middleware(self):
        async def session_middleware(request: Request, call_next):
            cookie = request.cookies.get(SESSION_COOKIE_NAME)
            if not cookie:
                logger.info("[Session] No session cookie")
                return await call_next(request)

            valid, session_id = self.verify_express_cookie(cookie, SESSION_SECRET)
            if not valid:
                logger.info("[Session] Invalid signature")
                return await call_next(request)

            try:
                with psycopg2.connect(SESSION_DB_DSN) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT sess FROM session WHERE sid = %s AND expire > NOW()",
                            (session_id,),
                        )
                        row = cur.fetchone()
                        if not row:
                            logger.info("[Session] Session expired or not found")
                            return await call_next(request)

                        session_data = row[0]
                        request.state.session_data = session_data
                        request.state.user_id = session_data.get("user")
            except psycopg2.OperationalError as e:
                logger.warning(f"[Session] DB connection error: {e}")
            except psycopg2.ProgrammingError as e:
                logger.error(f"[Session] DB query error: {e}")
            except Exception as e:
                logger.error(f"[Session] Unexpected error: {e}", exc_info=True)

            return await call_next(request)

        return session_middleware

    def verify_express_cookie(self, cookie_str: str, secret: str):
        def base64_to_base64url(s):
            return s.replace("+", "-").replace("/", "_").rstrip("=")

        cookie_str = urllib.parse.unquote(cookie_str)

        if not cookie_str.startswith("s:") or len(cookie_str) < 3:
            logger.warning(
                "[VerifyCookie] Invalid cookie format"
            )
            return False, None

        try:
            value, sig = cookie_str[2:].split(".", 1)
        except ValueError:
            logger.warning(
                "[VerifyCookie] Failed to split cookie into value and signature."
            )
            return False, None

        expected_sig = hmac.new(
            secret.encode(), msg=value.encode(), digestmod=hashlib.sha256
        ).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()

        # Convert incoming cookie signature to Base64URL format
        cookie_sig_urlsafe = base64_to_base64url(sig)

        if hmac.compare_digest(expected_sig_b64, cookie_sig_urlsafe):
            logger.info("[VerifyCookie] Signature valid")
            return True, value
        else:
            logger.info("[VerifyCookie] Signature mismatch")
            return False, None

    async def login_required(self, request: Request):
        if DEV_MODE:
            request.state.user_id = 0
            request.state.dev_mode = True
            return
        if not getattr(request.state, "user_id", None):
            raise HTTPException(
                status_code=307,
                detail="Redirecting to login",
                headers={"Location": LOGIN_URL},
            )

    def _define_routes(self):
        @self.app.get("/")
        def index():
            return FileResponse("static/index.html")

        @self.app.get("/listen")
        def listen(request: Request):
            channel_name = request.query_params.get("channel", "").strip()
            valid, result = self._validate_channel_name(channel_name)
            if not valid:
                return Response(result, status_code=400)

            # auto-create listener page with dynamic JS if needed
            return FileResponse("static/listener.html")

        @self.app.get("/host")
        async def host(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            return FileResponse("static/host.html")

        @self.app.get("/admin")
        async def admin_page(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            # Check if user is in admin whitelist
            if getattr(request.state, "dev_mode", False):
                user_email = DEV_USER_EMAIL
            else:
                user_id = getattr(request.state, "user_id", None)
                if not user_id:
                    raise HTTPException(status_code=401, detail="Unauthorized")

                try:
                    with psycopg2.connect(SESSION_DB_DSN) as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                'SELECT email FROM "public"."User" WHERE id = %s',
                                (user_id,),
                            )
                            row = cur.fetchone()
                            if not row:
                                raise HTTPException(status_code=404, detail="User not found")
                            user_email = row[0]
                except psycopg2.Error as e:
                    logger.error(f"[Admin] DB error: {e}")
                    raise HTTPException(status_code=500, detail="Database error")

            if user_email not in ADMIN_EMAILS:
                raise HTTPException(status_code=403, detail="Forbidden")

            return FileResponse("static/admin.html")

        @self.app.get("/playlists")
        def get_playlists_route(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            return {"playlists": get_all_playlists()}

        @self.app.post("/admin/reload")
        async def admin_reload(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            # In dev mode, use configured dev email
            if getattr(request.state, "dev_mode", False):
                user_email = DEV_USER_EMAIL
                logger.info(f"[Admin] Dev mode - using email: {user_email}")
            else:
                user_id = getattr(request.state, "user_id", None)
                if not user_id:
                    return {"error": "Unauthorized"}, 401

                # Query users table for email
                try:
                    with psycopg2.connect(SESSION_DB_DSN) as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                'SELECT email FROM "public"."User" WHERE id = %s',
                                (user_id,),
                            )
                            row = cur.fetchone()
                            if not row:
                                logger.warning(f"[Admin] User {user_id} not found in users table")
                                return {"error": "User not found"}, 404
                            user_email = row[0]
                except Exception as e:
                    logger.error(f"[Admin] DB error looking up user email: {e}")
                    return {"error": "Database error"}, 500

            # Check if email is in admin whitelist
            if user_email not in ADMIN_EMAILS:
                logger.warning(f"[Admin] Unauthorized reload attempt by {user_email}")
                return {"error": "Forbidden"}, 403

            # Reload both tracks and playlists
            logger.info(f"[Admin] Reload triggered by {user_email}")
            reload_tracks()
            reload_playlists()

            return {"status": "ok", "message": "Tracks and playlists reloaded"}

        @self.app.post("/command")
        async def command(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            try:
                data = await request.json()
            except Exception as e:
                logger.warning(f"[Command] Invalid JSON: {e}")
                return {"error": "Invalid JSON"}, 400

            if not isinstance(data, dict):
                return {"error": "Expected JSON object"}, 400

            cmd = data.get("command")
            channel_name = data.get("channel", "")
            playlist_name = data.get("playlist")

            valid, result = self._validate_channel_name(channel_name)
            if not valid:
                return {"error": result}, 400

            channel_name = result  # Use validated/normalized name
            try:
                channel = self._get_channel(channel_name)
                if playlist_name:
                    # Validate playlist exists
                    if get_playlist(playlist_name) is None:
                        return {"error": "Playlist not found"}, 400

                    channel.play_playlist(playlist_name, self.streamers)
                elif cmd:
                    channel.send_command(cmd, self.streamers)
                else:
                    return {"error": "Missing command or playlist"}, 400
                return {"status": "ok", "channel": channel_name}
            except Exception as e:
                logger.error(f"[Command] Error: {e}")
                return {"error": str(e)}, 500

        @self.app.get("/stream")
        async def stream(request: Request):
            channel_name = request.query_params.get("channel", "").strip()
            valid, result = self._validate_channel_name(channel_name)
            if not valid:
                return Response(content=result, status_code=400)

            channel_name = result  # Use validated/normalized name
            try:
                channel = self._get_channel(channel_name)
                playlist = channel.current_playlist
                if not playlist or playlist not in self.streamers:
                    return Response(content="Channel not active", status_code=400)

                q = queue.Queue(maxsize=LISTENER_QUEUE_MAXSIZE)
                self.streamers[playlist].add_listener(channel_name, q)

                try:
                    q.put_nowait(SILENT_BUFFER)
                except queue.Full:
                    pass

                def generate():
                    logger.info(f"[Stream] Client connected to {channel_name}")
                    try:
                        yield SILENT_BUFFER
                        while True:
                            try:
                                chunk = q.get(timeout=5)
                            except queue.Empty:
                                chunk = SILENT_BUFFER
                            yield chunk
                    finally:
                        self.streamers[playlist].remove_listener(channel_name, q)
                        if not self.streamers[playlist].listener_queues.get(
                            channel_name
                        ):
                            logger.info(
                                f"[Channel] No more listeners on '{channel_name}', removing channel"
                            )
                            del self.channels[channel_name]

                return StreamingResponse(
                    generate(),
                    media_type="audio/mpeg",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )

            except Exception as e:
                logger.exception("[Stream] Unhandled exception")
                return Response(content=str(e), status_code=500)


# === Signal Handler for Data Reload ===
def _handle_sighup(signum, frame):
    """Handle SIGHUP to reload tracks and playlists from source."""
    logger.info("[Signal] Received SIGHUP, reloading tracks and playlists...")
    reload_tracks()
    reload_playlists()


signal.signal(signal.SIGHUP, _handle_sighup)


# === Main Entrypoint ===
if __name__ == "__main__":
    # Load tracks and playlists on startup
    logger.info("Loading tracks and playlists...")
    reload_tracks()
    reload_playlists()

    service = RadioWebService()
    logger.info(f"Server running at http://{HOST}:{PORT}")
    uvicorn.run(service.app, host=HOST, port=PORT)
