from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import subprocess
import time
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from orbita_hud.quotas import flatten,claude_usage,codex_binary,codex_usage
from orbita_hud.config import load
from test_visible_progress import evaluate,quote,ROOT


class IdleQuotaTests(unittest.TestCase):
    def test_confirmed_zero_without_reset_is_idle_and_keeps_weekly(self):
        for provider in ('claude','chatgpt'):
            result=flatten(provider,{'observed_at':1000,'session':{'used':0,'reset':None},
                'weekly':{'used':33,'reset':9000}},now=1100)
            self.assertEqual(result[provider+'.session.state'],'idle')
            self.assertEqual(result[provider+'.session.used'],0)
            self.assertEqual(result[provider+'.weekly.used'],33)

    def test_unknown_expired_or_stale_does_not_become_idle_zero(self):
        for window in ({'used':None,'reset':None},{'used':42,'reset':900}, {'used':0,'reset':1050}):
            data={'observed_at':1000,'session':window}
            result=flatten('claude',data,now=1100)
            self.assertNotEqual(result['claude.session.state'],'idle')
            if window['reset'] is None or window['reset']<1100:
                self.assertIsNone(result['claude.session.used'])
        stale=flatten('claude',{'observed_at':1000,'session':{'used':0,'reset':None}},now=2000)
        self.assertEqual(stale['claude.session.state'],'stale')
        self.assertIsNone(stale['claude.session.used'])

    def test_new_provider_zero_after_old_reset_is_idle(self):
        result=flatten('chatgpt',{'observed_at':1100,'session':{'used':0,'reset':1000}},now=1200)
        self.assertEqual(result['chatgpt.session.state'],'idle')
        self.assertEqual(result['chatgpt.session.used'],0)

    def test_desktop_rewrites_do_not_change_sample_age(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'usage.json'
            path.write_text(json.dumps({'source':'claude-desktop','sampled_at':1000,'updated_at':10000,
                'five_hour':{'used_percentage':0,'resets_at':None},'seven_day':{'used_percentage':11}}))
            cfg=load('/nonexistent');cfg['usage']['claude_file']=str(path)
            result=claude_usage(cfg)
            self.assertEqual(result['source'],'claude-desktop')
            self.assertEqual(result['observed_at'],1000)
            self.assertEqual(flatten('claude',result,now=2000)['claude.session.state'],'stale')

    def test_renderer_labels_idle_zero_for_both_providers(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);script=path/'idle.lua';rc=path/'idle.conf'
            script.write_text(f'''dofile({quote(ROOT/'conky/render.lua')})
function conky_idle_test()
 local original=cairo_show_text
 cairo_show_text=function(cr,text) print('LABEL|'..text);original(cr,text) end
 local s=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,460,1000);local cr=cairo_create(s)
 local u={{}}
 for _,name in ipairs({{'chatgpt','claude'}}) do
 u[name..'.stale']='0';u[name..'.observed_at']='1000';u[name..'.session.used']='0';u[name..'.session.state']='idle'
 u[name..'.weekly.used']='11';u[name..'.weekly.reset']='9000'
 end
 orbita_draw_panel(cr,460,1000,{{}},u,{{}},1000)
 cairo_destroy(cr);cairo_surface_destroy(s)
end
''')
            rc.write_text(f"conky.config={{out_to_x=false,out_to_console=true,total_run_times=1,lua_load={quote(script)},lua_startup_hook='idle_test'}};conky.text=' ';\n")
            result=subprocess.run(['conky','-c',str(rc)],capture_output=True,text=True,check=True,timeout=10)
            self.assertEqual(result.stdout.count('LABEL|Sin iniciar'),2)
            self.assertEqual(result.stdout.count('LABEL|0%'),2)
            self.assertEqual(result.stdout.count('LABEL|11%'),2)


class CodexBackgroundTests(unittest.TestCase):
    def test_desktop_binary_fallback_without_interactive_path(self):
        with patch('orbita_hud.quotas.shutil.which',return_value=None), \
             patch('pathlib.Path.is_file',lambda p:str(p)=='/usr/lib/chatgpt/resources/codex'), \
             patch('orbita_hud.quotas.os.access',return_value=True):
            self.assertEqual(codex_binary(),'/usr/lib/chatgpt/resources/codex')

    def test_notifications_and_responses_in_one_read_are_not_lost(self):
        with tempfile.TemporaryDirectory() as folder:
            binary=Path(folder)/'codex'
            binary.write_text('''#!/usr/bin/python3
import sys,json,os,time
for line in sys.stdin:
    message=json.loads(line)
    if 'id' not in message:continue
    result={} if message['id']==1 else {'rateLimits':{'primary':{'usedPercent':0},'secondary':{'usedPercent':33,'resetsAt':9999999999}}}
    payload=(json.dumps({'method':'notification'})+'\\n'+json.dumps({'id':message['id'],'result':result})+'\\n').encode()
    os.write(1,payload[:7]);time.sleep(.005);os.write(1,payload[7:])
''')
            binary.chmod(0o700)
            result=codex_usage(binary=str(binary),timeout=3)
            self.assertEqual(result['session']['used'],0)
            self.assertEqual(result['weekly']['used'],33)


class ClockProgressTests(unittest.TestCase):
    def setUp(self):
        self.old_tz=os.environ.get('TZ')
        os.environ['TZ']='UTC';time.tzset()

    def tearDown(self):
        if self.old_tz is None:os.environ.pop('TZ',None)
        else:os.environ['TZ']=self.old_tz
        time.tzset()

    def progress(self,stamp):
        text=evaluate(f'''local clock=dofile({quote(ROOT/'conky/clock.lua')})
local p=clock.progress({stamp:.6f})
return string.format('%.12f,%.12f,%.12f,%.12f,%.12f',p.seconds,p.minutes,p.hours,p.week,p.year)''')
        return list(map(float,text.split(',')))

    def epoch(self,year,month,day,hour=0,minute=0,second=0):
        return datetime(year,month,day,hour,minute,second,tzinfo=timezone.utc).timestamp()

    def test_all_three_clock_hands_move_within_each_second(self):
        stamp=self.epoch(2026,10,31,12,30,15)
        a=self.progress(stamp+.1); b=self.progress(stamp+.9)
        for i,period in enumerate((60,3600,86400)):
            self.assertAlmostEqual(b[i]-a[i],.8/period,places=8)

    def test_seconds_wrap_without_minute_or_hour_jumps(self):
        stamp=self.epoch(2026,10,31,12,30,59)
        a=self.progress(stamp+.96);b=self.progress(stamp+1)
        self.assertGreater(a[0],.99);self.assertEqual(b[0],0)
        self.assertAlmostEqual(b[1]-a[1],.04/3600,places=8)
        self.assertAlmostEqual(b[2]-a[2],.04/86400,places=8)

    def test_week_starts_monday_and_seventh_sector_fills_sunday(self):
        self.assertAlmostEqual(self.progress(self.epoch(2026,10,26))[3],0)
        self.assertAlmostEqual(self.progress(self.epoch(2026,11,1,12))[3],6.5/7)
        self.assertAlmostEqual(self.progress(self.epoch(2026,11,2))[3],0)

    def test_twelve_month_sectors_use_actual_month_days_and_leap_years(self):
        self.assertAlmostEqual(self.progress(self.epoch(2026,1,1))[4],0)
        self.assertAlmostEqual(self.progress(self.epoch(2026,2,15))[4],1.5/12)
        self.assertAlmostEqual(self.progress(self.epoch(2024,2,29,12))[4],(1+28.5/29)/12)
        self.assertAlmostEqual(self.progress(self.epoch(2026,12,1))[4],11/12)

    def test_boot_clock_interpolates_even_after_suspend(self):
        result=evaluate(f'''local clock=dofile({quote(ROOT/'conky/clock.lua')})
local now=clock.now({{generated_at='1793500000.25',['clock.boottime']='10000.25'}},10000.50)
return string.format('%.2f',now)''')
        self.assertEqual(float(result),1793500000.5)

    def test_fractional_sector_fill_preserves_previous_completed_sectors(self):
        result=evaluate(f'''local clock=dofile({quote(ROOT/'conky/clock.lua')})
return string.format('%.3f,%.3f,%.3f',clock.segment_fraction(2.5/7,1,7),clock.segment_fraction(2.5/7,2,7),clock.segment_fraction(2.5/7,3,7))''')
        self.assertEqual(list(map(float,result.split(','))),[1,.5,0])


if __name__=='__main__':unittest.main()
