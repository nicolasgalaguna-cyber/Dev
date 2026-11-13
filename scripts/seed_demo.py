"""Generate original synthetic CC0 demo audio; no copyrighted music downloads."""
import argparse
import math
import sys
import uuid
import wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.audio import RATE, pcm_bytes
from server.store import Store


def seed(root):
    store = Store(root)
    if store.snapshot()['tracks']:
        store.close()
        return
    tracks = []
    specs = [('Horizonte común', 220, 24, 'music'), ('Patio sonoro', 293.66, 22, 'music'), ('Luz de barrio', 164.81, 26, 'music'), ('Identidad · RadioComún', 440, 3, 'jingle'), ('Señal de encuentro', 660, 2, 'jingle')]
    for title, freq, duration, kind in specs:
        ident = uuid.uuid4().hex
        def samples():
            for i in range(RATE*duration):
                t = i/RATE
                envelope = min(1, t/.08, (duration-t)/.2)
                pulse = .7+.3*math.sin(2*math.pi*2*t)
                yield 8500*envelope*pulse*(math.sin(2*math.pi*freq*t)+.25*math.sin(2*math.pi*freq*1.5*t))
        with wave.open(str(store.root/'media'/(ident+'.wav')), 'wb') as w:
            w.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            w.writeframes(pcm_bytes(samples()))
        tracks.append(dict(id=ident, title=title, artist='RadioComún · demo sintética CC0', file=ident+'.wav', duration=duration, kind=kind))
    pid = uuid.uuid4().hex
    with store.lock:
        store.data['tracks'] = tracks
        store.data['playlists'] = [dict(id=pid, name='Selección de la casa · DEMO', tracks=[t['id'] for t in tracks if t['kind']=='music'])]
        store.data['active_playlist'] = pid
        store.save()
    store.close()
    print('Demo creada: 3 piezas sintéticas y 2 jingles CC0. No se inicia la emisión automáticamente.')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', default='data')
    seed(p.parse_args().data)
