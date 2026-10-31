"""Execute the real Cairo clipping helper: overlapping holes must never become opaque."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def lua(s):
    return "'"+str(s).replace('\\','\\\\').replace("'","\\'")+"'"


class ClippingTests(unittest.TestCase):
    def test_foreground_disks_remove_background_tracks_without_painting_the_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); output=folder/'mask.png'; panel=folder/'panel.png'; script=folder/'test.lua'; rc=folder/'test.conf'
            script.write_text(f'''dofile({lua(ROOT/'conky/render.lua')})
function conky_test_mask()
 local s=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,100,100)
 local cr=cairo_create(s)
 -- Simulate a previous frame. Clearing is necessary after shrinking/occluding a ring.
 cairo_set_source_rgba(cr,1,0,0,1); cairo_paint(cr)
 orbita_clear_panel_surface(cr)
 orbita_clip_background(cr,100,100,{{{{40,50,25}},{{65,50,25}}}},function()
  cairo_set_source_rgba(cr,0,1,0,1); cairo_paint(cr)
 end)
 cairo_destroy(cr); cairo_surface_write_to_png(s,{lua(output)}); cairo_surface_destroy(s)
 local p=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,460,1000)
 local pc=cairo_create(p)
 orbita_draw_panel(pc,460,1000,{{}},{{}},{{}})
 cairo_destroy(pc); cairo_surface_write_to_png(p,{lua(panel)}); cairo_surface_destroy(p)
end
''')
            rc.write_text("conky.config={out_to_x=false,out_to_console=true,total_run_times=1,lua_load="+lua(script)+",lua_startup_hook='test_mask'};conky.text=' ';\n")
            subprocess.run(['conky','-c',str(rc)],check=True,timeout=10,capture_output=True)
            with Image.open(output) as source:
                image=source.convert('RGBA')
                for point in [(40,50),(65,50),(52,50)]:
                    self.assertEqual(image.getpixel(point)[3],0)
                self.assertEqual(image.getpixel((5,5)),(0,255,0,255))
                self.assertEqual(image.getpixel((95,95)),(0,255,0,255))
            with Image.open(panel) as source:
                alpha=source.convert('RGBA').getchannel('A')
                # Back-ring positions inside foreground disks must be fully empty,
                # including the points that used to cross the temperature labels.
                for x,y in [(440,340),(450,490),(440,660)]:
                    self.assertEqual(alpha.crop((x-1,y-1,x+2,y+2)).getextrema()[1],0)
                # The test must still contain the intended front/visible tracks.
                self.assertGreater(alpha.crop((239,480,250,499)).getextrema()[1],0)
                self.assertGreater(alpha.crop((295,325,315,335)).getextrema()[1],0)


if __name__=='__main__': unittest.main()
