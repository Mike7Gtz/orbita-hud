from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from orbita_hud.config import load, layout, workarea, intersect_workarea
from orbita_hud.daemon import PanelWatcher

ROOT=Path(__file__).resolve().parents[1]


class WorkareaTests(unittest.TestCase):
    def setUp(self):
        self.monitor=dict(index=0,x=2560,y=360,width=1920,height=1080)

    def test_cinnamon_returns_monitor_local_reservation(self):
        with patch('orbita_hud.config.subprocess.run', return_value=SimpleNamespace(stdout='([2560, 385, 1920, 1055],)')) as run:
            area=workarea(self.monitor)
        self.assertEqual(area,dict(x=2560,y=385,width=1920,height=1055,source='cinnamon'))
        self.assertIn('org.Cinnamon.GetMonitorWorkRect',run.call_args.args[0])
        self.assertEqual(run.call_args.args[0][-1],'0')

    def test_secondary_monitor_does_not_inherit_primary_menu(self):
        other=dict(index=1,x=4480,y=0,width=2560,height=1440)
        with patch('orbita_hud.config.subprocess.run',return_value=SimpleNamespace(stdout='([4480, 0, 2560, 1440],)')):
            self.assertEqual(workarea(other)['height'],1440)

    def test_ewmh_selects_current_workspace_and_clips_global_rectangle(self):
        ewmh='_NET_CURRENT_DESKTOP(CARDINAL) = 1\n_NET_WORKAREA(CARDINAL) = 0, 0, 7040, 1440, 0, 385, 7040, 1055\n'
        with patch('orbita_hud.config.subprocess.run',side_effect=[OSError('No Cinnamon'),SimpleNamespace(stdout=ewmh)]):
            area=workarea(self.monitor)
        self.assertEqual(area,dict(x=2560,y=385,width=1920,height=1055,source='ewmh'))

    def test_unavailable_or_invalid_workarea_falls_back_to_selected_monitor(self):
        for response in ['([0, 0, 0, 0],)','([9000, 9000, 1, 1],)','not a rectangle']:
            with patch('orbita_hud.config.subprocess.run',side_effect=[SimpleNamespace(stdout=response),OSError('No X')]):
                area=workarea(self.monitor)
            self.assertEqual(area['height'],1080)
            self.assertEqual(area['x'],2560)
            self.assertEqual(area['source'],'monitor')

    def test_negative_origin_and_side_panel_reservation(self):
        m=dict(index=2,x=-1920,y=0,width=1920,height=1080)
        self.assertEqual(intersect_workarea(m,[-1880,25,1880,1055]),dict(x=-1880,y=25,width=1880,height=1055))


class ResponsivePanelTests(unittest.TestCase):
    def test_outer_window_fits_workarea_for_both_sides_and_resolutions(self):
        cfg=load('/nonexistent')
        for width,height,menu in [(800,600,25),(1280,720,25),(1920,1080,25),(2560,1440,60),(3840,2160,48)]:
            m=dict(index=0,x=2560,y=360,width=width,height=height)
            a=dict(x=m['x']+20,y=m['y']+menu,width=width-50,height=height-menu-40)
            for side in ['left','right']:
                with self.subTest(width=width,height=height,side=side):
                    cfg['appearance']['side']=side
                    p=layout(cfg,'panel',m,a)
                    x=m['x']+p['gap_x']-1 if side=='left' else m['x']+width-p['width']-p['gap_x']-1
                    y=m['y']+p['gap_y']-1
                    self.assertGreaterEqual(x,a['x'])
                    self.assertGreaterEqual(y,a['y'])
                    self.assertLessEqual(x+p['width']+2,a['x']+a['width'])
                    self.assertLessEqual(y+p['height']+2,a['y']+a['height'])
                    self.assertAlmostEqual(p['width']/p['height'],.46,places=2)
                    self.assertGreater(p['width'],0)

    def test_menu_change_does_not_change_clock(self):
        cfg=load('/nonexistent')
        m=dict(index=0,x=2560,y=360,width=1920,height=1080)
        work=dict(x=2560,y=385,width=1920,height=1055)
        self.assertEqual(layout(cfg,'clock',m,m),layout(cfg,'clock',m,work))
        self.assertEqual(layout(cfg,'clock',m,m)['width'],885)
        panel=layout(cfg,'panel',m,work)
        self.assertEqual(panel['gap_y'],44)
        self.assertLess(panel['height'],1055)

    def test_resolution_or_menu_change_updates_geometry_fingerprint(self):
        cfg=load('/nonexistent')
        m=dict(index=0,x=0,y=0,width=1920,height=1080)
        first=layout(cfg,'panel',m,m)
        work=dict(x=0,y=40,width=1920,height=1040)
        self.assertNotEqual(first,layout(cfg,'panel',m,work))


class GaugeClearanceTests(unittest.TestCase):
    """Check the same geometry data the Cairo renderer actually consumes."""
    @classmethod
    def setUpClass(cls):
        cls.p={}
        for line in (ROOT/'conky/panel.layout').read_text().splitlines():
            if line and not line.startswith('#'):
                k,v=line.split('=',1); cls.p[k]=float(v)

    def test_circles_overlap_to_form_the_reference_silhouette(self):
        p=self.p
        small=p['gauge_radius']+p['gauge_span']
        temp=p['temperature_radius']+p['temperature_span']
        circles=[(p[key],small) for key in ['vram_y','gpu_y']]+[(p['temperature_y'],temp)]+[(p[key],small) for key in ['cpu_y','ram_y']]
        self.assertGreaterEqual(circles[0][0]-circles[0][1],10)
        self.assertLessEqual(circles[-1][0]+circles[-1][1],p['height']-10)
        for (y1,r1),(y2,r2) in zip(circles,circles[1:]):
            distance=((y2-y1)**2+(p['gauge_x']-p['temperature_x'])**2)**.5
            self.assertLess(distance,r1+r2)
            self.assertGreater(distance,abs(r1-r2))
        self.assertGreater(small,150)

    def test_percentages_fit_inside_arcs_even_at_100_percent(self):
        p=self.p
        left=p['gauge_text_x']-p['gauge_text_width']/2
        right=p['gauge_text_x']+p['gauge_text_width']/2
        self.assertGreaterEqual(left,p['gauge_x']-p['gauge_radius']+5)
        self.assertLessEqual(right,p['width']-5)
        self.assertGreaterEqual(p['temperature_text_x']-p['temperature_text_width']/2,
                                p['temperature_x']-p['temperature_radius']+5)
        self.assertLessEqual(p['temperature_text_x']+p['temperature_text_width']/2,p['width']-5)

    def test_hardware_text_is_inside_its_ring_and_clear_of_the_foreground(self):
        p=self.p
        thermal=(p['temperature_x'],p['temperature_y'],p['temperature_radius']+p['temperature_span'])
        gpu=(p['gauge_x'],p['gpu_y'],p['gauge_radius']+p['gauge_span'])
        cpu=(p['gauge_x'],p['cpu_y'],p['gauge_radius']+p['gauge_span'])
        for key,upper,front in [('vram_y',True,gpu),('gpu_y',True,thermal),('cpu_y',False,thermal),('ram_y',False,cpu)]:
            cy=p[key]
            for width,height,offset in [(50,16,p['gauge_label_upper' if upper else 'gauge_label_lower']),
                                        (p['gauge_text_width'],34,p['gauge_value_upper' if upper else 'gauge_value_lower'])]:
                x1=p['gauge_text_x']-width/2; x2=x1+width
                y2=cy+offset; y1=y2-height
                for x,y in [(x1,y1),(x1,y2),(x2,y1),(x2,y2)]:
                    self.assertLess(((x-p['gauge_x'])**2+(y-cy)**2)**.5,p['gauge_radius']-4)
                x=max(x1,min(x2,front[0])); y=max(y1,min(y2,front[1]))
                self.assertGreater(((x-front[0])**2+(y-front[1])**2)**.5,front[2]+4)

    def test_upper_and_lower_halves_are_symmetric(self):
        p=self.p
        self.assertEqual(p['vram_y']+p['ram_y'],p['height'])
        self.assertEqual(p['gpu_y']+p['cpu_y'],p['height'])
        self.assertEqual(p['quota_top_y']+p['quota_bottom_y'],p['height'])
        self.assertEqual(p['temperature_y'],p['height']/2)


class WatcherTests(unittest.TestCase):
    def test_geometry_change_restarts_only_panel(self):
        w=PanelWatcher({},Path('/theme/Orbita-HUD'))
        with patch('orbita_hud.daemon.layout',side_effect=[{'height':1000},{'height':950}]), \
             patch('orbita_hud.daemon.widgets_running',return_value=True), \
             patch('orbita_hud.daemon.subprocess.Popen') as start:
            self.assertFalse(w.poll())
            self.assertTrue(w.poll())
        self.assertEqual(start.call_count,1)
        self.assertEqual(start.call_args.args[0][1:],['/theme/Orbita-HUD/runner.py','start','--widget','panel'])

    def test_no_change_does_not_restart_widgets(self):
        w=PanelWatcher({},Path('/theme/Orbita-HUD'))
        with patch('orbita_hud.daemon.layout',return_value={'height':1000}), \
             patch('orbita_hud.daemon.subprocess.Popen') as start:
            w.poll(); w.poll()
        start.assert_not_called()

    def test_disabled_panel_is_not_reenabled_by_monitor_change(self):
        w=PanelWatcher({},Path('/theme/Orbita-HUD'))
        with patch('orbita_hud.daemon.layout',side_effect=[{'height':1000},{'height':950}]), \
             patch('orbita_hud.daemon.widgets_running',return_value=False), \
             patch('orbita_hud.daemon.subprocess.Popen') as start:
            w.poll(); self.assertFalse(w.poll())
        start.assert_not_called()


if __name__=='__main__': unittest.main()
