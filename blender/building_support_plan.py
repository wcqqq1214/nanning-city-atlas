"""Source-bound complete-footprint support for staged building consumers.

Reading a supported range does not certify site design: large relief and access
still require review. Uncovered footprints cannot silently use a center sample.
"""
import hashlib
import json
import math
from pathlib import Path


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class BuildingSupportPlan:
    def __init__(self,payload):
        if payload.get('metersPerUnit')!=100:raise ValueError('Expected 100 m scene units')
        self.payload=payload;self.records={}
        for record in payload['records']:
            if record['id'] in self.records:raise ValueError('Duplicate building support ID')
            self.records[record['id']]=record

    def bounds(self,building):
        record=self.records.get(building['id'])
        if record is None:raise ValueError(f'Missing support for {building["id"]}')
        footprint=hashlib.sha256(json.dumps(building['rings'],separators=(',',':')).encode()).hexdigest()
        if footprint!=record['footprintHash']:raise ValueError(f'Stale footprint support for {building["id"]}')
        if record['status']!='supported' or any(record['profiles'][p]['status']!='covered' for p in ['detail','smooth']):
            raise ValueError(f'Incomplete terrain under {building["id"]}; site review required')
        low,high=record['groundRangeSceneZ']
        expected=(min(record['profiles'][p]['minimumSceneZ'] for p in ['detail','smooth']),
                  max(record['profiles'][p]['maximumSceneZ'] for p in ['detail','smooth']))
        if not all(math.isfinite(v) for v in [low,high]) or low>high or (low,high)!=expected:
            raise ValueError('Support range differs from actual profile extrema')
        return low,high

    @classmethod
    def read(cls,path,root):
        root=Path(root).resolve();payload=json.loads(Path(path).read_text())
        hashes=payload.get('runtimeInputs',{})
        if not all(name in hashes for name in ['public/data/geography.json','public/data/terrain.json']):
            raise ValueError('Prepare source-bound support before city integration')
        for name,expected in hashes.items():
            source=(root/name).resolve();source.relative_to(root)
            if not source.is_file() or digest(source)!=expected:raise ValueError(f'Stale support source: {name}')
        for name in ['geography','detail','smooth']:
            entry=payload['inputs'][name];source=(root/entry['path']).resolve();source.relative_to(root)
            if not source.is_file() or digest(source)!=entry['sha256']:raise ValueError(f'Stale support context: {name}')
        if payload['inputs']['geography']['sha256']!=hashes['public/data/geography.json']:
            raise ValueError('Support geography differs from runtime inputs')
        return cls(payload)
