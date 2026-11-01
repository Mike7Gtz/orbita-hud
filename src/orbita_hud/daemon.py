"""Three independent sampling loops; no credentials or audio recordings on disk."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from .config import load, layout, runtime_dir, write_state
from .telemetry import Collector, apply_temperature_scales
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


def stop(root):
    """Upgrade only our installed worker; never signal an unrelated PID."""
    try:
        pid = int((runtime_dir()/'daemon.pid').read_text())
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if len(args)<3 or args[1]!=os.fsencode(str(root/'runner.py')) or args[2]!=b'daemon':
            return
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic()+22
        while alive() and time.monotonic()<deadline:
            time.sleep(.1)
        if alive():
            raise RuntimeError('El muestreador anterior sigue cerrándose; vuelve a instalar en unos segundos.')
    except (FileNotFoundError, ProcessLookupError, ValueError):
        pass


def widgets_running(kind=None):
    root = Path(__file__).resolve().parents[2]
    kinds = [kind] if kind else ['clock', 'panel']
    expected = {os.fsencode(str(root/f'conkyrc-{k}')) for k in kinds}
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


class PanelWatcher:
    def __init__(self, cfg, root):
        self.cfg, self.root, self.previous = cfg, root, None

    def poll(self):
        current = layout(self.cfg, 'panel')
        changed = self.previous is not None and current != self.previous
        self.previous = current
        if changed and widgets_running('panel'):
            subprocess.Popen([sys.executable, str(self.root/'runner.py'), 'start', '--widget', 'panel'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return True
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
            errors = {}
            next_codex=0
            next_claude=0
            while not stop.is_set():
                for name in providers:
                    current=time.monotonic()
                    if name=='chatgpt' and current<next_codex: continue
                    if name=='claude' and current<next_claude: continue
                    if name=='chatgpt': next_codex=current+cfg['usage']['interval_seconds']
                    if name=='claude': next_claude=current+(cfg['usage']['interval_seconds'] if cfg['usage']['claude_command'] else 1)
                    try:
                        if name == 'chatgpt':
                            if not cfg['usage']['codex_enabled']:
                                raise RuntimeError('disabled')
                            providers[name] = codex_usage(cfg['usage']['codex_socket'], binary=cfg['usage']['codex_binary'])
                        else:
                            providers[name] = claude_usage(cfg)
                        errors[name] = ''
                    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
                        # Diagnostics without raw provider responses or credentials.
                        reason=str(error)
                        errors[name] = reason if reason in {'codex_not_installed','codex_binary_not_executable','codex_account_unavailable','codex_usage_timeout','claude_not_connected','disabled'} else type(error).__name__
                values = {'generated_at': time.time(), 'stale_seconds': cfg['usage']['stale_seconds']}
                for name, data in providers.items():
                    values.update(flatten(name, data or {}, cfg['usage']['stale_seconds']))
                    values[name+'.error'] = errors.get(name, '')
                write_state(folder/'usage.state', values)
                stop.wait(1)
        audio = AudioWorker(cfg, folder, stop)
        audio.start()
        thread = threading.Thread(target=usage, name='orbita-quotas', daemon=True)
        thread.start()
        collector = Collector()
        last_widget = time.monotonic()
        next_layout = 0
        root = Path(__file__).resolve().parents[2]
        watcher = PanelWatcher(cfg, root)
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
                values = apply_temperature_scales(collector.sample(),cfg)
                # /proc/uptime and CLOCK_BOOTTIME include suspend. The renderer
                # interpolates between samples without spawning a clock process.
                values['clock.boottime'] = time.clock_gettime(time.CLOCK_BOOTTIME)
                values['side'] = cfg['appearance']['side']
                write_state(folder/'telemetry.state', values)
                if time.monotonic() >= next_layout:
                    watcher.poll()
                    next_layout = time.monotonic()+3
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
