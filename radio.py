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
TRACK_HEADER_BUFFER_SIZE = 100  # ~100KB of buffered start audio

# === Global State ===
listener_queues = set()
command_queue = queue.Queue()
listener_lock = threading.Lock()
track_header_buffer = []

def list_playlists(base_path="music\strahd"):
    return [
        name for name in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, name))
    ]

# === Streaming Thread with Infinite Shuffle Loop ===
def audio_streamer(initial_dir: str):
    global track_header_buffer
    music_dir = initial_dir

    while True:
        if not os.path.exists(music_dir):
            print(f"[!] Folder '{music_dir}' not found.")
            time.sleep(5)
            continue

        playlist = sorted([
            f for f in os.listdir(music_dir)
            if f.lower().endswith(('.mp3', '.wav', '.ogg', '.flac'))
        ])

        if not playlist:
            print("[!] No audio files found in /music. Waiting...")
            time.sleep(5)
            continue

        random.shuffle(playlist)

        for track in playlist:
            track_path = os.path.join(music_dir, track)
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
                # Check for commands during playback
                try:
                    cmd = command_queue.get_nowait()
                    if cmd == "stop":
                        proc.kill()
                        print("[Streamer] Received stop during playback.")
                        return
                    elif cmd == "next":
                        print("[Streamer] Received next command during playback")
                        break
                    elif cmd.startswith("change"):
                        new_dir = cmd[len("change"):].strip()
                        if os.path.isdir(new_dir):
                            music_dir = new_dir
                            proc.kill()
                            print(f"[Streamer] Directory changed to: {new_dir}")
                            break
                        else:
                            print(f"[Streamer] Invalid directory: {new_dir}")
                except queue.Empty:
                    pass

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

@app.route('/listen')
def listen():
    return send_from_directory('.', 'listener.html')

@app.route('/host')
def host():
    return send_from_directory('.', 'host.html')

@app.route('/playlists')
def get_playlists():
    return {"playlists": list_playlists()}

@app.route('/command', methods=['POST'])
def command():
    cmd = request.json.get("command")
    if not cmd:
        return {"error": "No command provided"}, 400
    command_queue.put(cmd)
    return {"status": "ok", "received": cmd}

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
    args = sys.argv
    music_dir = args[1]
    threading.Thread(target=audio_streamer, args=(music_dir,), daemon=True).start()
    threading.Thread(
        target=app.run,
        kwargs={"host": "0.0.0.0", "port": 8000, "threaded": True},
        daemon=True
    ).start()
    time.sleep(2)
    print("📡 Flask radio server running at http://localhost:8000")
    try:
        while True:
            cmd = input("Enter command (next, change, stop, quit): ")
            command_queue.put(cmd)
            if cmd == "quit":
                print("[Main] Exiting app")
                time.sleep(1)
                sys.exit(0)  # Will stop all threads and Flask too
    except KeyboardInterrupt:
        print("\n[Main] Keyboard interrupt received. Exiting.")
        sys.exit(0)
