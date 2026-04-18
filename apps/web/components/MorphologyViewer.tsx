"use client";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment } from "@react-three/drei";
import { useMemo } from "react";

interface LinkGeom {
  type: "box" | "capsule" | "sphere";
  size: [number, number, number];
  position: [number, number, number];
  color: string;
}

interface Props {
  urdfXml?: string | null;
}

function parseUrdfLinks(xml: string): LinkGeom[] {
  const geoms: LinkGeom[] = [];
  const geomRe = /<geom[^>]*type="(\w+)"[^>]*\/>/g;
  const sizeRe = /size="([^"]+)"/;
  const posRe = /pos="([^"]+)"/;
  let m: RegExpExecArray | null;
  let idx = 0;
  while ((m = geomRe.exec(xml)) !== null) {
    const type = m[1] as "capsule" | "box" | "sphere";
    const colors = ["#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444"];
    const color = colors[idx % colors.length];
    const sizeMatch = sizeRe.exec(m[0]);
    const s = sizeMatch ? parseFloat(sizeMatch[1].split(" ")[0]) : 0.05;
    const posMatch = posRe.exec(m[0]);
    const pos: [number, number, number] = posMatch
      ? (posMatch[1].split(" ").map(Number) as [number, number, number])
      : [0, 0, idx * 0.2];
    geoms.push({ type, size: [s, s * 4, s], position: pos, color });
    idx++;
  }
  return geoms;
}

function LinkMesh({ geom }: { geom: LinkGeom }) {
  return (
    <mesh position={geom.position}>
      {geom.type === "sphere" ? (
        <sphereGeometry args={[geom.size[0], 16, 16]} />
      ) : (
        <capsuleGeometry args={[geom.size[0], geom.size[1], 8, 16]} />
      )}
      <meshStandardMaterial color={geom.color} roughness={0.4} metalness={0.2} />
    </mesh>
  );
}

export function MorphologyViewer({ urdfXml }: Props) {
  const links = useMemo(
    () => (urdfXml ? parseUrdfLinks(urdfXml) : []),
    [urdfXml]
  );

  return (
    <div className="relative w-full h-full min-h-[240px] bg-zinc-900 rounded-lg overflow-hidden">
      <Canvas camera={{ position: [2, 2, 2], fov: 50 }} shadows>
        <ambientLight intensity={0.4} />
        <directionalLight position={[5, 5, 5]} intensity={0.8} castShadow />
        <Environment preset="city" />
        {links.map((g, i) => <LinkMesh key={i} geom={g} />)}
        <OrbitControls enablePan={false} />
        <gridHelper args={[4, 20, "#333", "#222"]} />
      </Canvas>
      {!urdfXml && (
        <div className="absolute inset-0 flex items-center justify-center text-zinc-500 text-sm">
          Waiting for morphology…
        </div>
      )}
    </div>
  );
}
