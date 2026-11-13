"""Reconnect public PCM output to Icecast using a streaming MP3 encoder."""
import os
import signal
import subprocess
import time
from urllib.parse import quote


def main():
    password = os.environ['ICECAST_SOURCE_PASSWORD']
    host = os.environ.get('ICECAST_HOST', 'icecast')
    port = int(os.environ.get('ICECAST_PORT', '8000'))
    mount = os.environ.get('ICECAST_MOUNT', 'radio.mp3')
    # FFmpeg URLs carry the secret inside this container's process list, never in logs.
    target = f'icecast://source:{quote(password, safe="")}@{host}:{port}/{quote(mount, safe="")}'
    proc = None
    stop = False
    def shutdown(*_):
        nonlocal stop
        stop = True
        if proc and proc.poll() is None:
            proc.terminate()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    while not stop:
        proc = subprocess.Popen(['ffmpeg','-nostdin','-loglevel','quiet','-i',os.environ.get('RADIO_STREAM','http://radio:8080/stream.wav'),'-vn','-ac','1','-ar','44100','-c:a','libmp3lame','-b:a','128k','-content_type','audio/mpeg','-f','mp3',target])
        proc.wait()
        if not stop:
            print('Puente de streaming desconectado; reintentando en 5 s', flush=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
