import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import type { EnergyPart, EnergyPoint } from "./energy-explorer";

export type HouseMode = "exterior" | "cutaway" | "exploded";
export type HouseRoom = "living" | "bedroom" | "roof";
export interface HouseController {
  setMode: (mode: HouseMode, immediate?: boolean) => void;
  setRotating: (active: boolean) => void;
  focus: (room: HouseRoom) => void;
  zoom: (factor: number) => void;
  reset: () => void;
  setEnergy: (
    active: EnergyPart[],
    planned: EnergyPart[],
    hovered: EnergyPart | null,
  ) => void;
  dispose: () => void;
}

// All geometry and textures are local, illustrative architecture. No sponsor
// property geometry, energy measurements or third-party model assets are implied.
export function createHouseScene(
  host: HTMLElement,
  options: {
    compact: boolean;
    office: boolean;
    onUnavailable: () => void;
    onHover?: (part: EnergyPart | null) => void;
    onProject?: (points: EnergyPoint[]) => void;
  },
): HouseController {
  const { compact, office } = options;
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: "low-power",
  });
  renderer.setPixelRatio(
    Math.min(window.devicePixelRatio || 1, compact ? 1.25 : 1.75),
  );
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.setClearColor(0xeeeae2, 0);
  renderer.domElement.setAttribute("aria-hidden", "true");
  host.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(compact ? 33 : 34, 1, 0.1, 120);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enabled = !compact;
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 10;
  controls.maxDistance = 38;
  controls.minPolarAngle = 0.25;
  controls.maxPolarAngle = Math.PI / 2.05;
  controls.autoRotateSpeed = 0.65;
  // Leave vertical scrolling available on touch screens; buttons also offer
  // fully operable alternatives to drag and pinch.
  if (!compact) renderer.domElement.style.touchAction = "pan-y";
  const reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;
  const pmrem = new THREE.PMREMGenerator(renderer);
  const roomEnvironment = new RoomEnvironment();
  const environment = pmrem.fromScene(roomEnvironment, 0.04);
  scene.environment = environment.texture;
  scene.environmentIntensity = 0.48;
  roomEnvironment.dispose();
  pmrem.dispose();
  scene.add(new THREE.HemisphereLight(0xe9f0f5, 0x9c8e74, 2.1));
  const sun = new THREE.DirectionalLight(0xffe9c9, 4.2);
  sun.position.set(-9, 17, 9);
  sun.castShadow = true;
  sun.shadow.mapSize.set(compact ? 512 : 2048, compact ? 512 : 2048);
  sun.shadow.camera.left = -13;
  sun.shadow.camera.right = 13;
  sun.shadow.camera.top = 14;
  sun.shadow.camera.bottom = -13;
  sun.shadow.normalBias = 0.025;
  sun.shadow.bias = -0.0002;
  sun.shadow.radius = 4;
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0xd9e9ff, 1.2);
  fill.position.set(10, 8, -10);
  scene.add(fill);

  const textures: THREE.Texture[] = [];
  const materials: THREE.Material[] = [];
  function texture(kind: "wood" | "stone" | "fabric" | "solar") {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 256;
    const ctx = canvas.getContext("2d")!;
    let seed = 42;
    const random = () => {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    };
    ctx.fillStyle = {
      wood: "#b79670",
      stone: "#d9d5ca",
      fabric: "#dad4c6",
      solar: "#172c37",
    }[kind];
    ctx.fillRect(0, 0, 256, 256);
    if (kind === "wood") {
      for (let y = 0; y < 256; y++) {
        ctx.strokeStyle = `rgba(65,38,16,${0.03 + random() * 0.1})`;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.bezierCurveTo(70, y + random() * 3, 170, y - random() * 4, 256, y);
        ctx.stroke();
      }
      ctx.strokeStyle = "#71583b55";
      ctx.lineWidth = 1;
      for (let y = 0; y < 256; y += 32) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(256, y);
        ctx.stroke();
        ctx.fillStyle = "#71583b44";
        ctx.fillRect((y * 7) % 220, y, 1, 32);
      }
    } else if (kind === "solar") {
      for (let x = 4; x < 256; x += 42)
        for (let y = 4; y < 256; y += 42) {
          ctx.fillStyle = `rgb(${23 + random() * 7},${44 + random() * 8},${55 + random() * 12})`;
          ctx.fillRect(x, y, 39, 39);
          ctx.strokeStyle = "#8ba3b455";
          ctx.lineWidth = 0.5;
          for (let i = 1; i < 5; i++) {
            ctx.beginPath();
            ctx.moveTo(x + i * 8, y);
            ctx.lineTo(x + i * 8, y + 39);
            ctx.stroke();
          }
        }
    } else {
      for (let i = 0; i < 18000; i++) {
        ctx.fillStyle = `rgba(${random() > 0.5 ? "255,255,255" : "50,42,32"},${random() * 0.1})`;
        ctx.fillRect(
          random() * 256,
          random() * 256,
          kind === "fabric" ? 1 : 2,
          1,
        );
      }
    }
    const result = new THREE.CanvasTexture(canvas);
    result.colorSpace = THREE.SRGBColorSpace;
    result.wrapS = result.wrapT = THREE.RepeatWrapping;
    if (kind === "wood") result.repeat.set(2, 3);
    textures.push(result);
    return result;
  }
  function mat(
    color: string,
    roughness = 0.7,
    extra: THREE.MeshStandardMaterialParameters = {},
  ) {
    const result = new THREE.MeshStandardMaterial({
      color,
      roughness,
      ...extra,
    });
    materials.push(result);
    return result;
  }
  const wood = mat("#d7b78e", 0.55, { map: texture("wood") });
  const plaster = mat("#f5f0e5", 0.9, { map: texture("stone") });
  const stone = mat("#b6b0a0", 0.92, { map: texture("stone") });
  const fabric = mat("#eee5d3", 0.94, { map: texture("fabric") });
  const olive = mat(office ? "#59656a" : "#71785a", 0.85);
  const charcoal = mat("#303832", 0.58);
  const roofMaterial = mat("#48514c", 0.75, { metalness: 0.18 });
  const bronze = mat("#9d7953", 0.28, { metalness: 0.7 });
  const white = mat("#faf5e9", 0.6);
  const glass = mat("#8eaca9", 0.13, {
    transparent: true,
    opacity: 0.42,
    metalness: 0.3,
    depthWrite: false,
  });
  const solar = mat("#bac9d1", 0.28, {
    map: texture("solar"),
    metalness: 0.45,
  });
  const green = mat("#526548", 0.92);
  const darkGreen = mat("#334e38", 0.9);
  const soil = mat("#554c3a");
  function box(
    parent: THREE.Object3D,
    size: [number, number, number],
    pos: [number, number, number],
    material: THREE.Material,
    radius = 0,
  ) {
    const geometry = radius
      ? new RoundedBoxGeometry(...size, 2, radius)
      : new THREE.BoxGeometry(...size);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.energyPart =
      material === solar
        ? "solar"
        : material === glass
          ? "windows"
          : material === roofMaterial
            ? "roof"
            : material === plaster
              ? "envelope"
              : undefined;
    mesh.position.set(...pos);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }
  function cylinder(
    parent: THREE.Object3D,
    radius: number,
    height: number,
    pos: [number, number, number],
    material: THREE.Material,
    top = radius,
  ) {
    const mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(top, radius, height, 20),
      material,
    );
    mesh.position.set(...pos);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }
  function plant(
    parent: THREE.Object3D,
    x: number,
    y: number,
    z: number,
    scale = 1,
  ) {
    cylinder(
      parent,
      0.2 * scale,
      0.37 * scale,
      [x, y + 0.18 * scale, z],
      stone,
      0.25 * scale,
    );
    cylinder(parent, 0.19 * scale, 0.02, [x, y + 0.37 * scale, z], soil);
    cylinder(
      parent,
      0.025 * scale,
      0.7 * scale,
      [x, y + 0.66 * scale, z],
      wood,
    );
    for (let i = 0; i < 7; i++) {
      const angle = i * 2.4;
      const leaf = new THREE.Mesh(
        new THREE.SphereGeometry(1, 8, 6),
        i % 2 ? green : darkGreen,
      );
      leaf.scale.set(0.14 * scale, 0.34 * scale, 0.07 * scale);
      leaf.position.set(
        x + Math.cos(angle) * 0.2 * scale,
        y + (0.65 + i * 0.07) * scale,
        z + Math.sin(angle) * 0.2 * scale,
      );
      leaf.rotation.set(0.3, angle, 0.8);
      leaf.castShadow = true;
      parent.add(leaf);
    }
  }
  const house = new THREE.Group();
  scene.add(house);
  box(house, [12.5, 0.35, 9.5], [0, -0.3, 0], stone, 0.1);
  box(house, [12.4, 0.06, 9.4], [0, -0.09, 0], mat("#c2c5ae"), 0.03);
  // Paved terrace, planting beds and recessed entry steps.
  box(house, [10, 0.08, 2], [0, 0, 3.6], stone);
  for (let i = 0; i < 15; i++)
    box(house, [0.015, 0.008, 2], [i * 0.7 - 4.9, 0.046, 3.6], mat("#97988c"));
  box(house, [2.4, 0.13, 0.5], [2, 0.04, 4.6], plaster);
  for (const x of [-5.3, 5.3]) {
    box(house, [0.7, 0.26, 7.6], [x, 0.04, -0.3], stone);
    for (let z = -3.5; z <= 2.7; z += 0.8) {
      const bush = new THREE.Mesh(
        new THREE.SphereGeometry(0.42, 10, 8),
        z % 2 ? green : darkGreen,
      );
      bush.scale.y = 0.7;
      bush.position.set(x, 0.38, z);
      bush.castShadow = true;
      house.add(bush);
    }
  }
  plant(house, -4.7, 0, 3.7, 1.6);
  plant(house, 4.7, 0, 3.7, 1.6);
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(200, 200),
    new THREE.ShadowMaterial({ color: 0x514b3d, opacity: 0.19 }),
  );
  materials.push(ground.material);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.49;
  ground.receiveShadow = true;
  scene.add(ground);
  const lower = new THREE.Group();
  house.add(lower);
  const upper = new THREE.Group();
  upper.position.y = 2.8;
  house.add(upper);
  const roof = new THREE.Group();
  roof.position.y = 5.6;
  house.add(roof);
  const shells: THREE.Object3D[] = [];
  const ceiling: THREE.Object3D[] = [];
  function windowFrame(
    parent: THREE.Object3D,
    x: number,
    y: number,
    z: number,
    side = false,
  ) {
    const group = new THREE.Group();
    group.userData.energyPart = "windows";
    group.position.set(x, y, z);
    if (side) group.rotation.y = Math.PI / 2;
    parent.add(group);
    box(group, [1.5, 1.48, 0.055], [0, 0, 0], glass);
    for (const a of [-0.79, 0.79])
      box(group, [0.065, 1.62, 0.12], [a, 0, 0], charcoal);
    for (const a of [-0.78, 0.78])
      box(group, [1.65, 0.065, 0.12], [0, a, 0], charcoal);
    box(group, [0.04, 1.6, 0.1], [0, 0, 0.02], charcoal);
    box(group, [1.9, 0.07, 0.3], [0, -0.84, 0.04], plaster);
  }
  function architecture(parent: THREE.Group, top = false) {
    box(parent, [9, 0.19, 6], [0, 0.1, 0], wood);
    box(parent, [9.15, 0.12, 6.12], [0, -0.04, 0], plaster);
    // Rear wall has actual apertures rather than glass painted on a solid wall.
    box(parent, [9, 0.6, 0.18], [0, 0.48, -2.96], plaster);
    box(parent, [9, 0.4, 0.18], [0, 2.43, -2.96], plaster);
    for (const x of [-4.14, -2.08, 0, 2.08, 4.14])
      box(parent, [0.72, 1.63, 0.18], [x, 1.59, -2.96], plaster);
    for (const x of [-3.12, -1.04, 1.04, 3.12])
      windowFrame(parent, x, 1.57, -2.96);
    // Left wall and partial room dividers remain in dollhouse views.
    box(parent, [0.18, 2.45, 6], [-4.46, 1.4, 0], plaster);
    for (let z = -2.7; z < 2.9; z += 0.16)
      box(parent, [0.03, 2.45, 0.025], [-4.35, 1.4, z], wood);
    box(parent, [0.12, 1.8, 2.7], [0.15, 1.1, -1.52], plaster);
    box(parent, [0.12, 0.55, 2.85], [0.15, 0.47, 1.35], plaster);
    const shell = new THREE.Group();
    parent.add(shell);
    shells.push(shell);
    // Front facade: two picture windows and a timber entry.
    box(shell, [9, 0.6, 0.18], [0, 0.48, 2.96], plaster);
    box(shell, [9, 0.42, 0.18], [0, 2.42, 2.96], plaster);
    for (const x of [-4.13, -1.65, 0.55, 2.5, 4.14])
      box(shell, [0.72, 1.62, 0.18], [x, 1.58, 2.96], plaster);
    for (const x of [-2.95, -0.55, 1.53, 3.35])
      windowFrame(shell, x, 1.57, 2.96);
    if (!top) {
      box(shell, [1.02, 2.2, 0.2], [1.52, 1.27, 3], wood);
      box(shell, [0.035, 0.35, 0.07], [1.84, 1.2, 3.14], bronze);
    }
    box(shell, [0.18, 0.6, 6], [4.46, 0.48, 0], plaster);
    box(shell, [0.18, 0.42, 6], [4.46, 2.42, 0], plaster);
    for (const z of [-2.55, -0.55, 1.45, 2.6])
      box(shell, [0.18, 1.62, 0.5], [4.46, 1.58, z], plaster);
    for (const z of [-1.55, 0.46]) windowFrame(shell, 4.46, 1.57, z, true);
    // Low cut edge makes the floor thickness legible when the facade is removed.
    box(parent, [9, 0.13, 0.11], [0, 0.24, 2.98], plaster);
    box(parent, [0.11, 0.13, 6], [4.48, 0.24, 0], plaster);
    if (top) {
      const lid = box(parent, [9, 0.08, 6], [0, 2.66, 0], plaster);
      ceiling.push(lid);
    }
  }
  architecture(lower);
  architecture(upper, true);
  // Ground floor: woven rug, sectional, walnut table, built-in kitchen.
  box(
    lower,
    [3.5, 0.025, 3.0],
    [-2.15, 0.215, 0.8],
    mat("#d4cbb9", 0.95, { map: texture("fabric") }),
    0.02,
  );
  box(lower, [2.7, 0.35, 0.92], [-2.3, 0.48, -0.22], olive, 0.1);
  box(lower, [2.75, 0.72, 0.22], [-2.3, 0.75, -0.68], olive, 0.08);
  for (const x of [-3.59, -1.01])
    box(lower, [0.21, 0.53, 0.94], [x, 0.7, -0.22], olive, 0.07);
  for (const x of [-3.05, -2.29, -1.53])
    box(lower, [0.7, 0.17, 0.75], [x, 0.73, -0.2], fabric, 0.06);
  for (const x of [-3.1, -1.5]) {
    const cushion = box(
      lower,
      [0.52, 0.5, 0.14],
      [x, 1, -0.45],
      x < -2 ? fabric : mat("#b0a184"),
      0.08,
    );
    cushion.rotation.x = -0.2;
  }
  const table = cylinder(lower, 0.7, 0.11, [-2.2, 0.69, 1.35], wood);
  table.scale.z = 0.72;
  cylinder(lower, 0.25, 0.45, [-2.2, 0.44, 1.35], charcoal);
  box(lower, [0.32, 0.045, 0.24], [-2.35, 0.77, 1.3], olive);
  cylinder(lower, 0.12, 0.04, [-1.98, 0.77, 1.35], white);
  box(lower, [0.72, 0.43, 0.78], [-3.5, 0.48, 1.6], fabric, 0.1);
  for (const x of [1, 1.8, 2.6, 3.4]) {
    box(lower, [0.78, 0.83, 0.68], [x, 0.62, -2.46], olive, 0.015);
    box(lower, [0.025, 0.3, 0.04], [x + 0.27, 0.7, -2.09], bronze);
  }
  box(lower, [3.25, 0.09, 0.78], [2.2, 1.08, -2.45], white);
  cylinder(lower, 0.21, 0.025, [1.3, 1.14, -2.45], charcoal);
  const faucet = new THREE.Mesh(
    new THREE.TorusGeometry(0.13, 0.018, 6, 16, Math.PI),
    bronze,
  );
  faucet.position.set(1.3, 1.39, -2.58);
  lower.add(faucet);
  box(lower, [1.6, 0.83, 0.8], [2, 0.62, -0.5], wood, 0.02);
  box(lower, [1.8, 0.08, 1], [2, 1.08, -0.5], white, 0.025);
  for (const x of [1.55, 2.45]) {
    cylinder(lower, 0.22, 0.08, [x, 0.8, 0.45], wood);
    for (const dx of [-0.12, 0.12])
      box(lower, [0.045, 0.57, 0.045], [x + dx, 0.48, 0.45], charcoal);
  }
  box(lower, [0.07, 1.1, 1.8], [-4.3, 1.3, 0.5], charcoal);
  box(lower, [0.08, 0.96, 1.65], [-4.25, 1.3, 0.5], mat("#323f3b", 0.23));
  plant(lower, 3.7, 0.2, 1.75, 1.4);
  plant(lower, -3.7, 0.2, -2.1, 0.9);
  // Open riser staircase leading to the upper floor.
  for (let i = 0; i < 11; i++)
    box(
      lower,
      [0.85, 0.09, 0.27],
      [3.8, 0.3 + i * 0.23, -2.3 + i * 0.25],
      wood,
    );
  // Upper floor: bed, reading corner and a home office.
  box(
    upper,
    [3.7, 0.025, 3.7],
    [-2.1, 0.215, 0],
    mat("#d8d0bc", 0.9, { map: texture("fabric") }),
  );
  box(upper, [2.25, 0.3, 2.8], [-2.1, 0.43, -0.55], wood, 0.06);
  box(upper, [2.15, 0.26, 2.7], [-2.1, 0.69, -0.55], fabric, 0.1);
  box(upper, [2.35, 1.1, 0.13], [-2.1, 0.86, -1.98], wood, 0.035);
  box(upper, [2.16, 0.12, 1.4], [-2.1, 0.87, 0.05], olive, 0.06);
  for (const x of [-2.66, -1.55])
    box(upper, [0.86, 0.18, 0.58], [x, 0.92, -1.42], white, 0.1);
  for (const x of [-3.65, -0.6]) {
    box(upper, [0.52, 0.5, 0.52], [x, 0.47, -1.58], wood, 0.025);
    cylinder(upper, 0.11, 0.22, [x, 0.85, -1.58], bronze);
    cylinder(upper, 0.22, 0.27, [x, 1.07, -1.58], fabric, 0.15);
  }
  box(upper, [2.8, 0.1, 0.8], [2.25, 0.98, -2.2], wood, 0.02);
  for (const x of [1.1, 3.4])
    box(upper, [0.1, 0.75, 0.65], [x, 0.6, -2.2], charcoal);
  box(upper, [0.7, 0.44, 0.045], [2.15, 1.33, -2.25], charcoal);
  box(upper, [0.63, 0.36, 0.02], [2.15, 1.33, -2.21], mat("#91a49b", 0.3));
  cylinder(upper, 0.06, 0.19, [2.15, 1.08, -2.25], charcoal);
  box(upper, [0.65, 0.12, 0.66], [2.2, 0.65, -1.08], olive, 0.07);
  box(upper, [0.65, 0.65, 0.12], [2.2, 0.96, -0.78], olive, 0.06);
  cylinder(upper, 0.06, 0.38, [2.2, 0.42, -1.08], charcoal);
  box(upper, [1.0, 0.43, 0.9], [2.5, 0.48, 1.15], fabric, 0.09);
  box(upper, [1, 0.65, 0.17], [2.5, 0.8, 0.75], fabric, 0.08);
  plant(upper, 3.7, 0.2, 2, 1.3);
  plant(upper, 0.8, 0.2, 1.7, 0.8);
  // Framed artwork and timber shelving give the interior a human scale.
  box(upper, [1.05, 0.94, 0.04], [-1.1, 1.68, -2.83], wood);
  box(upper, [0.9, 0.8, 0.05], [-1.1, 1.68, -2.79], mat("#c7b895"));
  cylinder(upper, 0.26, 0.015, [-1.1, 1.7, -2.75], olive).rotation.x =
    Math.PI / 2;
  for (let i = 0; i < 3; i++) {
    box(lower, [1.1, 0.055, 0.25], [2.4, 1.55 + i * 0.37, -2.8], wood);
    for (let j = 0; j < 4; j++)
      box(
        lower,
        [0.1, 0.24, 0.16],
        [2.05 + j * 0.15, 1.7 + i * 0.37, -2.78],
        j % 2 ? olive : fabric,
      );
  }
  // Standing-seam roof, warm exposed rafters and a six-panel solar array.
  if (office) {
    box(roof, [9.6, 0.25, 6.5], [0, 0.13, 0], roofMaterial);
    box(roof, [1.3, 0.55, 1.1], [-2.9, 0.53, -1.8], stone);
  } else {
    const angle = Math.atan2(1.35, 3.3),
      slope = Math.hypot(1.35, 3.3);
    for (const sign of [-1, 1]) {
      const half = new THREE.Group();
      half.position.set(0, 0.7, sign * 1.65);
      half.rotation.x = sign * angle;
      roof.add(half);
      box(half, [9.7, 0.17, slope], [0, 0, 0], roofMaterial);
      box(half, [9.75, 0.1, slope], [0, -0.13, 0], wood).userData.energyPart =
        "attic";
      for (let x = -4.7; x < 4.8; x += 0.38)
        box(half, [0.025, 0.035, slope], [x, 0.1, 0], roofMaterial);
      if (sign === 1)
        for (let x = -2.7; x < 3; x += 1.1)
          for (const z of [-0.75, 0.75])
            box(half, [1.02, 0.065, 1.37], [x, 0.18, z], solar, 0.012);
    }
    box(roof, [9.85, 0.12, 0.14], [0, 1.42, 0], charcoal, 0.03);
    box(roof, [0.55, 1.4, 0.65], [-3.3, 1.25, -1.25], plaster);
    box(roof, [0.67, 0.13, 0.77], [-3.3, 1.98, -1.25], charcoal);
  }
  if (office)
    for (let x = -2.5; x < 3; x += 1.1)
      for (const z of [-0.9, 0.7]) {
        const panel = box(roof, [1.02, 0.06, 1.45], [x, 0.4, z], solar);
        panel.rotation.x = 0.18;
      }

  // Inspectable energy systems, represented at concept locations only.
  const lights = new THREE.Group();
  lights.userData.energyPart = "lighting";
  lower.add(lights);
  for (const x of [-2.3, 2]) {
    cylinder(lights, 0.025, 0.42, [x, 2.23, -0.2], bronze);
    cylinder(lights, 0.28, 0.16, [x, 1.98, -0.2], white, 0.12);
    cylinder(
      lights,
      0.19,
      0.025,
      [x, 1.89, -0.2],
      mat("#fff3be", 0.3, { emissive: "#ffdf80", emissiveIntensity: 0.55 }),
    );
  }
  const pump = new THREE.Group();
  pump.userData.energyPart = "hvac";
  lower.add(pump);
  box(pump, [0.65, 0.95, 1.15], [4.96, 0.65, 1.8], stone, 0.04);
  const fan = cylinder(pump, 0.32, 0.06, [5.31, 0.67, 1.8], charcoal);
  fan.rotation.z = Math.PI / 2;
  for (let i = -2; i <= 2; i++)
    box(pump, [0.03, 0.62, 0.025], [5.35, 0.67, 1.8 + i * 0.1], stone);
  const tank = new THREE.Group();
  tank.userData.energyPart = "water";
  lower.add(tank);
  cylinder(tank, 0.28, 1.25, [3.8, 0.88, -1.6], white);
  box(tank, [0.17, 0.22, 0.03], [3.8, 1.14, -1.3], charcoal);
  const thermostat = box(
    lower,
    [0.07, 0.24, 0.28],
    [0.23, 1.5, 0.25],
    white,
    0.025,
  );
  thermostat.userData.energyPart = "controls";
  box(
    lower,
    [0.075, 0.12, 0.18],
    [0.27, 1.51, 0.25],
    olive,
  ).userData.energyPart = "controls";

  const energyAnchors: {
    part: EnergyPart;
    parent: THREE.Object3D;
    position: THREE.Vector3;
  }[] = [
    { part: "solar", parent: roof, position: new THREE.Vector3(0, 1.05, 1.6) },
    { part: "roof", parent: roof, position: new THREE.Vector3(3.7, 0.8, -1.6) },
    {
      part: "attic",
      parent: roof,
      position: new THREE.Vector3(-3, -0.12, 2.8),
    },
    {
      part: "lighting",
      parent: lower,
      position: new THREE.Vector3(-2.3, 1.98, -0.2),
    },
    {
      part: "envelope",
      parent: upper,
      position: new THREE.Vector3(-4.38, 1.5, 1.5),
    },
    {
      part: "windows",
      parent: upper,
      position: new THREE.Vector3(1.04, 1.57, -2.92),
    },
    { part: "hvac", parent: lower, position: new THREE.Vector3(5.3, 0.8, 1.8) },
    {
      part: "water",
      parent: lower,
      position: new THREE.Vector3(3.8, 1.5, -1.6),
    },
    {
      part: "controls",
      parent: lower,
      position: new THREE.Vector3(0.3, 1.5, 0.25),
    },
    {
      part: "workspace",
      parent: upper,
      position: new THREE.Vector3(2.2, 1.3, -2.2),
    },
  ];
  // Clone per-mesh materials so a window or lamp highlight never tints other
  // objects sharing the same base material.
  const energyMeshes: {
    mesh: THREE.Mesh;
    part: EnergyPart;
    material: THREE.MeshStandardMaterial;
  }[] = [];
  house.traverse((object) => {
    if (
      !(object instanceof THREE.Mesh) ||
      !(object.material instanceof THREE.MeshStandardMaterial)
    )
      return;
    let tagged: THREE.Object3D | null = object;
    while (tagged && !tagged.userData.energyPart) tagged = tagged.parent;
    if (!tagged) return;
    const part = tagged.userData.energyPart as EnergyPart;
    object.userData.energyPart = part;
    const material = object.material.clone();
    object.material = material;
    materials.push(material);
    energyMeshes.push({ mesh: object, part, material });
  });
  let energyActive: EnergyPart[] = [];
  let lastHover: EnergyPart | null = null;
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let dragging = false;
  const isVisible = (object: THREE.Object3D): boolean =>
    object.visible && (!object.parent || isVisible(object.parent));
  function hover(part: EnergyPart | null) {
    if (part !== lastHover) {
      lastHover = part;
      options.onHover?.(part);
    }
  }
  function pointerMove(event: PointerEvent) {
    if (compact || dragging || !energyActive.length) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      (-(event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    scene.updateMatrixWorld();
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster
      .intersectObject(house, true)
      .find((h) => isVisible(h.object));
    const part = hit?.object.userData.energyPart as EnergyPart | undefined;
    hover(part && energyActive.includes(part) ? part : null);
  }
  const pointerLeave = () => hover(null);
  let dragOrigin = { x: 0, y: 0 };
  const dragStart = (event: PointerEvent) => {
    dragOrigin = { x: event.clientX, y: event.clientY };
    dragging = true;
    hover(null);
  };
  const dragEnd = (event: PointerEvent) => {
    dragging = false;
    if (
      Math.hypot(event.clientX - dragOrigin.x, event.clientY - dragOrigin.y) < 5
    )
      pointerMove(event);
  };
  renderer.domElement.addEventListener("pointermove", pointerMove);
  renderer.domElement.addEventListener("pointerleave", pointerLeave);
  renderer.domElement.addEventListener("pointerdown", dragStart);
  window.addEventListener("pointerup", dragEnd);
  function projectEnergy() {
    scene.updateMatrixWorld();
    options.onProject?.(
      energyAnchors.map((anchor) => {
        const point = anchor.parent
          .localToWorld(anchor.position.clone())
          .project(camera);
        return {
          part: anchor.part,
          x: ((point.x + 1) / 2) * host.clientWidth,
          y: ((1 - point.y) / 2) * host.clientHeight,
          visible:
            isVisible(anchor.parent) &&
            point.z < 1 &&
            point.z > -1 &&
            Math.abs(point.x) < 0.96 &&
            Math.abs(point.y) < 0.96,
        };
      }),
    );
  }

  let mode: HouseMode = compact ? "exterior" : "exploded";
  let targetUpper = 4.1,
    targetRoof = 8.0,
    visible = true,
    disposed = false,
    dirty = true;
  let cameraGoal: THREE.Vector3 | null = null,
    targetGoal: THREE.Vector3 | null = null;
  let frame = 0,
    lastTime = 0;
  const initialCamera = new THREE.Vector3(17, 14.5, 20);
  function framing() {
    const aspect = camera.aspect;
    const scale = compact ? 1.02 : aspect < 1 ? 1.32 : 0.96;
    return initialCamera.clone().multiplyScalar(scale);
  }
  function reset(immediate = false) {
    const target = new THREE.Vector3(
      0,
      mode === "exterior" ? 2.4 : mode === "cutaway" ? 2.2 : 3.9,
      0,
    );
    const position = framing();
    if (mode === "cutaway") position.multiplyScalar(0.91);
    if (immediate || reducedMotion || compact) {
      camera.position.copy(position);
      controls.target.copy(target);
      controls.update();
      cameraGoal = null;
      targetGoal = null;
    } else {
      cameraGoal = position;
      targetGoal = target;
    }
    dirty = true;
  }
  function setMode(next: HouseMode, immediate = false) {
    mode = next;
    targetUpper = next === "exploded" ? 4.1 : 2.8;
    targetRoof = next === "exploded" ? 8 : 5.6;
    roof.visible = next !== "cutaway";
    for (const shell of shells) shell.visible = next === "exterior";
    for (const lid of ceiling) lid.visible = next === "exterior";
    // Cutaway isolates the ground floor; the exploded view reveals both levels.
    upper.visible = next !== "cutaway";
    if (immediate || reducedMotion || compact) {
      upper.position.y = targetUpper;
      roof.position.y = targetRoof;
    }
    reset(immediate);
    dirty = true;
  }
  function size() {
    if (disposed) return;
    const w = host.clientWidth,
      h = host.clientHeight;
    if (!w || !h) return;
    camera.aspect = w / h;
    camera.fov = compact ? 33 : camera.aspect < 0.9 ? 42 : 34;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
    reset(true);
    if (compact) renderer.render(scene, camera);
  }
  const resize = new ResizeObserver(size);
  resize.observe(host);
  const intersection = new IntersectionObserver((entries) => {
    visible = entries.some((e) => e.isIntersecting);
    if (visible) dirty = true;
  });
  intersection.observe(host);
  const interaction = () => {
    cameraGoal = null;
    targetGoal = null;
    dirty = true;
  };
  controls.addEventListener("start", interaction);
  const changed = () => {
    dirty = true;
  };
  controls.addEventListener("change", changed);
  const contextLost = (event: Event) => {
    event.preventDefault();
    options.onUnavailable();
  };
  renderer.domElement.addEventListener("webglcontextlost", contextLost);
  function animate(time: number) {
    if (disposed) return;
    frame = requestAnimationFrame(animate);
    if (!visible || document.hidden) {
      lastTime = time;
      return;
    }
    const delta = Math.min((time - lastTime) / 1000, 0.05);
    lastTime = time;
    const ease = 1 - Math.exp(-8 * delta);
    let moving = false;
    for (const [group, target] of [
      [upper, targetUpper],
      [roof, targetRoof],
    ] as const) {
      if (Math.abs(group.position.y - target) > 0.001) {
        group.position.y = THREE.MathUtils.lerp(group.position.y, target, ease);
        moving = true;
      }
    }
    if (cameraGoal && targetGoal) {
      camera.position.lerp(cameraGoal, ease);
      controls.target.lerp(targetGoal, ease);
      moving = true;
      if (camera.position.distanceTo(cameraGoal) < 0.015) {
        camera.position.copy(cameraGoal);
        controls.target.copy(targetGoal);
        cameraGoal = null;
        targetGoal = null;
      }
    }
    controls.update(delta);
    if (dirty || moving || controls.autoRotate) {
      renderer.render(scene, camera);
      projectEnergy();
      dirty = false;
    }
  }
  size();
  setMode(mode, true);
  if (!compact) frame = requestAnimationFrame(animate);
  else renderer.render(scene, camera);
  return {
    setMode,
    setEnergy(active, planned, hovered) {
      energyActive = active;
      for (const item of energyMeshes) {
        const lit = active.includes(item.part);
        item.material.emissive.set(
          lit
            ? planned.includes(item.part)
              ? "#6aab42"
              : "#c9a04a"
            : "#000000",
        );
        item.material.emissiveIntensity = lit
          ? hovered === item.part
            ? 0.65
            : planned.includes(item.part)
              ? 0.12
              : 0.025
          : 0;
      }
      dirty = true;
    },
    setRotating(active) {
      controls.autoRotate = active;
      dirty = true;
    },
    reset() {
      reset();
    },
    zoom(factor) {
      const offset = camera.position.clone().sub(controls.target);
      offset.setLength(
        THREE.MathUtils.clamp(
          offset.length() * factor,
          controls.minDistance,
          controls.maxDistance,
        ),
      );
      cameraGoal = controls.target.clone().add(offset);
      targetGoal = controls.target.clone();
      dirty = true;
      if (reducedMotion) {
        camera.position.copy(cameraGoal);
        cameraGoal = null;
        targetGoal = null;
        controls.update();
      }
    },
    focus(room) {
      const y =
        room === "bedroom"
          ? targetUpper + 0.9
          : room === "roof"
            ? targetRoof + 0.5
            : 0.9;
      const target = new THREE.Vector3(
        room === "roof" ? 0 : -1.5,
        y,
        room === "living" ? 0.3 : -0.4,
      );
      cameraGoal = target
        .clone()
        .add(
          room === "roof"
            ? new THREE.Vector3(8, 8, 10)
            : new THREE.Vector3(9, 6, 11),
        );
      targetGoal = target;
      if (reducedMotion) {
        camera.position.copy(cameraGoal);
        controls.target.copy(target);
        cameraGoal = null;
        targetGoal = null;
        controls.update();
      }
      dirty = true;
    },
    dispose() {
      disposed = true;
      cancelAnimationFrame(frame);
      resize.disconnect();
      intersection.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointermove", pointerMove);
      renderer.domElement.removeEventListener("pointerleave", pointerLeave);
      renderer.domElement.removeEventListener("pointerdown", dragStart);
      window.removeEventListener("pointerup", dragEnd);
      renderer.domElement.removeEventListener("webglcontextlost", contextLost);
      const geometries = new Set<THREE.BufferGeometry>();
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) geometries.add(object.geometry);
      });
      geometries.forEach((g) => g.dispose());
      materials.forEach((m) => m.dispose());
      textures.forEach((t) => t.dispose());
      environment.dispose();
      sun.shadow.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
}
