from audio_streamer import AudioStreamer
from typing import Callable


# === Channel Class ===
class Channel:
    def __init__(self, name: str, get_channels_list_CB: Callable):
        self.name = name
        self.current_playlist = None
        self.listener_queues = set()
        self.get_channels_list_CB = get_channels_list_CB

    def play_playlist(self, playlist_path: str, streamers: dict):
        if self.current_playlist == playlist_path:
            return
        self.current_playlist = playlist_path
        if playlist_path not in streamers:
            streamers[playlist_path] = AudioStreamer(
                playlist_path=playlist_path,
                get_channels_list_CB=self.get_channels_list_CB,
            )
            streamers[playlist_path].start()

    def send_command(self, cmd: str, streamers: dict):
        if self.current_playlist and self.current_playlist in streamers:
            streamers[self.current_playlist].put_command(cmd)
