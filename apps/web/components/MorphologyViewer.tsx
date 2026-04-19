"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useLoader } from "@react-three/fiber";
import { OrbitControls, Environment, Float, ContactShadows } from "@react-three/drei";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import type { EngineeringScene, RobotDesignCandidate } from "@/lib/types";
import * as THREE from "three";

type ViewerMode = "concept" | "engineering" | "joints" | "components";

interface LinkGeom {
  type: "box" | "capsule" | "sphere" | "cylinder";
  size: [number, number, number];
  position: [number, number, number];
  rotation?: [number, number, number];
  color: string;
  isJoint?: boolean;
}

interface Props {
  urdfXml?: string | null;
  candidate?: RobotDesignCandidate | null;
  renderGlb?: string | null;
  uiScene?: EngineeringScene | null;
  mode?: ViewerMode;
  animated?: boolean;
  onHoverComponent?: (component: EngineeringScene["nodes"][number] | null) => void;
}

const COLORS = {
  torso: "#5dd6c0",
  head: "#f7b267",
  arm: "#8b5cf6",
  leg: "#6366f1",
  joint: "#f97316",
  foot: "#10b981",
  hand: "#06b6d4",
};

function generateFromCandidate(c: RobotDesignCandidate): LinkGeom[] {
  const geoms: LinkGeom[] = [];
  const scale = 0.8;

  if (c.has_torso) {
    const torsoH = c.torso_length_m * scale;
    geoms.push({
      type: "capsule",
      size: [0.15, torsoH, 0.12],
      position: [0, torsoH / 2 + 0.1, 0],
      color: COLORS.torso,
    });
    geoms.push({
      type: "sphere",
      size: [0.12, 0.12, 0.12],
      position: [0, torsoH + 0.25, 0],
      color: COLORS.head,
    });
  }

  const legSpread = 0.12 * Math.max(1, c.num_legs - 1);
  for (let i = 0; i < c.num_legs; i += 1) {
    const xOff = c.num_legs === 1 ? 0 : -legSpread / 2 + (legSpread / (c.num_legs - 1)) * i;
    const legH = c.leg_length_m * scale * 0.5;

    geoms.push({ type: "sphere", size: [0.04, 0.04, 0.04], position: [xOff, 0.08, 0], color: COLORS.joint, isJoint: true });
    geoms.push({ type: "capsule", size: [0.035, legH, 0.035], position: [xOff, -legH / 2, 0], color: COLORS.leg });
    geoms.push({ type: "sphere", size: [0.035, 0.035, 0.035], position: [xOff, -legH - 0.02, 0], color: COLORS.joint, isJoint: true });
    geoms.push({ type: "capsule", size: [0.03, legH * 0.9, 0.03], position: [xOff, -legH - legH * 0.45, 0], color: COLORS.leg });
    geoms.push({ type: "box", size: [0.06, 0.025, 0.1], position: [xOff, -legH * 2 - 0.02, 0.02], color: COLORS.foot });
  }

  const shoulderY = c.has_torso ? c.torso_length_m * scale + 0.05 : 0.2;
  const armSpread = 0.2;
  for (let i = 0; i < c.num_arms; i += 1) {
    const xOff = c.num_arms === 1 ? 0.22 : (i === 0 ? -armSpread : armSpread);
    const armH = c.arm_length_m * scale * 0.45;

    geoms.push({ type: "sphere", size: [0.04, 0.04, 0.04], position: [xOff, shoulderY, 0], color: COLORS.joint, isJoint: true });
    geoms.push({ type: "capsule", size: [0.03, armH, 0.03], position: [xOff + (i === 0 ? -0.05 : 0.05), shoulderY - armH / 2, 0], rotation: [0, 0, i === 0 ? 0.3 : -0.3], color: COLORS.arm });
    geoms.push({ type: "sphere", size: [0.03, 0.03, 0.03], position: [xOff + (i === 0 ? -0.1 : 0.1), shoulderY - armH, 0], color: COLORS.joint, isJoint: true });
    geoms.push({ type: "capsule", size: [0.025, armH * 0.85, 0.025], position: [xOff + (i === 0 ? -0.12 : 0.12), shoulderY - armH - armH * 0.4, 0], color: COLORS.arm });
    geoms.push({ type: "sphere", size: [0.035, 0.035, 0.035], position: [xOff + (i === 0 ? -0.14 : 0.14), shoulderY - armH * 2 - 0.02, 0], color: COLORS.hand });
  }

  return geoms;
}

function parseUrdfLinks(xml: string): LinkGeom[] {
  const geoms: LinkGeom[] = [];
  const geomRe = /<geom[^>]*type="(\w+)"[^>]*\/>/g;
  const sizeRe = /size="([^"]+)"/;
  const posRe = /pos="([^"]+)"/;
  let match: RegExpExecArray | null;
  let idx = 0;
  while ((match = geomRe.exec(xml)) !== null) {
    const type = match[1] as "capsule" | "box" | "sphere" | "cylinder";
    const colors = ["#5dd6c0", "#8b5cf6", "#06b6d4", "#10b981", "#f7b267", "#6366f1"];
    const color = colors[idx % colors.length];
    const sizeMatch = sizeRe.exec(match[0]);
    const s = sizeMatch ? parseFloat(sizeMatch[1].split(" ")[0]) : 0.05;
    const posMatch = posRe.exec(match[0]);
    const pos: [number, number, number] = posMatch
      ? (posMatch[1].split(" ").map(Number) as [number, number, number])
      : [0, idx * 0.15, 0];
    geoms.push({ type, size: [s, s * 3, s], position: pos, color });
    idx += 1;
  }
  return geoms;
}

function LinkMesh({ geom, animated }: { geom: LinkGeom; animated?: boolean }) {
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (animated && geom.isJoint && meshRef.current) {
      meshRef.current.scale.setScalar(1 + Math.sin(state.clock.elapsedTime * 3) * 0.08);
    }
  });

  const rotation = geom.rotation ?? [0, 0, 0];

  return (
    <mesh ref={meshRef} position={geom.position} rotation={rotation as [number, number, number]} castShadow receiveShadow>
      {geom.type === "sphere" ? (
        <sphereGeometry args={[geom.size[0], 32, 32]} />
      ) : geom.type === "box" ? (
        <boxGeometry args={geom.size} />
      ) : geom.type === "cylinder" ? (
        <cylinderGeometry args={[geom.size[0], geom.size[0], geom.size[1], 32]} />
      ) : (
        <capsuleGeometry args={[geom.size[0], geom.size[1], 16, 32]} />
      )}
      {geom.isJoint ? (
        <meshStandardMaterial
          color={geom.color}
          roughness={0.2}
          metalness={0.9}
          emissive={geom.color}
          emissiveIntensity={0.3}
        />
      ) : (
        <meshStandardMaterial color={geom.color} roughness={0.35} metalness={0.6} envMapIntensity={1.2} />
      )}
    </mesh>
  );
}

function ConceptRobot({ links, animated }: { links: LinkGeom[]; animated?: boolean }) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (animated && groupRef.current) {
      groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.5) * 0.15;
    }
  });

  return (
    <Float speed={1.5} rotationIntensity={0.1} floatIntensity={0.3} floatingRange={[-0.02, 0.02]}>
      <group ref={groupRef}>
        {links.map((geom, index) => (
          <LinkMesh key={`${geom.type}-${index}`} geom={geom} animated={animated} />
        ))}
      </group>
    </Float>
  );
}

function EngineeringAsset({ renderGlb, animated }: { renderGlb: string; animated?: boolean }) {
  const gltf = useLoader(GLTFLoader, renderGlb);
  const scene = useMemo(() => gltf.scene.clone(true), [gltf.scene]);

  useEffect(() => {
    scene.traverse((node) => {
      if (node instanceof THREE.Mesh) {
        node.castShadow = true;
        node.receiveShadow = true;
      }
    });
  }, [scene]);

  useFrame((state) => {
    if (animated) {
      scene.rotation.y = Math.sin(state.clock.elapsedTime * 0.4) * 0.08;
    }
  });

  return <primitive object={scene} />;
}

function EngineeringOverlays({
  uiScene,
  mode,
  hoveredComponentId,
  onHoverComponent,
}: {
  uiScene: EngineeringScene | null;
  mode: ViewerMode;
  hoveredComponentId: string | null;
  onHoverComponent?: (component: EngineeringScene["nodes"][number] | null) => void;
}) {
  if (!uiScene || mode === "concept") return null;

  return (
    <group>
      {uiScene.nodes.map((node) => {
        const isHovered = hoveredComponentId === node.component_id;
        const showFrame = mode === "components" || isHovered;
        const opacity = mode === "components" ? (isHovered ? 0.38 : 0.12) : (isHovered ? 0.24 : 0.015);
        return (
          <mesh
            key={`component-${node.component_id}`}
            position={node.position}
            scale={node.scale}
            onPointerOver={(event) => {
              event.stopPropagation();
              onHoverComponent?.(node);
            }}
            onPointerOut={(event) => {
              event.stopPropagation();
              onHoverComponent?.(null);
            }}
          >
            <boxGeometry args={[1, 1, 1]} />
            <meshBasicMaterial
              color={isHovered ? "#79d165" : "#53c46a"}
              wireframe={showFrame}
              transparent
              opacity={opacity}
            />
          </mesh>
        );
      })}
      {mode === "joints"
        ? uiScene.joints.map((joint) => (
            <mesh key={`joint-${joint.name}`} position={joint.position}>
              <sphereGeometry args={[0.045, 20, 20]} />
              <meshStandardMaterial color="#f9a14a" emissive="#f9a14a" emissiveIntensity={0.32} />
            </mesh>
          ))
        : null}
    </group>
  );
}

export function MorphologyViewer({
  urdfXml,
  candidate,
  renderGlb,
  uiScene,
  mode = "concept",
  animated = true,
  onHoverComponent,
}: Props) {
  const [hoveredComponentId, setHoveredComponentId] = useState<string | null>(null);
  const links = useMemo(() => {
    if (urdfXml) return parseUrdfLinks(urdfXml);
    if (candidate) return generateFromCandidate(candidate);
    return [];
  }, [urdfXml, candidate]);

  const engineeringAvailable = Boolean(renderGlb && uiScene);
  const showConceptFallback = mode === "concept" || !engineeringAvailable;
  const hasData = links.length > 0 || engineeringAvailable;

  useEffect(() => {
    if (!uiScene || !hoveredComponentId) return;
    if (!uiScene.nodes.some((node) => node.component_id === hoveredComponentId)) {
      setHoveredComponentId(null);
      onHoverComponent?.(null);
    }
  }, [hoveredComponentId, onHoverComponent, uiScene]);

  return (
    <div className="relative h-full min-h-[240px] w-full overflow-hidden rounded-lg bg-gradient-to-b from-zinc-900 via-zinc-950 to-black">
      <Canvas
        camera={{ position: [1.25, 0.95, 1.25], fov: 42 }}
        shadows
        gl={{ antialias: true, alpha: true }}
        onPointerMissed={() => {
          setHoveredComponentId(null);
          onHoverComponent?.(null);
        }}
      >
        <color attach="background" args={["#0a0a0f"]} />
        <fog attach="fog" args={["#0a0a0f", 2, 6]} />
        <ambientLight intensity={0.28} />
        <directionalLight position={[3, 5, 2]} intensity={1.1} castShadow shadow-mapSize={[1024, 1024]} />
        <pointLight position={[-2, 2, -2]} intensity={0.35} color="#5dd6c0" />
        <pointLight position={[2, 1, 2]} intensity={0.25} color="#f7b267" />
        <Environment preset="night" />
        <Suspense fallback={null}>
          {showConceptFallback && links.length > 0 ? <ConceptRobot links={links} animated={animated} /> : null}
          {!showConceptFallback && renderGlb ? <EngineeringAsset renderGlb={renderGlb} animated={animated} /> : null}
          <EngineeringOverlays
            uiScene={uiScene ?? null}
            mode={mode}
            hoveredComponentId={hoveredComponentId}
            onHoverComponent={(component) => {
              setHoveredComponentId(component?.component_id ?? null);
              onHoverComponent?.(component);
            }}
          />
        </Suspense>
        <ContactShadows position={[0, -0.5, 0]} opacity={0.5} scale={3} blur={2} far={1} color="#000" />
        <OrbitControls enablePan={false} minDistance={0.8} maxDistance={4} autoRotate={animated && hasData} autoRotateSpeed={0.45} />
        <gridHelper args={[3, 15, "#1a1a2e", "#12121a"]} position={[0, -0.5, 0]} />
      </Canvas>
      {!hasData ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
          <div className="flex h-16 w-16 animate-pulse items-center justify-center rounded-full border-2 border-dashed border-zinc-700">
            <div className="h-8 w-8 animate-spin rounded-full border border-zinc-600" style={{ animationDuration: "3s" }} />
          </div>
          <p className="text-sm text-zinc-500">Generating morphology…</p>
        </div>
      ) : null}
      {!engineeringAvailable && mode !== "concept" ? (
        <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-amber-400/18 bg-black/45 px-3 py-1.5 text-xs text-amber-200/80">
          Engineering mode unavailable; showing degraded concept mode.
        </div>
      ) : null}
      {uiScene && hoveredComponentId ? (
        <div className="pointer-events-none absolute right-3 top-3 rounded-md border border-[#79d165]/25 bg-black/55 px-3 py-2 text-xs text-slate-200">
          {uiScene.nodes.find((node) => node.component_id === hoveredComponentId)?.display_name}
        </div>
      ) : null}
    </div>
  );
}
