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
