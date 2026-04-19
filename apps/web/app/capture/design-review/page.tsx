"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { DesignSelector } from "@/components/DesignSelector";
import { VideoGrid } from "@/components/VideoGrid";
import {
  designIds,
  designReviewCandidates,
  designReviewPlan,
  designReviewRankings,
  designReviewVideos,
  videoPrompt,
} from "@/lib/video-fixtures";

function DesignReviewCapturePageContent() {
  const searchParams = useSearchParams();
  const selectedVideo = searchParams.get("video") ?? designReviewVideos[0].id;
  const selectedDesign = searchParams.get("design") as "A" | "B" | "C" | null;

  return (
    <main className="min-h-screen bg-zinc-950 bg-dotted p-8 text-zinc-100">
      <div className="mx-auto max-w-[1520px]">
        <header className="mb-6 animate-fade-scale-in">
          <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Capture Surface</p>
          <h1 className="mt-3 text-3xl font-semibold text-white">Task analysis and design review</h1>
          <p className="mt-2 max-w-3xl text-zinc-400">{videoPrompt}</p>
        </header>

        <div className="mb-6 grid gap-6 lg:grid-cols-[1.05fr_1.6fr]">
          <section className="tile-glow rounded-2xl p-6">
            <p className="text-xs uppercase tracking-[0.28em] text-zinc-500">Task Goal</p>
            <h2 className="mt-3 text-xl font-medium text-zinc-100">{designReviewPlan.task_goal}</h2>
            <p className="mt-4 text-sm leading-6 text-zinc-400">{designReviewPlan.success_criteria}</p>
            <div className="mt-5 flex flex-wrap gap-2">
              {designReviewPlan.affordances.map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-white/8 bg-white/4 px-3 py-1 text-xs text-zinc-300"
                >
                  {item}
                </span>
              ))}
            </div>
          </section>

          <section className="tile-glow rounded-2xl p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-zinc-100">Reference videos</h2>
              <span className="text-xs text-zinc-500">{designReviewVideos.length} clips shortlisted</span>
            </div>
            <VideoGrid
              videos={designReviewVideos}
              selectedId={selectedVideo}
            />
          </section>
        </div>

        <section className="tile-glow rounded-2xl p-6">
          <DesignSelector
            candidates={designReviewCandidates}
            designIds={designIds}
            modelPreferredId="A"
            rankings={designReviewRankings}
            onSelect={() => {}}
            initialSelectedId={selectedDesign}
          />
        </section>
      </div>
    </main>
  );
}

export default function DesignReviewCapturePage() {
  return (
    <Suspense fallback={null}>
      <DesignReviewCapturePageContent />
    </Suspense>
  );
}
