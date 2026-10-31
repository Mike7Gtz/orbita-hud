"""Three independent sampling loops; no credentials or audio recordings on disk."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from .config import load, runtime_dir, write_state
from .telemetry import Collector
from .audio import AudioWorker
from .quotas import codex_usage, claude_usage, flatten


def alive():
    path = runtime_dir()/'daemon.lock'
    with path.open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True


def ensure(root):
    if alive():
        return
    with (runtime_dir()/'daemon.log').open('w') as log:
        subprocess.Popen([sys.executable, str(root/'runner.py'), 'daemon'],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)


def reload_settings():
    try:
        pid = int((runtime_dir()/'daemon.pid').read_text())
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if len(args)>2 and b'orbita-hud' in args[1].lower() and args[1].endswith(b'/runner.py') and args[2]==b'daemon':
            os.kill(pid, signal.SIGHUP)
    except (OSError, ValueError):
        pass


def widgets_running():
    root = Path(__file__).resolve().parents[2]
    expected = {os.fsencode(str(root/'conkyrc-clock')), os.fsencode(str(root/'conkyrc-panel'))}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p/'cmdline').read_bytes().split(b'\0')
            if args and Path(os.fsdecode(args[0])).name == 'conky' and expected.intersection(args):
                return True
        except OSError:
            pass
    return False


def run():
    folder = runtime_dir()
    with (folder/'daemon.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        (folder/'daemon.pid').write_text(str(os.getpid()))
        cfg = load()
        stop = threading.Event()
        reload = threading.Event()
        signal.signal(signal.SIGHUP, lambda *_: reload.set())
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        def usage():
            providers = {'chatgpt': None, 'claude': None}
            while not stop.is_set():
                for name in providers:
                    try:
                        if name == 'chatgpt':
                            if not cfg['usage']['codex_enabled']:
                                raise RuntimeError('disabled')
                            providers[name] = codex_usage(cfg['usage']['codex_socket'])
                        else:
                            providers[name] = claude_usage(cfg)
                    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError):
                        pass
                values = {'generated_at': time.time(), 'stale_seconds': cfg['usage']['stale_seconds']}
                for name, data in providers.items():
                    values.update(flatten(name, data or {}, cfg['usage']['stale_seconds']))
                write_state(folder/'usage.state', values)
                stop.wait(cfg['usage']['interval_seconds'])
        audio = AudioWorker(cfg, folder, stop)
        audio.start()
        thread = threading.Thread(target=usage, name='orbita-quotas', daemon=True)
        thread.start()
        collector = Collector()
        last_widget = time.monotonic()
        try:
            while not stop.is_set():
                if reload.is_set():
                    reload.clear()
                    try:
                        new = load()
                        audio_changed = new['audio'] != cfg['audio']
                        for key in cfg:
                            cfg[key].update(new[key])
                        if audio_changed:
                            audio.close()
                    except (ValueError, OSError):
                        pass
                values = collector.sample()
                values['side'] = cfg['appearance']['side']
                write_state(folder/'telemetry.state', values)
                if widgets_running():
                    last_widget = time.monotonic()
                elif time.monotonic()-last_widget > 60:
                    break
                stop.wait(1)
        finally:
            stop.set()
            audio.close()
            audio.join(timeout=5)
            thread.join(timeout=20)
            (folder/'daemon.pid').unlink(missing_ok=True)
