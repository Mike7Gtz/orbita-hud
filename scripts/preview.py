#!/usr/bin/env python3
"""Render the actual Conky/Lua drawing code offscreen with clearly marked sample data."""
from pathlib import Path
import argparse
import math
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def lua_string(s):
    return "'"+str(s).replace('\\','\\\\').replace("'","\\'")+"'"


def main():
    p=argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    p.add_argument('--side', choices=['left','right'], default='right')
    args=p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='orbita-preview-') as tmp:
        folder=Path(tmp)
        script=folder/'preview.lua'
        # Synthetic FFT and percentages exist ONLY in this explicitly labeled preview.
        bands=','.join(f'{.15+.72*abs(math.sin(i*.31)*math.cos(i*.117)):.3f}' for i in range(96))
        script.write_text(f'''dofile({lua_string(ROOT/'conky/render.lua')})
function conky_preview()
 local s=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,1920,1080)
 local cr=cairo_create(s)
 cairo_set_source_rgb(cr,0.025,0.055,0.095); cairo_paint(cr)
 local t={{['gpu.temperature']='54',['cpu.temperature']='48',['gpu.load']='17',['cpu.load']='9',['ram.percent']='13',['vram.percent']='11'}}
 local u={{['chatgpt.stale']='0',['claude.stale']='0',['chatgpt.observed_at']='1793389320',['claude.observed_at']='1793389320',['chatgpt.source']='Codex / ChatGPT',['claude.source']='example',
 ['chatgpt.session.used']='68',['chatgpt.weekly.used']='42',['claude.session.used']='53',['claude.weekly.used']='26'}}
 local a={{available='1',bands={lua_string(bands)}}}
 cairo_save(cr); cairo_translate(cr,510,90); orbita_draw_clock(cr,900,900,t,u,a,1793389320); cairo_restore(cr)
 cairo_save(cr); cairo_translate(cr,{'0' if args.side=='left' else '1503'},18)
 orbita_draw_panel(cr,417,1044,t,u,a,1793389320,{lua_string(args.side)}); cairo_restore(cr)
 cairo_set_source_rgb(cr,.4,.6,.75); cairo_select_font_face(cr,'DejaVu Sans',0,0); cairo_set_font_size(cr,15)
 cairo_move_to(cr,30,1045); cairo_show_text(cr,'ÓRBITA HUD · ONOCRU · VISTA DE EJEMPLO, NO DATOS EN VIVO')
 cairo_destroy(cr); cairo_surface_write_to_png(s,{lua_string(args.output.resolve())}); cairo_surface_destroy(s)
end
''')
        rc=folder/'preview.conf'
        rc.write_text("conky.config={out_to_x=false,out_to_console=true,total_run_times=1,lua_load="+lua_string(script)+",lua_startup_hook='preview'}; conky.text=' ';\n")
        subprocess.run(['conky','-c',str(rc)],check=True,timeout=10)
    print(args.output)


if __name__=='__main__': main()
