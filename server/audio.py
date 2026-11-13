"""Small real-time PCM mixer: server-owned clock, independent of browser lifetime."""
import array
import datetime as dt
import io
import logging
import math
import queue
import shutil
import struct
import subprocess
import sys
import threading
import time
import wave
from zoneinfo import ZoneInfo

RATE = 22050
BLOCK = 1024
LOG = logging.getLogger(__name__)


def pcm_bytes(samples):
    out = array.array('h', (max(-32767, min(32767, int(x))) for x in samples))
    if sys.byteorder != 'little':
        out.byteswap()
    return out.tobytes()


def decode(path):
    # Native WAV path makes the demo run without FFmpeg. Production imports use FFmpeg.
    try:
        with wave.open(str(path), 'rb') as w:
            if w.getparams()[:3] == (1, 2, RATE):
                data = w.readframes(w.getnframes())
            else:
                raise ValueError('Needs FFmpeg conversion')
    except (wave.Error, EOFError, ValueError):
        if not shutil.which('ffmpeg'):
            raise ValueError('Instala FFmpeg para importar este formato; WAV mono PCM16 22050 Hz funciona sin él')
        p = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-t', '1800', '-f', 's16le', '-ar', str(RATE), '-ac', '1', 'pipe:1'], capture_output=True, timeout=90)
        if p.returncode:
            raise ValueError('Archivo de audio no válido')
        data = p.stdout
    samples = array.array('h')
    samples.frombytes(data)
    if sys.byteorder != 'little':
        samples.byteswap()
    if not 1 <= len(samples) / RATE <= 1800:
        raise ValueError('Duración admitida: 1 a 1800 segundos')
    return samples


def wav_header():
    return b'RIFF' + struct.pack('<I', 0xffffffff) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, RATE, RATE*2, 2, 16) + b'data' + struct.pack('<I', 0xffffffff - 36)


class Engine:
    def __init__(self, store, timezone='America/Bogota'):
        self.store, self.zone = store, ZoneInfo(timezone)
        self.lock = threading.RLock()
        self.decks = [None, None]
        self.current = 0
        self.running = False
        self.autodj = True
        self.crossfade = 3.0
        self.manual_mix = None
        self.master = 0.8
        self.jingles = []
        self.listeners = set()
        self.events = []
        self.peak = 0
        self.error = None
        self.last_scheduled = None
        self.rotation = {}
        self.live_owner = None
        self.live_until = 0
        self.live_buffer = array.array('h')
        self.stop_event = threading.Event()
        self.thread = None
        self.last_fill = 0
        self.last_schedule_check = 0

    def emit(self, msg):
        self.events = (self.events + [{'time': time.time(), 'message': msg}])[-30:]

    def load(self, deck, ident, playing=False):
        track = self.store.track(ident)
        if not track:
            raise ValueError('Pista inexistente')
        samples = decode(self.store.root / 'media' / track['file'])
        with self.lock:
            self.decks[deck] = dict(track=track, samples=samples, pos=0, playing=playing, gain=1.0)
            self.emit('Cargada: ' + track['title'])

    def schedule(self, now=None):
        now = now or dt.datetime.now(self.zone)
        day, minute = now.weekday(), now.hour*60+now.minute
        state = self.store.snapshot()
        eligible = [s for s in state['schedules'] if day in s['days'] and s['start'] <= minute < s['end']]
        selected = max(eligible, key=lambda s: (s['priority'], s['start'], s['id']), default=None)
        key = selected['id'] if selected else None
        if key != self.last_scheduled:
            self.last_scheduled = key
            self.rotation.clear()
            self.emit('Parrilla: ' + (selected['name'] if selected else 'rotación base'))
        return selected['playlist'] if selected else state['active_playlist']

    def next_track(self):
        playlist_id = self.schedule()
        state = self.store.snapshot()
        playlist = next((p for p in state['playlists'] if p['id'] == playlist_id), None)
        ids = playlist['tracks'] if playlist else [t['id'] for t in state['tracks'] if t['kind'] == 'music']
        if not ids:
            return None
        i = self.rotation.get(playlist_id, 0)
        self.rotation[playlist_id] = i + 1
        return ids[i % len(ids)]

    def fill(self):
        # Decode outside the real-time thread; slow disks/codecs cannot stall the output clock.
        for i in range(2):
            with self.lock:
                needed = self.running and self.autodj and self.decks[i] is None
            if needed:
                ident = self.next_track()
                if ident:
                    try:
                        self.load(i, ident, i == self.current)
                    except Exception as e:
                        with self.lock:
                            self.error = str(e)
                            self.emit('Audio omitido: ' + str(e))

    def maintenance(self):
        while not self.stop_event.wait(.3):
            try:
                self.fill()
            except Exception:
                LOG.exception('AutoDJ maintenance failure')

    def acquire_live(self, owner):
        with self.lock:
            if self.live_owner and self.live_until > time.monotonic() and self.live_owner != owner:
                raise ValueError('Otro locutor tiene el micrófono')
            self.live_owner, self.live_until = owner, time.monotonic() + 3

    def live(self, owner, data):
        with self.lock:
            if self.live_owner != owner or self.live_until < time.monotonic():
                raise ValueError('Adquiere el micrófono antes de enviar audio')
            a = array.array('h')
            a.frombytes(data)
            if sys.byteorder != 'little':
                a.byteswap()
            if len(self.live_buffer) + len(a) > RATE * 2:
                raise ValueError('Buffer de micrófono lleno')
            self.live_buffer.extend(a)
            self.live_until = time.monotonic() + 3

    def release_live(self, owner):
        with self.lock:
            if self.live_owner == owner:
                self.live_owner = None
                self.live_buffer = array.array('h')

    def render(self, count=BLOCK):
        with self.lock:
            live = bool(self.live_owner and self.live_until > time.monotonic())
            if not live:
                self.live_owner = None
                self.live_buffer = array.array('h')
            out = [0.] * count
            if self.running:
                cur, nxt = self.decks[self.current], self.decks[1-self.current]
                if cur and self.autodj:
                    cur['playing'] = True
                    remaining = (len(cur['samples']) - cur['pos']) / RATE
                    if nxt and remaining <= self.crossfade:
                        nxt['playing'] = True
                for n in range(count):
                    cur = self.decks[self.current]
                    remaining = (len(cur['samples']) - cur['pos']) / RATE if cur else 999
                    blend = max(0., min(1., 1-remaining / max(.01, self.crossfade))) if self.autodj and self.decks[1-self.current] else 0
                    gains = [0., 0.]
                    gains[self.current], gains[1-self.current] = math.cos(blend*math.pi/2), math.sin(blend*math.pi/2)
                    if self.manual_mix is not None and not self.autodj:
                        gains = [math.cos(self.manual_mix*math.pi/2), math.sin(self.manual_mix*math.pi/2)]
                    for i, d in enumerate(self.decks):
                        if d and d['playing'] and d['pos'] < len(d['samples']):
                            out[n] += d['samples'][d['pos']] * gains[i] * d['gain'] * (.18 if live else 1)
                            d['pos'] += 1
                for i, d in enumerate(self.decks):
                    if d and d['pos'] >= len(d['samples']):
                        with self.store.lock:
                            self.store.data['history'] = (self.store.data['history'] + [dict(track=d['track']['id'], title=d['track']['title'], ended=time.time())])[-200:]
                            self.store.save()
                        self.decks[i] = None
                        if i == self.current:
                            self.current = 1-i
                for j in self.jingles:
                    chunk = j['samples'][j['pos']:j['pos']+count]
                    for n, v in enumerate(chunk):
                        out[n] += v * .65
                    j['pos'] += len(chunk)
                self.jingles = [j for j in self.jingles if j['pos'] < len(j['samples'])]
            if live:
                chunk = self.live_buffer[:count]
                del self.live_buffer[:count]
                for n, v in enumerate(chunk):
                    out[n] += v
            out = [v*self.master for v in out]
            self.peak = min(1, max((abs(v) for v in out), default=0)/32767)
            return pcm_bytes(out)

    def subscribe(self):
        q = queue.Queue(maxsize=22)
        with self.lock:
            if len(self.listeners) >= 20:
                raise ValueError('Máximo 20 monitores directos; usa Icecast para más oyentes')
            self.listeners.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.listeners.discard(q)

    def start(self):
        def loop():
            deadline = time.monotonic()
            while not self.stop_event.is_set():
                try:
                    data = self.render()
                    with self.lock:
                        for q in list(self.listeners):
                            if q.full():
                                q.get_nowait()
                            q.put_nowait(data)
                except Exception as e:
                    self.error = str(e)
                    LOG.exception('Audio render failure')
                deadline += BLOCK/RATE
                self.stop_event.wait(max(0, deadline-time.monotonic()))
                if time.monotonic()-deadline > 1:
                    deadline = time.monotonic()
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()
        self.worker = threading.Thread(target=self.maintenance, daemon=True)
        self.worker.start()

    def status(self):
        with self.lock:
            return dict(running=self.running, autodj=self.autodj, crossfade=self.crossfade, master=self.master, peak=self.peak, current=self.current,
                        decks=[dict(track=d['track'], position=d['pos']/RATE, duration=len(d['samples'])/RATE, playing=d['playing'], gain=d['gain']) if d else None for d in self.decks],
                        live=bool(self.live_owner and self.live_until > time.monotonic()), listeners=len(self.listeners), error=self.error, events=self.events[-8:])

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(3)
            self.worker.join(3)
