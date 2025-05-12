import queue
import os
from config import (
    AVAILABLE_CHANNELS,
    MUSIC_BASE_DIR,
    LISTENER_QUEUE_MAXSIZE,
    SILENT_BUFFER,
)
from channel import Channel
from flask import Flask, Response, send_from_directory, request, stream_with_context

from gevent import pywsgi
from gevent.monkey import patch_all

patch_all()


# === Web Service ===
class RadioWebService:
    def __init__(self):
        self.app = Flask(__name__, static_folder="static")
        self.channels = {
            name: Channel(name=name, get_channels_list_CB=self.get_channels_list)
            for name in AVAILABLE_CHANNELS
        }

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

        @self.app.route("/")
        def index():
            return send_from_directory(".", "index.html")

        @self.app.route("/channels")
        def list_channels():
            return {"channels": AVAILABLE_CHANNELS}

        @self.app.route("/listen")
        def listen():
            return send_from_directory(".", "listener.html")

        @self.app.route("/playlists")
        def get_playlists():
            try:
                playlists = [
                    name
                    for name in os.listdir(MUSIC_BASE_DIR)
                    if os.path.isdir(os.path.join(MUSIC_BASE_DIR, name))
                ]
                return {"playlists": playlists}
            except Exception as e:
                return {"error": str(e)}, 500

        @self.app.route("/host")
        def host():
            return send_from_directory(".", "host.html")

        @self.app.route("/command", methods=["POST"])
        def command():
            cmd = request.json.get("command")
            channel_name = request.json.get("channel")
            playlist = request.json.get("playlist")
            if not channel_name:
                return {"error": "Missing channel name"}, 400
            try:
                channel = self._get_channel(channel_name)
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

        @self.app.route("/stream")
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
                    print("[Stream] Client connected:", channel_name)
                    try:
                        yield SILENT_BUFFER
                        while True:
                            try:
                                chunk = client_queue.get(timeout=5)
                            except queue.Empty:
                                chunk = SILENT_BUFFER
                            yield chunk
                    finally:
                        self.channels[channel_name].listener_queues.discard(
                            client_queue
                        )

                response = Response(
                    stream_with_context(generate()), mimetype="audio/mpeg"
                )
                response.headers.update(
                    {
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    }
                )
                return response

            except Exception as e:
                return Response(str(e), status=500)


# === Main Entry Point ===
if __name__ == "__main__":
    web_service = RadioWebService()

    server = pywsgi.WSGIServer(
        ("0.0.0.0", 443),
        web_service.app,
        certfile="/etc/letsencrypt/live/strahdradiolocal.farreachco.com/fullchain.pem",
        keyfile="/etc/letsencrypt/live/strahdradiolocal.farreachco.com/privkey.pem"
    )

    print("📡 Gevent radio server running at https://strahdradiolocal.farreachco.com")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Main] Keyboard interrupt received. Exiting.")
