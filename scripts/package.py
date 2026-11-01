#!/usr/bin/env python3
from pathlib import Path
import hashlib
import subprocess
import runpy
import zipfile
ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'dist'; output.mkdir(exist_ok=True)
version=runpy.run_path(str(ROOT/'src/orbita_hud/__init__.py'))['__version__']
target=output/f'orbita-hud-{version}.zip'
exclude={'dist','build','.git','references','__pycache__','.venv'}
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    if (ROOT/'.git').is_dir():
        tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        files=[ROOT/name for name in tracked if name]
    else:
        top={'README.md','CHANGELOG.md','CREDITS.md','LICENSE','.gitignore','install.sh','runner.py','config.example.toml','conkyrc-clock','conkyrc-panel'}
        folders={'src','scripts','tests','docs','assets','conky','contrib','.github'}
        files=[f for f in ROOT.rglob('*') if f.relative_to(ROOT).parts[0] in folders or f.name in top]
    for file in sorted(files):
        rel=file.relative_to(ROOT)
        if not file.is_file() or exclude.intersection(rel.parts): continue
        if file.suffix in {'.pyc','.state','.log','.pid','.lock'}: continue
        if file.name.startswith('usage-private'): continue
        z.write(file,Path('orbita-hud')/rel)
digest=hashlib.sha256(target.read_bytes()).hexdigest()
target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n')
print(target)
