import json
import math
import os
import subprocess
import threading
import time
from .config import write_state


def choose_monitor(settings, sources, default_sink):
    # PulseAudio and PipeWire's pactl JSON expose different monitor fields.
    monitors = [s['name'] for s in sources if
                s.get('properties', {}).get('device.class') == 'monitor' or
                str(s.get('monitor_of_sink', '')) not in {'', '-1', '4294967295', 'None', 'n/a'}]
    wanted = settings.get('monitor') or default_sink + '.monitor'
    if wanted in monitors:
        return wanted
    if settings.get('monitor'):
        raise RuntimeError('audio_source_is_not_an_output_monitor')
    if monitors:
        return monitors[0]
    raise RuntimeError('no_output_monitor')


class Spectrum:
    def __init__(self, bars=128, rate=22050, samples=1024, gain=1):
        import numpy as np
        self.np, self.bars, self.rate, self.samples, self.gain = np, bars, rate, samples, gain
        self.window = np.hanning(samples)
        self.edges = np.geomspace(45, 9500, bars+1)
        self.values = np.zeros(bars)

    def process(self, raw):
        np = self.np
        samples = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32768
        if len(samples) != self.samples:
            return None
        rms = float(np.sqrt(np.mean(samples**2)))
        bins = np.abs(np.fft.rfft(samples * self.window)) / self.samples
        levels = []
        for low, high in zip(self.edges[:-1], self.edges[1:]):
            i = max(1, int(low*self.samples/self.rate))
            j = max(i+1, int(high*self.samples/self.rate))
            energy = float(np.max(bins[i:j])) if i < len(bins) else 0
            db = 20*math.log10(max(energy, 1e-8))
            levels.append(max(0, min(1, (db+70)/58*self.gain)))
        levels = np.array(levels)
        weights = np.where(levels > self.values, .72, .18)
        self.values += weights * (levels-self.values)
        if rms < 0.00003:
            self.values *= .75
        return self.values.tolist(), rms


class AudioWorker(threading.Thread):
    def __init__(self, cfg, folder, stop):
        super().__init__(daemon=True, name='orbita-audio')
        self.cfg, self.folder, self.stop = cfg, folder, stop
        self.proc = None

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def run(self):
        path = self.folder/'audio.state'
        settings = self.cfg['audio']
        env = dict(os.environ, LC_ALL='C.UTF-8')
        while not self.stop.is_set():
            try:
                if not settings['enabled']:
                    write_state(path, {'generated_at': time.time(), 'available': False, 'reason': 'disabled'})
                    return
                spectrum = Spectrum(bars=settings['bars'], gain=float(settings['gain']))
                r = subprocess.run(['pactl', '--format=json', 'list', 'sources'], capture_output=True, text=True, timeout=3, check=True, env=env)
                sink = subprocess.run(['pactl', 'get-default-sink'], capture_output=True, text=True, timeout=3, check=True, env=env).stdout.strip()
                source = choose_monitor(settings, json.loads(r.stdout), sink)
                self.proc = subprocess.Popen(['parec', '--raw', '--format=s16le', '--rate=22050', '--channels=1',
                                              '--latency-msec=50', '--device='+source], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                check = time.monotonic()
                while not self.stop.is_set():
                    raw = self.proc.stdout.read(2048)
                    if len(raw) != 2048:
                        break
                    values, rms = spectrum.process(raw)
                    write_state(path, {'generated_at': time.time(), 'available': True, 'count': settings['bars'], 'rms': round(rms, 6),
                                       'source': source, 'bands': ','.join(f'{v:.3f}' for v in values)})
                    if time.monotonic()-check > 4:
                        current = subprocess.run(['pactl', 'get-default-sink'], capture_output=True, text=True, timeout=3, env=env).stdout.strip()
                        if not settings['monitor'] and current != sink:
                            break
                        check = time.monotonic()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, ImportError):
                write_state(path, {'generated_at': time.time(), 'available': False, 'reason': 'output_monitor_unavailable'})
            finally:
                self.close()
                if self.proc:
                    try:
                        self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.proc.kill(); self.proc.wait()
                    self.proc.stdout.close()
                    self.proc = None
            self.stop.wait(3)
