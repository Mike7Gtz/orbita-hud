from pathlib import Path
import ast
import math
import os
import re
import subprocess
import tomllib

DEFAULT = {
    'temperature': {'cpu_max_c': 0, 'gpu_max_c': 0, 'fallback_max_c': 100},
    'appearance': {'side': 'right', 'monitor': '', 'top_margin': 18, 'bottom_margin': 18,
                   'clock_scale': 0.82, 'opacity': 0, 'language': 'es', 'fps': 25},
    'audio': {'enabled': True, 'monitor': '', 'bars': 128, 'gain': 1.0},
    'usage': {'interval_seconds': 180, 'stale_seconds': 900, 'codex_enabled': True,
              'codex_socket': '', 'codex_binary': '', 'claude_file': '', 'claude_command': []},
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
    for key in ('cpu_max_c','gpu_max_c','fallback_max_c'):
        value=float(cfg['temperature'][key])
        if not math.isfinite(value) or value<0 or value>200 or (key=='fallback_max_c' and value==0):
            raise ValueError('Escala térmica inválida: '+key)
        cfg['temperature'][key]=value
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


def intersect_workarea(screen, rect):
    """Clip a global work rectangle to this monitor, including offset/negative origins."""
    if len(rect) != 4 or any(not isinstance(v, int) for v in rect):
        raise ValueError('invalid_workarea')
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        raise ValueError('invalid_workarea')
    left, top = max(screen['x'], x), max(screen['y'], y)
    right = min(screen['x']+screen['width'], x+w)
    bottom = min(screen['y']+screen['height'], y+h)
    if right <= left or bottom <= top:
        raise ValueError('workarea_outside_monitor')
    return dict(x=left, y=top, width=right-left, height=bottom-top)


def workarea(screen):
    """Cinnamon has per-monitor work areas; EWMH only offers a global fallback."""
    try:
        r = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.Cinnamon',
                            '--object-path', '/org/Cinnamon', '--method',
                            'org.Cinnamon.GetMonitorWorkRect', str(screen['index'])],
                           capture_output=True, text=True, timeout=2, check=True)
        rect = ast.literal_eval(r.stdout.strip())[0]
        return dict(intersect_workarea(screen, rect), source='cinnamon')
    except (OSError, subprocess.SubprocessError, ValueError, SyntaxError, IndexError, TypeError):
        pass
    try:
        r = subprocess.run(['xprop', '-root', '_NET_CURRENT_DESKTOP', '_NET_WORKAREA'],
                           capture_output=True, text=True, timeout=2, check=True)
        current = re.search(r'_NET_CURRENT_DESKTOP\([^)]*\)\s*=\s*(\d+)', r.stdout)
        areas = re.search(r'_NET_WORKAREA\([^)]*\)\s*=\s*([^\n]+)', r.stdout)
        if areas:
            values = list(map(int, re.findall(r'-?\d+', areas.group(1))))
            index = int(current.group(1)) if current else 0
            return dict(intersect_workarea(screen, values[index*4:index*4+4]), source='ewmh')
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        pass
    return dict(x=screen['x'], y=screen['y'], width=screen['width'], height=screen['height'], source='monitor')


def layout(cfg, kind, screen=None, work=None):
    m = screen or monitor(cfg)
    a = cfg['appearance']
    if kind == 'clock':
        size = int(min(m['height'] * a['clock_scale'], m['width'] * .61))
        return dict(width=size, height=size, monitor=m['index'], gap_x=0, gap_y=0,
                    alignment='middle_middle', side=a['side'], opacity=a['opacity'], fps=a['fps'])
    area = work if work is not None else workarea(m)
    top = min(max(0, int(a['top_margin'])), max(0, area['height']-4))
    bottom = min(max(0, int(a['bottom_margin'])), max(0, area['height']-top-4))
    # Conky adds a 1 px outer edge on every side, even with border margins at zero.
    available = max(1, area['height']-top-bottom-2)
    clock_size = min(m['height']*a['clock_scale'], m['width']*.61)
    center = m['x']+m['width']/2
    if a['side'] == 'right':
        free_width = area['x']+area['width']-(center+clock_size/2)-12
        gap = m['x']+m['width']-(area['x']+area['width'])
    else:
        free_width = center-clock_size/2-area['x']-12
        gap = area['x']-m['x']
    width = max(1, min(int(available*.46), int(max(1, free_width-2))))
    height = max(1, min(available, int(width/.46)))
    return dict(width=width, height=height, monitor=m['index'],
                gap_x=gap+1, gap_y=area['y']-m['y']+top+1, alignment='top_' + a['side'],
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
