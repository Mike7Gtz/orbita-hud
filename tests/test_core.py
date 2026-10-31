import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from orbita_hud.config import load, layout, parse_monitors, write_state
from orbita_hud.quotas import normalize_window, flatten, claude_usage
from orbita_hud.audio import Spectrum, choose_monitor
from orbita_hud.telemetry import cpu_temperature, memory_metrics, Collector


class LayoutTests(unittest.TestCase):
    def test_multimonitor_primary_not_virtual_desktop(self):
        text='''Monitors: 3
 0: +*HDMI-0 1920/530x1080/300+2560+360 HDMI-0
 1: +DP-0.3 2560/600x1440/340+4480+0 DP-0.3
 2: +DP-0.4 2560/600x1440/340+0+0 DP-0.4'''
        monitors=parse_monitors(text)
        self.assertEqual(monitors[0]['width'],1920)
        self.assertTrue(monitors[0]['primary'])
        cfg=load('/nonexistent')
        for m in monitors:
            clock=layout(cfg,'clock',m,work=m); panel=layout(cfg,'panel',m,work=m)
            self.assertEqual(clock['width'],clock['height'])
            self.assertAlmostEqual(panel['width']/panel['height'],.46,places=2)
            self.assertLess(panel['height'],m['height'])
        cfg['appearance']['side']='left'
        self.assertEqual(layout(cfg,'panel',monitors[0],work=monitors[0])['alignment'],'top_left')


class QuotaTests(unittest.TestCase):
    def test_missing_and_nonfinite_are_unknown(self):
        for value in [None,{}, {'usedPercent':True}, {'usedPercent':float('nan')}]:
            self.assertIsNone(normalize_window(value)['used'])
        self.assertEqual(normalize_window({'usedPercent':110})['used'],100)
        self.assertEqual(normalize_window({'utilization':31})['used'],31)

    def test_expired_and_stale_are_not_zero(self):
        data={'observed_at':1000,'session':{'used':42,'reset':1200},'weekly':{'used':18,'reset':9000}}
        current=flatten('claude',data,900,now=1100)
        self.assertEqual(current['claude.session.used'],42)
        expired=flatten('claude',data,900,now=1300)
        self.assertIsNone(expired['claude.session.used'])
        self.assertEqual(expired['claude.weekly.used'],18)
        stale=flatten('claude',data,900,now=2000)
        self.assertIsNone(stale['claude.weekly.used'])
        self.assertIsNone(flatten('claude',{},900,now=2000)['claude.session.used'])

    def test_iso_reset_and_invalid_reset(self):
        self.assertIsInstance(normalize_window({'resets_at':'2026-10-30T12:00:00Z'})['reset'],float)
        self.assertIsNone(normalize_window({'resets_at':'not a timestamp'})['reset'])

    def test_claude_file_no_false_observation_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'quota.json'
            file.write_text(json.dumps({'observed_at':100,'five_hour':{'utilization':47},'seven_day':{'utilization':12}}))
            cfg=load('/nonexistent'); cfg['usage']['claude_file']=str(file)
            data=claude_usage(cfg)
            self.assertEqual(data['observed_at'],100)
            self.assertEqual(data['session']['used'],47)


class TelemetryTests(unittest.TestCase):
    def test_temperature_never_uses_disk_sensor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for i,name,label,value in [(0,'nvme','Composite',92000),(1,'k10temp','Tctl',48000)]:
                chip=root/f'hwmon{i}'; chip.mkdir()
                (chip/'name').write_text(name); (chip/'temp1_label').write_text(label)
                (chip/'temp1_input').write_text(str(value))
            self.assertEqual(cpu_temperature(root),(48.0,'k10temp:tctl'))

    def test_memory_excludes_reclaimable_cache(self):
        self.assertEqual(memory_metrics('MemTotal: 1000 kB\nMemAvailable: 600 kB\nMemFree: 100 kB')['ram.percent'],40)

    def test_cpu_global_delta_and_initial_unknown(self):
        c=Collector()
        with patch('orbita_hud.telemetry.read',side_effect=['cpu 100 0 0 900 0 0 0 0','cpu 130 0 0 970 0 0 0 0']), \
             patch('orbita_hud.telemetry.cpu_temperature',return_value=(40,'test')), \
             patch('orbita_hud.telemetry.memory_metrics',return_value={}), \
             patch('orbita_hud.telemetry.gpu_metrics',return_value={}), \
             patch('orbita_hud.telemetry.temperature_limits',return_value={}):
            self.assertIsNone(c.sample()['cpu.load'])
            self.assertEqual(c.sample()['cpu.load'],30)


class AudioTests(unittest.TestCase):
    def test_monitor_only_never_microphone(self):
        sources=[{'name':'microphone','monitor_of_sink':4294967295},
                 {'name':'speaker.monitor','monitor_of_sink':3}]
        self.assertEqual(choose_monitor({},sources,'speaker'),'speaker.monitor')
        with self.assertRaises(RuntimeError): choose_monitor({'monitor':'microphone'},sources,'speaker')
        with self.assertRaises(RuntimeError): choose_monitor({},sources[:1],'speaker')

    def test_fft_silence_and_tone(self):
        import numpy as np
        fft=Spectrum()
        v,rms=fft.process(bytes(2048)); self.assertEqual(max(v),0); self.assertEqual(rms,0)
        signal=(np.sin(np.arange(1024)*2*math.pi*1000/22050)*16000).astype('<i2').tobytes()
        for _ in range(5): v,rms=fft.process(signal)
        peak=int(np.argmax(v)); self.assertLess(abs(math.log(fft.edges[peak]/1000)),.2)
        self.assertGreater(max(v),.5); self.assertLessEqual(max(v),1)
        for _ in range(40): v,rms=fft.process(bytes(2048))
        self.assertLess(max(v),.001)

    def test_pipewire_pactl_json_uses_device_class(self):
        sources=[{'name':'mic','monitor_source':'','properties':{'device.class':'sound'}},
                 {'name':'speaker.monitor','monitor_source':'speaker','properties':{'device.class':'monitor'}}]
        self.assertEqual(choose_monitor({},sources,'speaker'),'speaker.monitor')
        with self.assertRaises(RuntimeError): choose_monitor({'monitor':'mic'},sources,'speaker')


class StateTests(unittest.TestCase):
    def test_data_format_does_not_execute_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'audio.state'
            write_state(path,{'available':False,'value':None,'text':'one\ntwo'})
            self.assertEqual(path.read_text(),'available=0\nvalue=--\ntext=one two\n')
            self.assertFalse(path.with_suffix('.state.tmp').exists())


if __name__=='__main__': unittest.main()
