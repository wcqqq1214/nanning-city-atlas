"""Check all actual Zhuxi builders before spending memory on a full city export."""
import hashlib,json
import numpy as np
from road_collision_checks import ROOT,intersections


def validate():
    folder=ROOT/'work/zhuxi-repair'
    for path,digest in json.loads((folder/'native-inputs.json').read_text()).items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,f'Recapture interfaces after changing {path}'
    report={}
    for profile in ['detail','smooth']:
        with np.load(folder/f'native-interfaces-{profile}.npz') as data:
            groups={key:data[key] for key in data.files}
        assert all(len(groups[key])>0 for key in ['roads','structure','lamps'])
        report[profile]={}
        for a,b in [('structure','roads'),('lamps','roads'),('lamps','structure'),('roads','roads')]:
            result=intersections(groups[a],groups[b],profile+' actual builders '+a+'/'+b,self_test=a==b)
            report[profile][a+'/'+b]=result
        assert all(r['pairs']==0 for r in report[profile].values()),f'Incomplete {profile} road interface repair'
    (folder/'native-validation.json').write_text(json.dumps(report))
    print('PASS: both profiles include native Minzu walls/abutments, resolved roads and lamps without intersections.')


if __name__=='__main__':validate()
