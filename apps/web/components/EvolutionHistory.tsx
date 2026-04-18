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
    supabase
      .from("iterations")
      .select("*")
      .eq("evolution_id", evolutionId)
      .order("iter_num")
      .then(({ data, error }) => {
        if (error) { console.error("EvolutionHistory fetch error:", error.message); return; }
        if (data) setIterations(data as Iteration[]);
      });

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
