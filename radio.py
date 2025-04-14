import threading
import subprocess
import time
import queue
import os
import sys
import random
from flask import Flask, Response, send_from_directory, request

# === Config ===
CHUNK_SIZE = 1024
LISTENER_QUEUE_MAXSIZE = 256
SILENCE_PATH = "silence.mp3"
MUSIC_BASE_DIR = os.path.join("music", "strahd")
AVAILABLE_CHANNELS = ["alpha", "beta", "gamma", "delta", "epsilon"]

# === Load Silence Buffer ===
with open(SILENCE_PATH, "rb") as f:
    SILENT_BUFFER = f.read()

# === Streamer Class ===
class AudioStreamer:
    active_channels = set()
    IDLE_TIMEOUT = 600  # seconds (10 minutes)

    def __init__(self, playlist_path: str, listener_registry: dict, stream_id: str):
        self.playlist_path = playlist_path
        self.stream_id = stream_id
        self._active = True
        self.command_queue = queue.Queue()
        self.listener_registry = listener_registry
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def _run(self):
        last_listener_time = time.time()
        while True:
            

            if not os.path.exists(self.playlist_path):
                print(f"[!] Folder '{self.playlist_path}' not found.")
                time.sleep(5)
                continue

            playlist = sorted([
                f for f in os.listdir(self.playlist_path)
                if f.lower().endswith(('.mp3', '.wav', '.ogg', '.flac'))
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
                    'ffmpeg', '-hide_banner', '-loglevel', 'quiet',
                    '-re', '-i', track_path, '-vn',
                    '-acodec', 'libmp3lame', '-ar', '44100', '-b:a', '128k',
                    '-f', 'mp3', '-'], stdout=subprocess.PIPE)

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
                            else:
                                print(f"[Streamer] Invalid directory: {new_dir}")
                    except queue.Empty:
                        pass

                    chunk = proc.stdout.read(CHUNK_SIZE)
                    delivered = False
                    if chunk:
                        for ch_name, channel in RadioWebService.instance.channels.items():
                            if channel.current_playlist == self.playlist_path:
                                if channel.listener_queues:
                                    last_listener_time = time.time()
                                for q in channel.listener_queues:
                                    try:
                                        q.put_nowait(chunk)
                                        delivered = True
                                    except queue.Full:
                                        pass
                                    except queue.Full:
                                        pass
                    if not chunk:
                        print("[Streamer] End of track reached (no more data).")
                        break


                    # Check for idle timeout
                    if time.time() - last_listener_time > self.IDLE_TIMEOUT:
                        print(f"[Streamer] No listeners for {self.IDLE_TIMEOUT} seconds. Shutting down {self.playlist_path}.")
                        proc.kill()
                        return

                    to_remove = []
                    active_channels = [ch for ch, channel in RadioWebService.instance.channels.items() if channel.current_playlist == self.playlist_path]
                    for q, ch_name in self.listener_registry.items():
                        if ch_name in active_channels:
                            try:
                                q.put_nowait(chunk)
                            except queue.Full:
                                to_remove.append(q)
                    for q in to_remove:
                        self.listener_registry.pop(q, None)

                proc.kill()

                

    def put_command(self, cmd: str):
        self.command_queue.put(cmd)

# === Channel Class ===
class Channel:
    def __init__(self, name: str, listener_registry: dict):
        self.name = name
        self.current_playlist = None
        self.listener_queues = set()
        self.name = name
        self.listener_registry = listener_registry
        self.current_playlist = None
        self.name = name
        self.listener_registry = listener_registry
        self.current_playlist = None

    def play_playlist(self, playlist_path: str, streamers: dict):
        if self.current_playlist == playlist_path:
            return
        self.current_playlist = playlist_path
        if playlist_path not in streamers:
            streamers[playlist_path] = AudioStreamer(playlist_path, self.listener_registry, playlist_path)
            streamers[playlist_path].start()

    def send_command(self, cmd: str, streamers: dict):
        if self.current_playlist and self.current_playlist in streamers:
            streamers[self.current_playlist].put_command(cmd)

# === Web Service ===
class RadioWebService:
    def __init__(self):
        self.app = Flask(__name__, static_folder="static")
        self.channels = {name: Channel(name, {}) for name in AVAILABLE_CHANNELS}
        self.listener_registry = {}
        self.streamers = {}
        RadioWebService.instance = self
        self._define_routes()

    def _get_channel(self, name: str) -> Channel:
        if name not in self.channels:
            raise ValueError(f"Channel '{name}' is not available.")
        return self.channels[name]

    def _define_routes(self):
        self.streamers = {}
        @self.app.route('/')
        def index():
            return send_from_directory('.', 'index.html')
        @self.app.route('/channels')
        def list_channels():
            return {"channels": AVAILABLE_CHANNELS}
        @self.app.route('/listen')
        def listen():
            return send_from_directory('.', 'listener.html')

        @self.app.route('/playlists')
        def get_playlists():
            try:
                playlists = [
                    name for name in os.listdir(MUSIC_BASE_DIR)
                    if os.path.isdir(os.path.join(MUSIC_BASE_DIR, name))
                ]
                return {"playlists": playlists}
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.route('/host')
        def host():
            return send_from_directory('.', 'host.html')

        @self.app.route('/command', methods=['POST'])
        def command():
            cmd = request.json.get("command")
            channel_name = request.json.get("channel")
            playlist = request.json.get("playlist")
            if not channel_name:
                return {"error": "Missing channel name"}, 400
            try:
                channel = channel = self._get_channel(channel_name)
                if playlist:
                    playlist_path = os.path.join(MUSIC_BASE_DIR, playlist)
                    if not os.path.isdir(playlist_path):
                        return {"error": f"Invalid playlist path: {playlist_path}"}, 400
                    channel.play_playlist(playlist_path, self.streamers)
                elif cmd:
                    channel.send_command(cmd, self.streamers)
                else:
                    return {"error": "Missing command or playlist"}, 400
                return {"status": "ok", "channel": channel_name}
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.route('/stream')
        def stream():
            channel_name = request.args.get("channel")
            if not channel_name:
                return Response("Missing channel name", status=400)
            try:
                self._get_channel(channel_name)
                client_queue = queue.Queue(maxsize=LISTENER_QUEUE_MAXSIZE)
                self.channels[channel_name].listener_queues.add(client_queue)

                try:
                    client_queue.put_nowait(SILENT_BUFFER)
                except queue.Full:
                    pass

                def generate():
                    try:
                        yield SILENT_BUFFER
                        while True:
                            chunk = client_queue.get(timeout=5)
                            yield chunk
                    except queue.Empty:
                        pass
                    finally:
                        self.channels[channel_name].listener_queues.discard(client_queue)

                from flask import stream_with_context

                headers = {
                    "Content-Type": "audio/mpeg",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Transfer-Encoding": "chunked",
                }

                return Response(
                    stream_with_context(generate()),
                    headers=headers,
                    direct_passthrough=True
                )
            except Exception as e:
                return Response(str(e), status=500)

    def start(self):
        threading.Thread(
            target=self.app.run,
            kwargs={"host": "0.0.0.0", "port": 8000, "threaded": True},
            daemon=True
        ).start()

# === Main Entry Point ===
if __name__ == "__main__":
    web_service = RadioWebService()
    web_service.start()

    print("📡 Flask radio server running at http://localhost:8000")

    try:
        while True:
            cmd = input("Enter command: ")
            if cmd == "quit":
                print("[Main] Exiting app")
                break
    except KeyboardInterrupt:
        print("\n[Main] Keyboard interrupt received. Exiting.")
