"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ProgramMdEditor } from "@/components/ProgramMdEditor";
import { programDraft } from "@/lib/video-fixtures";

export default function ProgramCapturePage() {
  const [content, setContent] = useState(programDraft);

  return (
    <main className="min-h-screen bg-zinc-950 p-8 text-zinc-100">
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Capture Surface</p>
          <h1 className="mt-3 text-3xl font-semibold text-white">Review research plan</h1>
          <p className="mt-2 text-zinc-400">
            This is the agenda the agent will follow. Edit freely, then approve to start the evolution.
          </p>
        </div>

        <div className="overflow-hidden rounded-2xl border border-white/8 bg-black/30 shadow-[0_20px_60px_rgba(0,0,0,0.4)]">
          <ProgramMdEditor value={content} onChange={setContent} />
        </div>

        <div className="flex gap-3">
          <Button className="bg-white text-zinc-950 hover:bg-zinc-200">
            ✓ Approve + Start
          </Button>
          <Button variant="outline" disabled>
            ↺ Regenerate
          </Button>
        </div>
      </div>
    </main>
  );
}
