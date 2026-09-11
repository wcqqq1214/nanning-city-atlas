import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import type {
  Landmark,
  Overview,
  SceneController,
  SceneOptions,
  QualityPreference,
  SceneMetrics,
} from './types';
import { DEFAULT_LAYERS } from './types';
import { assetUrl } from './assets';
import { TapGesture } from './tap-gesture';
import { COMPACT_LAYOUT } from './display';
import { createAreaHighlight } from './area-highlight';
import { landmarkArea } from './landmark-areas';
import { createNightLighting } from './night-lighting';

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
    metrics: (value: SceneMetrics) => void;
  },
  signal: AbortSignal,
  quality: QualityPreference = 'auto',
): Promise<SceneController> {
  const startedAt = performance.now();
  const diagnostics = new URLSearchParams(window.location.search).has('stats');
  const connection = (
    navigator as Navigator & { connection?: { saveData?: boolean } }
  ).connection;
  const compactDevice = window.matchMedia(
    `${COMPACT_LAYOUT}, (pointer: coarse)`,
  ).matches;
  const lightweight =
    quality === 'smooth' ||
    (quality === 'auto' && (compactDevice || Boolean(connection?.saveData)));
  const profile = lightweight ? 'smooth' : 'detail';
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#e1eae4');
  scene.fog = new THREE.FogExp2('#e1eae4', 0.0012);
  const renderer = new THREE.WebGLRenderer({
    antialias: !lightweight,
    alpha: false,
    preserveDrawingBuffer: false,
    powerPreference: lightweight ? 'low-power' : 'high-performance',
  });
  renderer.setPixelRatio(
    Math.min(window.devicePixelRatio, lightweight ? 1.25 : 1.7),
  );
  renderer.shadowMap.enabled = !lightweight;
  renderer.shadowMap.autoUpdate = false;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.96;
  renderer.domElement.className = 'city-canvas';
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute(
    'aria-label',
    '南宁三维地图。方向键平移，加减键缩放，Home 键复位；鼠标拖动旋转，右键拖动平移。触屏单指旋转，双指缩放和平移。',
  );
  host.appendChild(renderer.domElement);
  const labelLayer = document.createElement('div');
  labelLayer.className = 'map-labels';
  host.appendChild(labelLayer);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.12, 3000);
  const initialPosition = new THREE.Vector3(112, 162, 177);
  const overviewPosition = () => {
    const bounds = overview?.bounds ?? [-103, -78, 103, 78];
    const direction = initialPosition.clone().normalize();
    const right = new THREE.Vector3()
      .crossVectors(new THREE.Vector3(0, 1, 0), direction)
      .normalize();
    const up = new THREE.Vector3().crossVectors(direction, right).normalize();
    const vertical = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
    let distance = 0;
    for (const x of [bounds[0], bounds[2]])
      for (const z of [-bounds[3], -bounds[1]])
        for (const y of [-3, 14]) {
          const point = new THREE.Vector3(x, y, z);
          distance = Math.max(
            distance,
            Math.abs(point.dot(right)) / (vertical * camera.aspect) +
              point.dot(direction),
            Math.abs(point.dot(up)) / vertical + point.dot(direction),
          );
        }
    return direction.multiplyScalar(distance * 1.08);
  };
  camera.position.copy(initialPosition);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.065;
  controls.minDistance = 2.4;
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
  controls.maxDistance = 360;
  controls.maxPolarAngle = Math.PI / 2.12;
  controls.minPolarAngle = 0.025;
  controls.autoRotateSpeed = 0.45;
  controls.target.set(0, 0, 0);
  controls.update();
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hemi = new THREE.HemisphereLight('#f4f8eb', '#668f84', 1.5);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight('#fff3d7', 2.7);
  sun.position.set(-90, 130, 40);
  sun.castShadow = !lightweight;
  scene.add(sun.target);
  const sunOffset = sun.position.clone();
  Object.assign(sun.shadow.camera, {
    left: -145,
    right: 145,
    top: 140,
    bottom: -140,
    near: 1,
    far: 1000,
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
  let dirty = true;
  const invalidate = () => {
    dirty = true;
  };
  controls.addEventListener('change', invalidate);
  let city: THREE.Group | null = null;
  let areaHighlight: ReturnType<typeof createAreaHighlight> | null = null;
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
    width: number;
  }[] = [];
  const meshes: THREE.Mesh[] = [];
  const materialDefaults = new Map<THREE.MeshStandardMaterial, THREE.Color>();
  const draco = new DRACOLoader()
    .setDecoderPath(assetUrl('/draco/'))
    .setWorkerLimit(lightweight ? 1 : 2);
  let waterMaterial: THREE.ShaderMaterial | null = null;
  let lastFrameTime = 0;
  let lastTelemetry = 0;
  let metricStart = performance.now();
  let renderedFrames = 0;
  let loadMs = 0;
  let modelBytes = 0;
  let lastRender = 0;
  let lastAdaptation = startedAt;
  let lastLongitude = NaN,
    lastLatitude = NaN,
    lastHeading = NaN;
  const projected = new THREE.Vector3();
  const viewDirection = new THREE.Vector3();
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const tapGesture = new TapGesture();
  const startInteraction = () => {
    flight = null;
    callbacks.interaction();
  };
  controls.addEventListener('start', startInteraction);
  let labelVisibilityDistance = 0;
  const resize = () => {
    dirty = true;
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height);
    areaHighlight?.resize(width, height);
    for (const label of labels) {
      const display = label.el.style.display;
      label.el.style.display = 'flex';
      label.width = label.el.offsetWidth;
      label.el.style.display = display;
    }
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    const overviewDistance = overviewPosition().length();
    // Leave the default overview clear; show labels once the user zooms in.
    labelVisibilityDistance = overviewDistance * 0.98;
    controls.maxDistance = Math.max(360, overviewDistance * 1.15);
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
  const focus = (id: string | null, close = false) => {
    const place = places.find((p) => p.id === id);
    const areaBounds = areaHighlight?.select(place?.id ?? null);
    dirty = true;
    if (!place) {
      fly(
        new THREE.Vector3(),
        option.topDown
          ? new THREE.Vector3(0, overviewPosition().length(), 0.5)
          : overviewPosition(),
      );
      return;
    }
    close = close && place.closeDistance !== undefined;
    const target = new THREE.Vector3(...place.position);
    if (areaBounds && !close) areaBounds.getCenter(target);
    target.y *= option.heightScale;
    if (close) target.y += place.anchorHeight * 0.25 * option.heightScale;
    const distance =
      (close
        ? (place.closeDistance ?? place.cameraDistance * 0.65)
        : place.cameraDistance) * Math.max(1, 0.72 / camera.aspect);
    const offset = option.topDown
      ? new THREE.Vector3(0, distance * 2, 0.1)
      : new THREE.Vector3(
          distance,
          distance * (close ? 0.72 : 1.15),
          distance * 1.35,
        );
    if (!option.topDown && place.cameraBearing !== undefined) {
      const bearing = THREE.MathUtils.degToRad(place.cameraBearing);
      const radius = Math.hypot(offset.x, offset.z);
      offset.x = Math.sin(bearing) * radius;
      offset.z = -Math.cos(bearing) * radius;
    }
    if (areaBounds && !close) {
      const size = areaBounds.getSize(new THREE.Vector3());
      size.y *= option.heightScale;
      const halfFov = Math.atan(
        Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) *
          Math.min(1, camera.aspect),
      );
      const fitDistance = ((size.length() * 0.5) / Math.sin(halfFov)) * 1.08;
      offset.setLength(Math.max(offset.length(), fitDistance));
    }
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
  // Labels sit above the canvas, so send their wheel input to the same controls.
  const onLabelWheel = (event: WheelEvent) => {
    event.preventDefault();
    renderer.domElement.dispatchEvent(new WheelEvent('wheel', event));
  };
  labelLayer.addEventListener('wheel', onLabelWheel, { passive: false });
  const onPointerDown = (event: PointerEvent) => tapGesture.start(event);
  const onPointerMove = (event: PointerEvent) => tapGesture.move(event);
  const onPointerUp = (event: PointerEvent) => {
    if (!tapGesture.end(event) || !city) return;
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
  const cancelPointer = (event: PointerEvent) => tapGesture.cancel(event);
  renderer.domElement.addEventListener('pointermove', onPointerMove);
  renderer.domElement.addEventListener('pointercancel', cancelPointer);
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
    // Smooth mode caps animated frames at 30 fps and rests when the view is still.
    if (lightweight && now - lastFrameTime < 1000 / 30 - 0.5) return;
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
    const wantsAnimation = Boolean(
      flight ||
      controls.autoRotate ||
      (!lightweight && !reduced && option.layers.water),
    );
    const needsOverlays = dirty || Boolean(flight || controls.autoRotate);
    if (dirty || wantsAnimation) {
      sun.target.position.copy(controls.target);
      sun.position.copy(controls.target).add(sunOffset);
      if (!lightweight && dirty) {
        const range = THREE.MathUtils.clamp(
          camera.position.distanceTo(controls.target) * 0.65,
          10,
          280,
        );
        Object.assign(sun.shadow.camera, {
          left: -range,
          right: range,
          top: range,
          bottom: -range,
        });
        sun.shadow.camera.updateProjectionMatrix();
        sun.target.position.copy(controls.target);
        sun.position.copy(controls.target).add(sunOffset);
        renderer.shadowMap.needsUpdate = true;
      }
      if (waterMaterial)
        waterMaterial.uniforms.uTime.value = reduced ? 0 : now / 1000;
      renderer.render(scene, camera);
      dirty = false;
      renderedFrames += 1;
      lastRender = now;
    } else if (now - lastTelemetry < 1000) return;
    if (now - metricStart >= 1000 && city) {
      const fps =
        now - lastRender > 300
          ? 0
          : Math.round((renderedFrames * 1000) / (now - metricStart));
      // Lower resolution only during sustained foreground animation, never from idle frames.
      if (
        quality === 'auto' &&
        document.hasFocus() &&
        wantsAnimation &&
        renderedFrames >= 12 &&
        fps < 25 &&
        now - lastAdaptation > 2500 &&
        now - startedAt > 6000
      ) {
        const nextRatio = Math.max(0.85, renderer.getPixelRatio() - 0.15);
        if (nextRatio < renderer.getPixelRatio()) {
          renderer.setPixelRatio(nextRatio);
          dirty = true;
        }
        lastAdaptation = now;
      }
      if (diagnostics)
        callbacks.metrics({
          profile,
          loadMs,
          modelBytes,
          fps,
          triangles: renderer.info.render.triangles,
          calls: renderer.info.render.calls,
          pixelRatio: renderer.getPixelRatio(),
        });
      metricStart = now;
      renderedFrames = 0;
    }
    if (needsOverlays) {
      camera.getWorldDirection(viewDirection);
      const labelsVisible =
        option.layers.labels &&
        camera.position.distanceTo(controls.target) < labelVisibilityDistance;
      const occupied: { x: number; y: number; width: number }[] = [];
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
          (p) =>
            Math.abs(p.x - x) < (p.width + label.width) / 2 + 12 &&
            Math.abs(p.y - y) < 48,
        );
        const show =
          labelsVisible &&
          (!compactDevice ||
            !option.selected ||
            label.place.id === option.selected) &&
          inFront &&
          projected.z < 1 &&
          x > label.width / 2 + 12 &&
          x < host.clientWidth - label.width / 2 - 12 &&
          y > 60 &&
          y < host.clientHeight - 74 &&
          !collision;
        label.el.style.display = show ? 'flex' : 'none';
        if (show) {
          label.el.style.transform = `translate(${x}px,${y}px) translate(-50%,-100%)`;
          occupied.push({ x, y, width: label.width });
        }
      }
    }
    if (now - lastTelemetry > 180) {
      lastTelemetry = now;
      const heading = (controls.getAzimuthalAngle() * 180) / Math.PI;
      if (
        !Number.isFinite(lastHeading) ||
        Math.abs(heading - lastHeading) > 0.1
      ) {
        callbacks.heading(heading);
        lastHeading = heading;
      }
      if (overview) {
        const lon =
          overview.center[0] +
          controls.target.x /
            (1113.2 * Math.cos((overview.center[1] * Math.PI) / 180));
        const lat = overview.center[1] - controls.target.z / 1113.2;
        if (
          !Number.isFinite(lastLongitude) ||
          Math.abs(lon - lastLongitude) > 0.00001 ||
          Math.abs(lat - lastLatitude) > 0.00001
        ) {
          callbacks.view(lon, lat);
          lastLongitude = lon;
          lastLatitude = lat;
        }
      }
    }
  }
  frame = requestAnimationFrame(animate);

  const dispose = () => {
    if (destroyed) return;
    destroyed = true;
    cancelAnimationFrame(frame);
    observer.disconnect();
    controls.removeEventListener('start', startInteraction);
    controls.removeEventListener('change', invalidate);
    controls.dispose();
    areaHighlight?.dispose();
    renderer.domElement.removeEventListener('keydown', keyDown);
    labelLayer.removeEventListener('wheel', onLabelWheel);
    renderer.domElement.removeEventListener('pointerdown', onPointerDown);
    renderer.domElement.removeEventListener('pointerup', onPointerUp);
    renderer.domElement.removeEventListener('pointercancel', cancelPointer);
    renderer.domElement.removeEventListener('pointermove', onPointerMove);
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
    resize();
    modelBytes = overview.models[profile].bytes;
    callbacks.progress(
      lightweight ? '载入轻量城市模型' : '载入精细城市模型',
      24,
    );
    const model = await new GLTFLoader()
      .setDRACOLoader(draco)
      .loadAsync(
        assetUrl(
          lightweight
            ? '/models/nanning-city-mobile.glb'
            : '/models/nanning-city.glb',
        ),
        (event) => {
          if (!signal.aborted)
            callbacks.progress(
              '载入南宁城市模型',
              event.total ? 24 + (event.loaded / event.total) * 65 : 48,
            );
        },
      );
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
      // Repeated sleepers and thin overhead fittings add noisy, costly shadows.
      // The railway deck, embankments and bridge structure still cast shadows.
      object.castShadow =
        !lightweight && !object.name.startsWith('Railway_Details_');
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
          void main(){float r=sin(vWorld.x*2.8+vWorld.z*1.8+uTime*.9);float r2=sin(vWorld.x*.9-vWorld.z*4.0+uTime*.6);float glint=pow(max(0.0,r*r2),14.0)*.17;vec3 day=vec3(.17,.57,.52)+glint+sin(vWorld.z*.32+vWorld.x*.17)*.017;vec3 night=vec3(.012,.055,.09)+glint*vec3(.3,.52,.65);gl_FragColor=vec4(mix(day,night,uNight),1.0);
          #include <colorspace_fragment>
          }`,
          side: THREE.DoubleSide,
        });
        object.material = waterMaterial;
      }
    });
    const nightLighting = createNightLighting(city, lightweight);
    areaHighlight = createAreaHighlight(city, overview.center, landmarkArea);
    areaHighlight.resize(host.clientWidth, host.clientHeight);
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
      el.style.display = 'flex';
      const width = el.offsetWidth;
      el.style.display = 'none';
      labels.push({ el, point, place, width });
    }
    const apply = (next: SceneOptions) => {
      const wasTop = option.topDown;
      option = { ...next, layers: { ...next.layers } };
      if (!city) return;
      dirty = true;
      const night = THREE.MathUtils.smoothstep(next.hour, 17.5, 21);
      const dusk = Math.sin(
        THREE.MathUtils.clamp((next.hour - 15) / 6, 0, 1) * Math.PI,
      );
      const background = new THREE.Color('#e1eae4').lerp(
        new THREE.Color('#071322'),
        night,
      );
      scene.background = background;
      (scene.fog as THREE.FogExp2).color.copy(background);
      (floor.material as THREE.MeshStandardMaterial).color.copy(background);
      hemi.intensity = 1.5 - night * 1.22;
      sun.intensity = 2.7 - night * 2.48;
      hemi.color.set('#f4f8eb').lerp(new THREE.Color('#779bd6'), night);
      sun.color
        .set('#fff3d7')
        .lerp(new THREE.Color('#ffbf85'), dusk * 0.6)
        .lerp(new THREE.Color('#81b9da'), night);
      const sunAngle = ((next.hour - 6) / 12) * Math.PI;
      sunOffset.set(
        -Math.cos(sunAngle) * 300,
        100 + Math.max(0.1, Math.sin(sunAngle)) * 300,
        45,
      );
      renderer.toneMappingExposure = 0.96;
      nightLighting.setNight(night);
      gridMaterial.opacity = 0.19 * (1 - night * 0.8);
      if (waterMaterial) waterMaterial.uniforms.uNight.value = night;
      city.scale.y = next.heightScale;
      areaHighlight?.select(next.selected);
      const names: Partial<Record<string, boolean>> = {
        Buildings: next.layers.buildings,
        Vegetation: next.layers.vegetation,
        Roads: next.layers.roads,
        Bridges: next.layers.roads,
        Railways: next.layers.railways,
        Water: next.layers.water,
      };
      Object.entries(names).forEach(([name, visible]) => {
        const object = city!.getObjectByName(name);
        if (object) object.visible = Boolean(visible);
      });
      places.forEach((place) => {
        const object = city!.getObjectByName(`Landmark_${place.id}`);
        if (object) object.visible = next.layers[place.layer ?? 'buildings'];
      });
      materialDefaults.forEach((base, mat) => {
        mat.color.copy(base);
        mat.emissiveIntensity = 0;
      });
      controls.autoRotate = next.autoRotate && !reduced;
      labels.forEach((label) =>
        label.el.classList.toggle('selected', label.place.id === next.selected),
      );
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
    loadMs = performance.now() - startedAt;
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
