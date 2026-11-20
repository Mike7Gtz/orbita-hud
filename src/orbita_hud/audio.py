import json
import math
import os
import struct
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
    backend = 'numpy'

    def __init__(self, bars=128, rate=22050, samples=1024, gain=1):
        import numpy as np
        self.np, self.bars, self.rate, self.samples, self.gain = np, bars, rate, samples, gain
        self.window = np.hanning(samples)
        self.edges = np.geomspace(45, 9500, bars+1)
        self.values = np.zeros(bars)

    def process(self, raw):
        if len(raw) != self.samples * 2:
            return None
        np = self.np
        samples = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32768
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

    def close(self):
        pass


class FftwSpectrum:
    backend = 'fftw'

    def __init__(self, bars=128, rate=22050, samples=1024, gain=1):
        import ctypes

        self.library = ctypes.CDLL('libfftw3.so.3')
        double_ptr = ctypes.POINTER(ctypes.c_double)
        plan = self.library.fftw_plan_dft_r2c_1d
        plan.argtypes = [ctypes.c_int, double_ptr, double_ptr, ctypes.c_uint]
        plan.restype = ctypes.c_void_p
        self.library.fftw_execute.argtypes = [ctypes.c_void_p]
        self.library.fftw_execute.restype = None
        self.library.fftw_destroy_plan.argtypes = [ctypes.c_void_p]
        self.library.fftw_destroy_plan.restype = None

        self.samples, self.gain = samples, gain
        self.pcm = struct.Struct(f'<{samples}h')
        bin_count = samples // 2 + 1
        self.input = (ctypes.c_double * samples)()
        self.output = (ctypes.c_double * (2 * bin_count))()
        self.window = ((1 / 32768,) if samples == 1 else
                       tuple((1 - math.cos(2 * math.pi * i / (samples - 1))) / 65536 for i in range(samples)))
        edges = [int(45 * (9500 / 45)**(i / bars) * samples / rate) for i in range(bars + 1)]
        self.ranges = [(max(1, lo), min(bin_count, max(2, lo + 1, hi))) for lo, hi in zip(edges, edges[1:])]
        self.magnitudes = [0.] * bin_count
        self.values = [0.] * bars
        fftw_estimate = 1 << 6  # FFTW_ESTIMATE from fftw3.h
        self.plan = plan(samples, self.input, self.output, fftw_estimate)
        if not self.plan:
            raise RuntimeError('fftw_plan_unavailable')

    def process(self, raw):
        if len(raw) != self.pcm.size:
            return None
        power = 0
        for i, sample in enumerate(self.pcm.unpack(raw)):
            power += sample * sample
            self.input[i] = sample * self.window[i]
        rms = math.sqrt(power / self.samples) / 32768
        self.library.fftw_execute(self.plan)
        for i in range(self.ranges[-1][1]):
            self.magnitudes[i] = math.hypot(self.output[2*i], self.output[2*i+1]) / self.samples
        silence = .75 if rms < .00003 else 1
        for i, (lo, hi) in enumerate(self.ranges):
            energy = 0.
            for j in range(lo, hi):
                energy = max(energy, self.magnitudes[j])
            db = 20*math.log10(max(energy, 1e-8))
            level = max(0, min(1, (db+70)/58*self.gain))
            before = self.values[i]
            weight = .72 if level > before else .18
            self.values[i] = (before + weight * (level - before)) * silence
        return self.values.copy(), rms

    def close(self):
        if self.plan:
            self.library.fftw_destroy_plan(self.plan)
            self.plan = None


def new_spectrum(**options):
    try:
        return FftwSpectrum(**options)
    except (OSError, AttributeError, RuntimeError):
        return Spectrum(**options)


class AudioWorker(threading.Thread):
    def __init__(self, cfg, folder, stop):
        super().__init__(daemon=True, name='orbita-audio')
        self.settings, self.folder, self.stop = cfg['audio'].copy(), folder, stop
        self.proc = None

    def close(self):
        proc = self.proc
        if proc and proc.poll() is None:
            proc.terminate()

    def run(self):
        path = self.folder/'audio.state'
        settings = self.settings
        env = dict(os.environ, LC_ALL='C.UTF-8')
        while not self.stop.is_set():
            spectrum = None
            try:
                if not settings['enabled']:
                    write_state(path, {'generated_at': time.time(), 'available': False, 'reason': 'disabled'})
                    return
                r = subprocess.run(['pactl', '--format=json', 'list', 'sources'], capture_output=True, text=True, timeout=3, check=True, env=env)
                sink = subprocess.run(['pactl', 'get-default-sink'], capture_output=True, text=True, timeout=3, check=True, env=env).stdout.strip()
                source = choose_monitor(settings, json.loads(r.stdout), sink)
                if self.stop.is_set():
                    break
                spectrum = new_spectrum(bars=settings['bars'], gain=float(settings['gain']))
                self.proc = subprocess.Popen(['parec', '--raw', '--format=s16le', '--rate=22050', '--channels=1',
                                              '--latency-msec=50', '--device='+source], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                check = time.monotonic()
                while not self.stop.is_set():
                    raw = self.proc.stdout.read(2048)
                    if len(raw) != 2048 or self.stop.is_set():
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
                if spectrum:
                    spectrum.close()
                self.close()
                if self.proc:
                    try:
                        self.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.proc.kill(); self.proc.wait()
                    self.proc.stdout.close()
                    self.proc = None
            self.stop.wait(3)
