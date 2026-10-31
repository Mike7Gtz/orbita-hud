#!/usr/bin/env python3
"""Parse Lua using Conky's system Lua library, including CM transparency edits."""
from pathlib import Path
import ctypes
import ctypes.util
import re
import tempfile

ROOT=Path(__file__).resolve().parents[1]
name=ctypes.util.find_library('lua5.3') or ctypes.util.find_library('lua5.4')
if not name: raise SystemExit('Se necesita liblua5.3 o liblua5.4')
lua=ctypes.CDLL(name)
lua.luaL_newstate.restype=ctypes.c_void_p
lua.luaL_loadfilex.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p]
lua.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p]
lua.lua_tolstring.restype=ctypes.c_char_p
lua.lua_close.argtypes=[ctypes.c_void_p]


def check(path):
    state=lua.luaL_newstate()
    try:
        if lua.luaL_loadfilex(state,str(path).encode(),None):
            raise RuntimeError(lua.lua_tolstring(state,-1,None).decode())
    finally: lua.lua_close(state)


for path in list((ROOT/'conky').glob('*.lua'))+list(ROOT.glob('conkyrc-*')):
    check(path)
    if path.name.startswith('conkyrc-'):
        text=path.read_text()
        edited=re.sub(r'(?m)^(\s*own_window_transparent\s*=).*$',r'\1 false,',text)
        edited=re.sub(r'(?m)^(\s*own_window_argb_value\s*=).*$',r'\1 230,',edited)
        for prop in ('minimum_width','minimum_height','maximum_width'):
            before=re.search(r'(?m)^\s*'+prop+r'\s*=\s*(\d+),',text).group(1)
            after=re.search(r'(?m)^\s*'+prop+r'\s*=\s*(\d+),',edited).group(1)
            assert before==after
        with tempfile.NamedTemporaryFile(suffix='.lua',mode='w') as f:
            f.write(edited); f.flush(); check(Path(f.name))
print('Lua correcto; cambios de transparencia conservan las dimensiones.')
