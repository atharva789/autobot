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
