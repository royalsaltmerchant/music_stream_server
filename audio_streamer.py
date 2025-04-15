import subprocess
import time
import random
import queue
import threading
import os
from config import CHUNK_SIZE
from typing import Callable


# === Streamer Class ===
class AudioStreamer:
    active_channels = set()
    IDLE_TIMEOUT = 600  # seconds (10 minutes)

    def __init__(self, playlist_path: str, get_channels_list_CB: Callable):
        self.playlist_path = playlist_path
        self.get_channels_list_CB = get_channels_list_CB
        self._active = True
        self.command_queue = queue.Queue()
        self.listener_registry = {}
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
                    if chunk:
                        for ch_name, channel in self.get_channels_list_CB():
                            if channel.current_playlist == self.playlist_path:
                                if channel.listener_queues:
                                    last_listener_time = time.time()
                                for q in channel.listener_queues:
                                    try:
                                        q.put_nowait(chunk)
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
                    active_channels = [ch for ch, channel in self.get_channels_list_CB() if channel.current_playlist == self.playlist_path]
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