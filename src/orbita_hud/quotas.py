import json
import math
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
from . import __version__


def normalize_window(value):
    if not isinstance(value, dict):
        return {'used': None, 'reset': None, 'minutes': None}
    percent = value.get('usedPercent', value.get('used_percent', value.get('used_percentage', value.get('utilization'))))
    if not isinstance(percent, (int, float)) or isinstance(percent, bool) or not math.isfinite(percent):
        percent = None
    reset = value.get('resetsAt', value.get('resets_at'))
    if isinstance(reset, str):
        from datetime import datetime
        try:
            reset = float(reset)
        except ValueError:
            try:
                reset = datetime.fromisoformat(reset.replace('Z', '+00:00')).timestamp()
            except ValueError:
                reset = None
    if not isinstance(reset, (float, int)) or isinstance(reset, bool) or not math.isfinite(reset):
        reset = None
    return {'used': max(0, min(100, percent)) if percent is not None else None,
            'reset': reset,
            'minutes': value.get('windowDurationMins', value.get('minutes'))}


def codex_usage(sock='', timeout=15):
    """Use Codex's documented read-only RPC; never read or export its auth file."""
    binary = shutil.which('codex')
    if not binary:
        raise RuntimeError('codex_not_installed')
    command = [binary, 'app-server', 'proxy', '--sock', sock] if sock else [binary, 'app-server', '--stdio']
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    def send(message):
        proc.stdin.write(json.dumps(message) + '\n')
        proc.stdin.flush()
    def receive(request_id):
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            line = proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get('id') == request_id:
                if 'error' in message:
                    raise RuntimeError('codex_account_unavailable')
                return message.get('result', {})
        raise TimeoutError('codex_usage_timeout')
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {
            'name': 'orbita_hud', 'title': 'Orbita HUD', 'version': __version__}}})
        receive(1)
        send({'method': 'initialized', 'params': {}})
        send({'id': 2, 'method': 'account/rateLimits/read'})
        data = receive(2)
        bucket = data.get('rateLimitsByLimitId', {}).get('codex') or data.get('rateLimits') or {}
        return {'source': 'Codex / ChatGPT', 'observed_at': time.time(),
                'session': normalize_window(bucket.get('primary')),
                'weekly': normalize_window(bucket.get('secondary'))}
    finally:
        selector.close()
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if proc.stdout:
            proc.stdout.close()


def claude_usage(cfg):
    settings = cfg['usage']
    command = settings['claude_command']
    if command:
        result = subprocess.run(command, capture_output=True, text=True, timeout=12, check=True)
        data = json.loads(result.stdout)
        source = 'external_provider'
    else:
        name = settings['claude_file']
        path = Path(name).expanduser() if name else Path.home()/'.claude/usage.json'
        if not name and not path.exists():
            path=Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'orbita-hud/claude-usage.json'
        if not path.exists():
            raise RuntimeError('claude_not_connected')
        data = json.loads(path.read_text())
        source = 'imported'
    if not isinstance(data, dict):
        raise ValueError('claude_invalid_reading')
    if data.get('source')=='claude-code-statusline': source='claude-code-statusline'
    windows=data.get('rate_limits',data)
    if not isinstance(windows,dict): raise ValueError('claude_invalid_windows')
    return {'source': source, 'observed_at': data.get('observed_at',data.get('updated_at',0)),
            'session': normalize_window(windows.get('session') or windows.get('five_hour')),
            'weekly': normalize_window(windows.get('weekly') or windows.get('seven_day'))}


def flatten(name, data, stale_seconds=900, now=None):
    now = time.time() if now is None else now
    try:
        observed = float(data.get('observed_at', 0))
    except (ValueError, TypeError):
        observed = 0
    if not math.isfinite(observed):
        observed = 0
    age = now - observed
    stale = age > stale_seconds or age < -60
    out = {f'{name}.stale': stale, f'{name}.source': data.get('source', 'unavailable'),
           f'{name}.observed_at': data.get('observed_at', 0)}
    for key in ['session', 'weekly']:
        w = data.get(key, {})
        expired = w.get('reset') is not None and float(w['reset']) <= now
        out[f'{name}.{key}.used'] = None if stale or expired else w.get('used')
        out[f'{name}.{key}.reset'] = w.get('reset')
        out[f'{name}.{key}.minutes'] = w.get('minutes')
    return out
