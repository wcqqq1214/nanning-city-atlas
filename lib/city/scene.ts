import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import type {
  Landmark,
  Overview,
  SceneController,
  SceneOptions,
} from './types';
import { DEFAULT_LAYERS } from './types';
import { assetUrl } from './assets';

export async function createCityScene(
  host: HTMLElement,
  callbacks: {
    progress: (message: string, value: number) => void;
    ready: (places: Landmark[], overview: Overview) => void;
    select: (id: string) => void;
    heading: (angle: number) => void;
    view: (lon: number, lat: number) => void;
    interaction: () => void;
    error: (message: string) => void;
  },
  signal: AbortSignal,
): Promise<SceneController> {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#e1eae4');
  scene.fog = new THREE.FogExp2('#e1eae4', 0.0012);
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: false,
    preserveDrawingBuffer: true,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.7));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.23;
  renderer.domElement.className = 'city-canvas';
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute(
    'aria-label',
    '南宁三维地图。方向键平移，加减键缩放，Home 键复位；鼠标拖动旋转，右键拖动平移。',
  );
  host.appendChild(renderer.domElement);
  const labelLayer = document.createElement('div');
  labelLayer.className = 'map-labels';
  host.appendChild(labelLayer);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.2, 1500);
  const initialPosition = new THREE.Vector3(112, 162, 177);
  const overviewPosition = () =>
    initialPosition.clone().multiplyScalar(Math.max(1, 1.32 / camera.aspect));
  camera.position.copy(initialPosition);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.065;
  controls.minDistance = 9;
  controls.maxDistance = 360;
  controls.maxPolarAngle = Math.PI / 2.12;
  controls.minPolarAngle = 0.025;
  controls.autoRotateSpeed = 0.45;
  controls.target.set(0, 0, 0);
  controls.update();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hemi = new THREE.HemisphereLight('#f4f8eb', '#668f84', 2.5);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight('#fff3d7', 3.4);
  sun.position.set(-90, 130, 40);
  sun.castShadow = true;
  Object.assign(sun.shadow.camera, {
    left: -145,
    right: 145,
    top: 140,
    bottom: -140,
    near: 1,
    far: 500,
  });
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.00015;
  sun.shadow.normalBias = 0.08;
  scene.add(sun);
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(2400, 2400),
    new THREE.MeshStandardMaterial({ color: '#dce5df', roughness: 1 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -2.8;
  floor.receiveShadow = true;
  scene.add(floor);
  const grid = new THREE.GridHelper(400, 40, '#8ba79b', '#9fb6a9');
  grid.position.y = -2.77;
  const gridMaterial = grid.material as THREE.Material;
  gridMaterial.transparent = true;
  gridMaterial.opacity = 0.19;
  scene.add(grid);
  let destroyed = false;
  let frame = 0;
  let city: THREE.Group | null = null;
  let places: Landmark[] = [];
  let overview: Overview | null = null;
  let option: SceneOptions = {
    layers: { ...DEFAULT_LAYERS },
    hour: 14,
    heightScale: 1,
    autoRotate: false,
    topDown: false,
    selected: null,
  };
  let flight: {
    from: THREE.Vector3;
    to: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
    start: number;
    duration: number;
  } | null = null;
  const labels: {
    el: HTMLButtonElement;
    point: THREE.Vector3;
    place: Landmark;
  }[] = [];
  const meshes: THREE.Mesh[] = [];
  const materialDefaults = new Map<THREE.MeshStandardMaterial, THREE.Color>();
  const draco = new DRACOLoader()
    .setDecoderPath(assetUrl('/draco/'))
    .setWorkerLimit(2);
  const selectedRing = new THREE.Mesh(
    new THREE.RingGeometry(0.85, 0.94, 64),
    new THREE.MeshBasicMaterial({
      color: '#c69844',
      transparent: true,
      opacity: 0.9,
      side: THREE.DoubleSide,
      depthTest: false,
    }),
  );
  selectedRing.rotation.x = -Math.PI / 2;
  selectedRing.visible = false;
  selectedRing.renderOrder = 3;
  scene.add(selectedRing);
  let waterMaterial: THREE.ShaderMaterial | null = null;
  let lastFrameTime = 0;
  let lastTelemetry = 0;
  const projected = new THREE.Vector3();
  const viewDirection = new THREE.Vector3();
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let pointerDown: { x: number; y: number } | null = null;
  const startInteraction = () => {
    flight = null;
    callbacks.interaction();
  };
  controls.addEventListener('start', startInteraction);
  const resize = () => {
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    controls.maxDistance = Math.max(360, overviewPosition().length() * 1.15);
    if (!option.selected && !flight)
      camera.position.copy(
        option.topDown
          ? new THREE.Vector3(0, overviewPosition().length(), 0.5)
          : overviewPosition(),
      );
  };
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  resize();

  const fly = (target: THREE.Vector3, position: THREE.Vector3) => {
    flight = {
      from: camera.position.clone(),
      to: position,
      fromTarget: controls.target.clone(),
      toTarget: target,
      start: performance.now(),
      duration: reduced ? 0 : 1500,
    };
  };
  const focus = (id: string | null) => {
    const place = places.find((p) => p.id === id);
    if (!place) {
      fly(
        new THREE.Vector3(),
        option.topDown
          ? new THREE.Vector3(0, overviewPosition().length(), 0.5)
          : overviewPosition(),
      );
      return;
    }
    const target = new THREE.Vector3(...place.position);
    target.y *= option.heightScale;
    const distance =
      place.id === 'nanhu' ? 40 : place.id === 'qingxiu' ? 33 : 21;
    const offset = option.topDown
      ? new THREE.Vector3(0, distance * 2, 0.1)
      : new THREE.Vector3(distance, distance * 1.15, distance * 1.35);
    fly(target, target.clone().add(offset));
  };
  const keyDown = (event: KeyboardEvent) => {
    const directions: Record<string, [number, number]> = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    if (event.key in directions) {
      event.preventDefault();
      startInteraction();
      const [x, z] = directions[event.key];
      const amount = camera.position.distanceTo(controls.target) * 0.025;
      const delta = new THREE.Vector3(x * amount, 0, z * amount);
      camera.position.add(delta);
      controls.target.add(delta);
    } else if (event.key === '+' || event.key === '=') {
      event.preventDefault();
      zoom(0.8);
    } else if (event.key === '-') {
      event.preventDefault();
      zoom(1.25);
    } else if (event.key === 'Home') {
      event.preventDefault();
      focus(null);
    }
  };
  const zoom = (factor: number) => {
    flight = null;
    const offset = camera.position.clone().sub(controls.target);
    offset.setLength(
      THREE.MathUtils.clamp(
        offset.length() * factor,
        controls.minDistance,
        controls.maxDistance,
      ),
    );
    camera.position.copy(controls.target).add(offset);
    controls.update();
  };
  renderer.domElement.addEventListener('keydown', keyDown);
  const onPointerDown = (event: PointerEvent) => {
    pointerDown = { x: event.clientX, y: event.clientY };
  };
  const onPointerUp = (event: PointerEvent) => {
    if (
      !pointerDown ||
      Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y) >
        5 ||
      !city
    )
      return;
    pointerDown = null;
    const bounds = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      (-(event.clientY - bounds.top) / bounds.height) * 2 + 1,
    );
    raycaster.setFromCamera(pointer, camera);
    // Limit raycasting to the interactive landmark meshes, keeping city interaction cheap.
    const targets = places
      .map((p) => city!.getObjectByName(`Landmark_${p.id}`))
      .filter((o): o is THREE.Object3D => Boolean(o?.visible));
    const hit = raycaster.intersectObjects(targets, true)[0];
    if (hit) {
      let object: THREE.Object3D | null = hit.object;
      while (object) {
        const place = places.find((p) => object!.name === `Landmark_${p.id}`);
        if (place) {
          callbacks.select(place.id);
          break;
        }
        object = object.parent;
      }
    }
  };
  renderer.domElement.addEventListener('pointerdown', onPointerDown);
  renderer.domElement.addEventListener('pointerup', onPointerUp);
  const contextLost = (event: Event) => {
    event.preventDefault();
    callbacks.error('图形上下文已中断，请重新载入场景。');
  };
  renderer.domElement.addEventListener('webglcontextlost', contextLost);

  function animate(now: number) {
    if (destroyed) return;
    frame = requestAnimationFrame(animate);
    if (document.hidden) {
      lastFrameTime = now;
      return;
    }
    const delta = Math.min(0.06, (now - lastFrameTime) / 1000 || 0.016);
    lastFrameTime = now;
    if (flight) {
      const t =
        flight.duration === 0
          ? 1
          : Math.min(1, (now - flight.start) / flight.duration);
      const eased = t * t * (3 - 2 * t);
      camera.position.lerpVectors(flight.from, flight.to, eased);
      controls.target.lerpVectors(flight.fromTarget, flight.toTarget, eased);
      if (t >= 1) flight = null;
    }
    controls.update(delta);
    // Keep panning on this finite geographic tile.
    if (overview) {
      const x = THREE.MathUtils.clamp(
        controls.target.x,
        overview.bounds[0],
        overview.bounds[2],
      );
      const z = THREE.MathUtils.clamp(
        controls.target.z,
        -overview.bounds[3],
        -overview.bounds[1],
      );
      camera.position.x += x - controls.target.x;
      camera.position.z += z - controls.target.z;
      controls.target.x = x;
      controls.target.z = z;
    }
    if (waterMaterial)
      waterMaterial.uniforms.uTime.value = reduced ? 0 : now / 1000;
    renderer.render(scene, camera);
    camera.getWorldDirection(viewDirection);
    const occupied: { x: number; y: number }[] = [];
    const ordered = [...labels].sort(
      (a, b) =>
        Number(b.place.id === option.selected) -
        Number(a.place.id === option.selected),
    );
    for (const label of ordered) {
      projected.copy(label.point);
      projected.y *= option.heightScale;
      const inFront =
        projected.clone().sub(camera.position).dot(viewDirection) > 0;
      projected.project(camera);
      const x = (projected.x * 0.5 + 0.5) * host.clientWidth;
      const y = (-projected.y * 0.5 + 0.5) * host.clientHeight;
      const collision = occupied.some(
        (p) => Math.abs(p.x - x) < 125 && Math.abs(p.y - y) < 44,
      );
      const show =
        option.layers.labels &&
        inFront &&
        projected.z < 1 &&
        x > 40 &&
        x < host.clientWidth - 40 &&
        y > 60 &&
        y < host.clientHeight - 74 &&
        !collision;
      label.el.style.display = show ? 'flex' : 'none';
      if (show) {
        label.el.style.transform = `translate(${x}px,${y}px) translate(-50%,-100%)`;
        occupied.push({ x, y });
      }
    }
    if (now - lastTelemetry > 180) {
      lastTelemetry = now;
      callbacks.heading((controls.getAzimuthalAngle() * 180) / Math.PI);
      if (overview)
        callbacks.view(
          overview.center[0] +
            controls.target.x /
              (1113.2 * Math.cos((overview.center[1] * Math.PI) / 180)),
          overview.center[1] - controls.target.z / 1113.2,
        );
    }
  }
  frame = requestAnimationFrame(animate);

  const dispose = () => {
    if (destroyed) return;
    destroyed = true;
    cancelAnimationFrame(frame);
    observer.disconnect();
    controls.removeEventListener('start', startInteraction);
    controls.dispose();
    renderer.domElement.removeEventListener('keydown', keyDown);
    renderer.domElement.removeEventListener('pointerdown', onPointerDown);
    renderer.domElement.removeEventListener('pointerup', onPointerUp);
    renderer.domElement.removeEventListener('webglcontextlost', contextLost);
    const materials = new Set<THREE.Material>();
    const geometries = new Set<THREE.BufferGeometry>();
    scene.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (mesh.geometry) geometries.add(mesh.geometry);
      if (mesh.material)
        (Array.isArray(mesh.material)
          ? mesh.material
          : [mesh.material]
        ).forEach((m) => materials.add(m));
    });
    geometries.forEach((g) => g.dispose());
    materials.forEach((m) => m.dispose());
    materialDefaults.forEach((_, m) => m.dispose());
    draco.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    renderer.domElement.remove();
    labelLayer.remove();
    signal.removeEventListener('abort', dispose);
  };
  signal.addEventListener('abort', dispose, { once: true });
  if (signal.aborted) {
    dispose();
    throw new DOMException('Aborted', 'AbortError');
  }
  try {
    callbacks.progress('读取地理资料', 12);
    const getJson = async <T>(url: string): Promise<T> => {
      const response = await fetch(url, { signal });
      if (!response.ok) throw new Error(`无法读取 ${url} (${response.status})`);
      return response.json();
    };
    [places, overview] = await Promise.all([
      getJson<Landmark[]>(assetUrl('/data/landmarks.json')),
      getJson<Overview>(assetUrl('/data/overview.json')),
    ]);
    callbacks.progress('载入南宁城市模型', 24);
    const model = await new GLTFLoader()
      .setDRACOLoader(draco)
      .loadAsync(assetUrl('/models/nanning-city.glb'), (event) => {
        if (!signal.aborted)
          callbacks.progress(
            '载入南宁城市模型',
            event.total ? 24 + (event.loaded / event.total) * 65 : 48,
          );
      });
    if (signal.aborted) {
      model.scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        if (m.material)
          (Array.isArray(m.material) ? m.material : [m.material]).forEach((v) =>
            v.dispose(),
          );
      });
      throw new DOMException('Aborted', 'AbortError');
    }
    city = model.scene;
    scene.add(city);
    city.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      meshes.push(object);
      object.castShadow = true;
      object.receiveShadow = true;
      const mats = Array.isArray(object.material)
        ? object.material
        : [object.material];
      mats.forEach((m) => {
        if (m instanceof THREE.MeshStandardMaterial) {
          m.side = THREE.DoubleSide;
          materialDefaults.set(m, m.color.clone());
        }
      });
      if (object.name === 'Water') {
        object.castShadow = false;
        waterMaterial = new THREE.ShaderMaterial({
          uniforms: { uTime: { value: 0 }, uNight: { value: 0 } },
          vertexShader: `varying vec3 vWorld; void main(){vec4 w=modelMatrix*vec4(position,1.0);vWorld=w.xyz;gl_Position=projectionMatrix*viewMatrix*w;}`,
          fragmentShader: `varying vec3 vWorld;uniform float uTime;uniform float uNight;
          void main(){float r=sin(vWorld.x*2.8+vWorld.z*1.8+uTime*.9);float r2=sin(vWorld.x*.9-vWorld.z*4.0+uTime*.6);float glint=pow(max(0.0,r*r2),14.0)*.17;vec3 day=vec3(.17,.57,.52)+glint+sin(vWorld.z*.32+vWorld.x*.17)*.017;vec3 night=vec3(.055,.23,.24)+glint*.35;gl_FragColor=vec4(mix(day,night,uNight),1.0);
          #include <colorspace_fragment>
          }`,
          side: THREE.DoubleSide,
        });
        object.material = waterMaterial;
      }
    });
    for (const place of places) {
      const el = document.createElement('button');
      el.className = 'landmark-label';
      el.type = 'button';
      const dot = document.createElement('span');
      dot.className = 'landmark-dot';
      el.appendChild(dot);
      const text = document.createElement('span');
      text.textContent = place.name;
      el.appendChild(text);
      el.setAttribute('aria-label', `前往${place.name}`);
      el.addEventListener('click', () => callbacks.select(place.id));
      labelLayer.appendChild(el);
      const point = new THREE.Vector3(...place.position);
      point.y += place.anchorHeight;
      labels.push({ el, point, place });
    }
    const apply = (next: SceneOptions) => {
      const wasTop = option.topDown;
      option = { ...next, layers: { ...next.layers } };
      if (!city) return;
      const night = THREE.MathUtils.smoothstep(next.hour, 17.5, 21);
      const dusk = Math.sin(
        THREE.MathUtils.clamp((next.hour - 15) / 6, 0, 1) * Math.PI,
      );
      const background = new THREE.Color('#e1eae4').lerp(
        new THREE.Color('#122c32'),
        night,
      );
      scene.background = background;
      (scene.fog as THREE.FogExp2).color.copy(background);
      (floor.material as THREE.MeshStandardMaterial).color.copy(background);
      hemi.intensity = 2.5 - night * 1.5;
      sun.intensity = 3.4 - night * 2.5;
      hemi.color.set(night > 0.5 ? '#89b9ce' : '#f4f8eb');
      sun.color
        .set('#fff3d7')
        .lerp(new THREE.Color('#ffbf85'), dusk * 0.6)
        .lerp(new THREE.Color('#81b9da'), night);
      const sunAngle = ((next.hour - 6) / 12) * Math.PI;
      sun.position.set(
        -Math.cos(sunAngle) * 130,
        35 + Math.max(0.1, Math.sin(sunAngle)) * 130,
        45,
      );
      renderer.toneMappingExposure = 1.23 - night * 0.16;
      if (waterMaterial) waterMaterial.uniforms.uNight.value = night;
      city.scale.y = next.heightScale;
      const names: Partial<Record<string, boolean>> = {
        Buildings: next.layers.buildings,
        Vegetation: next.layers.vegetation,
        Roads: next.layers.roads,
        Bridges: next.layers.roads,
        Water: next.layers.water,
      };
      Object.entries(names).forEach(([name, visible]) => {
        const object = city!.getObjectByName(name);
        if (object) object.visible = Boolean(visible);
      });
      places.forEach((place) => {
        const object = city!.getObjectByName(`Landmark_${place.id}`);
        if (object)
          object.visible =
            place.id === 'bridge' ? next.layers.roads : next.layers.buildings;
      });
      materialDefaults.forEach((base, mat) => {
        mat.color.copy(base);
        mat.emissive.set('#efbc69');
        mat.emissiveIntensity =
          (mat.name.includes('glass') ? 0.16 : 0.015) * night;
      });
      controls.autoRotate = next.autoRotate && !reduced;
      labels.forEach((label) =>
        label.el.classList.toggle('selected', label.place.id === next.selected),
      );
      const selected = places.find((p) => p.id === next.selected);
      selectedRing.visible = Boolean(selected);
      if (selected) {
        selectedRing.position.set(
          selected.position[0],
          (selected.position[1] + 0.1) * next.heightScale,
          selected.position[2],
        );
      }
      if (next.topDown !== wasTop) {
        const distance = camera.position.distanceTo(controls.target);
        fly(
          controls.target.clone(),
          controls.target
            .clone()
            .add(
              next.topDown
                ? new THREE.Vector3(0, distance, 0.1)
                : new THREE.Vector3(
                    distance * 0.43,
                    distance * 0.64,
                    distance * 0.65,
                  ),
            ),
        );
      }
    };
    apply(option);
    callbacks.progress('城市就绪', 100);
    callbacks.ready(places, overview);
    return {
      apply,
      focus,
      zoom,
      north: () => {
        const d = camera.position.distanceTo(controls.target);
        fly(
          controls.target.clone(),
          controls.target
            .clone()
            .add(
              option.topDown
                ? new THREE.Vector3(0, d, 0.1)
                : new THREE.Vector3(0, d * 0.72, d * 0.72),
            ),
        );
      },
      capture: () =>
        new Promise<void>((resolve, reject) => {
          renderer.render(scene, camera);
          renderer.domElement.toBlob((blob) => {
            if (!blob) {
              reject(new Error('图像导出失败'));
              return;
            }
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.download = 'nanning-city-atlas.png';
            a.href = url;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            resolve();
          }, 'image/png');
        }),
      dispose,
    };
  } catch (error) {
    dispose();
    throw error;
  }
}
