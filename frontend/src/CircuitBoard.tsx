import { useEffect, useRef } from "react";
import * as THREE from "three";
import * as echarts from "echarts/core";
import { LineChart, BarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);

// A continuous wire loop, fixed resistor, cell and ammeter share one schematic coordinate system.
export function CircuitBoard({
  voltage = 1,
  resistance = 10,
}: {
  voltage?: number;
  resistance?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const holder = ref.current;
    if (!holder) return;
    let renderer: THREE.WebGLRenderer | null = null;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      /* Draw the same geometry on a 2D canvas below. */
    }
    const canvas = renderer?.domElement || document.createElement("canvas");
    holder.prepend(canvas);
    const scene = new THREE.Scene(),
      camera = new THREE.OrthographicCamera(-6, 6, 3.2, -3.2, 0.1, 40);
    camera.position.z = 12;
    const copper = new THREE.MeshBasicMaterial({ color: 0x79e1c4 }),
      gold = new THREE.MeshBasicMaterial({ color: 0xffbf75 }),
      paper = new THREE.MeshBasicMaterial({ color: 0xe0f4ec });
    const geometry: THREE.BufferGeometry[] = [];
    const strokes: { a: number[]; b: number[]; r: number; color: string }[] =
      [];
    function wire(a: number[], b: number[], r = 0.028, mat = copper) {
      strokes.push({ a, b, r, color: "#" + mat.color.getHexString() });
      const p = new THREE.Vector3(a[0], a[1], 0),
        q = new THREE.Vector3(b[0], b[1], 0),
        v = q.clone().sub(p);
      const g = new THREE.CylinderGeometry(r, r, v.length(), 10);
      geometry.push(g);
      const mesh = new THREE.Mesh(g, mat);
      mesh.position.copy(p.add(q).multiplyScalar(0.5));
      mesh.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        v.normalize(),
      );
      scene.add(mesh);
    }
    const points = [
      [-0.3, -1.65],
      [-3.7, -1.65],
      [-3.7, 1.65],
      [-1.15, 1.65],
    ];
    const right = [
      [1.15, 1.65],
      [3.65, 1.65],
      [3.65, 0.45],
    ];
    const bottom = [
      [3.65, -0.45],
      [3.65, -1.65],
      [0.3, -1.65],
    ];
    for (const path of [points, right, bottom])
      for (let i = 1; i < path.length; i++) wire(path[i - 1], path[i]);
    const resistor = [
      [-1.15, 1.65],
      [-0.94, 1.65],
      [-0.78, 2],
      [-0.48, 1.3],
      [-0.17, 2],
      [0.14, 1.3],
      [0.45, 2],
      [0.76, 1.3],
      [0.94, 1.65],
      [1.15, 1.65],
    ];
    for (let i = 1; i < resistor.length; i++)
      wire(resistor[i - 1], resistor[i], 0.04, gold);
    wire([-0.3, -2.06], [-0.3, -1.24], 0.05, paper);
    wire([0.3, -1.9], [0.3, -1.4], 0.05, paper);
    const ring = new THREE.TorusGeometry(0.44, 0.035, 10, 52);
    geometry.push(ring);
    const meter = new THREE.Mesh(ring, paper);
    meter.position.set(3.65, 0, 0);
    scene.add(meter);
    wire([3.48, -0.17], [3.65, 0.19], 0.021, paper);
    wire([3.65, 0.19], [3.82, -0.17], 0.021, paper);
    wire([3.55, -0.02], [3.75, -0.02], 0.021, paper);
    const fit = () => {
      const w = holder.clientWidth,
        h = holder.clientHeight;
      if (!w || !h) return;
      const half = Math.max(2.9, (5.3 * h) / w),
        pixelRatio = Math.min(devicePixelRatio, 2);
      if (renderer) {
        camera.left = (-half * w) / h;
        camera.right = -camera.left;
        camera.top = half;
        camera.bottom = -half;
        camera.updateProjectionMatrix();
        renderer.setPixelRatio(pixelRatio);
        renderer.setSize(w, h);
        renderer.render(scene, camera);
      } else {
        canvas.width = w * pixelRatio;
        canvas.height = h * pixelRatio;
        canvas.style.width = w + "px";
        canvas.style.height = h + "px";
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        const scale = canvas.height / (half * 2);
        ctx.setTransform(
          scale,
          0,
          0,
          -scale,
          canvas.width / 2,
          canvas.height / 2,
        );
        ctx.lineCap = "round";
        for (const s of strokes) {
          ctx.beginPath();
          ctx.moveTo(s.a[0], s.a[1]);
          ctx.lineTo(s.b[0], s.b[1]);
          ctx.strokeStyle = s.color;
          ctx.lineWidth = s.r * 2;
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.arc(3.65, 0, 0.44, 0, 2 * Math.PI);
        ctx.lineWidth = 0.07;
        ctx.stroke();
      }
    };
    const observer = new ResizeObserver(fit);
    observer.observe(holder);
    fit();
    return () => {
      observer.disconnect();
      renderer?.dispose();
      geometry.forEach((g) => g.dispose());
      [copper, gold, paper].forEach((m) => m.dispose());
      canvas.remove();
    };
  }, []);
  return (
    <div
      className="board"
      ref={ref}
      role="img"
      aria-label={
        "定值电阻电路，电阻 " + resistance + " 欧姆，电压 " + voltage + " 伏特"
      }
    >
      <span className="board-label">R = {resistance} Ω</span>
      <span className="board-foot">
        U = {voltage} V <b>·</b> I = {Number((voltage / resistance).toFixed(5))}{" "}
        A
      </span>
    </div>
  );
}
export function Plot({ option }: { option: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    const obs = new ResizeObserver(() => chart.resize());
    obs.observe(ref.current);
    return () => {
      obs.disconnect();
      chart.dispose();
    };
  }, [option]);
  return (
    <div
      ref={ref}
      style={{ height: 235, width: "100%" }}
      role="img"
      aria-label="教学数据图表"
    />
  );
}
