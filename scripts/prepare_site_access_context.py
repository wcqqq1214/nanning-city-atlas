"""Bind support preparation to checked, actually exported access terrain."""
import argparse
import hashlib
import json
from pathlib import Path


def prepare(root,runtime,candidate):
    root=root.resolve();report_path=runtime/'report.json';report=json.loads(report_path.read_text())
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if report['candidateSha256']!=digest(candidate):raise ValueError('Runtime candidate changed')
    bindings={}
    def add(name,expected):
        path=(root/name).resolve();relative=str(path.relative_to(root))
        if digest(path)!=expected:raise ValueError('Stale runtime source: '+relative)
        if relative in bindings and bindings[relative]!=expected:raise ValueError('Conflicting source: '+relative)
        bindings[relative]=expected
    for field in ['inputs','tools']:
        for name,expected in report[field].items():add(name,expected)
    # The audited candidate binds its original terrain report and road metadata;
    # carry their checked source dependencies into the final support manifest.
    for name in list(bindings):
        path=root/name
        if path.suffix!='.json' or path.name=='block-grading-plan.json':continue
        metadata=json.loads(path.read_text())
        for field in ['inputHashes','tools']:
            for dependency,expected in metadata.get(field,{}).items():add(dependency,expected)
    for profile in ['detail','smooth']:
        entry=report['profiles'][profile]
        if not entry['outsidePositionsMaterialsCornerNormalsIdentical'] or not entry['cityAndForestShareSampler']:
            raise ValueError('Runtime scope or sampler audit incomplete')
        add(runtime/(profile+'.glb'),entry['export']['sha256'])
    add(candidate,digest(candidate));add(report_path,digest(report_path))
    return {'status':'actual terrain and access context; city buildings and surrounding roads not included',
            'inputHashes':bindings,'runtimeAudit':str(report_path.resolve().relative_to(root))}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['root','runtime','candidate','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    args.output.write_text(json.dumps(prepare(args.root,args.runtime.resolve(),args.candidate.resolve()),indent=2)+'\n')
