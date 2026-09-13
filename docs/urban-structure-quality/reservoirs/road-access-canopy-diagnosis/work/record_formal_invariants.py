from pathlib import Path
import json,hashlib
root=Path.cwd();source=root/'work/urban-structure/p5/staging/work/p5/tianbao-formal-before.json';expected=json.loads(source.read_text());actual={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in expected};record={'passed':actual==expected,'expected':expected,'actual':actual};(root/'work/urban-structure/p5/full-city-review/road-canopy-formal-assets.json').write_text(json.dumps(record,indent=2)+'\n');assert record['passed'];print('PASS: five formal P4 assets unchanged')
