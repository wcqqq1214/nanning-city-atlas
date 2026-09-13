"""Compare upstream and final support without feeding resolved roads back upstream.

This audits prepared-building candidates only. It records unsupported structures
explicitly and does not replace complete road capture or final city validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

TOOLS_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS_ROOT/'blender'))
from building_support_plan import BuildingSupportPlan
from building_placement import prepared,envelope,validate_road_envelope
from road_inputs import building_envelopes


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene-root',type=Path,default=TOOLS_ROOT)
    parser.add_argument('--base-support',type=Path,required=True)
    parser.add_argument('--final-support',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.scene_root.resolve()
    # Placement helpers are the current implementation; site visibility and its
    # import-time data must come from the scene being audited, including staging.
    sys.path.insert(0,str(root/'blender'))
    from city_visibility import CityVisibility
    from railways import REMOVED_BUILDINGS
    geography=json.loads((root/'public/data/geography.json').read_text())
    visibility=CityVisibility(geography,json.loads((root/'data/landmarks.json').read_text()))
    base=BuildingSupportPlan.read(args.base_support,root)
    final=BuildingSupportPlan.read(args.final_support,root)
    if any(name.startswith('data/road-solids-') for name in base.payload['runtimeInputs']):
        raise ValueError('Base support is downstream of the roads it would rebuild')
    records=[];unresolved=[];mismatches=[];hidden=[]
    for index,building in enumerate(geography['buildings']):
        if not prepared(building):continue
        if not visibility.building_visible(building,railway_hidden=index in REMOVED_BUILDINGS):
            hidden.append(building['id']);continue
        try:
            before=envelope(building,base);after=envelope(building,final)
        except ValueError as error:
            if building.get('use')!='dam' and not str(error).startswith('Incomplete terrain under '):raise
            unresolved.append({'index':index,'id':building['id'],'sourceRef':building.get('sourceRef'),'reason':str(error)})
            continue
        captured=building_envelopes(geography,[[index,before['bottom'],before['top']]])
        errors={key:abs(before[key]-after[key])*100 for key in ['bottom','top']}
        record={'index':index,'id':building['id'],'kind':after['kind'],
                'base':[before['bottom'],before['top']],'final':[after['bottom'],after['top']],
                'errorsMeters':errors,'siteReviewRequired':after['siteReviewRequired']}
        records.append(record)
        try:validate_road_envelope(index,building,after,{index:captured[0]})
        except ValueError as error:mismatches.append({'id':building['id'],'reason':str(error),**errors})
    files={}
    for module in list(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if not filename:continue
        path=Path(filename).resolve()
        if path.parent in [root/'blender',TOOLS_ROOT/'blender'] and path.suffix=='.py':files[str(path)]=digest(path)
    paths={'baseSupport':args.base_support.resolve(),'finalSupport':args.final_support.resolve(),
           'geography':root/'public/data/geography.json','tool':Path(__file__).resolve()}
    result={'status':'prepared-volume parity audit; unresolved structures and complete road/city integration pending',
            'sceneRoot':str(root),'toolsRoot':str(TOOLS_ROOT),'checked':len(records),'hiddenBySitesOrRailway':len(hidden),
            'compoundBuildings':sum(r['kind']=='compound' for r in records),
            'largeReliefSiteReviews':sum(r['siteReviewRequired'] for r in records),
            'maximumEnvelopeDifferenceMeters':max((max(r['errorsMeters'].values()) for r in records),default=0),
            'toleranceMeters':.005,'unresolved':unresolved,'mismatches':mismatches,
            'records':records,'hiddenIds':hidden,'moduleHashes':files,
            'inputs':{name:{'path':str(path),'sha256':digest(path)} for name,path in paths.items()}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['records','hiddenIds','moduleHashes','inputs']},ensure_ascii=False,indent=2))
    if mismatches:raise SystemExit('Building support changes require upstream recapture')


if __name__=='__main__':main()
