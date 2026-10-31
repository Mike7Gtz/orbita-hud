from pathlib import Path
import os
import re
import subprocess
import tomllib

DEFAULT = {
    'appearance': {'side': 'right', 'monitor': '', 'top_margin': 18, 'bottom_margin': 18,
                   'clock_scale': 0.82, 'opacity': 0, 'language': 'es', 'fps': 25},
    'audio': {'enabled': True, 'monitor': '', 'bars': 96, 'gain': 1.0},
    'usage': {'interval_seconds': 180, 'stale_seconds': 900, 'codex_enabled': True,
              'codex_socket': '', 'claude_file': '', 'claude_command': []},
}


def config_dir():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'orbita-hud'


def runtime_dir():
    base = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    if not base.is_dir() or not os.access(base, os.W_OK):
        base = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    result = base / 'orbita-hud'
    result.mkdir(parents=True, exist_ok=True, mode=0o700)
    return result


def load(path=None):
    cfg = {k: dict(v) for k, v in DEFAULT.items()}
    target = Path(path) if path else config_dir() / 'config.toml'
    if target.exists():
        with target.open('rb') as f:
            for key, values in tomllib.load(f).items():
                if key in cfg and isinstance(values, dict):
                    cfg[key].update(values)
    a = cfg['appearance']
    if a['side'] not in {'left', 'right'}:
        raise ValueError('appearance.side debe ser left o right')
    a['clock_scale'] = max(.3, min(.95, float(a['clock_scale'])))
    a['fps'] = max(10, min(40, int(a['fps'])))
    a['opacity'] = max(0, min(100, int(a['opacity'])))
    cfg['audio']['bars'] = max(32, min(128, int(cfg['audio']['bars'])))
    cfg['usage']['interval_seconds'] = max(60, int(cfg['usage']['interval_seconds']))
    if not isinstance(cfg['usage']['claude_command'], list):
        raise ValueError('usage.claude_command debe ser una lista de argumentos')
    return cfg


def parse_monitors(text):
    pattern = r'^\s*(\d+):\s+(\S+)\s+(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)\s+(\S+)'
    result = []
    for line in text.splitlines():
        m = re.match(pattern, line)
        if m:
            i, flags, w, h, x, y, name = m.groups()
            result.append(dict(index=int(i), primary='*' in flags, width=int(w), height=int(h),
                               x=int(x), y=int(y), name=name))
    return result


def monitor(cfg):
    try:
        r = subprocess.run(['xrandr', '--listactivemonitors'], capture_output=True, text=True, timeout=3)
        choices = parse_monitors(r.stdout)
    except (OSError, subprocess.TimeoutExpired):
        choices = []
    wanted = cfg['appearance']['monitor']
    return (next((m for m in choices if wanted and m['name'] == wanted), None)
            or next((m for m in choices if m['primary']), None)
            or next(iter(choices), None)
            or dict(index=0, primary=True, width=1366, height=768, x=0, y=0, name='fallback'))


def layout(cfg, kind, screen=None):
    m = screen or monitor(cfg)
    a = cfg['appearance']
    available = max(200, m['height'] - int(a['top_margin']) - int(a['bottom_margin']))
    if kind == 'clock':
        size = int(min(m['height'] * a['clock_scale'], m['width'] * .61))
        return dict(width=size, height=size, monitor=m['index'], gap_x=0, gap_y=0,
                    alignment='middle_middle', side=a['side'], opacity=a['opacity'], fps=a['fps'])
    return dict(width=int(available * .4), height=available, monitor=m['index'],
                gap_x=0, gap_y=int(a['top_margin']), alignment='top_' + a['side'],
                side=a['side'], opacity=a['opacity'], fps=a['fps'])


def write_state(path, values):
    """A small data-only format: never execute a generated Lua/Python file."""
    def clean(value):
        if value is None:
            return '--'
        if isinstance(value, bool):
            return '1' if value else '0'
        return str(value).replace('\n', ' ').replace('\r', ' ')
    text = ''.join(f'{key}={clean(value)}\n' for key, value in values.items())
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text)
    tmp.replace(path)
