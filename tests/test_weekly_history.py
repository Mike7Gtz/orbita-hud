from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from orbita_hud.quotas import flatten
from test_visible_progress import quote,ROOT


class WeeklyHistoryTests(unittest.TestCase):
    def test_old_weekly_reading_stays_visible_with_its_original_date(self):
        for name in ('claude','chatgpt'):
            data={'observed_at':1000,'weekly':{'used':11,'reset':10000}}
            result=flatten(name,data,900,now=4000)
            self.assertTrue(result[name+'.stale'])
            self.assertEqual(result[name+'.observed_at'],1000)
            self.assertEqual(result[name+'.weekly.used'],11)
            self.assertEqual(result[name+'.weekly.state'],'last_known')

    def test_weekly_history_is_removed_at_the_actual_reset(self):
        result=flatten('claude',{'observed_at':1000,'weekly':{'used':11,'reset':10000}},900,now=10000)
        self.assertIsNone(result['claude.weekly.used'])
        self.assertNotEqual(result['claude.weekly.state'],'last_known')

    def test_invalid_history_is_not_presented_as_a_reading(self):
        for observed,window in ((0,{'used':11,'reset':10000}),
                                (10000,{'used':11,'reset':15000}),
                                (1000,{'used':None,'reset':10000}),
                                (1000,{'used':11,'reset':None}),
                                (1000,{'used':11,'reset':700000})):
            result=flatten('claude',{'observed_at':observed,'weekly':window},900,now=4000)
            self.assertIsNone(result['claude.weekly.used'])

    def test_real_renderer_keeps_the_old_percentage_and_discloses_age(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);script=path/'old.lua';rc=path/'old.conf'
            script.write_text(f'''dofile({quote(ROOT/'conky/render.lua')})
function conky_history_test()
 local original=cairo_show_text
 cairo_show_text=function(cr,text) print('LABEL|'..text);original(cr,text) end
 local s=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,460,1000);local cr=cairo_create(s)
 local u={{['claude.stale']='1',['claude.observed_at']='1000',['claude.weekly.state']='last_known',
 ['claude.weekly.used']='11',['claude.weekly.reset']='10000',['claude.source']='claude-desktop'}}
 orbita_draw_panel(cr,460,1000,{{}},u,{{}},4000)
 cairo_destroy(cr);cairo_surface_destroy(s)
end
''')
            rc.write_text(f"conky.config={{out_to_x=false,out_to_console=true,total_run_times=1,lua_load={quote(script)},lua_startup_hook='history_test'}};conky.text=' ';\n")
            result=subprocess.run(['conky','-c',str(rc)],capture_output=True,text=True,check=True,timeout=10)
            self.assertIn('LABEL|11%',result.stdout)
            self.assertIn('LABEL|Última lectura · hace 50 min',result.stdout)
            self.assertIn('LABEL|Reinicio: 1 h 40 min',result.stdout)


if __name__=='__main__':unittest.main()
