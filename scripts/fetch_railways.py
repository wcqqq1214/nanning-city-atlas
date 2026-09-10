"""Retain a reproducible OSM railway snapshot for the current city extent.

Existing matching snapshots are reused. Pass --refresh to deliberately replace
the snapshot; normal model rebuilding never requests the public API.
"""
import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(refresh=False):
    bbox = json.loads((ROOT/'data/region.json').read_text())['bbox']
    path = ROOT/'data/railways-source.json'
    if path.exists() and not refresh:
        assert json.loads(path.read_text())['bbox'] == bbox, 'Railway extent changed; use --refresh'
        print('Reusing', path)
        return
    w, s, e, n = bbox
    query = f'[out:json][timeout:180];way["railway"="rail"]({s},{w},{n},{e});out body geom;'
    failures = []
    for endpoint in ['https://overpass-api.de/api/interpreter',
                     'https://overpass.kumi.systems/api/interpreter']:
        try:
            request = urllib.request.Request(endpoint,
                urllib.parse.urlencode({'data': query}).encode(),
                headers={'User-Agent': 'NanningCityAtlas/1.0 geographic visualization'})
            with urllib.request.urlopen(request, timeout=210) as response:
                source = json.load(response)
            if source.get('remark') or not source.get('elements'):
                raise ValueError(source.get('remark', 'Empty railway snapshot'))
            source.update(bbox=bbox, query=query, endpoint=endpoint,
                          attribution='© OpenStreetMap contributors, ODbL 1.0')
            path.write_text(json.dumps(source, ensure_ascii=False, separators=(',', ':'))+'\n')
            print(f"Saved {len(source['elements'])} railway ways at {source['osm3s']['timestamp_osm_base']}", flush=True)
            return
        except Exception as error:
            failures.append(str(error))
            print(f'{endpoint}: {error}', flush=True)
    raise RuntimeError('No complete railway snapshot: '+'; '.join(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    fetch(parser.parse_args().refresh)
