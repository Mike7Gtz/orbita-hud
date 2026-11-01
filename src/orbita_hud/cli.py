import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from .config import load, layout, monitor, workarea, runtime_dir, config_dir, write_state
from . import daemon

ROOT = Path(__file__).resolve().parents[2]


def owned_widgets(root=ROOT):
    expected = {str(root/'conkyrc-clock'), str(root/'conkyrc-panel')}
    result = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p/'cmdline').read_bytes().split(b'\0')
            if args and Path(os.fsdecode(args[0])).name == 'conky' and expected.intersection(map(os.fsdecode, args)):
                result.append(int(p.name))
        except OSError:
            pass
    return result


def terminate_widgets(pids):
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic()+3
    while time.monotonic()<deadline and any(Path(f'/proc/{pid}').exists() for pid in pids):
        time.sleep(.05)


def stop_widgets(root=ROOT):
    terminate_widgets(owned_widgets(root))


def start(kind='all'):
    if kind == 'all':
        kinds = ['clock', 'panel']
    else:
        kinds = [kind]
    folder = runtime_dir()
    # Stop only windows belonging to this installed copy.
    previous=[]
    for pid in owned_widgets():
        try:
            args = Path(f'/proc/{pid}/cmdline').read_bytes()
            if any(os.fsencode(str(ROOT/f'conkyrc-{k}')) in args.split(b'\0') for k in kinds):
                previous.append(pid)
        except (OSError, ProcessLookupError):
            pass
    terminate_widgets(previous)
    daemon.ensure(ROOT)
    daemon.reload_settings()
    for kind in kinds:
        with (folder/f'{kind}.log').open('w') as log:
            subprocess.Popen(['conky', '-c', str(ROOT/f'conkyrc-{kind}')],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    print('Órbita HUD iniciado: ' + ', '.join(kinds))


def install(autostart=False):
    target = Path.home()/'.conky/Orbita-HUD'
    if target.resolve() != ROOT.resolve():
        daemon.stop(target)
        stop_widgets(target)
        if target.exists():
            backup = target.with_name('Orbita-HUD.backup-'+time.strftime('%Y%m%d-%H%M%S'))
            shutil.copytree(target, backup)
        target.mkdir(parents=True, exist_ok=True)
        for name in ('src', 'conky', 'runner.py', 'conkyrc-clock', 'conkyrc-panel',
                     'config.example.toml', 'README.md', 'LICENSE', 'CREDITS.md', 'CHANGELOG.md'):
            source = ROOT/name
            if source.is_dir():
                shutil.copytree(source, target/name, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copy2(source, target/name)
    cfg = config_dir()
    cfg.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not (cfg/'config.toml').exists():
        shutil.copy2(ROOT/'config.example.toml', cfg/'config.toml')
    if autostart:
        folder = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'autostart'
        folder.mkdir(parents=True, exist_ok=True)
        escaped = str(target/'runner.py').replace('\\', '\\\\').replace('"', '\\"')
        (folder/'orbita-hud.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Órbita HUD\n'
            f'Exec=python3 "{escaped}" start\nX-GNOME-Autostart-Delay=8\nTerminal=false\n')
    print('Instalado: '+str(target))


def doctor():
    result = {name: bool(shutil.which(name)) for name in ('conky', 'python3', 'xrandr', 'xprop', 'gdbus', 'pactl', 'parec', 'codex')}
    result['numpy'] = importlib.util.find_spec('numpy') is not None
    cfg=load(); screen=monitor(cfg); area=workarea(screen)
    from .quotas import codex_binary
    try:
        result['codex_binary'] = codex_binary(cfg['usage']['codex_binary'])
        result['codex'] = True
    except RuntimeError:
        result['codex_binary'] = None
    result['workarea'] = area
    result['layout'] = layout(cfg, 'panel', screen, area)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not all(result[name] for name in ('conky', 'python3', 'xrandr', 'pactl', 'parec', 'numpy')):
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description='Órbita HUD · Onocru')
    subs = p.add_subparsers(dest='command', required=True)
    subs.add_parser('doctor')
    s = subs.add_parser('start'); s.add_argument('--widget', choices=['all', 'clock', 'panel'], default='all')
    subs.add_parser('stop')
    d = subs.add_parser('daemon'); d.add_argument('--ensure', action='store_true')
    l = subs.add_parser('layout'); l.add_argument('kind', choices=['clock', 'panel'])
    subs.add_parser('runtime')
    subs.add_parser('claude-statusline')
    subs.add_parser('connect-claude')
    i = subs.add_parser('install'); i.add_argument('--autostart', action='store_true')
    q = subs.add_parser('import-claude'); q.add_argument('file', type=Path)
    args = p.parse_args()
    if args.command == 'doctor': doctor()
    elif args.command == 'start': start(args.widget)
    elif args.command == 'stop': stop_widgets()
    elif args.command == 'daemon': daemon.ensure(ROOT) if args.ensure else daemon.run()
    elif args.command == 'runtime': print(runtime_dir())
    elif args.command == 'claude-statusline':
        from .claude_statusline import main as statusline
        statusline()
    elif args.command == 'connect-claude':
        from .claude_statusline import configure
        path=configure(ROOT)
        print('Puente Claude preparado: '+str(path))
        print('La lectura llegará después de una respuesta de Claude Code con tu suscripción.')
    elif args.command == 'layout':
        values = layout(load(), args.kind); values['runtime'] = str(runtime_dir())
        for key, value in values.items(): print(f'{key}={value}')
    elif args.command == 'install': install(args.autostart)
    elif args.command == 'import-claude':
        from .quotas import normalize_window
        data = json.loads(args.file.read_text())
        # Preserve the observation timestamp. Importing an old reading cannot make it fresh.
        clean = {'observed_at': float(data['observed_at'])}
        for key, alias in [('session','five_hour'), ('weekly','seven_day')]:
            w = normalize_window(data.get(key, data.get(alias)))
            clean[key] = {'used_percent': w['used'], 'resets_at': w['reset']}
        config_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
        file = config_dir()/'claude-usage.json'
        file.write_text(json.dumps(clean, indent=2)); file.chmod(0o600)
        print('Lectura importada; se ocultará al caducar.')
