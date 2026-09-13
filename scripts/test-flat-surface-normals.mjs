import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { restoreFlatSurfaceNormals } from '../lib/city/flat-surface-normals.ts';

test('shared positions regain distinct face normals without moving geometry',()=>{
 const source=new THREE.BufferGeometry();source.setAttribute('position',new THREE.Float32BufferAttribute([0,0,0,1,0,0,0,1,0,0,0,1],3));source.setIndex([0,1,2,0,3,1]);
 const a=new THREE.Mesh(source),b=new THREE.Mesh(source);const scene=new THREE.Group();scene.add(a,b);let disposed=0;source.addEventListener('dispose',()=>disposed++);
 restoreFlatSurfaceNormals(scene);assert.equal(a.geometry,b.geometry);assert.equal(disposed,1);assert.equal(a.geometry.index,null);
 assert.deepEqual([...a.geometry.attributes.position.array],[0,0,0,1,0,0,0,1,0,0,0,0,0,0,1,1,0,0]);
 assert.deepEqual([...a.geometry.attributes.normal.array],[0,0,1,0,0,1,0,0,1,0,1,0,0,1,0,0,1,0]);
 const geometry=a.geometry;restoreFlatSurfaceNormals(scene);assert.equal(a.geometry,geometry);assert.equal(disposed,1);
});

test('explicit artistic normals and geometry remain untouched',()=>{
 const source=new THREE.BufferGeometry();source.setAttribute('position',new THREE.Float32BufferAttribute([0,0,0,1,0,0,0,1,0],3));source.setAttribute('normal',new THREE.Float32BufferAttribute([0,.6,.8,0,.6,.8,0,.6,.8],3));
 const mesh=new THREE.Mesh(source);const before=source.attributes.normal.array.slice();restoreFlatSurfaceNormals(mesh);assert.equal(mesh.geometry,source);assert.deepEqual(source.attributes.normal.array,before);
});
