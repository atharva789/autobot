"use client";

import { ArrowRight, Bot, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { videoPrompt } from "@/lib/video-fixtures";

export default function PromptCapturePage() {
  return (
    <main className="min-h-screen px-5 py-5 text-slate-100 md:px-6">
      <div className="mx-auto max-w-[1720px]">
        <div className="autobot-shell overflow-hidden px-5 py-4 md:px-6">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/7 pb-4">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <Bot className="size-4 text-[#d9b15f]" />
                  AutoBot
                </span>
                <span className="text-slate-600">/</span>
                <span className="text-sm text-slate-400">orchard_01</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="autobot-status" data-tone="success">
                3 active
              </span>
              <span className="autobot-status" data-tone="warning">
                2 waiting
              </span>
              <span className="autobot-status" data-tone="muted">
                AV
              </span>
            </div>
          </header>

          <section className="flex flex-1 flex-col justify-center py-10">
            <div className="mx-auto flex w-full max-w-[1040px] flex-col items-center text-center">
              <div className="flex size-24 items-center justify-center rounded-[18px] border border-white/10 bg-white/4 shadow-[0_24px_80px_rgba(0,0,0,0.38)]">
                <Bot className="size-11 text-[#d9b15f]" />
              </div>
              <h1 className="mt-10 max-w-4xl text-balance text-[clamp(3.2rem,6vw,5.4rem)] font-semibold leading-[0.92] tracking-[-0.05em] text-slate-100">
                AutoBot builds the workspace around the robot, not around a dashboard.
              </h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-400">
                Describe the task. The app will synthesize candidates, surface approval checkpoints, and stage export-ready artifacts for review.
              </p>

              <div className="autobot-panel mt-12 w-full px-5 py-5 text-left">
                <label className="autobot-label flex items-center gap-2">
                  <Sparkles className="size-4 text-[#79d165]" />
                  Active prompt
                </label>
                <Textarea
                  value={videoPrompt}
                  readOnly
                  className="mt-4 min-h-[144px] resize-none border-0 bg-transparent px-0 py-0 text-lg text-slate-100 shadow-none focus-visible:ring-0"
                />
                <div className="mt-4 flex items-center justify-end">
                  <Button
                    size="lg"
                    className="h-11 bg-[#d9b15f] px-5 text-[#0a0d10] hover:bg-[#e7c57c]"
                  >
                    Build workspace
                    <ArrowRight className="size-4" />
                  </Button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
