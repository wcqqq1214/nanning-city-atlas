"""Compose a review-only full scene from frozen city and checked canopy exports."""
from pathlib import Path
import copy,hashlib,json,struct,sys
root=Path.cwd();sys.path.insert(0,str(root/'scripts'))
from pack_flat_surfaces import referenced_views,remap_views
b=root/'work/urban-structure/p5/full-city-review';stage=b/'precision-complete-models';out=b/'global-conforming-v3-preview';out.mkdir(exist_ok=False)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 raw=p.read_bytes();assert struct.unpack_from('<III',raw)==(0x46546c67,2,len(raw));n,k=struct.unpack_from('<II',raw,12);assert k==0x4e4f534a
 d=json.loads(raw[20:20+n]);binary=raw[28+n:];return d,[binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']] for v in d['bufferViews']]
reports=[]
for profile,filename in [('detail','nanning-city.glb'),('smooth','nanning-city-mobile.glb')]:
 source=stage/'public/models'/filename;doc,payloads=read(source);original=copy.deepcopy(doc);old_payloads=list(payloads);records=[];changed_meshes=set();inputs={str(source):digest(source)}
 for region in ['nearby','all']:
  p=b/'global-conforming-v3-native'/(region+'-'+profile+'.glb');d,blobs=read(p);inputs[str(p)]=digest(p)
  old_nodes={n['name']:n for n in doc['nodes'] if 'mesh' in n and n.get('name','').startswith('Vegetation_'+region+'_canopy_')}
  new_nodes={n['name'].replace(region+'-'+profile,region):n for n in d['nodes'] if 'mesh' in n}
  assert old_nodes.keys()==new_nodes.keys(),'Changed spatial batch ownership requires a full rebuild'
  for name,node in new_nodes.items():
   assert not any(k in node for k in ['matrix','translation','rotation','scale'])
   mesh_id=old_nodes[name]['mesh'];mesh=doc['meshes'][mesh_id];parts=[]
   for primitive in d['meshes'][node['mesh']]['primitives']:
    q=copy.deepcopy(primitive);material=d['materials'][q['material']]
    matches=[i for i,m in enumerate(doc['materials']) if m==material];assert len(matches)==1,'Canopy material changed';q['material']=matches[0]
    for key,accessor_id in list(q['attributes'].items()):
     a=copy.deepcopy(d['accessors'][accessor_id]);assert 'bufferView' not in a and 'sparse' not in a
     q['attributes'][key]=len(doc['accessors']);doc['accessors'].append(a)
    a=copy.deepcopy(d['accessors'][q['indices']]);assert 'bufferView' not in a and 'sparse' not in a
    q['indices']=len(doc['accessors']);doc['accessors'].append(a)
    extension=q['extensions']['KHR_draco_mesh_compression'];old_view=extension['bufferView'];extension['bufferView']=len(payloads)
    payloads.append(blobs[old_view]);doc['bufferViews'].append({'buffer':0,'byteLength':len(blobs[old_view])});parts.append(q)
   mesh['primitives']=parts;changed_meshes.add(mesh_id);records.append(name)
 # Unchanged mesh records and every byte of their encoded attributes must stay.
 for i,m in enumerate(original['meshes']):
  if i in changed_meshes:continue
  assert m==doc['meshes'][i]
  for v in referenced_views(m):assert payloads[v]==old_payloads[v]
 for key in ['nodes','scenes','scene','materials','images','textures','samplers']:assert original.get(key)==doc.get(key),key
 used=sorted(set(referenced_views(doc)));mapping={v:i for i,v in enumerate(used)};views=doc.pop('bufferViews');remap_views(doc,mapping)
 binary=bytearray();new_views=[]
 for v in used:
  binary.extend(b'\0'*(-len(binary)%4));view=copy.deepcopy(views[v]);view['byteOffset']=len(binary);view['buffer']=0;binary.extend(payloads[v]);new_views.append(view)
 doc['bufferViews']=new_views;doc['buffers']=[{'byteLength':len(binary)}];binary.extend(b'\0'*(-len(binary)%4));s=json.dumps(doc,separators=(',',':')).encode();s+=b' '*(-len(s)%4)
 raw=struct.pack('<III',0x46546c67,2,28+len(s)+len(binary))+struct.pack('<II',len(s),0x4e4f534a)+s+struct.pack('<II',len(binary),0x004e4942)+binary
 target=out/'public/models'/filename;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 reports.append({'profile':profile,'inputs':inputs,'outputSha256':digest(target),'bytes':len(raw),'replacedNodes':records,'otherMeshRecordsAndPayloadBytesExact':True,'sceneHierarchyAndMaterialsExact':True})
data=out/'public/data';data.mkdir(parents=True);overview=json.loads((stage/'public/data/overview.json').read_text())
for r in reports:overview['models'][r['profile']]['bytes']=r['bytes']
(data/'overview.json').write_text(json.dumps(overview,separators=(',',':'))+'\n');(data/'landmarks.json').write_bytes((stage/'public/data/landmarks.json').read_bytes())
(out/'report.json').write_text(json.dumps({'status':'review-only composition; source pipeline integration, full validators and budgets pending','profiles':reports,'toolSha256':digest(Path(__file__))},indent=2)+'\n');print([(r['profile'],len(r['replacedNodes'])) for r in reports])
