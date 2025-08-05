import base64
import hashlib
import hmac
import queue
import os
import time
import random
import threading
import subprocess
import urllib
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
    SILENT_BUFFER,
    SESSION_COOKIE_NAME,
    SESSION_SECRET,
    SESSION_DB_DSN,
    MUSIC_BASE_DIR,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("radio")


# === AudioStreamer ===
class AudioStreamer:
    IDLE_TIMEOUT = 600

    def __init__(self, playlist_path: str):
        self.playlist_path = playlist_path
        self.listener_queues = {}  # key: channel_name, value: set of queues
        self.command_queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self.thread.is_alive():
            self.thread.start()

    def add_listener(self, channel_name, q):
        if channel_name not in self.listener_queues:
            self.listener_queues[channel_name] = set()
        self.listener_queues[channel_name].add(q)

    def remove_listener(self, channel_name, q):
        if channel_name in self.listener_queues:
            self.listener_queues[channel_name].discard(q)
            if not self.listener_queues[channel_name]:
                del self.listener_queues[channel_name]

    def put_command(self, cmd: str):
        self.command_queue.put(cmd)

    def _run(self):
        last_listener_time = time.time()
        while True:
            if not os.path.exists(self.playlist_path):
                logger.warning(f"[!] Folder '{self.playlist_path}' not found.")
                time.sleep(5)
                continue

            playlist = sorted(
                [
                    f
                    for f in os.listdir(self.playlist_path)
                    if f.lower().endswith((".mp3", ".wav", ".ogg", ".flac"))
                ]
            )

            if not playlist:
                logger.warning("[!] No audio files found. Waiting...")
                time.sleep(5)
                continue

            random.shuffle(playlist)

            for track in playlist:
                track_path = os.path.join(self.playlist_path, track)
                logger.info(f"🎶 Now playing: {track}")

                proc = subprocess.Popen(
                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-loglevel",
                        "quiet",
                        "-re",
                        "-i",
                        track_path,
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
                )

                while True:
                    try:
                        cmd = self.command_queue.get_nowait()
                        if cmd == "stop":
                            proc.kill()
                            logger.info("[Streamer] Stopped.")
                            return
                        elif cmd == "next":
                            logger.info("[Streamer] Skipping track.")
                            proc.kill()
                            break
                        elif cmd.startswith("change"):
                            new_dir = cmd[len("change") :].strip()
                            if os.path.isdir(new_dir):
                                logger.info(
                                    f"[Streamer] Changing directory to: {new_dir}"
                                )
                                self.playlist_path = new_dir
                                proc.kill()
                                break
                    except queue.Empty:
                        pass

                    chunk = proc.stdout.read(CHUNK_SIZE)
                    if chunk:
                        if any(self.listener_queues.values()):
                            last_listener_time = time.time()
                        for listeners in self.listener_queues.values():
                            for q in listeners:
                                try:
                                    q.put_nowait(chunk)
                                except queue.Full:
                                    pass
                    else:
                        logger.info("[Streamer] End of track reached.")
                        break

                    if time.time() - last_listener_time > self.IDLE_TIMEOUT:
                        logger.info(
                            f"[Streamer] No listeners for {self.IDLE_TIMEOUT} seconds. Exiting."
                        )
                        proc.kill()
                        return

                proc.kill()


# === Channel ===
class Channel:
    def __init__(self, name: str):
        self.name = name
        self.current_playlist = None

    def play_playlist(self, playlist_path: str, streamers: dict):
        if self.current_playlist == playlist_path:
            return

        old_playlist = self.current_playlist
        self.current_playlist = playlist_path

        if (
            playlist_path not in streamers
            or not streamers[playlist_path].thread.is_alive()
        ):
            streamer = AudioStreamer(playlist_path=playlist_path)
            streamers[playlist_path] = streamer
            streamer.start()

        if old_playlist and old_playlist in streamers:
            old_streamer = streamers[old_playlist]
            new_streamer = streamers[playlist_path]

            if self.name in old_streamer.listener_queues:
                for q in list(old_streamer.listener_queues[self.name]):
                    old_streamer.remove_listener(self.name, q)
                    new_streamer.add_listener(self.name, q)

        old_playlist = self.current_playlist
        self.current_playlist = playlist_path

        if playlist_path not in streamers:
            streamer = AudioStreamer(playlist_path=playlist_path)
            streamers[playlist_path] = streamer
            streamer.start()

        if old_playlist and old_playlist in streamers:
            old_streamer = streamers[old_playlist]
            new_streamer = streamers[playlist_path]

            if self.name in old_streamer.listener_queues:
                for q in list(old_streamer.listener_queues[self.name]):
                    old_streamer.remove_listener(self.name, q)
                    new_streamer.add_listener(self.name, q)

    def send_command(self, cmd: str, streamers: dict):
        if self.current_playlist and self.current_playlist in streamers:
            streamers[self.current_playlist].put_command(cmd)


# === Radio Web Service ===
class RadioWebService:
    def __init__(self):
        self.app = FastAPI()
        self.channels = {}
        self.streamers = {}
        self.app.add_middleware(
            BaseHTTPMiddleware, dispatch=self.create_session_middleware()
        )
        self.app.mount("/static", StaticFiles(directory="static"), name="static")
        self._define_routes()

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
            except Exception as e:
                logger.warning(f"[Session] Error accessing DB: {e}")

            return await call_next(request)

        return session_middleware

    def verify_express_cookie(self, cookie_str: str, secret: str):
        def base64_to_base64url(s):
            return s.replace("+", "-").replace("/", "_").rstrip("=")

        cookie_str = urllib.parse.unquote(cookie_str)

        if not cookie_str.startswith("s:"):
            logger.warning(
                "[VerifyCookie] Cookie does not start with 's:', skipping verification."
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
        if not getattr(request.state, "user_id", None):
            raise HTTPException(
                status_code=307,
                detail="Redirecting to login",
                headers={"Location": "https://farreachco.com/login"},
            )

    def _define_routes(self):
        @self.app.get("/")
        def index():
            return FileResponse("static/index.html")

        @self.app.get("/listen")
        def listen(request: Request):
            channel_name = request.query_params.get("channel")
            if not channel_name:
                return Response("Missing channel name", status=400)

            # auto-create listener page with dynamic JS if needed
            return FileResponse("static/listener.html")

        @self.app.get("/host")
        async def host(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            return FileResponse("static/host.html")

        @self.app.get("/playlists")
        def get_playlists(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            try:
                playlists = [
                    name
                    for name in os.listdir(MUSIC_BASE_DIR)
                    if os.path.isdir(os.path.join(MUSIC_BASE_DIR, name))
                ]
                return {"playlists": playlists}
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.post("/command")
        async def command(
            request: Request,
            _: None = Depends(self.login_required),
        ):
            data = await request.json()
            cmd = data.get("command")
            channel_name = data.get("channel")
            playlist = data.get("playlist")
            if not channel_name:
                return {"error": "Missing channel name"}, 400
            try:
                channel = self._get_channel(channel_name)
                if playlist:
                    path = os.path.join(MUSIC_BASE_DIR, playlist)
                    if not os.path.isdir(path):
                        return {"error": f"Invalid playlist path: {path}"}, 400
                    channel.play_playlist(path, self.streamers)
                elif cmd:
                    channel.send_command(cmd, self.streamers)
                else:
                    return {"error": "Missing command or playlist"}, 400
                return {"status": "ok", "channel": channel_name}
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.get("/stream")
        async def stream(request: Request):
            channel_name = request.query_params.get("channel")
            if not channel_name:
                return Response(content="Missing channel name", status_code=400)

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


# === Main Entrypoint ===
if __name__ == "__main__":
    service = RadioWebService()
    logger.info("Server running at http://localhost:5000")
    uvicorn.run(service.app, host="0.0.0.0", port=5000)
