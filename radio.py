import threading
import subprocess
import time
import queue
import os
import random
from flask import Flask, Response, send_from_directory

# === Config ===
MUSIC_FOLDER = "music"
CHUNK_SIZE = 1024
LISTENER_QUEUE_MAXSIZE = 256
TRACK_HEADER_BUFFER_SIZE = 100  # ~100KB of buffered start audio

# === Global State ===
listener_queues = set()
listener_lock = threading.Lock()
track_header_buffer = []

# === Streaming Thread with Infinite Shuffle Loop ===
def audio_streamer():
    global track_header_buffer

    while True:
        if not os.path.exists(MUSIC_FOLDER):
            print(f"[!] Folder '{MUSIC_FOLDER}' not found.")
            time.sleep(5)
            continue

        playlist = sorted([
            f for f in os.listdir(MUSIC_FOLDER)
            if f.lower().endswith(('.mp3', '.wav', '.ogg', '.flac'))
        ])

        if not playlist:
            print("[!] No audio files found in /music. Waiting...")
            time.sleep(5)
            continue

        random.shuffle(playlist)

        for track in playlist:
            track_path = os.path.join(MUSIC_FOLDER, track)
            print(f"🎶 Now playing: {track}")
            track_header_buffer = []

            proc = subprocess.Popen(
                [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'quiet',
                    '-re',
                    '-i', track_path,
                    '-vn',
                    '-acodec', 'libmp3lame',
                    '-ar', '44100',
                    '-b:a', '128k',
                    '-f', 'mp3',
                    '-write_xing', '0',
                    '-fflags', '+bitexact',
                    '-flags', '+bitexact',
                    '-map_metadata', '-1',
                    '-map', 'a',
                    '-'
                ],
                stdout=subprocess.PIPE
            )

            chunk_count = 0
            while True:
                chunk = proc.stdout.read(CHUNK_SIZE)
                if not chunk:
                    break

                if chunk_count < TRACK_HEADER_BUFFER_SIZE:
                    track_header_buffer.append(chunk)
                    chunk_count += 1

                with listener_lock:
                    for q in list(listener_queues):
                        try:
                            q.put_nowait(chunk)
                        except queue.Full:
                            pass

            proc.kill()

# === Flask App ===
app = Flask(__name__)

@app.route('/')
def index():
    return send_from_directory('.', 'listener.html')

@app.route('/stream')
def stream():
    client_queue = queue.Queue(maxsize=LISTENER_QUEUE_MAXSIZE)
    with listener_lock:
        listener_queues.add(client_queue)

    # Send buffered header chunks first
    for chunk in track_header_buffer:
        try:
            client_queue.put_nowait(chunk)
        except queue.Full:
            break

    def generate():
        try:
            while True:
                yield client_queue.get(timeout=5)
        except queue.Empty:
            pass
        finally:
            with listener_lock:
                listener_queues.discard(client_queue)

    return Response(generate(), mimetype="audio/mpeg")

# === Launch ===
if __name__ == "__main__":
    threading.Thread(target=audio_streamer, daemon=True).start()
    print("📡 Flask radio server running at http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, threaded=True)
