import queue
import os
import time
import random
import threading
import subprocess
from flask import Flask, Response, send_from_directory, request, stream_with_context
from gevent import pywsgi
from gevent.monkey import patch_all
from typing import Callable

from config import (
    AVAILABLE_CHANNELS,
    MUSIC_BASE_DIR,
    LISTENER_QUEUE_MAXSIZE,
    SILENT_BUFFER,
    CHUNK_SIZE,
)

patch_all()

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
                print(f"[!] Folder '{self.playlist_path}' not found.")
                time.sleep(5)
                continue

            playlist = sorted([
                f for f in os.listdir(self.playlist_path)
                if f.lower().endswith((".mp3", ".wav", ".ogg", ".flac"))
            ])

            if not playlist:
                print("[!] No audio files found. Waiting...")
                time.sleep(5)
                continue

            random.shuffle(playlist)

            for track in playlist:
                track_path = os.path.join(self.playlist_path, track)
                print(f"🎶 Now playing: {track}")

                proc = subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-loglevel", "quiet", "-re",
                    "-i", track_path, "-vn", "-acodec", "libmp3lame",
                    "-ar", "44100", "-b:a", "128k", "-f", "mp3", "-"
                ], stdout=subprocess.PIPE)

                while True:
                    try:
                        cmd = self.command_queue.get_nowait()
                        if cmd == "stop":
                            proc.kill()
                            print("[Streamer] Stopped.")
                            return
                        elif cmd == "next":
                            print("[Streamer] Skipping track.")
                            proc.kill()
                            break
                        elif cmd.startswith("change"):
                            new_dir = cmd[len("change"):].strip()
                            if os.path.isdir(new_dir):
                                print(f"[Streamer] Changing directory to: {new_dir}")
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
                        print("[Streamer] End of track reached.")
                        break

                    if time.time() - last_listener_time > self.IDLE_TIMEOUT:
                        print(f"[Streamer] No listeners for {self.IDLE_TIMEOUT} seconds. Exiting.")
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

        if playlist_path not in streamers or not streamers[playlist_path].thread.is_alive():
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
        self.app = Flask(__name__, static_folder="static")
        self.channels = {name: Channel(name) for name in AVAILABLE_CHANNELS}
        self.streamers = {}
        self._define_routes()

    def _get_channel(self, name: str) -> Channel:
        if name not in self.channels:
            raise ValueError(f"Channel '{name}' not found.")
        return self.channels[name]

    def _define_routes(self):
        @self.app.route("/")
        def index():
            return send_from_directory(".", "index.html")

        @self.app.route("/listen")
        def listen():
            return send_from_directory(".", "listener.html")

        @self.app.route("/host")
        def host():
            return send_from_directory(".", "host.html")

        @self.app.route("/channels")
        def list_channels():
            return {"channels": AVAILABLE_CHANNELS}

        @self.app.route("/playlists")
        def get_playlists():
            try:
                playlists = [
                    name for name in os.listdir(MUSIC_BASE_DIR)
                    if os.path.isdir(os.path.join(MUSIC_BASE_DIR, name))
                ]
                return {"playlists": playlists}
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.route("/command", methods=["POST"])
        def command():
            data = request.json
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

        @self.app.route("/stream")
        def stream():
            channel_name = request.args.get("channel")
            if not channel_name:
                return Response("Missing channel name", status=400)
            try:
                channel = self._get_channel(channel_name)
                playlist = channel.current_playlist
                if not playlist or playlist not in self.streamers:
                    return Response("Channel not active", status=400)

                q = queue.Queue(maxsize=LISTENER_QUEUE_MAXSIZE)
                self.streamers[playlist].add_listener(channel_name, q)

                try:
                    q.put_nowait(SILENT_BUFFER)
                except queue.Full:
                    pass

                def generate():
                    print(f"[Stream] Client connected to {channel_name}")
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

                return Response(
                    stream_with_context(generate()),
                    mimetype="audio/mpeg",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                )
            except Exception as e:
                return Response(str(e), status=500)


# === Main Entrypoint ===
if __name__ == "__main__":
    service = RadioWebService()
    server = pywsgi.WSGIServer(
        ("0.0.0.0", 5000),
        service.app,
    )
    print("📡 Gevent radio server running at https://strahdradiolocal.farreachco.com")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Main] Keyboard interrupt received. Exiting.")
