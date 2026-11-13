import argparse
import hashlib
import hmac
import io
import json
import logging
import os
import queue
import secrets
import threading
import time
import uuid
import wave
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .audio import Engine, RATE, decode, pcm_bytes, wav_header
from .store import Store
from .copilot import research, script, validate_claim

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def label(value, limit=120):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, 'Texto vacío o demasiado largo')
    return value.strip()


class StationServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store, token):
        require(len(token) >= 16, 'RADIO_TOKEN debe contener al menos 16 caracteres')
        self.store, self.token = store, token
        self.engine = Engine(store, os.environ.get('STATION_TIMEZONE', 'America/Bogota'))
        self.sessions, self.failures = {}, {}
        self.auth_lock = threading.Lock()
        self.research_gate = threading.BoundedSemaphore(1)
        self.research_at = 0
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'RadioComun/1.0'

    def log_message(self, fmt, *args):
        # Never log credentials, request bodies or query strings.
        logging.info('%s %s', self.command, urlsplit(self.path).path)

    def headers_common(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; media-src 'self' blob:; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
        self.send_header('Cache-Control', 'no-store')

    def respond(self, obj, status=200, cookie=None):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(data)

    def body(self, max_size=1_000_000):
        length = int(self.headers.get('Content-Length', '-1'))
        require(0 <= length <= max_size, 'Tamaño de solicitud no admitido')
        raw = self.rfile.read(length)
        require(len(raw) == length, 'Solicitud incompleta')
        return raw

    def json_body(self):
        obj = json.loads(self.body())
        require(isinstance(obj, dict), 'Se esperaba un objeto JSON')
        return obj

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            return None
        value = cookie.get('rc_session')
        sid = value.value if value else None
        with self.server.auth_lock:
            expires = self.server.sessions.get(sid, 0)
        return sid if expires > time.time() else None

    def authenticated(self):
        sid = self.session()
        if not sid:
            self.respond({'error': 'Inicia sesión'}, 401)
        return sid

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == '/health':
                return self.respond({'ok': self.server.engine.thread is not None and self.server.engine.thread.is_alive()})
            if path.startswith('/api/'):
                if not self.authenticated():
                    return
                if path == '/api/state':
                    return self.respond(dict(station=self.server.store.snapshot(), audio=self.server.engine.status(), capabilities=dict(ai=bool(os.environ.get('OPENAI_API_KEY')), ffmpeg=__import__('shutil').which('ffmpeg') is not None)))
                return self.respond({'error': 'Ruta inexistente'}, 404)
            if path == '/stream.wav':
                # Public listener output. Studio commands and raw media remain authenticated.
                q = self.server.engine.subscribe()
                try:
                    self.send_response(200)
                    self.headers_common()
                    self.send_header('Content-Type', 'audio/wav')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(wav_header())
                    self.wfile.flush()
                    while not self.server.engine.stop_event.is_set():
                        self.wfile.write(q.get(timeout=3))
                        self.wfile.flush()
                finally:
                    self.server.engine.unsubscribe(q)
                return
            if path.startswith('/media/'):
                if not self.authenticated():
                    return
                track = self.server.store.track(path.removeprefix('/media/'))
                if not track:
                    return self.respond({'error': 'Pista inexistente'}, 404)
                file = self.server.store.root / 'media' / track['file']
                return self.send_file(file, 'audio/wav')
            files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/mic-worklet.js': ('mic-worklet.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if path not in files:
                return self.respond({'error': 'Ruta inexistente'}, 404)
            filename, mime = files[path]
            self.send_file(PUBLIC / filename, mime)
        except (BrokenPipeError, ConnectionResetError, queue.Empty):
            pass
        except ValueError as e:
            self.respond({'error': str(e)}, 400)
        except Exception:
            logging.exception('GET failed')
            self.respond({'error': 'Error interno'}, 500)

    def send_file(self, path, mime):
        # Byte ranges allow independent deck cue/seek playback.
        total = path.stat().st_size
        start, end, status = 0, total-1, 200
        r = self.headers.get('Range')
        if r:
            import re
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', r)
            require(match is not None, 'Rango inválido')
            start = int(match[1])
            end = min(total-1, int(match[2])) if match[2] else total-1
            if not 0 <= start <= end < total:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{total}')
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end-start+1))
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{total}')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start)
            remaining = end-start+1
            while remaining:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            # JSON + custom header required for commands; SameSite cookie and no CORS.
            if path == '/api/login':
                require(self.headers.get('Content-Type', '').startswith('application/json'), 'Se requiere JSON')
                data = self.json_body()
                address = self.client_address[0]
                with self.server.auth_lock:
                    now = time.time()
                    self.server.failures = {k:v for k,v in self.server.failures.items() if v[1] > now-60}
                    n, stamp = self.server.failures.get(address, (0, now))
                    if n >= 10:
                        return self.respond({'error': 'Demasiados intentos; espera un minuto'}, 429)
                    if not hmac.compare_digest(str(data.get('token', '')), self.server.token):
                        self.server.failures[address] = (n+1, stamp)
                        return self.respond({'error': 'Clave incorrecta'}, 401)
                    sid = secrets.token_urlsafe(32)
                    self.server.sessions = {k:v for k,v in self.server.sessions.items() if v > now}
                    self.server.sessions[sid] = now+43200
                secure = '; Secure' if os.environ.get('COOKIE_SECURE') == '1' else ''
                return self.respond({'ok': True}, cookie=f'rc_session={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200{secure}')
            sid = self.authenticated()
            if not sid:
                return
            require(self.headers.get('X-Radio-Request') == '1', 'Falta cabecera de protección')
            store, engine = self.server.store, self.server.engine
            if path == '/api/logout':
                engine.release_live(sid)
                with self.server.auth_lock:
                    self.server.sessions.pop(sid, None)
                return self.respond({'ok': True}, cookie='rc_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path == '/api/upload':
                # Raw upload avoids multipart parser ambiguity and arbitrary file paths.
                import urllib.parse
                title = label(urllib.parse.unquote(self.headers.get('X-Title', '')))
                artist = label(urllib.parse.unquote(self.headers.get('X-Artist', '')))
                kind = self.headers.get('X-Kind', 'music')
                require(kind in ('music', 'jingle'), 'Tipo inválido')
                raw = self.body(80_000_000)
                ident = uuid.uuid4().hex
                temp = store.root / 'media' / (ident+'.upload')
                try:
                    temp.write_bytes(raw)
                    samples = decode(temp)
                    filename = ident+'.wav'
                    with wave.open(str(store.root / 'media' / filename), 'wb') as w:
                        w.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                        w.writeframes(pcm_bytes(samples))
                finally:
                    temp.unlink(missing_ok=True)
                t = dict(id=ident, title=title, artist=artist, kind=kind, file=filename, duration=len(samples)/RATE)
                with store.lock:
                    store.data['tracks'].append(t)
                    store.save()
                return self.respond(t, 201)
            if path == '/api/live/chunk':
                raw = self.body(RATE*2)
                require(len(raw)%2 == 0, 'PCM16 incompleto')
                engine.live(sid, raw)
                return self.respond({'ok': True})
            d = self.json_body()
            if path == '/api/transport':
                with engine.lock:
                    action = d.get('action')
                    require(action in ('start', 'stop', 'skip', 'settings'), 'Acción desconocida')
                    if action == 'start':
                        engine.running = True
                    elif action == 'stop':
                        engine.running = False
                    elif action == 'skip':
                        engine.decks[engine.current] = None
                        engine.current = 1-engine.current
                    elif action == 'settings':
                        if 'autodj' in d:
                            require(isinstance(d['autodj'], bool), 'AutoDJ inválido')
                            engine.autodj = d['autodj']
                        for key, lo, hi in [('crossfade', .2, 12), ('master', 0, 1), ('manual_mix', 0, 1)]:
                            if key in d:
                                v = float(d[key])
                                require(lo <= v <= hi, 'Nivel fuera de rango')
                                setattr(engine, key, v)
                return self.respond(engine.status())
            if path == '/api/deck':
                idx = d.get('deck')
                require(type(idx) is int and idx in (0, 1), 'Deck inválido')
                if d.get('action') == 'load':
                    require(not engine.autodj, 'Desactiva AutoDJ antes de cargar manualmente')
                    engine.load(idx, d.get('track'))
                else:
                    with engine.lock:
                        deck = engine.decks[idx]
                        require(deck is not None, 'Deck vacío')
                        if d.get('action') == 'play':
                            deck['playing'] = not deck['playing']
                        elif d.get('action') == 'cue':
                            deck['pos'], deck['playing'] = 0, False
                        elif d.get('action') == 'gain':
                            gain = float(d.get('value'))
                            require(0 <= gain <= 1.5, 'Ganancia fuera de rango')
                            deck['gain'] = gain
                        else:
                            raise ValueError('Acción de deck desconocida')
                return self.respond(engine.status())
            if path == '/api/jingle':
                t = store.track(d.get('track'))
                require(t is not None and t['kind'] == 'jingle', 'Jingle inexistente')
                samples = decode(store.root / 'media' / t['file'])
                with engine.lock:
                    require(len(engine.jingles) < 4, 'Máximo 4 jingles simultáneos')
                    engine.jingles.append(dict(samples=samples, pos=0))
                return self.respond({'ok': True})
            if path == '/api/live/acquire':
                engine.acquire_live(sid)
                return self.respond({'lease_seconds': 3, 'sample_rate': RATE})
            if path == '/api/live/release':
                engine.release_live(sid)
                return self.respond({'ok': True})
            if path == '/api/playlists':
                name = label(d.get('name'))
                ids = d.get('tracks')
                require(isinstance(ids, list) and 0 < len(ids) <= 500 and all(isinstance(x, str) and store.track(x) for x in ids), 'Selecciona pistas válidas')
                p = dict(id=uuid.uuid4().hex, name=name, tracks=ids)
                with store.lock:
                    store.data['playlists'].append(p)
                    store.save()
                return self.respond(p, 201)
            if path == '/api/playlist/activate':
                require(d.get('id') is None or any(p['id'] == d.get('id') for p in store.snapshot()['playlists']), 'Lista inexistente')
                with store.lock:
                    store.data['active_playlist'] = d['id']
                    store.save()
                return self.respond({'ok': True})
            if path == '/api/schedules':
                require(any(p['id'] == d.get('playlist') for p in store.snapshot()['playlists']), 'Lista inexistente')
                days = d.get('days')
                require(isinstance(days, list) and days and all(type(x) is int and 0 <= x <= 6 for x in days), 'Días inválidos')
                start, end, priority = d.get('start'), d.get('end'), d.get('priority', 0)
                require(all(type(v) is int for v in (start, end, priority)) and 0 <= start < end <= 1440 and 0 <= priority <= 100, 'Horario inválido; divide bloques nocturnos en dos')
                s = dict(id=uuid.uuid4().hex, name=label(d.get('name')), playlist=d['playlist'], days=days, start=start, end=end, priority=priority)
                with store.lock:
                    store.data['schedules'].append(s)
                    store.save()
                return self.respond(s, 201)
            if path == '/api/schedule/delete':
                with store.lock:
                    store.data['schedules'] = [s for s in store.data['schedules'] if s['id'] != d.get('id')]
                    store.save()
                return self.respond({'ok': True})
            if path in ('/api/research', '/api/claim', '/api/script'):
                track = store.track(d.get('track'))
                require(track is not None, 'Pista inexistente')
                if path == '/api/research':
                    if not self.server.research_gate.acquire(blocking=False):
                        return self.respond({'error': 'Ya hay una investigación en curso'}, 429)
                    try:
                        if time.monotonic()-self.server.research_at < 15:
                            return self.respond({'error': 'Espera 15 segundos entre consultas'}, 429)
                        self.server.research_at = time.monotonic()
                        result = research(track)
                        with store.lock:
                            dossier = store.data['dossiers'].setdefault(track['id'], {'claims': []})
                            dossier['research'] = result
                            store.save()
                    finally:
                        self.server.research_gate.release()
                elif path == '/api/claim':
                    claim = validate_claim(d.get('claim'))
                    with store.lock:
                        dossier = store.data['dossiers'].setdefault(track['id'], {'claims': []})
                        dossier['claims'].append(claim)
                        store.save()
                    result = claim
                else:
                    claims = store.snapshot()['dossiers'].get(track['id'], {}).get('claims', [])
                    result = script(track, claims, d.get('seconds', 30))
                    result.update(id=uuid.uuid4().hex, track=track['id'], created=time.time())
                    with store.lock:
                        store.data['scripts'] = (store.data['scripts'] + [result])[-100:]
                        store.save()
                return self.respond(result)
            return self.respond({'error': 'Ruta inexistente'}, 404)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
            self.respond({'error': str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception('Command failed')
            self.respond({'error': 'Error de servicio; consulta el registro del servidor'}, 502)


def main():
    parser = argparse.ArgumentParser(description='RadioComún station server')
    parser.add_argument('--host', default=os.environ.get('HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '8080')))
    parser.add_argument('--data', default=os.environ.get('RADIO_DATA', 'data'))
    args = parser.parse_args()
    token = os.environ.get('RADIO_TOKEN', '')
    if len(token) < 16:
        parser.error('Configura RADIO_TOKEN con al menos 16 caracteres')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    store = Store(args.data)
    server = StationServer((args.host, args.port), store, token)
    server.engine.start()
    logging.info('RadioComún: http://%s:%s', args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.engine.close()
        server.server_close()
        store.close()


if __name__ == '__main__':
    main()
