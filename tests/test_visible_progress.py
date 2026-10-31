import ctypes
import ctypes.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def quote(value):
    return "'"+str(value).replace('\\','\\\\').replace("'","\\'")+"'"


def evaluate(body):
    lib=ctypes.CDLL(ctypes.util.find_library('lua5.3') or ctypes.util.find_library('lua5.4'))
    lib.luaL_newstate.restype=ctypes.c_void_p
    lib.luaL_openlibs.argtypes=[ctypes.c_void_p]
    lib.luaL_loadstring.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
    lib.lua_pcallk.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_longlong,ctypes.c_void_p]
    lib.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p]
    lib.lua_tolstring.restype=ctypes.c_char_p
    lib.lua_close.argtypes=[ctypes.c_void_p]
    state=lib.luaL_newstate(); lib.luaL_openlibs(state)
    prefix=f'''local visible=dofile({quote(ROOT/'conky/visible.lua')})
local countdown=dofile({quote(ROOT/'conky/countdown.lua')})
local p={{}}
for line in io.lines({quote(ROOT/'conky/panel.layout')}) do
 local k,v=line:match('^([%w_]+)=(.*)$'); if k then p[k]=tonumber(v) end
end
local tracks=visible.panel_tracks(p)
'''
    try:
        if lib.luaL_loadstring(state,(prefix+body).encode()) or lib.lua_pcallk(state,0,1,0,0,None):
            raise RuntimeError(lib.lua_tolstring(state,-1,None).decode())
        return lib.lua_tolstring(state,-1,None).decode()
    finally: lib.lua_close(state)


class VisibleProgressTests(unittest.TestCase):
    def test_percent_is_fraction_of_visible_length_for_every_metric(self):
        result=evaluate('''local rows={}
for _,name in ipairs({'vram','gpu','cpu','ram','gpu_temperature','cpu_temperature'}) do
 for _,percent in ipairs({0,25,50,75,100}) do
  local t=tracks[name]; local _,painted=visible.fill(t,percent)
  rows[#rows+1]=string.format('%s,%d,%.9f,%.9f',name,percent,t.length,painted)
 end
end
return table.concat(rows,string.char(10))''')
        for row in result.splitlines():
            name,percent,total,painted=row.split(',')
            with self.subTest(metric=name,percent=percent):
                self.assertGreater(float(total),0)
                self.assertAlmostEqual(float(painted)/float(total),float(percent)/100,places=7)

    def test_masks_subtract_union_of_hidden_intervals(self):
        result=evaluate('''local s=visible.segment(0,10,10,10,100,100,{{4,10,2},{6,10,2}})
local length=0; for _,v in ipairs(s) do length=length+v.length end
return string.format('%d,%.9f',#s,length)''')
        count,length=result.split(','); self.assertEqual(int(count),2); self.assertAlmostEqual(float(length),4)

    def test_empty_and_clamped_tracks(self):
        result=evaluate('''local t=visible.track{x=500,y=500,radius=10,span=5,start=0,sweep=360,count=10,width=100,height=100}
local _,empty=visible.fill(t,50); local _,over=visible.fill(tracks.ram,150); local _,under=visible.fill(tracks.ram,-10)
return string.format('%.9f,%.9f,%.9f',empty,over/tracks.ram.length,under)''')
        self.assertEqual(list(map(float,result.split(','))),[0,1,0])

    def test_visible_hardware_path_is_shorter_than_a_semicircle(self):
        result=evaluate('''local rows={}
for _,name in ipairs({'vram','gpu','cpu','ram'}) do rows[#rows+1]=string.format('%.9f',tracks[name].length/(p.gauge_count/2*p.gauge_span)) end
return table.concat(rows,',')''')
        for fraction in map(float,result.split(',')):
            self.assertGreater(fraction,.1); self.assertLess(fraction,.9)

    def test_countdowns_use_real_resets_and_expire(self):
        result=evaluate('''local rows={}
for _,seconds in ipairs({8280,273600,59,65,0,-1}) do
 local value,status=countdown.format(100+seconds,100);rows[#rows+1]=value or status
end
local value,status=countdown.format('--',100);rows[#rows+1]=value or status
return table.concat(rows,'|')''')
        self.assertEqual(result.split('|'),['2 h 18 min','3 d 4 h','59 s','1 min','expired','expired','unavailable'])


class RenderedProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); folder=Path(cls.temp.name); cls.folder=folder
        commands=[]
        for key in ['vram.percent','gpu.load','cpu.load','ram.percent','gpu.temperature','cpu.temperature']:
            for percent in [0,50,100]:
                path=folder/(key+'-'+str(percent)+'.png')
                commands.append(f'''do
 local s=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,460,1000);local cr=cairo_create(s)
 local t={{[{quote(key)}]={quote(str(percent))},['gpu.temperature.scale_max']='100',['cpu.temperature.scale_max']='100'}}
 orbita_draw_panel(cr,460,1000,t,{{}},{{}})
 cairo_destroy(cr);cairo_surface_write_to_png(s,{quote(path)});cairo_surface_destroy(s)
end''')
        script=folder/'render.lua'; rc=folder/'render.conf'
        script.write_text('dofile('+quote(ROOT/'conky/render.lua')+')\nfunction conky_progress_test()\n'+'\n'.join(commands)+'\nend\n')
        rc.write_text("conky.config={out_to_x=false,out_to_console=true,total_run_times=1,lua_load="+quote(script)+",lua_startup_hook='progress_test'};conky.text=' ';\n")
        subprocess.run(['conky','-c',str(rc)],capture_output=True,check=True,timeout=15)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def pixels(self,key,value):
        with Image.open(self.folder/(key+'-'+str(value)+'.png')) as image:
            return np.array(image.convert('RGBA')).astype(float)

    def test_half_of_visible_green_pixels_at_fifty_percent(self):
        for key in ['vram.percent','gpu.load','cpu.load','ram.percent']:
            counts=[]
            for percent in [0,50,100]:
                a=self.pixels(key,percent)
                green=(a[:,:,1]>a[:,:,0]*1.8)&(a[:,:,1]>a[:,:,2]*1.2)&(a[:,:,3]>100)
                counts.append(int(green.sum()))
            with self.subTest(metric=key):
                self.assertEqual(counts[0],0)
                self.assertGreater(counts[2],100)
                self.assertAlmostEqual(counts[1]/counts[2],.5,delta=.035)

    def test_red_only_appears_toward_maximum_for_both_components(self):
        for key in ['gpu.temperature','cpu.temperature']:
            counts=[]
            for percent in [0,50,100]:
                a=self.pixels(key,percent)
                red=(a[:,:,0]>a[:,:,1]*1.8)&(a[:,:,0]>a[:,:,2]*1.5)&(a[:,:,3]>100)
                counts.append(int(red.sum()))
            with self.subTest(component=key):
                self.assertEqual(counts[0],0); self.assertEqual(counts[1],0); self.assertGreater(counts[2],10)


if __name__=='__main__': unittest.main()
