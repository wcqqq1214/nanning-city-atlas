import * as THREE from 'three';

// Display lighting is illustrative, independent of the daytime model materials.
// One uniform drives every material: changing time does not rebuild geometry.
export function createNightLighting(city: THREE.Group, lightweight: boolean) {
  const night = { value: 0 };
  const litMaterials = new Set<THREE.MeshStandardMaterial>();
  const glows: THREE.Points[] = [];
  const sources: THREE.Mesh[] = [];
  city.updateMatrixWorld(true);
  city.traverse((object) => {
    if (object instanceof THREE.Mesh) sources.push(object);
  });

  for (const mesh of sources) {
    const materials = Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material];
    for (const material of materials) {
      if (
        !(material instanceof THREE.MeshStandardMaterial) ||
        litMaterials.has(material)
      )
        continue;
      litMaterials.add(material);
      const name = material.name.toLowerCase();
      const windows =
        /glass|glazing|curtain wall|porcelain/.test(name) &&
        !/earth/.test(name);
      const accent =
        /lettering|clock face|brass accent|entrance surrounds|jade eave|ochre eave|ivory membrane|folded white aluminium|vermilion steel|pale gold steel|ivory towers|silver cables/.test(
          name,
        );
      const road = /lane markings|road markings/.test(name);

      const facadeWash =
        /mall pale limestone|museum pale limestone|longxiang warm brick|tingzi warm ivory/.test(
          name,
        );
      if (!windows && !accent && !road && !facadeWash) continue;
      const strength = windows
        ? /porcelain/.test(name)
          ? 0.7
          : 1.05
        : road
          ? 0.25
          : facadeWash
            ? 0.12
            : 0.5;
      const color = new THREE.Color(
        windows ? '#ffc879' : road ? '#ffdb99' : '#78cddd',
      );
      if (/lettering|brass|eave|entrance|gold/.test(name) || facadeWash)
        color.set('#ffc476');
      if (/vermilion steel/.test(name)) color.set('#ff8b66');
      material.onBeforeCompile = (shader) => {
        shader.uniforms.uCityNight = night;
        shader.uniforms.uCityLightColor = { value: color };
        shader.vertexShader =
          `varying vec3 vNightPosition;\n${shader.vertexShader}`.replace(
            '#include <worldpos_vertex>',
            '#include <worldpos_vertex>\nvNightPosition = (modelMatrix * vec4(transformed, 1.0)).xyz;',
          );
        shader.fragmentShader =
          `uniform float uCityNight;\nuniform vec3 uCityLightColor;\nvarying vec3 vNightPosition;\n${shader.fragmentShader}`.replace(
            '#include <emissivemap_fragment>',
            `#include <emissivemap_fragment>
          ${
            windows
              ? `
          vec3 faceNormal = normalize(cross(dFdx(vNightPosition), dFdy(vNightPosition)));
          float wall = 1.0 - smoothstep(0.3, 0.65, abs(faceNormal.y));
          // World-space cells keep windows stable while orbiting or changing quality.
          vec2 facade = vec2(abs(faceNormal.x) > abs(faceNormal.z) ? vNightPosition.z : vNightPosition.x, vNightPosition.y);
          vec2 cell = facade / vec2(0.065, 0.07);
          vec2 edge = abs(fract(cell) - 0.5);
          vec2 aa = max(fwidth(cell), vec2(0.001));
          vec2 pane = 1.0 - smoothstep(vec2(0.31) - aa, vec2(0.31) + aa, edge);
          float occupied = step(0.55, fract(sin(dot(floor(cell), vec2(127.1, 311.7))) * 43758.5453));
          float mask = wall * pane.x * pane.y * occupied;
          // Sub-pixel windows converge to their mean instead of sparkling at distance.
          mask = mix(mask, wall * 0.17, smoothstep(0.65, 2.0, max(aa.x, aa.y)));
          `
              : 'float mask = 1.0;'
          }
          totalEmissiveRadiance += uCityLightColor * (${strength.toFixed(2)} * uCityNight * mask);`,
          );
      };
      material.customProgramCacheKey = () =>
        `city-night-${windows ? 'windows' : 'accent'}-${strength}`;
      material.needsUpdate = true;
    }
  }

  // Sample the actual road markings, including elevated decks. Light halos stay
  // attached to their source mesh, inheriting layer visibility and height scale.
  const glowMaterial = new THREE.ShaderMaterial({
    uniforms: { uCityNight: night },
    vertexShader: `
      void main() {
        vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * viewPosition;
        gl_PointSize = clamp(65.0 / max(1.0, -viewPosition.z), 1.5, 9.0);
      }`,
    fragmentShader: `
      uniform float uCityNight;
      void main() {
        float r = length(gl_PointCoord - 0.5) * 2.0;
        float glow = exp(-r * r * 5.0) * (1.0 - smoothstep(0.75, 1.0, r));
        gl_FragColor = vec4(vec3(1.0, 0.65, 0.26), glow * uCityNight * 0.85);
        #include <colorspace_fragment>
      }`,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });
  const occupied = new Set<string>();
  const a = new THREE.Vector3(),
    b = new THREE.Vector3(),
    c = new THREE.Vector3();
  const normal = new THREE.Vector3(),
    center = new THREE.Vector3();
  const spacing = lightweight ? 1.25 : 0.9;
  const budget = lightweight ? 4500 : 8000;
  for (const mesh of sources) {
    const materials = Array.isArray(mesh.material)
      ? mesh.material
      : [mesh.material];
    const geometry = mesh.geometry;
    const positions = geometry.getAttribute('position');
    if (!positions) continue;
    const indices = geometry.index;
    const groups = geometry.groups.length
      ? geometry.groups
      : [
          {
            start: 0,
            count: indices?.count ?? positions.count,
            materialIndex: 0,
          },
        ];
    const points: number[] = [];
    for (const group of groups) {
      if (
        !/lane markings|road markings/i.test(
          materials[group.materialIndex ?? 0]?.name ?? '',
        )
      )
        continue;
      for (
        let i = group.start;
        i < group.start + group.count && occupied.size < budget;
        i += 3
      ) {
        a.fromBufferAttribute(
          positions,
          indices ? indices.getX(i) : i,
        ).applyMatrix4(mesh.matrixWorld);
        b.fromBufferAttribute(
          positions,
          indices ? indices.getX(i + 1) : i + 1,
        ).applyMatrix4(mesh.matrixWorld);
        c.fromBufferAttribute(
          positions,
          indices ? indices.getX(i + 2) : i + 2,
        ).applyMatrix4(mesh.matrixWorld);
        center
          .copy(a)
          .add(b)
          .add(c)
          .multiplyScalar(1 / 3);
        normal.subVectors(b, a).cross(c.sub(a)).normalize();
        if (Math.abs(normal.y) < 0.8) continue;
        const key = `${Math.floor(center.x / spacing)},${Math.floor(center.z / spacing)},${Math.floor(center.y / 0.2)}`;
        if (occupied.has(key)) continue;
        occupied.add(key);
        center.y += 0.025;
        mesh.worldToLocal(center);
        points.push(center.x, center.y, center.z);
      }
    }
    if (!points.length) continue;
    const glow = new THREE.Points(
      new THREE.BufferGeometry().setAttribute(
        'position',
        new THREE.Float32BufferAttribute(points, 3),
      ),
      glowMaterial,
    );
    glow.name = 'NightRoadLights';
    glow.visible = false;
    glow.raycast = () => {};
    mesh.add(glow);
    glows.push(glow);
  }
  // The scene's resource disposer owns the attached geometries and material.
  if (!glows.length) glowMaterial.dispose();
  return {
    setNight(value: number) {
      night.value = value;
      for (const glow of glows) glow.visible = value > 0.001;
    },
  };
}
