"use client";
import { Suspense, useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton, SkeletonCard } from "@/components/ui/skeleton";
import { DesignSelector } from "@/components/DesignSelector";
import { VideoGrid } from "@/components/VideoGrid";
import { api } from "@/lib/api";
import type { Er16Plan, EvolutionCreated, GenerateDesignsResponse } from "@/lib/types";

interface VideoItem {
  id: string;
  title: string;
  thumbnail: string;
  duration?: string;
}

function IngestPageContent() {
  const { jobId } = useParams<{ jobId: string }>();
  const searchParams = useSearchParams();
  const videoId = searchParams.get("videoId") ?? "";
  const router = useRouter();

  const [plan, setPlan] = useState<Er16Plan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [designsResponse, setDesignsResponse] = useState<GenerateDesignsResponse | null>(null);
  const [generatingDesigns, setGeneratingDesigns] = useState(false);
  const [selectedDesignId, setSelectedDesignId] = useState<string | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<"A" | "B" | "C" | null>(null);
  const [selectedVideoId, setSelectedVideoId] = useState<string>(videoId);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [videosLoading, setVideosLoading] = useState(true);

  useEffect(() => {
    let ignore = false;
    api.ingest.get(jobId).then((job) => {
      if (ignore) return;
      try {
        const planData = JSON.parse(job.er16_plan_json);
        setPlan(planData);
        // Generate mock videos from search queries for demo
        const mockVideos: VideoItem[] = (planData.search_queries || []).slice(0, 8).map((q: string, i: number) => ({
          id: i === 0 ? videoId : `video_${i}`,
          title: q,
          thumbnail: `https://img.youtube.com/vi/${i === 0 ? videoId : 'dQw4w9WgXcQ'}/mqdefault.jpg`,
          duration: `${Math.floor(Math.random() * 3) + 1}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}`,
        }));
        setVideos(mockVideos);
        setVideosLoading(false);
      } catch {
        setError("Server returned invalid task analysis — please retry.");
      }
    }).catch(() => setError("Failed to load task analysis."));
    return () => { ignore = true; };
  }, [jobId, videoId]);

  async function handleGenerateDesigns() {
    setGeneratingDesigns(true);
    setError(null);
    try {
      const response = await api.designs.generate(jobId);
      setDesignsResponse(response);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to generate designs.");
    } finally {
      setGeneratingDesigns(false);
    }
  }

  function handleDesignSelect(designId: string, candidateId: "A" | "B" | "C") {
    setSelectedDesignId(designId);
    setSelectedCandidateId(candidateId);
  }

  async function handleDraftPlan() {
    if (!selectedDesignId) {
      setError("Please select a design first.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const evo: EvolutionCreated = await api.evolutions.create("run-placeholder", jobId);
      await api.designs.select(selectedDesignId, evo.evolution_id);
      router.push(`/evolutions/${evo.evolution_id}/program?draft=${encodeURIComponent(evo.draft_content)}&design=${selectedCandidateId}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to draft research plan.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen p-8 bg-zinc-950 bg-dotted text-zinc-100">
      {/* Header */}
      <header className="mb-8 animate-fade-scale-in">
        <h1 className="text-2xl font-bold text-white">Task Analysis</h1>
        <p className="text-zinc-500 mt-1">Review the analysis and select reference videos</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
        {/* Task Analysis Card */}
        <section className="lg:col-span-1">
          <div className="tile-glow rounded-2xl p-6 animate-cascade-in">
            <h2 className="text-lg font-semibold text-zinc-200 mb-4 flex items-center gap-2">
              <span className="w-2 h-2 bg-emerald-500 rounded-full" />
              Task Goal
            </h2>
            {plan ? (
              <div className="space-y-4">
                <p className="text-zinc-300 leading-relaxed">{plan.task_goal}</p>
                <div className="flex flex-wrap gap-2">
                  {plan.affordances.map((a, i) => (
                    <Badge
                      key={a}
                      variant="secondary"
                      className="bg-zinc-800/80 text-zinc-300 border-zinc-700/50 animate-cascade-in"
                      style={{ animationDelay: `${(i + 1) * 0.05}s` }}
                    >
                      {a}
                    </Badge>
                  ))}
                </div>
                <div className="pt-4 border-t border-zinc-800">
                  <p className="text-zinc-500 text-sm">
                    <span className="text-zinc-600">Success criteria:</span>
                  </p>
                  <p className="text-zinc-400 text-sm mt-1">{plan.success_criteria}</p>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            )}
          </div>
        </section>

        {/* Video Grid */}
        <section className="lg:col-span-2">
          <div className="tile-glow rounded-2xl p-6 animate-cascade-in cascade-delay-2">
            <h2 className="text-lg font-semibold text-zinc-200 mb-4 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <span className="w-2 h-2 bg-blue-500 rounded-full" />
                Reference Videos
              </span>
              <span className="text-xs text-zinc-500 font-normal">
                {videos.length} videos found
              </span>
            </h2>
            <VideoGrid
              videos={videos}
              selectedId={selectedVideoId}
              onSelect={setSelectedVideoId}
              loading={videosLoading}
              loadingCount={8}
            />
          </div>
        </section>
      </div>

      {/* Selected Video Preview */}
      {selectedVideoId && !videosLoading && (
        <section className="mb-8 animate-fade-scale-in">
          <div className="tile-glow rounded-2xl p-6">
            <h2 className="text-lg font-semibold text-zinc-200 mb-4 flex items-center gap-2">
              <span className="w-2 h-2 bg-purple-500 rounded-full" />
              Selected Reference
            </h2>
            <div className="aspect-video max-w-2xl rounded-xl overflow-hidden bg-zinc-900">
              <iframe
                className="w-full h-full"
                src={`https://www.youtube.com/embed/${selectedVideoId}`}
                allowFullScreen
              />
            </div>
          </div>
        </section>
      )}

      {/* Generate Designs Button */}
      {!designsResponse && (
        <section className="mb-8 animate-cascade-in cascade-delay-4">
          <div className="tile-glow rounded-2xl p-6 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-zinc-200">Ready to generate designs?</h2>
              <p className="text-zinc-500 text-sm mt-1">
                AI will create 3 robot design candidates based on your task
              </p>
            </div>
            <Button
              onClick={handleGenerateDesigns}
              disabled={generatingDesigns || !plan}
              className="h-12 px-6 bg-white text-zinc-900 hover:bg-zinc-200 disabled:bg-zinc-800 disabled:text-zinc-500"
            >
              {generatingDesigns ? (
                <span className="flex items-center gap-3">
                  <Spinner size="sm" />
                  Generating...
                </span>
              ) : (
                "Generate Robot Designs"
              )}
            </Button>
          </div>
          {error && (
            <p className="text-red-400 text-sm mt-4 animate-cascade-in">{error}</p>
          )}
        </section>
      )}

      {/* Skeleton Design Cards while generating */}
      {generatingDesigns && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-zinc-200 mb-4 flex items-center gap-3">
            <Spinner size="sm" />
            Generating Robot Designs...
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <SkeletonCard
                key={i}
                className={`animate-cascade-in`}
                style={{ animationDelay: `${i * 0.1}s` } as React.CSSProperties}
              />
            ))}
          </div>
        </section>
      )}

      {/* Design Selector */}
      {designsResponse && (
        <section className="border-t border-zinc-800/50 pt-8 animate-fade-scale-in">
          <DesignSelector
            candidates={designsResponse.candidates}
            designIds={designsResponse.design_ids}
            modelPreferredId={designsResponse.model_preferred_id}
            rankings={designsResponse.fallback_rankings}
            onSelect={handleDesignSelect}
            disabled={loading}
          />

          <div className="mt-8 tile-glow rounded-2xl p-6 flex items-center justify-between">
            <div>
              {selectedCandidateId ? (
                <>
                  <h3 className="text-lg font-semibold text-zinc-200">
                    Design {selectedCandidateId} selected
                  </h3>
                  {selectedCandidateId !== designsResponse.model_preferred_id && (
                    <p className="text-amber-400 text-sm mt-1 flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-amber-400 rounded-full" />
                      Different from AI recommendation
                    </p>
                  )}
                </>
              ) : (
                <p className="text-zinc-500">Select a design to continue</p>
              )}
            </div>
            <Button
              onClick={handleDraftPlan}
              disabled={loading || !selectedDesignId}
              className="h-12 px-6 bg-emerald-600 text-white hover:bg-emerald-500 disabled:bg-zinc-800 disabled:text-zinc-500"
            >
              {loading ? (
                <span className="flex items-center gap-3">
                  <Spinner size="sm" />
                  Creating evolution...
                </span>
              ) : (
                `Continue with Design ${selectedCandidateId ?? "..."}`
              )}
            </Button>
          </div>
        </section>
      )}
    </main>
  );
}

export default function IngestPage() {
  return (
    <Suspense fallback={null}>
      <IngestPageContent />
    </Suspense>
  );
}
