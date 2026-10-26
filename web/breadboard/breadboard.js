// 3D breadboard view (Phase 35): shows where every part's legs go on a real breadboard.
// The plan (which hole each leg goes in) comes from layout.js; this file only draws it.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { fromNetlist, mainValue } from "../editor/model.js";
import { COLUMNS, colorBands, planBreadboard } from "./layout.js";

const $ = (id) => document.getElementById(id);
const ROW_Z = { "+": -8.6, "-": -7.6, a: -5, b: -4, c: -3, d: -2, e: -1, f: 1, g: 2, h: 3, i: 4, j: 5 };
const BOARD_TOP = 0.4;
const BAND_HEX = { black: 0x111111, brown: 0x6b3a1e, red: 0xd12a2a, orange: 0xf08a1c, yellow: 0xf5d020, green: 0x2e9b45,
  blue: 0x2a5bd1, violet: 0x8a3fc4, gray: 0x8a8a8a, white: 0xf2f2f2, gold: 0xc9a227 };
const NET_COLORS = [0xe53935, 0x1e88e5, 0x43a047, 0xfdd835, 0x8e24aa, 0xfb8c00, 0x00acc1];

const scene = new THREE.Scene();
const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
scene.background = new THREE.Color(dark ? 0x15181e : 0xe9ecf1);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
$("view").appendChild(renderer.domElement);
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 500);
camera.position.set(20, 38, 34);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(22, 0, 0);
controls.update();
scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.2));
const sun = new THREE.DirectionalLight(0xffffff, 1.4);
sun.position.set(10, 30, 15);
scene.add(sun);

const partGroups = new Map(); // part name -> group, for hover labels and highlighting
let highlighted = null;

function holePosition(hole) {
  return new THREE.Vector3(hole.col, BOARD_TOP, ROW_Z[hole.row]);
}

function material(color, extra = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.05, ...extra });
}

function buildBoard() {
  const board = new THREE.Mesh(new THREE.BoxGeometry(COLUMNS + 3, 0.8, 20), material(0xf4f1ea));
  board.position.set(COLUMNS / 2, 0, 0);
  scene.add(board);
  const gap = new THREE.Mesh(new THREE.BoxGeometry(COLUMNS + 3, 0.82, 0.7), material(0xd9d4c8));
  gap.position.set(COLUMNS / 2, 0, 0);
  scene.add(gap);
  // Rail stripes: red next to the + row, blue next to the - row.
  for (const [z, color] of [[-9.3, 0xd32f2f], [-6.9, 0x1565c0]]) {
    const stripe = new THREE.Mesh(new THREE.BoxGeometry(COLUMNS, 0.02, 0.12), material(color));
    stripe.position.set(COLUMNS / 2 + 0.5, BOARD_TOP + 0.01, z);
    scene.add(stripe);
  }
  // Every hole, as one instanced mesh so thousands of holes stay fast.
  const holes = [];
  for (let col = 1; col <= COLUMNS; col++) {
    for (const row of Object.keys(ROW_Z)) {
      if ((row === "+" || row === "-") && col % 6 === 0) continue; // rails come in groups of five
      holes.push([col, ROW_Z[row]]);
    }
  }
  const holeMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.34, 0.06, 0.34), material(0x3a3a3a), holes.length);
  const m = new THREE.Matrix4();
  holes.forEach(([x, z], k) => {
    m.makeTranslation(x, BOARD_TOP, z);
    holeMesh.setMatrixAt(k, m);
  });
  scene.add(holeMesh);
  for (let col = 5; col <= COLUMNS; col += 5) addText(String(col), new THREE.Vector3(col, BOARD_TOP + 0.02, -6.1), 0.9);
  for (const row of ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]) addText(row, new THREE.Vector3(-0.4, BOARD_TOP + 0.02, ROW_Z[row]), 0.9);
}

function addText(text, position, size, group = scene) {
  // Text as a flat canvas texture lying on the board.
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#555";
  ctx.font = "bold 40px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 64, 32);
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size * 2, size), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true }));
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.copy(position);
  group.add(mesh);
}

function lead(points, color = 0xb0b0b0, radius = 0.06) {
  const curve = new THREE.CatmullRomCurve3(points);
  return new THREE.Mesh(new THREE.TubeGeometry(curve, 24, radius, 6, false), material(color, { metalness: 0.6, roughness: 0.3 }));
}

function twoLegPart(placement) {
  const group = new THREE.Group();
  const [a, b] = placement.legs.map(holePosition);
  const lift = 1.3;
  const mid = a.clone().add(b).multiplyScalar(0.5).setY(BOARD_TOP + lift);
  const along = b.clone().sub(a).setY(0);
  const length = Math.max(1.2, Math.min(3, along.length() - 0.8));
  const dir = along.lengthSq() > 0 ? along.normalize() : new THREE.Vector3(1, 0, 0);
  const endA = mid.clone().addScaledVector(dir, -length / 2);
  const endB = mid.clone().addScaledVector(dir, length / 2);
  group.add(lead([a, a.clone().setY(BOARD_TOP + lift), endA]));
  group.add(lead([b, b.clone().setY(BOARD_TOP + lift), endB]));

  const body = new THREE.Group();
  const type = placement.kind;
  const colors = { R: 0xd9c08c, C: 0x2f6fd0, L: 0x2e7d32, D: 0x222222, LED: 0xff3030, S: 0x777777, V: 0xf0c020, I: 0xf0c020 };
  const radius = type === "C" ? 0.5 : 0.35;
  const cyl = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, length, 20),
    material(colors[type] || 0x999999, type === "LED" ? { transparent: true, opacity: 0.8, emissive: 0x550000 } : {}));
  cyl.rotation.z = Math.PI / 2;
  body.add(cyl);
  if (type === "R") {
    // The real color bands, so the model matches the resistor in your parts drawer.
    colorBands(mainValue(placement.part.value)).forEach((band, k) => {
      const ring = new THREE.Mesh(new THREE.CylinderGeometry(radius + 0.02, radius + 0.02, 0.16, 20), material(BAND_HEX[band]));
      ring.rotation.z = Math.PI / 2;
      ring.position.x = -length / 2 + 0.35 + k * (k === 3 ? 0.55 : 0.35);
      body.add(ring);
    });
  }
  if (type === "D") {
    const band = new THREE.Mesh(new THREE.CylinderGeometry(radius + 0.02, radius + 0.02, 0.2, 20), material(0xdddddd));
    band.rotation.z = Math.PI / 2;
    band.position.x = length / 2 - 0.3;
    body.add(band);
  }
  body.position.copy(mid);
  body.rotation.y = -Math.atan2(dir.z, dir.x);
  group.add(body);
  return group;
}

function threeLegPart(placement) {
  // A TO-92 transistor: a black half-cylinder with three legs fanning out to their holes.
  const group = new THREE.Group();
  const holes = placement.legs.map(holePosition);
  const center = holes.reduce((s, h) => s.add(h), new THREE.Vector3()).multiplyScalar(1 / holes.length).setY(BOARD_TOP + 2.2);
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, 1.2, 24, 1, false, 0, Math.PI), material(0x1b1b1b));
  body.position.copy(center);
  group.add(body);
  holes.forEach((h, k) => {
    const foot = center.clone().add(new THREE.Vector3((k - 1) * 0.35, -0.6, 0));
    group.add(lead([foot, foot.clone().setY(BOARD_TOP + 1.2), h.clone().setY(BOARD_TOP + 0.8), h]));
  });
  return group;
}

function dipChip(placement) {
  const group = new THREE.Group();
  const body = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.7, 2.4), material(0x1b1b1b));
  body.position.set(placement.col + 1.5, BOARD_TOP + 0.75, 0);
  group.add(body);
  for (let k = 0; k < 4; k++) {
    for (const z of [-1, 1]) {
      const pin = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.7, 0.18), material(0xcccccc, { metalness: 0.8 }));
      pin.position.set(placement.col + k, BOARD_TOP + 0.3, z);
      group.add(pin);
    }
  }
  const notch = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 0.05, 16), material(0x444444));
  notch.position.set(placement.col - 0.1, BOARD_TOP + 1.11, 0);
  group.add(notch);
  return group;
}

function jumper(j, k) {
  const a = holePosition(j.from);
  const b = holePosition(j.to);
  const height = BOARD_TOP + 1.2 + (k % 3) * 0.4;
  return lead([a, a.clone().setY(height), b.clone().setY(height), b], NET_COLORS[k % NET_COLORS.length], 0.1);
}

function supplyLeads(plan) {
  if (!plan.supply) return;
  const box = new THREE.Mesh(new THREE.BoxGeometry(4, 2.5, 3), material(0x37474f));
  box.position.set(-5, 1.2, -8);
  scene.add(box);
  addText(`${plan.supply.source.value} V`, new THREE.Vector3(-5, 2.5, -8), 1.2);
  scene.add(lead([new THREE.Vector3(-3, 1.5, -8.6), new THREE.Vector3(0, 1.4, -8.6), holePosition({ col: 1, row: "+" })], 0xd32f2f, 0.12));
  scene.add(lead([new THREE.Vector3(-3, 1.0, -7.6), new THREE.Vector3(0, 1.0, -7.6), holePosition({ col: 1, row: "-" })], 0x222222, 0.12));
}

function show(design) {
  let plan;
  try {
    plan = planBreadboard(design);
  } catch (error) {
    $("steps").innerHTML = `<li class="error">${error.message}</li>`;
    return;
  }
  supplyLeads(plan);
  for (const placement of plan.placements) {
    const group = placement.kind === "dip" ? dipChip(placement)
      : placement.legs.length === 2 ? twoLegPart(placement) : threeLegPart(placement);
    group.userData.name = placement.part.name;
    partGroups.set(placement.part.name, group);
    scene.add(group);
  }
  plan.jumpers.forEach((j, k) => scene.add(jumper(j, k)));
  frame(plan);
  $("steps").innerHTML = plan.instructions.map((text) => `<li>${text.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</li>`).join("");
  [...$("steps").children].forEach((li, k) => {
    const name = (plan.instructions[k].match(/^(\S+?)[ :(]/) || [])[1];
    if (name && partGroups.has(name)) li.addEventListener("click", () => highlight(name));
  });
}

function frame(plan) {
  // Aim the camera at the columns the circuit actually uses instead of the whole board.
  const cols = plan.placements.flatMap((p) => (p.legs ? p.legs.map((h) => h.col) : [p.col, p.col + 3]));
  if (!cols.length) return;
  const lo = Math.min(...cols) - 2;
  const hi = Math.max(...cols) + 2;
  const center = (lo + hi) / 2;
  const span = Math.max(14, hi - lo);
  controls.target.set(center, 0, -2);
  camera.position.set(center - span * 0.15, span * 0.9, span * 0.95);
  controls.update();
}

function highlight(name) {
  if (highlighted) highlighted.traverse((o) => o.material && o.material.emissive && o.material.emissive.setHex(o.userData.emissive || 0));
  highlighted = partGroups.get(name) || null;
  if (highlighted) {
    highlighted.traverse((o) => {
      if (o.material && o.material.emissive) {
        o.userData.emissive = o.material.emissive.getHex();
        o.material.emissive.setHex(0x664400);
      }
    });
  }
}

// Hover: name the part under the mouse.
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
renderer.domElement.addEventListener("pointermove", (event) => {
  const box = renderer.domElement.getBoundingClientRect();
  pointer.set(((event.clientX - box.left) / box.width) * 2 - 1, -((event.clientY - box.top) / box.height) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects([...partGroups.values()], true)[0];
  let name = null;
  for (let o = hit && hit.object; o; o = o.parent) if (o.userData.name) { name = o.userData.name; break; }
  const tip = $("tip");
  tip.hidden = !name;
  if (name) {
    tip.textContent = name;
    tip.style.left = `${event.clientX + 12}px`;
    tip.style.top = `${event.clientY + 12}px`;
  }
});

function resize() {
  const view = $("view");
  renderer.setSize(view.clientWidth, view.clientHeight);
  camera.aspect = view.clientWidth / Math.max(1, view.clientHeight);
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);

function loadDesign() {
  try {
    const saved = JSON.parse(localStorage.getItem("minispice.design"));
    if (saved && saved.design && saved.design.parts.length) {
      $("title").textContent = saved.title || "Your circuit";
      return saved.design;
    }
  } catch (error) {
    // fall through to the file picker
  }
  return null;
}

$("file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const text = await file.text();
  const design = file.name.endsWith(".json") ? JSON.parse(text).design : fromNetlist(text);
  location.hash = "";
  localStorage.setItem("minispice.design", JSON.stringify({ title: file.name, design }));
  location.reload();
});

buildBoard();
resize();
const design = loadDesign();
if (design) show(design);
else $("steps").innerHTML = "<li>Draw a circuit in the editor first, or open a saved design or netlist above.</li>";
renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});
