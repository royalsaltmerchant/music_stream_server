import threading
import queue
import os
from config import AVAILABLE_CHANNELS, MUSIC_BASE_DIR, LISTENER_QUEUE_MAXSIZE, SILENT_BUFFER
from channel import Channel
from flask import Flask, Response, send_from_directory, request, stream_with_context


# === Web Service ===
class RadioWebService:
    def __init__(self):
        self.app = Flask(__name__, static_folder="static")
        # Init Channles
        self.channels = {name: Channel(name=name, get_channels_list_CB=self.get_channels_list) for name in AVAILABLE_CHANNELS}

        self.listener_registry = {}
        self.streamers = {}
        RadioWebService.instance = self
        self._define_routes()

    def get_channels_list(self) -> list:
        return self.channels.items()

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
