import array
import datetime as dt
import http.client
import json
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from server.audio import Engine, RATE, decode, pcm_bytes
from server.app import StationServer
from server.copilot import research, script, validate_claim
from server.store import Store
from scripts.seed_demo import seed


class StationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        seed(cls.fixture.name)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        shutil.copytree(self.fixture.name, self.temp.name, dirs_exist_ok=True)
        self.store = Store(self.temp.name)
        self.engine = Engine(self.store)
        self.tracks = self.store.snapshot()['tracks']

    def tearDown(self):
        self.engine.close()
        self.store.close()
        self.temp.cleanup()

    def test_restart_persistence(self):
        other = Store(self.temp.name)
        self.assertEqual(other.snapshot()['active_playlist'], self.store.snapshot()['active_playlist'])
        self.assertEqual(len(other.snapshot()['tracks']), 5)
        other.close()

    def test_decode_and_limiter(self):
        samples = decode(self.store.root/'media'/self.tracks[0]['file'])
        self.assertEqual(len(samples), 24*RATE)
        self.assertEqual(struct.unpack('<hhh', pcm_bytes([50000,-50000,12])), (32767,-32767,12))

    def test_crossfade_advances_both_decks_and_rotates(self):
        e = self.engine
        e.load(0, self.tracks[0]['id'], True)
        e.load(1, self.tracks[1]['id'])
        e.running = True
        e.decks[0]['pos'] = len(e.decks[0]['samples']) - 512
        data = e.render(1024)
        self.assertGreater(max(array.array('h', data)), 100)
        self.assertIsNone(e.decks[0])
        self.assertEqual(e.current, 1)
        self.assertGreater(e.decks[1]['pos'], 0)
        self.assertEqual(len(self.store.snapshot()['history']), 1)

    def test_rotation_only_uses_playlist(self):
        ids = [t['id'] for t in self.tracks[:3]]
        self.assertEqual([self.engine.next_track() for _ in range(4)], ids+[ids[0]])

    def test_schedule_priority_end_boundary(self):
        with self.store.lock:
            self.store.data['schedules'] = [dict(id='a', name='Low', days=[0], start=480, end=600, priority=1, playlist='low'), dict(id='b', name='High', days=[0], start=540, end=570, priority=5, playlist='high')]
        self.assertEqual(self.engine.schedule(dt.datetime(2026,11,16,9,0)), 'high')
        self.assertEqual(self.engine.schedule(dt.datetime(2026,11,16,9,30)), 'low')
        self.assertEqual(self.engine.schedule(dt.datetime(2026,11,16,10,0)), self.store.data['active_playlist'])

    def test_live_lease_contention_expiry_and_audio(self):
        e = self.engine
        e.acquire_live('a')
        with self.assertRaises(ValueError):
            e.acquire_live('b')
        e.live('a', pcm_bytes([10000]*1024))
        self.assertEqual(array.array('h', e.render())[0], 8000)
        e.live_until = time.monotonic()-1
        self.assertEqual(set(e.render()), {0})
        self.assertIsNone(e.live_owner)
        with self.assertRaises(ValueError):
            e.live('a', b'\0\0')

    def test_live_ducking_preserves_music_and_recovers(self):
        e = self.engine
        e.running = True
        e.autodj = False
        e.decks[0] = dict(track=self.tracks[0], samples=array.array('h', [10000]*4096), pos=0, playing=True, gain=1)
        self.assertEqual(array.array('h', e.render())[0], 8000)
        e.acquire_live('voice')
        e.live('voice', pcm_bytes([0]*1024))
        self.assertEqual(array.array('h', e.render())[0], 1440)
        e.release_live('voice')
        self.assertEqual(array.array('h', e.render())[0], 8000)

    def test_slow_listener_bounded(self):
        q = self.engine.subscribe()
        self.assertEqual(q.maxsize, 22)
        self.engine.unsubscribe(q)
        self.assertEqual(len(self.engine.listeners), 0)

    def test_script_and_editorial_gate(self):
        self.assertNotIn('inspir', script(self.tracks[0], [], 30)['text'])
        c = validate_claim(dict(text='La memoria puede ser una lectura posible.',kind='interpretation',url='https://example.org/source',reviewer='Editor'))
        result = script(self.tracks[0], [c], 15)
        self.assertIn('Una posible lectura', result['text'])
        self.assertEqual(result['sources'], ['https://example.org/source'])
        for url in ('javascript:alert(1)', 'http://example.com', 'https://user:pass@example.com'):
            with self.assertRaises(ValueError):
                validate_claim(dict(text='test',kind='fact',url=url,reviewer='Editor'))

    def test_research_citations_remain_draft(self):
        def provider(payload):
            self.assertEqual(payload['tools'], [{'type':'web_search'}])
            return {'output':[{'type':'message','content':[{'type':'output_text','text':'Contexto [1]','annotations':[{'type':'url_citation','url':'https://example.org','title':'Source','start_index':9,'end_index':12}]}]}]}
        r = research(self.tracks[0], provider)
        self.assertEqual(r['status'],'draft')
        self.assertEqual(r['citations'][0]['url'],'https://example.org')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg is not installed locally')
    def test_ffmpeg_import(self):
        source=self.store.root/'media'/self.tracks[0]['file']
        target=self.store.root/'fixture.mp3'
        subprocess.run(['ffmpeg','-v','error','-i',str(source),str(target)],check=True)
        self.assertGreater(len(decode(target)), RATE)


class HTTPCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        seed(cls.fixture.name)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        shutil.copytree(self.fixture.name, self.temp.name, dirs_exist_ok=True)
        self.store = Store(self.temp.name)
        self.server = StationServer(('127.0.0.1', 0), self.store, 'test-station-token-123456789')
        self.server.engine.start()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.cookie = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.engine.close()
        self.server.server_close()
        self.store.close()
        self.temp.cleanup()

    def request(self,path,body=None,headers=None,raw=False):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        h={'Content-Type':'application/json','Cookie':self.cookie,'X-Radio-Request':'1'}
        h.update(headers or {})
        c.request('GET' if body is None else 'POST',path,body if raw else (json.dumps(body) if body is not None else None),h)
        r=c.getresponse()
        data=r.read()
        cookie=r.getheader('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        status=r.status
        c.close()
        try:return status,json.loads(data)
        except ValueError:return status,data

    def login(self):
        self.assertEqual(self.request('/api/login',{'token':'test-station-token-123456789'})[0],200)

    def test_auth_static_paths_and_csrf(self):
        self.assertEqual(self.request('/api/state')[0],401)
        self.assertEqual(self.request('/api/login',{'token':'wrong'})[0],401)
        self.assertEqual(self.request('/')[0],200)
        self.assertEqual(self.request('/../data/station.sqlite3')[0],404)
        self.login()
        self.assertEqual(self.request('/api/state')[0],200)
        self.assertEqual(self.request('/api/transport',{'action':'start'}, {'X-Radio-Request':''})[0],400)
        self.assertEqual(self.request('/api/transport',{'action':'settings','master':9})[0],400)
        self.assertEqual(self.request('/api/deck',{'deck':-1,'action':'play'})[0],400)
        self.assertEqual(self.request('/api/logout',{})[0],200)
        self.assertEqual(self.request('/api/state')[0],401)

    def test_playlist_schedule_research_disabled(self):
        self.login()
        tid=self.store.snapshot()['tracks'][0]['id']
        code,p=self.request('/api/playlists',{'name':'Morning','tracks':[tid]})
        self.assertEqual(code,201)
        self.assertEqual(self.request('/api/playlist/activate',{'id':p['id']})[0],200)
        self.assertEqual(self.request('/api/playlist/activate',{'id':None})[0],200)
        self.assertEqual(self.request('/api/schedules',{'name':'Daily','playlist':p['id'],'days':[0,1],'start':540,'end':600,'priority':2})[0],201)
        self.assertEqual(self.request('/api/schedules',{'name':'Invalid','playlist':p['id'],'days':[7],'start':540,'end':600})[0],400)
        with patch.dict(os.environ, {'OPENAI_API_KEY':''}):
            code,body=self.request('/api/research',{'track':tid})
            self.assertEqual(code,400)
            self.assertIn('OPENAI_API_KEY',body['error'])
        self.assertEqual(self.request('/api/script',{'track':tid,'seconds':30})[0],200)

    def test_upload_range_jingle_and_monitor(self):
        self.login()
        t=self.store.snapshot()['tracks'][0]
        raw=(self.store.root/'media'/t['file']).read_bytes()
        status,track=self.request('/api/upload',raw,{'X-Title':'Imported','X-Artist':'Test','X-Kind':'jingle'},raw=True)
        self.assertEqual(status,201)
        code,data=self.request('/media/'+track['id'],headers={'Range':'bytes=0-43'})
        self.assertEqual(code,206)
        self.assertEqual(data[:4],b'RIFF')
        self.assertEqual(len(data),44)
        self.assertEqual(self.request('/api/jingle',{'track':track['id']})[0],200)
        self.assertEqual(self.request('/api/transport',{'action':'start'})[0],200)
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        c.request('GET','/stream.wav')
        r=c.getresponse()
        self.assertEqual(r.status,200)
        self.assertEqual(r.read(4),b'RIFF')
        self.assertGreater(len(r.read(2048)),0)
        c.close()
        time.sleep(.5)
        self.assertTrue(self.server.engine.thread.is_alive())
        self.assertTrue(any(d and d['pos']>0 for d in self.server.engine.decks))

    def test_live_pcm_and_fallback(self):
        self.login()
        self.assertEqual(self.request('/api/live/acquire',{})[0],200)
        self.assertEqual(self.request('/api/live/chunk',pcm_bytes([3000]*4096),raw=True)[0],200)
        self.assertTrue(self.server.engine.status()['live'])
        self.assertEqual(self.request('/api/live/release',{})[0],200)
        self.assertFalse(self.server.engine.status()['live'])


if __name__ == '__main__':
    unittest.main()
