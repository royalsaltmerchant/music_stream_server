import logging

from streamer import AudioStreamer

logger = logging.getLogger("radio")


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
