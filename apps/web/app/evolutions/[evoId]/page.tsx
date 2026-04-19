"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { MorphologyViewer } from "@/components/MorphologyViewer";
import { EvolutionHistory } from "@/components/EvolutionHistory";
import { IterationDrawer } from "@/components/IterationDrawer";
import { api } from "@/lib/api";
import type { Evolution, Iteration } from "@/lib/types";

export default function EvolutionPage() {
  const { evoId } = useParams<{ evoId: string }>();
  const [evo, setEvo] = useState<Evolution | null>(null);
  const [iterations, setIterations] = useState<Iteration[]>([]);
  const [current, setCurrent] = useState<Iteration | null>(null);
  const [drawerIter, setDrawerIter] = useState<Iteration | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let iv: ReturnType<typeof setInterval> | null = null;
    const load = async () => {
      const [nextEvo, nextIterations] = await Promise.all([
        api.evolutions.get(evoId),
        api.evolutions.listIterations(evoId),
      ]);
      if (cancelled) {
        return;
      }
      setEvo(nextEvo);
      setIterations(nextIterations.items);
      if (["done", "stopped", "failed"].includes(nextEvo.status) && iv) {
        clearInterval(iv);
        iv = null;
      }
    };

    void load();
    iv = setInterval(() => {
      load().catch((err: unknown) => {
        console.error("Evolution polling failed:", err instanceof Error ? err.message : err);
      });
    }, 3000);
    return () => {
      cancelled = true;
      if (iv) {
        clearInterval(iv);
      }
    };
  }, [evoId]);

  useEffect(() => {
    if (iterations.length === 0) {
      setCurrent(null);
      return;
    }
    const preferred =
      (evo?.best_iteration_id
        ? iterations.find((iter) => iter.id === evo.best_iteration_id)
        : null) ??
      iterations[iterations.length - 1] ??
      null;
    setCurrent(preferred);
  }, [evo?.best_iteration_id, iterations]);

  async function handleStop() {
    try {
      await api.evolutions.stop(evoId);
      setEvo((e) => e ? { ...e, status: "stopped" } : e);
    } catch (err: unknown) {
      console.error("Failed to stop evolution:", err instanceof Error ? err.message : err);
    }
  }

  async function handleMarkBest(iterId: string) {
    try {
      await api.evolutions.markBest(evoId, iterId);
      setEvo((e) => e ? { ...e, best_iteration_id: iterId } : e);
    } catch (err: unknown) {
      console.error("Failed to mark best iteration:", err instanceof Error ? err.message : err);
    }
  }

  const isRunning = evo?.status === "running";

  return (
    <main className="min-h-screen flex flex-col gap-4 p-4 bg-zinc-950 text-zinc-100">
      <div className="flex items-center justify-between text-sm">
        <span className="font-mono text-zinc-400">
          {evo?.status?.toUpperCase()} · ${(evo?.total_cost_usd ?? 0).toFixed(2)} spent
        </span>
        {isRunning && (
          <Button variant="destructive" size="sm" onClick={handleStop}>■ Stop</Button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4 flex-1">
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

        <div className="flex flex-col gap-3 bg-zinc-900 rounded-lg p-4">
          <p className="text-xs text-zinc-500 uppercase tracking-wide">Current morphology</p>
          <div className="flex-1 min-h-[240px] relative">
            <MorphologyViewer urdfXml={null} />
          </div>
          <div className="text-xs font-mono text-zinc-400">
            <span>score: {current?.fitness_score?.toFixed(3) ?? "—"}</span>
            <span className="ml-4">tracking: {current?.tracking_error?.toFixed(3) ?? "—"}</span>
            <span className="ml-4">ER16: {current?.er16_success_prob?.toFixed(3) ?? "—"}</span>
          </div>
        </div>

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

      <div className="bg-zinc-900 rounded-lg p-4">
        <p className="text-xs text-zinc-500 uppercase tracking-wide mb-3">Evolution history</p>
        <EvolutionHistory
          iterations={iterations}
          bestIterationId={evo?.best_iteration_id ?? null}
          onSelect={(iter) => { setDrawerIter(iter); setDrawerOpen(true); }}
          onMarkBest={handleMarkBest}
        />
      </div>

      <Button
        className="w-full"
        disabled={!evo?.best_iteration_id}
        onClick={() => {
          if (current?.controller_ckpt_url) {
            window.open(current.controller_ckpt_url, "_blank");
          } else {
            alert("No checkpoint available — select a best iteration first.");
          }
        }}
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
