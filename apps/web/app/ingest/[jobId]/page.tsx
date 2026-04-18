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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.ingest.get(jobId).then((job) => {
      try { setPlan(JSON.parse(job.er16_plan_json.replace(/'/g, '"'))); }
      catch { setError("Failed to parse task analysis — the server returned invalid JSON."); }
    });
  }, [jobId]);

  async function handleDraftPlan() {
    setLoading(true);
    setError(null);
    try {
      const evo: EvolutionCreated = await api.evolutions.create("run-placeholder", jobId);
      router.push(`/evolutions/${evo.evolution_id}/program?draft=${encodeURIComponent(evo.draft_content)}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to draft research plan.");
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
        {error && <p className="text-red-400 text-sm">{error}</p>}
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
