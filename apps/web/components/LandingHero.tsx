"use client";

import { Bot } from "lucide-react";

interface LandingHeroProps {
  onGetStarted?: () => void;
  projectName?: string;
  activeCount?: number;
  waitingCount?: number;
}

export function LandingHero({
  onGetStarted,
  projectName = "orchard_01",
  activeCount = 0,
  waitingCount = 0,
}: LandingHeroProps) {
  return (
    <div className="relative flex min-h-screen flex-col bg-black">
      <header className="flex items-center justify-between border-b border-white/5 px-6 py-4">
        <div className="flex items-center gap-2 text-sm">
          <Bot className="h-4 w-4 text-amber-400" />
          <span className="font-medium text-white">AutoBot</span>
          <span className="text-white/30">/</span>
          <span className="text-white/60">{projectName}</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-white/50">
          {activeCount > 0 && <span>{activeCount} active</span>}
          {waitingCount > 0 && <span>{waitingCount} waiting</span>}
          <span className="font-mono text-white/30">AV</span>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6">
        <div className="flex h-20 w-20 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
          <Bot className="h-10 w-10 text-amber-400" />
        </div>

        <h1 className="mt-12 max-w-4xl text-center font-serif text-5xl font-bold leading-[1.1] tracking-tight text-white md:text-6xl lg:text-7xl">
          AutoBot builds the workspace around the robot, not around a dashboard.
        </h1>

        <p className="mt-8 max-w-2xl text-center text-lg text-white/50">
          Describe the task. The app will synthesize candidates, surface approval
          checkpoints, and stage export-ready artifacts for review.
        </p>

        {onGetStarted && (
          <button
            onClick={onGetStarted}
            className="mt-12 rounded-lg bg-white px-8 py-3 text-sm font-medium text-black transition-all hover:bg-white/90"
          >
            Get Started
          </button>
        )}
      </main>

      <footer className="border-t border-white/5 px-6 py-4 text-center text-xs text-white/30">
        Task-conditioned robot design with recursive component generation
      </footer>
    </div>
  );
}
