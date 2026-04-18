# Frontend (Workstream C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 4-screen Next.js 14 dashboard: prompt entry → task plan review → program.md HITL (Monaco editor) → evolution dashboard with 3-pane live view + Supabase Realtime history timeline.

**Architecture:** Next.js App Router with server components for initial data, client components for all interactive/realtime elements. Supabase JS SDK handles Realtime subscriptions. React Three Fiber renders URDF geometry as 3D. Monaco Editor hosts program.md editing. All API calls go through the FastAPI backend at `NEXT_PUBLIC_API_URL`.

**Tech Stack:** Next.js 14, shadcn/ui, Tailwind, TanStack Query, Supabase JS SDK (Realtime), Monaco Editor (`@monaco-editor/react`), React Three Fiber + drei, Three.js

**Prerequisites:** Plan 00 complete (Next.js scaffold, Supabase types, env vars set). Backend running at `localhost:8000`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `apps/web/src/lib/api.ts` | Create | Typed API client for FastAPI backend |
| `apps/web/src/lib/types.ts` | Create | Frontend-only types (extends Supabase types) |
| `apps/web/src/app/page.tsx` | Create | Screen 1: prompt entry |
| `apps/web/src/app/ingest/[jobId]/page.tsx` | Create | Screen 2: task plan + reference clip |
| `apps/web/src/app/evolutions/[evoId]/program/page.tsx` | Create | Screen 3: program.md HITL |
| `apps/web/src/app/evolutions/[evoId]/page.tsx` | Create | Screen 4: evolution dashboard |
| `apps/web/src/components/MorphologyViewer.tsx` | Create | React Three Fiber URDF 3D renderer |
| `apps/web/src/components/EvolutionHistory.tsx` | Create | Realtime history timeline |
| `apps/web/src/components/IterationDrawer.tsx` | Create | Slide-in detail drawer per iteration |
| `apps/web/src/components/ProgramMdEditor.tsx` | Create | Monaco editor wrapper |
| `apps/web/src/components/VideoPlayer.tsx` | Create | Simple `<video>` with signed URL |

---

## Task C1: API client + types

- [ ] **Step 1: Create `apps/web/src/lib/types.ts`**

```typescript
export interface Er16Plan {
  task_goal: string;
  affordances: string[];
  success_criteria: string;
  search_queries: string[];
}

export interface IngestJob {
  job_id: string;
  er16_plan: Er16Plan;
  video_id: string;
}

export interface EvolutionCreated {
  evolution_id: string;
  draft_id: string;
  draft_content: string;
}

export interface Iteration {
  id: string;
  evolution_id: string;
  iter_num: number;
  fitness_score: number | null;
  tracking_error: number | null;
  er16_success_prob: number | null;
  replay_mp4_url: string | null;
  controller_ckpt_url: string | null;
  reasoning_log: string | null;
  train_py_diff: string | null;
  morph_factory_diff: string | null;
  created_at: string;
}

export interface Evolution {
  id: string;
  run_id: string;
  status: "pending" | "running" | "stopped" | "done";
  best_iteration_id: string | null;
  total_cost_usd: number;
  program_md: string | null;
}
```

- [ ] **Step 2: Create `apps/web/src/lib/api.ts`**

```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

import type { IngestJob, EvolutionCreated, Evolution, Iteration } from "./types";

export const api = {
  ingest: {
    start: (prompt: string): Promise<IngestJob> =>
      req("/ingest", { method: "POST", body: JSON.stringify({ prompt }) }),
    get: (jobId: string) => req<{ status: string; er16_plan_json: string }>(`/ingest/${jobId}`),
  },
  evolutions: {
    create: (runId: string, ingestJobId: string): Promise<EvolutionCreated> =>
      req("/evolutions", {
        method: "POST",
        body: JSON.stringify({ run_id: runId, ingest_job_id: ingestJobId }),
      }),
    approveProgram: (evoId: string, content: string) =>
      req(`/evolutions/${evoId}/approve-program`, {
        method: "POST",
        body: JSON.stringify({ content }),
      }),
    stop: (evoId: string) => req(`/evolutions/${evoId}/stop`, { method: "POST" }),
    markBest: (evoId: string, iterId: string) =>
      req(`/evolutions/${evoId}/mark-best/${iterId}`, { method: "POST" }),
    get: (evoId: string): Promise<Evolution> => req(`/evolutions/${evoId}`),
  },
};
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd apps/web && npx tsc --noEmit
# Expected: no errors
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/
git commit -m "feat: add typed API client and frontend type definitions"
```

---

## Task C2: Screen 1 — Prompt entry

- [ ] **Step 1: Replace `apps/web/src/app/page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

export default function HomePage() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function handleAnalyze() {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const job = await api.ingest.start(prompt.trim());
      router.push(`/ingest/${job.job_id}?videoId=${job.video_id}&evoId=pending`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-8 p-8 bg-zinc-950 text-zinc-100">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight">autoResearch · Robotics</h1>
        <p className="text-zinc-400 mt-2">Type a task. Watch a robot evolve to perform it.</p>
      </div>

      <div className="w-full max-w-xl flex flex-col gap-4">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder='e.g. "a robot that picks up a box and carries it upstairs"'
          className="h-32 bg-zinc-900 border-zinc-700 text-zinc-100 placeholder:text-zinc-500"
          onKeyDown={(e) => e.key === "Enter" && e.metaKey && handleAnalyze()}
        />
        {error && <p className="text-red-400 text-sm">{error}</p>}
        <Button
          onClick={handleAnalyze}
          disabled={loading || !prompt.trim()}
          className="w-full"
        >
          {loading ? "Analyzing task…" : "Analyze task →"}
        </Button>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Run dev server and verify**

```bash
cd apps/web && npm run dev
# Open http://localhost:3000 — type a prompt, click "Analyze task"
# Should redirect to /ingest/[jobId] (404 for now — Screen 2 not built yet)
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/page.tsx
git commit -m "feat: Screen 1 — prompt entry with ingest API call"
```

---

## Task C3: Screen 2 — Task plan + reference clip

- [ ] **Step 1: Create `apps/web/src/app/ingest/[jobId]/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Er16Plan, EvolutionCreated } from "@/lib/types";

export default function IngestPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const searchParams = useSearchParams();
  const videoId = searchParams.get("videoId") ?? "";
  const router = useRouter();

  const [plan, setPlan] = useState<Er16Plan | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.ingest.get(jobId).then((job) => {
      try { setPlan(JSON.parse(job.er16_plan_json.replace(/'/g, '"'))); }
      catch { /* ignore parse error, show raw */ }
    });
  }, [jobId]);

  async function handleDraftPlan() {
    setLoading(true);
    try {
      // Create an evolution (which triggers program.md draft)
      const evo: EvolutionCreated = await api.evolutions.create("run-placeholder", jobId);
      router.push(`/evolutions/${evo.evolution_id}/program?draft=${encodeURIComponent(evo.draft_content)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen grid grid-cols-2 gap-8 p-8 bg-zinc-950 text-zinc-100">
      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold">Task analysis</h2>
        {plan ? (
          <>
            <p className="text-zinc-300">{plan.task_goal}</p>
            <div className="flex flex-wrap gap-2">
              {plan.affordances.map((a) => (
                <Badge key={a} variant="secondary">{a}</Badge>
              ))}
            </div>
            <p className="text-zinc-400 text-sm">
              <span className="text-zinc-500">Success criteria: </span>{plan.success_criteria}
            </p>
          </>
        ) : (
          <p className="text-zinc-500 animate-pulse">Loading task analysis…</p>
        )}
        <Button onClick={handleDraftPlan} disabled={loading || !plan} className="mt-4 w-fit">
          {loading ? "Drafting research plan…" : "Draft research plan →"}
        </Button>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold">Reference clip</h2>
        {videoId ? (
          <iframe
            className="w-full aspect-video rounded-lg"
            src={`https://www.youtube.com/embed/${videoId}`}
            allowFullScreen
          />
        ) : (
          <div className="w-full aspect-video bg-zinc-800 rounded-lg animate-pulse" />
        )}
      </section>
    </main>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/app/ingest/
git commit -m "feat: Screen 2 — task plan review + YouTube embed"
```

---

## Task C4: Screen 3 — program.md HITL (Monaco editor)

- [ ] **Step 1: Create `apps/web/src/components/ProgramMdEditor.tsx`**

```tsx
"use client";
import dynamic from "next/dynamic";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface Props {
  value: string;
  onChange: (v: string) => void;
}

export function ProgramMdEditor({ value, onChange }: Props) {
  return (
    <MonacoEditor
      height="400px"
      language="markdown"
      theme="vs-dark"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
    />
  );
}
```

- [ ] **Step 2: Create `apps/web/src/app/evolutions/[evoId]/program/page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ProgramMdEditor } from "@/components/ProgramMdEditor";
import { api } from "@/lib/api";

export default function ProgramPage() {
  const { evoId } = useParams<{ evoId: string }>();
  const searchParams = useSearchParams();
  const initialDraft = decodeURIComponent(searchParams.get("draft") ?? "");
  const [content, setContent] = useState(initialDraft);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleApprove() {
    setLoading(true);
    await api.evolutions.approveProgram(evoId, content);
    router.push(`/evolutions/${evoId}`);
  }

  async function handleRegenerate() {
    setLoading(true);
    // Re-create evolution draft (same evoId, new draft)
    const evo = await api.evolutions.get(evoId);
    setContent("Regenerating…");
    // Simplified: just clear and let user know to retry
    setContent("# Regenerated plan\n\nPlease describe your research agenda here.");
    setLoading(false);
  }

  return (
    <main className="min-h-screen flex flex-col gap-6 p-8 bg-zinc-950 text-zinc-100 max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold">Review research plan</h1>
        <p className="text-zinc-400 mt-1">
          This is the agenda the agent will follow. Edit freely, then approve to start the evolution.
        </p>
      </div>

      <ProgramMdEditor value={content} onChange={setContent} />

      <div className="flex gap-3">
        <Button onClick={handleApprove} disabled={loading || !content.trim()}>
          {loading ? "Starting evolution…" : "✓ Approve + Start"}
        </Button>
        <Button variant="outline" onClick={handleRegenerate} disabled={loading}>
          ↺ Regenerate
        </Button>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/ProgramMdEditor.tsx apps/web/src/app/evolutions/
git commit -m "feat: Screen 3 — program.md HITL with Monaco editor"
```

---

## Task C5: Morphology 3D viewer (React Three Fiber)

- [ ] **Step 1: Create `apps/web/src/components/MorphologyViewer.tsx`**

```tsx
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
  urdgXml?: string | null;
}

function parseUrdfLinks(xml: string): LinkGeom[] {
  // Minimal parser: extract geom types and sizes from MJCF
  const geoms: LinkGeom[] = [];
  const geomRe = /<geom[^>]*type="(\w+)"[^>]*\/>/g;
  const fromtoRe = /fromto="([^"]+)"/;
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

export function MorphologyViewer({ urdgXml }: Props) {
  const links = useMemo(
    () => (urdgXml ? parseUrdfLinks(urdgXml) : []),
    [urdgXml]
  );

  return (
    <div className="w-full h-full min-h-[240px] bg-zinc-900 rounded-lg overflow-hidden">
      <Canvas camera={{ position: [2, 2, 2], fov: 50 }} shadows>
        <ambientLight intensity={0.4} />
        <directionalLight position={[5, 5, 5]} intensity={0.8} castShadow />
        <Environment preset="city" />
        {links.map((g, i) => <LinkMesh key={i} geom={g} />)}
        <OrbitControls enablePan={false} />
        <gridHelper args={[4, 20, "#333", "#222"]} />
      </Canvas>
      {!urdgXml && (
        <div className="absolute inset-0 flex items-center justify-center text-zinc-500 text-sm">
          Waiting for morphology…
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/MorphologyViewer.tsx
git commit -m "feat: add URDF 3D viewer (React Three Fiber, MJCF parser)"
```

---

## Task C6: Evolution history + Realtime

- [ ] **Step 1: Create `apps/web/src/components/EvolutionHistory.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { Iteration } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Props {
  evolutionId: string;
  bestIterationId: string | null;
  onSelect: (iter: Iteration) => void;
  onMarkBest: (iterId: string) => void;
}

export function EvolutionHistory({ evolutionId, bestIterationId, onSelect, onMarkBest }: Props) {
  const [iterations, setIterations] = useState<Iteration[]>([]);

  useEffect(() => {
    // Load existing iterations
    supabase
      .from("iterations")
      .select("*")
      .eq("evolution_id", evolutionId)
      .order("iter_num")
      .then(({ data }) => { if (data) setIterations(data as Iteration[]); });

    // Subscribe to new iterations via Realtime
    const channel = supabase
      .channel(`iterations:${evolutionId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "iterations", filter: `evolution_id=eq.${evolutionId}` },
        (payload) => setIterations((prev) => [...prev, payload.new as Iteration])
      )
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, [evolutionId]);

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {iterations.map((iter) => {
        const isBest = iter.id === bestIterationId;
        return (
          <button
            key={iter.id}
            onClick={() => onSelect(iter)}
            className={`flex-shrink-0 flex flex-col items-center gap-1 p-2 rounded-lg border transition-colors
              ${isBest ? "border-yellow-400 bg-yellow-400/10" : "border-zinc-700 bg-zinc-800 hover:bg-zinc-700"}`}
          >
            <span className="text-xs text-zinc-400">#{iter.iter_num + 1}</span>
            <span className="text-sm font-mono font-bold">
              {iter.fitness_score != null ? iter.fitness_score.toFixed(2) : "…"}
            </span>
            {isBest && <Badge className="text-[10px] px-1 py-0 bg-yellow-400 text-black">BEST</Badge>}
            <Button
              size="sm"
              variant="ghost"
              className="text-[10px] h-5 px-1"
              onClick={(e) => { e.stopPropagation(); onMarkBest(iter.id); }}
            >
              ★
            </Button>
          </button>
        );
      })}
      {iterations.length === 0 && (
        <p className="text-zinc-500 text-sm animate-pulse">Waiting for first iteration…</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create `apps/web/src/components/IterationDrawer.tsx`**

```tsx
"use client";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import type { Iteration } from "@/lib/types";

interface Props {
  iteration: Iteration | null;
  open: boolean;
  onClose: () => void;
}

export function IterationDrawer({ iteration, open, onClose }: Props) {
  if (!iteration) return null;
  return (
    <Drawer open={open} onOpenChange={(v) => !v && onClose()}>
      <DrawerContent className="bg-zinc-900 text-zinc-100 max-h-[80vh] overflow-y-auto">
        <DrawerHeader>
          <DrawerTitle>Iteration #{iteration.iter_num + 1}</DrawerTitle>
        </DrawerHeader>
        <div className="px-6 pb-6 flex flex-col gap-4">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div><p className="text-zinc-500">Fitness</p><p className="font-mono">{iteration.fitness_score?.toFixed(3)}</p></div>
            <div><p className="text-zinc-500">Tracking err</p><p className="font-mono">{iteration.tracking_error?.toFixed(3)}</p></div>
            <div><p className="text-zinc-500">ER 1.6 prob</p><p className="font-mono">{iteration.er16_success_prob?.toFixed(3)}</p></div>
          </div>
          {iteration.reasoning_log && (
            <div>
              <p className="text-zinc-500 text-sm mb-1">Agent reasoning</p>
              <p className="text-sm text-zinc-300 whitespace-pre-wrap">{iteration.reasoning_log}</p>
            </div>
          )}
          {iteration.train_py_diff && (
            <div>
              <p className="text-zinc-500 text-sm mb-1">train.py diff</p>
              <pre className="text-xs bg-zinc-800 rounded p-3 overflow-x-auto">{iteration.train_py_diff}</pre>
            </div>
          )}
          {iteration.replay_mp4_url && (
            <div>
              <p className="text-zinc-500 text-sm mb-1">Replay</p>
              <video src={iteration.replay_mp4_url} controls className="w-full rounded" />
            </div>
          )}
          <div className="flex gap-2">
            {iteration.controller_ckpt_url && <a href={iteration.controller_ckpt_url} className="text-indigo-400 text-sm underline">Download controller</a>}
            {iteration.replay_mp4_url && <a href={iteration.replay_mp4_url} className="text-indigo-400 text-sm underline">Download replay</a>}
          </div>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/EvolutionHistory.tsx apps/web/src/components/IterationDrawer.tsx
git commit -m "feat: add Realtime evolution history + iteration detail drawer"
```

---

## Task C7: Screen 4 — Evolution dashboard (main)

- [ ] **Step 1: Create `apps/web/src/app/evolutions/[evoId]/page.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { MorphologyViewer } from "@/components/MorphologyViewer";
import { EvolutionHistory } from "@/components/EvolutionHistory";
import { IterationDrawer } from "@/components/IterationDrawer";
import { VideoPlayer } from "@/components/VideoPlayer";
import { api } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import type { Evolution, Iteration } from "@/lib/types";

export default function EvolutionPage() {
  const { evoId } = useParams<{ evoId: string }>();
  const [evo, setEvo] = useState<Evolution | null>(null);
  const [current, setCurrent] = useState<Iteration | null>(null);
  const [drawerIter, setDrawerIter] = useState<Iteration | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    api.evolutions.get(evoId).then(setEvo);
    // Poll evolution status every 5s while running
    const iv = setInterval(() => {
      api.evolutions.get(evoId).then((e) => {
        setEvo(e);
        if (e.status === "done" || e.status === "stopped") clearInterval(iv);
      });
    }, 5000);
    return () => clearInterval(iv);
  }, [evoId]);

  useEffect(() => {
    // Update current display when best changes
    if (!evo?.best_iteration_id) return;
    supabase
      .from("iterations")
      .select("*")
      .eq("id", evo.best_iteration_id)
      .single()
      .then(({ data }) => { if (data) setCurrent(data as Iteration); });
  }, [evo?.best_iteration_id]);

  async function handleStop() {
    await api.evolutions.stop(evoId);
    setEvo((e) => e ? { ...e, status: "stopped" } : e);
  }

  async function handleMarkBest(iterId: string) {
    await api.evolutions.markBest(evoId, iterId);
    setEvo((e) => e ? { ...e, best_iteration_id: iterId } : e);
  }

  const isRunning = evo?.status === "running";

  return (
    <main className="min-h-screen flex flex-col gap-4 p-4 bg-zinc-950 text-zinc-100">
      {/* Header bar */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-mono text-zinc-400">
          {evo?.status?.toUpperCase()} · ${(evo?.total_cost_usd ?? 0).toFixed(2)} spent
        </span>
        {isRunning && (
          <Button variant="destructive" size="sm" onClick={handleStop}>■ Stop</Button>
        )}
      </div>

      {/* 3-pane layout */}
      <div className="grid grid-cols-3 gap-4 flex-1">
        {/* Pane 1: prompt + reference clip */}
        <div className="flex flex-col gap-3 bg-zinc-900 rounded-lg p-4">
          <p className="text-xs text-zinc-500 uppercase tracking-wide">Prompt</p>
          <p className="text-sm text-zinc-300">{evo?.program_md?.slice(0, 120)}…</p>
          {current?.reasoning_log && (
            <>
              <p className="text-xs text-zinc-500 uppercase tracking-wide mt-2">Agent reasoning</p>
              <p className="text-sm text-zinc-400 line-clamp-4">{current.reasoning_log}</p>
            </>
          )}
        </div>

        {/* Pane 2: current morphology */}
        <div className="flex flex-col gap-3 bg-zinc-900 rounded-lg p-4">
          <p className="text-xs text-zinc-500 uppercase tracking-wide">Current morphology</p>
          <div className="flex-1 min-h-[240px] relative">
            <MorphologyViewer urdgXml={null} />
          </div>
          <div className="text-xs font-mono text-zinc-400">
            <span>score: {current?.fitness_score?.toFixed(3) ?? "—"}</span>
            <span className="ml-4">tracking: {current?.tracking_error?.toFixed(3) ?? "—"}</span>
            <span className="ml-4">ER16: {current?.er16_success_prob?.toFixed(3) ?? "—"}</span>
          </div>
        </div>

        {/* Pane 3: current replay */}
        <div className="flex flex-col gap-3 bg-zinc-900 rounded-lg p-4">
          <p className="text-xs text-zinc-500 uppercase tracking-wide">Current replay</p>
          <div className="flex-1">
            {current?.replay_mp4_url ? (
              <video src={current.replay_mp4_url} autoPlay loop muted className="w-full rounded" />
            ) : (
              <div className="w-full aspect-video bg-zinc-800 rounded animate-pulse" />
            )}
          </div>
        </div>
      </div>

      {/* Evolution history */}
      <div className="bg-zinc-900 rounded-lg p-4">
        <p className="text-xs text-zinc-500 uppercase tracking-wide mb-3">Evolution history</p>
        <EvolutionHistory
          evolutionId={evoId}
          bestIterationId={evo?.best_iteration_id ?? null}
          onSelect={(iter) => { setDrawerIter(iter); setDrawerOpen(true); }}
          onMarkBest={handleMarkBest}
        />
      </div>

      {/* Export button */}
      <Button
        className="w-full"
        disabled={!evo?.best_iteration_id}
        onClick={() => fetch(`/api/runs/${evoId}/export`, { method: "POST" })}
      >
        ✓ Approve best + Export
      </Button>

      <IterationDrawer
        iteration={drawerIter}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </main>
  );
}
```

- [ ] **Step 2: Create `apps/web/src/components/VideoPlayer.tsx`**

```tsx
interface Props { src: string | null; }
export function VideoPlayer({ src }: Props) {
  if (!src) return <div className="w-full aspect-video bg-zinc-800 rounded animate-pulse" />;
  return <video src={src} autoPlay loop muted className="w-full rounded" />;
}
```

- [ ] **Step 3: Run full dev check**

```bash
cd apps/web && npm run build
# Expected: no TypeScript errors, build succeeds
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/app/evolutions/ apps/web/src/components/VideoPlayer.tsx
git commit -m "feat: Screen 4 — evolution dashboard with 3-pane layout + history + drawer"
```
