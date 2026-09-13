"""Source-bound water-control structures owned by active reservoir plans."""
import hashlib
import json
import re
from pathlib import Path
from water_control_structures import WaterControlStructure

MATERIAL_KEYS=['viaduct_concrete','viaduct_metal']


class WaterControls:
    def __init__(self,entries,reservoirs,root):
        self.records=[];self.input_paths=[];ids=set();names=set()
        root=Path(root).resolve()
        geo=json.loads((root/'public/data/geography.json').read_text()) if entries else None
        plans={p.payload['id']:p for p in reservoirs.plans}
        for entry in entries:
            path=(root/entry['source']).resolve();name=str(path.relative_to(root))
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
                raise ValueError('Reprepare water-control registry after changing '+name)
            spec=json.loads(path.read_text());identity=spec['id']
            if identity!=entry['id'] or not re.fullmatch(r'[a-z0-9_-]+',identity):
                raise ValueError('Invalid water-control registry identity')
            node='Reservoir_control_'+identity.replace('-','_')
            if node in names or name in self.input_paths:raise ValueError('Duplicate water-control source or node')
            model=WaterControlStructure(spec,geo);owner=plans.get(entry['reservoirId'])
            if owner is None or spec['waterIndex'] not in {w['geographyWaterIndex'] for w in owner.payload['waterBodies']}:
                raise ValueError('Water-control structure must belong to its active lake plan')
            if spec['buildingId'] in ids or spec['buildingId'] in reservoirs.dam_ids:
                raise ValueError('Duplicate embankment/structure ownership of a mapped dam')
            ids.add(spec['buildingId']);names.add(node);self.input_paths.append(name)
            self.records.append({'model':model,'owner':owner,'node':node,'source':name})
        self.ids=frozenset(ids)

    def build(self,env,parent):
        results=[];bounds=env['GEO']['bounds'];cols=env['COLS'];rows=env['ROWS']
        final=lambda x,y,m:env['terrain_surface'](x,y,env['height'],bounds,cols,rows,lightweight=m)
        for record in self.records:
            owner=record['owner'];surfaces=[]
            for mobile in [False,True]:
                surface,collapsed=owner.surface(env['unpatched_height'],bounds,cols,rows,mobile,env['coarse_terrain_surface'])
                if collapsed:raise ValueError('Water-control support has collapsed native terrain faces')
                surfaces.append(surface)
            geometry=record['model'].geometry_on_surfaces(surfaces,owner.water_level,final)
            batch=env['Batch'](record['node'],MATERIAL_KEYS)
            for part in geometry['parts']:
                for face in part['faces']:batch.face(face,part['material'])
            obj=batch.finish();obj.parent=parent
            obj['mappedBuildingId']=record['model'].spec['buildingId']
            obj['reservoirId']=owner.payload['id']
            obj['sourceSha256']=hashlib.sha256((env['ROOT']/record['source']).read_bytes()).hexdigest()
            results.append({'id':record['model'].spec['id'],'node':record['node'],
                            'buildingId':record['model'].spec['buildingId'],'source':record['source'],'geometry':geometry})
        return results
