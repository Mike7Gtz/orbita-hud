"""Official Claude Code status-line input -> private, sanitized quota cache."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile
import time
from .config import config_dir
from .quotas import normalize_window


def atomic_json(path,data,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'w') as file:
            json.dump(data,file,ensure_ascii=False,indent=2)
            file.write('\n')
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def consume(payload,path=None,now=None):
    if not isinstance(payload,dict) or not isinstance(payload.get('rate_limits'),dict):
        return None
    rate=payload['rate_limits']
    session=normalize_window(rate.get('five_hour'))
    weekly=normalize_window(rate.get('seven_day'))
    if session['used'] is None and weekly['used'] is None:
        return None
    now=time.time() if now is None else now
    path=Path(path) if path else Path.home()/'.claude/usage.json'
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Timer/mode events can replay the same JSON. They must not make an old
    # server reading fresh. API-duration changes distinguish real responses.
    cost=payload.get('cost') if isinstance(payload.get('cost'),dict) else {}
    fingerprint=hashlib.sha256(json.dumps({
        'windows':[session,weekly], 'session':payload.get('session_id'),
        'api_duration':cost.get('total_api_duration_ms')},sort_keys=True).encode()).hexdigest()
    lock=path.with_suffix('.lock')
    with lock.open('a') as file:
        lock.chmod(0o600); fcntl.flock(file,fcntl.LOCK_EX)
        try: previous=json.loads(path.read_text())
        except (OSError,ValueError): previous={}
        if isinstance(previous,dict) and previous.get('fingerprint')==fingerprint:
            return previous
        result={'observed_at':now,'source':'claude-code-statusline','fingerprint':fingerprint}
        for name,window in [('session',session),('weekly',weekly)]:
            result[name]={'used_percent':window['used'],'resets_at':window['reset']}
        atomic_json(path,result)
        return result


def configure(root,settings_file=None):
    file=Path(settings_file) if settings_file else Path.home()/'.claude/settings.json'
    if file.is_symlink(): file=file.resolve()
    original=file.read_bytes() if file.exists() else None
    data=json.loads(original) if original is not None else {}
    if not isinstance(data,dict): raise ValueError('La configuración Claude debe ser un objeto JSON.')
    wrapper=file.parent/'usage-statusline.sh'
    command=shlex.quote(str(wrapper))
    body='#!/bin/sh\nexec python3 '+shlex.quote(str(root/'runner.py'))+' claude-statusline\n'
    existing=data.get('statusLine')
    if existing and (not isinstance(existing,dict) or existing.get('command')!=command):
        raise ValueError('Ya existe una línea de estado personalizada; se conserva. Consulta docs/providers.md para integrar el puente.')
    file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if wrapper.exists() and wrapper.read_text()!=body:
        script_backup=wrapper.with_name(wrapper.name+'.orbita-backup-'+str(time.time_ns()))
        script_backup.write_bytes(wrapper.read_bytes()); script_backup.chmod(0o600)
    fd,name=tempfile.mkstemp(prefix='.usage-statusline-',dir=file.parent)
    try:
        os.fchmod(fd,0o700)
        with os.fdopen(fd,'w') as output: output.write(body)
        os.replace(name,wrapper)
    finally:
        if os.path.exists(name): os.unlink(name)
    if existing and existing.get('command')==command: return file
    if original is not None:
        backup=file.with_name(file.name+'.orbita-backup-'+str(time.time_ns()))
        backup.write_bytes(original); backup.chmod(0o600)
    mode=stat.S_IMODE(file.stat().st_mode) if file.exists() else 0o600
    data['statusLine']={'type':'command','command':command}
    if original is not None and file.read_bytes()!=original:
        raise RuntimeError('La configuración cambió durante la preparación; vuelve a ejecutar la conexión.')
    atomic_json(file,data,mode)
    return file


def main():
    try:
        raw=sys.stdin.buffer.read(1048577)
        data=consume(json.loads(raw)) if len(raw)<=1048576 else None
        def percent(name):
            value=data.get(name,{}).get('used_percent') if data else None
            return f'{value:.0f}%' if value is not None else '—'
        print('Claude · 5h: '+percent('session')+' · semanal: '+percent('weekly'))
    except (OSError,ValueError,TypeError):
        print('Claude · límites no disponibles')
