from pathlib import Path
import json
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from orbita_hud.claude_statusline import consume,configure
from orbita_hud.config import load
from orbita_hud.quotas import claude_usage,flatten
from orbita_hud.telemetry import nvidia_operating_limit,apply_temperature_scales


class ClaudeBridgeTests(unittest.TestCase):
    def payload(self):
        return {'rate_limits':{'five_hour':{'used_percentage':42,'resets_at':5000},
                               'seven_day':{'used_percentage':18,'resets_at':10000}},
                'session_id':'private-session','cost':{'total_api_duration_ms':400},
                'workspace':{'current_dir':'/private/path'},'prompt':'private message'}

    def test_official_input_flows_to_reader_without_private_session_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'usage.json'; data=consume(self.payload(),path,now=1000)
            cfg=load('/nonexistent');cfg['usage']['claude_file']=str(path)
            reading=claude_usage(cfg)
            self.assertEqual(reading['source'],'claude-code-statusline')
            self.assertEqual(reading['session']['used'],42);self.assertEqual(reading['weekly']['used'],18)
            self.assertEqual(reading['observed_at'],1000)
            self.assertNotIn('private',path.read_text()); self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertIsNone(flatten('claude',reading,900,now=2000)['claude.session.used'])

    def test_replayed_statusline_does_not_refresh_old_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'usage.json'; payload=self.payload()
            consume(payload,path,now=1000)
            self.assertEqual(consume(payload,path,now=2000)['observed_at'],1000)
            payload['cost']['total_api_duration_ms']=500
            self.assertEqual(consume(payload,path,now=2100)['observed_at'],2100)

    def test_absent_limits_neither_fabricate_zero_nor_overwrite_last_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'usage.json';consume(self.payload(),path,now=1000);before=path.read_bytes()
            self.assertIsNone(consume({'model':{}},path,now=2000))
            self.assertEqual(path.read_bytes(),before)

    def test_original_script_schema_updated_at_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'usage.json';path.write_text(json.dumps(dict(self.payload()['rate_limits'],updated_at=1234)))
            cfg=load('/nonexistent');cfg['usage']['claude_file']=str(path)
            reading=claude_usage(cfg)
            self.assertEqual(reading['observed_at'],1234);self.assertEqual(reading['session']['used'],42)

    def test_configure_preserves_settings_backs_up_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.json';original={'permissions':{'allow':['Read']},'modelSettings':{'model':'unchanged'}}
            path.write_text(json.dumps(original));before=path.read_bytes()
            configure(Path('/project with space'),path)
            data=json.loads(path.read_text())
            self.assertEqual(data['permissions'],original['permissions']);self.assertEqual(data['modelSettings'],original['modelSettings'])
            self.assertEqual(data['statusLine']['type'],'command')
            backups=list(Path(tmp).glob('settings.json.orbita-backup-*'))
            self.assertEqual(backups[0].read_bytes(),before)
            self.assertIn("'/project with space/runner.py'",(Path(tmp)/'usage-statusline.sh').read_text())
            self.assertEqual((Path(tmp)/'usage-statusline.sh').stat().st_mode&0o777,0o700)
            configure(Path('/project with space'),path)
            self.assertEqual(len(list(Path(tmp).glob('settings.json.orbita-backup-*'))),1)

    def test_custom_statusline_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.json';path.write_text('{"statusLine":{"command":"my-custom-command"}}');before=path.read_bytes()
            with self.assertRaises(ValueError):configure(Path('/project'),path)
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse((Path(tmp)/'usage-statusline.sh').exists())


class ThermalLimitTests(unittest.TestCase):
    def test_nvidia_relative_margin_is_not_used_as_absolute_maximum(self):
        text='GPU Current Temp : 42 C\nGPU T.Limit Temp : 45 C\nGPU Max Operating T.Limit Temp : 0 C\n'
        self.assertEqual(nvidia_operating_limit(text),87)
        self.assertEqual(nvidia_operating_limit('GPU Max Operating Temp : 83 C'),83)
        self.assertIsNone(nvidia_operating_limit('GPU Target Temperature : 87 C'))

    def test_explicit_or_hardware_or_fallback_scale(self):
        cfg=load('/nonexistent')
        data=apply_temperature_scales({'gpu.temperature.limit':87},cfg)
        self.assertEqual(data['gpu.temperature.scale_max'],87)
        self.assertEqual(data['cpu.temperature.scale_max'],100)
        self.assertEqual(data['cpu.temperature.scale_source'],'fallback')
        cfg['temperature']['cpu_max_c']=95
        self.assertEqual(apply_temperature_scales({},cfg)['cpu.temperature.scale_max'],95)


if __name__=='__main__':unittest.main()
