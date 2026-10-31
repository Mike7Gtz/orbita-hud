from pathlib import Path
import re
import shutil
import subprocess
import time


def read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return ''


def sensor_value(path):
    try:
        value = float(read(path)) / 1000
        return value if -20 <= value <= 150 else None
    except ValueError:
        return None


def cpu_temperature(root=Path('/sys/class/hwmon')):
    candidates = []
    for chip in root.glob('hwmon*'):
        name = read(chip / 'name').lower()
        if name not in {'coretemp', 'k10temp', 'zenpower'}:
            continue
        for p in chip.glob('temp*_input'):
            value = sensor_value(p)
            label = read(p.with_name(p.name.replace('_input', '_label'))).lower()
            if value is not None:
                rank = 0 if label.startswith('package') or label == 'tdie' else 1 if label == 'tctl' else 2
                candidates.append((rank, -value, value, name + ':' + label))
    return (min(candidates)[2:] if candidates else (None, 'unavailable'))


def gpu_metrics(root=Path('/sys/class/hwmon')):
    if shutil.which('nvidia-smi'):
        try:
            r = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total',
                                '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=2)
            rows = []
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    cells = line.split(',')
                    if len(cells) != 4:
                        continue
                    vals = []
                    for cell in cells:
                        try:
                            vals.append(float(cell.strip()))
                        except ValueError:
                            vals.append(None)
                    rows.append(vals)
            if rows:
                temp, usage, used, total = rows[0]
                return {'gpu.temperature': temp, 'gpu.load': usage, 'vram.used': used,
                        'vram.total': total, 'vram.percent': used / total * 100 if used is not None and total else None,
                        'gpu.source': 'nvidia-smi (GPU 0)'}
        except (OSError, subprocess.TimeoutExpired):
            pass
    # AMD DRM sensors expose utilization and VRAM without account credentials.
    for chip in root.glob('hwmon*'):
        name = read(chip / 'name')
        if name not in {'amdgpu', 'nouveau', 'i915', 'xe'}:
            continue
        device = chip / 'device'
        def number(name):
            try:
                return float(read(device / name))
            except ValueError:
                return None
        used, total = number('mem_info_vram_used'), number('mem_info_vram_total')
        temps = [sensor_value(p) for p in chip.glob('temp*_input')]
        temps = [v for v in temps if v is not None]
        return {'gpu.temperature': temps[0] if temps else None,
                'gpu.load': number('gpu_busy_percent'), 'vram.used': used, 'vram.total': total,
                'vram.percent': used / total * 100 if used is not None and total else None, 'gpu.source': name}
    return dict.fromkeys(['gpu.temperature', 'gpu.load', 'vram.used', 'vram.total', 'vram.percent'], None)


def memory_metrics(text=None):
    text = read('/proc/meminfo') if text is None else text
    values = {}
    for line in text.splitlines():
        name, _, tail = line.partition(':')
        try:
            values[name] = int(tail.strip().split()[0])
        except (ValueError, IndexError):
            continue
    total, available = values.get('MemTotal', 0), values.get('MemAvailable')
    return {'ram.total': total, 'ram.used': total - available if available is not None else None,
            'ram.percent': 100 * (total - available) / total if total and available is not None else None}


def nvidia_operating_limit(text):
    values={}
    for line in text.splitlines():
        match=re.match(r'\s*(GPU [^:]+?)\s*:\s*(-?\d+(?:\.\d+)?)\s*C\s*$',line)
        if match: values[match.group(1).strip()]=float(match.group(2))
    absolute=values.get('GPU Max Operating Temp')
    if absolute is None:
        current=values.get('GPU Current Temp')
        margin=values.get('GPU Current T.Limit Temp',values.get('GPU T.Limit Temp'))
        threshold=values.get('GPU Max Operating T.Limit Temp Specification',values.get('GPU Max Operating T.Limit Temp',0))
        if current is not None and margin is not None:
            absolute=current+margin-threshold
    return absolute if absolute is not None and 40<=absolute<=150 else None


def temperature_limits(root=Path('/sys/class/hwmon')):
    cpu=[]; gpu=[]
    for chip in root.glob('hwmon*'):
        name=read(chip/'name').lower()
        if name not in {'k10temp','coretemp','zenpower','amdgpu','nouveau','i915','xe'}: continue
        target=cpu if name in {'k10temp','coretemp','zenpower'} else gpu
        for path in chip.glob('temp*_crit'):
            value=sensor_value(path)
            if value is not None and 40<=value<=150: target.append(value)
    result={'cpu.temperature.limit':min(cpu) if cpu else None,
            'gpu.temperature.limit':min(gpu) if gpu else None}
    if shutil.which('nvidia-smi'):
        try:
            query=subprocess.run(['nvidia-smi','-q','-d','TEMPERATURE','-i','0'],capture_output=True,text=True,timeout=2)
            if query.returncode==0:
                limit=nvidia_operating_limit(query.stdout)
                if limit is not None: result['gpu.temperature.limit']=limit
        except (OSError,subprocess.TimeoutExpired): pass
    return result


def apply_temperature_scales(values,cfg):
    for component in ('cpu','gpu'):
        override=cfg['temperature'][component+'_max_c']
        reported=values.get(component+'.temperature.limit')
        maximum=override or reported or cfg['temperature']['fallback_max_c']
        values[component+'.temperature.scale_max']=maximum
        values[component+'.temperature.scale_source']='configured' if override else 'hardware' if reported else 'fallback'
    return values


class Collector:
    def __init__(self):
        self.previous = None
        self.gpu = {}
        self.last_gpu = 0
        self.limits={}
        self.last_limits=0

    def sample(self):
        line = read('/proc/stat').splitlines()[0]
        ticks = list(map(int, line.split()[1:9]))
        total, idle = sum(ticks), ticks[3] + ticks[4]
        load = None
        if self.previous:
            dt, di = total - self.previous[0], idle - self.previous[1]
            load = max(0, min(100, 100 * (dt - di) / dt)) if dt else None
        self.previous = (total, idle)
        temp, source = cpu_temperature()
        if time.monotonic() - self.last_gpu >= 3:
            self.gpu = gpu_metrics()
            self.last_gpu = time.monotonic()
        if time.monotonic()-self.last_limits>=60:
            self.limits=temperature_limits()
            self.last_limits=time.monotonic()
        return {'generated_at': time.time(), 'cpu.load': load, 'cpu.temperature': temp,
                'cpu.source': source, **memory_metrics(), **self.gpu, **self.limits}
