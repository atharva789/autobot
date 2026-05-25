"use client";

import { useMemo, useState } from "react";
import { AlertCircle, Bot, CheckCircle2, LoaderCircle, Network, Play, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { CandidateTelemetry, GenerateDesignsResponse, IngestJob, RobotDesignCandidate } from "@/lib/types";

const DEFAULT_POPULATION = 6;

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function formatNumber(value: number, digits = 1) {
  return Number.isFinite(value) ? value.toFixed(digits) : "0.0";
}

function countDof(candidate: RobotDesignCandidate) {
  return candidate.num_legs * candidate.leg_dof + candidate.num_arms * candidate.arm_dof + candidate.spine_dof;
}

function selectedRanking(response: GenerateDesignsResponse | null, candidateId: string | null) {
  if (!response || !candidateId) return null;
  return response.fallback_rankings.find((ranking) => ranking.candidate_id === candidateId) ?? null;
}

function MorphologySketch({ candidate }: { candidate: RobotDesignCandidate | null }) {
  if (!candidate) {
    return (
      <div className="flex h-full min-h-[420px] items-center justify-center rounded-lg border border-white/8 bg-black/30 text-sm text-slate-500">
        Awaiting morphology
      </div>
    );
  }

  const bodySegments = candidate.has_torso ? Math.max(1, Math.min(7, candidate.spine_dof + 1)) : Math.max(4, Math.min(12, candidate.spine_dof));
  const bodyWidth = candidate.has_torso ? clamp(candidate.torso_length_m * 320, 120, 260) : clamp(candidate.torso_length_m * 220, 80, 190);
  const centerX = 360;
  const centerY = 210;
  const segmentGap = bodyWidth / Math.max(1, bodySegments - 1);
  const segmentStart = centerX - bodyWidth / 2;
  const legPairs = Math.ceil(candidate.num_legs / 2);
  const armPairs = Math.ceil(candidate.num_arms / 2);
  const legLength = clamp(candidate.leg_length_m * 220, 55, 130);
  const armLength = clamp(candidate.arm_length_m * 180, 45, 105);
  const segmentPoints = Array.from({ length: bodySegments }, (_, index) => ({
    x: segmentStart + index * segmentGap,
    y: centerY + Math.sin(index * 0.9) * (candidate.has_torso ? 4 : 18),
  }));

  return (
    <svg viewBox="0 0 720 420" role="img" aria-label={`Simple ${candidate.embodiment_class} morphology sketch`} className="h-full min-h-[420px] w-full rounded-lg border border-white/8 bg-[#080b0e]">
      <defs>
        <linearGradient id="body-gradient" x1="0" x2="1">
          <stop offset="0%" stopColor="#e7c57c" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#79d165" stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="718" height="418" rx="8" fill="none" stroke="rgba(255,255,255,0.05)" />
      {Array.from({ length: 13 }, (_, index) => (
        <line key={`grid-x-${index}`} x1={40 + index * 54} x2={40 + index * 54} y1="36" y2="384" stroke="rgba(255,255,255,0.035)" />
      ))}
      {Array.from({ length: 7 }, (_, index) => (
        <line key={`grid-y-${index}`} x1="40" x2="680" y1={60 + index * 48} y2={60 + index * 48} stroke="rgba(255,255,255,0.035)" />
      ))}

      <polyline
        points={segmentPoints.map((point) => `${point.x},${point.y}`).join(" ")}
        fill="none"
        stroke="url(#body-gradient)"
        strokeWidth={candidate.has_torso ? 18 : 14}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {segmentPoints.map((point, index) => (
        <circle key={`segment-${index}`} cx={point.x} cy={point.y} r={candidate.has_torso ? 14 : 12} fill="#10161a" stroke="#d9b15f" strokeWidth="2" />
      ))}

      {Array.from({ length: legPairs }, (_, pairIndex) => {
        const anchor = segmentPoints[Math.floor(((pairIndex + 0.5) / Math.max(1, legPairs)) * segmentPoints.length)] ?? segmentPoints[0];
        const spread = 34 + pairIndex * 2;
        return (
          <g key={`leg-pair-${pairIndex}`}>
            <line x1={anchor.x} y1={anchor.y + 8} x2={anchor.x - spread} y2={anchor.y + legLength} stroke="#79d165" strokeWidth="5" strokeLinecap="round" />
            <line x1={anchor.x} y1={anchor.y + 8} x2={anchor.x + spread} y2={anchor.y + legLength} stroke="#79d165" strokeWidth="5" strokeLinecap="round" />
            <circle cx={anchor.x - spread} cy={anchor.y + legLength} r="7" fill="#79d165" />
            <circle cx={anchor.x + spread} cy={anchor.y + legLength} r="7" fill="#79d165" />
          </g>
        );
      })}

      {Array.from({ length: armPairs }, (_, pairIndex) => {
        const anchor = segmentPoints[Math.floor(((pairIndex + 0.5) / Math.max(1, armPairs)) * segmentPoints.length)] ?? segmentPoints[0];
        const spread = 34 + pairIndex * 2;
        return (
          <g key={`arm-pair-${pairIndex}`}>
            <line x1={anchor.x} y1={anchor.y - 8} x2={anchor.x - spread} y2={anchor.y - armLength} stroke="#7dd3fc" strokeWidth="4" strokeLinecap="round" />
            <line x1={anchor.x} y1={anchor.y - 8} x2={anchor.x + spread} y2={anchor.y - armLength} stroke="#7dd3fc" strokeWidth="4" strokeLinecap="round" />
            <circle cx={anchor.x - spread} cy={anchor.y - armLength} r="6" fill="#7dd3fc" />
            <circle cx={anchor.x + spread} cy={anchor.y - armLength} r="6" fill="#7dd3fc" />
          </g>
        );
      })}

      <text x="28" y="392" fill="#64748b" fontSize="12" fontFamily="monospace">
        {candidate.num_legs} legs / {candidate.num_arms} arms / {candidate.spine_dof} spine DoF
      </text>
    </svg>
  );
}

function CandidateCard({
  candidate,
  telemetry,
  selected,
  onSelect,
}: {
  candidate: RobotDesignCandidate;
  telemetry: CandidateTelemetry | null;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`rounded-lg border p-3 text-left transition ${
        selected ? "border-[#79d165]/70 bg-[#79d165]/10" : "border-white/8 bg-white/[0.03] hover:bg-white/[0.06]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm text-slate-100">{candidate.candidate_id}</span>
        <span className="rounded bg-black/30 px-2 py-0.5 text-[11px] text-slate-400">{candidate.embodiment_class}</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-400">
        <span>{candidate.num_legs} legs</span>
        <span>{countDof(candidate)} DoF</span>
        <span>{formatNumber(candidate.total_mass_kg)} kg</span>
        <span>{formatNumber(candidate.payload_capacity_kg)} kg payload</span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-black/40">
        <div className="h-full rounded-full bg-[#79d165]" style={{ width: `${Math.round((telemetry?.design_quality_score ?? candidate.confidence) * 100)}%` }} />
      </div>
    </button>
  );
}

function GrammarPanel({ response }: { response: GenerateDesignsResponse | null }) {
  const hitl = response?.grammar_hitl;
  const rules = Object.entries(hitl?.structural_rules ?? {});
  const criteria = hitl?.checklist.criteria ?? [];

  return (
    <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
      <div className="rounded-lg border border-white/8 bg-black/25 p-4">
        <div className="mb-3 flex items-center gap-2">
          <Network className="size-4 text-[#79d165]" />
          <h2 className="text-sm font-semibold text-slate-100">Structural Rules</h2>
          <span className={`ml-auto rounded px-2 py-0.5 text-[11px] ${hitl?.compile_safe ? "bg-green-500/10 text-green-300" : "bg-yellow-500/10 text-yellow-300"}`}>
            {hitl?.compile_safe ? "compile safe" : "pending"}
          </span>
        </div>
        <div className="max-h-[260px] overflow-auto rounded border border-white/6">
          {rules.length ? (
            rules.map(([lhs, rhs]) => (
              <div key={lhs} className="grid grid-cols-[120px_minmax(0,1fr)] border-b border-white/6 px-3 py-2 text-sm last:border-b-0">
                <span className="font-mono text-[#e7c57c]">{lhs}</span>
                <span className="font-mono text-slate-300">{rhs.join(" ")}</span>
              </div>
            ))
          ) : (
            <div className="px-3 py-8 text-center text-sm text-slate-500">No rules yet</div>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-white/8 bg-black/25 p-4">
        <h2 className="text-sm font-semibold text-slate-100">Evaluator Checklist</h2>
        <div className="mt-3 space-y-2">
          {criteria.length ? (
            criteria.map((criterion) => (
              <div key={criterion.description} className="flex gap-2 rounded border border-white/6 bg-white/[0.03] p-2">
                {criterion.isSuccessful ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[#79d165]" /> : <AlertCircle className="mt-0.5 size-4 shrink-0 text-[#e7c57c]" />}
                <div>
                  <p className="text-xs text-slate-200">{criterion.description}</p>
                  {criterion.critiques.length ? <p className="mt-1 text-[11px] text-slate-500">{criterion.critiques.join(" ")}</p> : null}
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-500">No checklist yet</p>
          )}
        </div>
      </div>
    </section>
  );
}

export default function HomePage() {
  const [prompt, setPrompt] = useState("Ice-skating robot that can skate and serve drinks on icy/slippery terrain");
  const [population, setPopulation] = useState(DEFAULT_POPULATION);
  const [ingest, setIngest] = useState<IngestJob | null>(null);
  const [response, setResponse] = useState<GenerateDesignsResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedCandidate = useMemo(
    () => response?.candidates.find((candidate) => candidate.candidate_id === selectedId) ?? response?.candidates[0] ?? null,
    [response, selectedId],
  );
  const resolvedSelectedId = selectedCandidate?.candidate_id ?? null;
  const selectedTelemetry = resolvedSelectedId ? response?.candidate_telemetry[resolvedSelectedId] ?? null : null;
  const ranking = selectedRanking(response, resolvedSelectedId);

  async function generate() {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    setSelectedId(null);
    try {
      const ingestJob = await api.ingest.start(trimmed);
      setIngest(ingestJob);
      const generated = await api.designs.generate(ingestJob.job_id, population);
      setResponse(generated);
      setSelectedId(generated.model_preferred_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to generate robot designs.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen px-5 py-5 text-slate-100 md:px-8">
      <div className="mx-auto max-w-[1500px]">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-white/8 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex size-9 items-center justify-center rounded-lg border border-white/10 bg-white/5">
              <Bot className="size-5 text-[#e7c57c]" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-normal text-slate-100">RoboGrammar Morphology Generator</h1>
              <p className="text-xs text-slate-500">Grammar rules to simple robot morphology</p>
            </div>
          </div>
          <span className="rounded border border-white/8 bg-black/25 px-3 py-1 text-xs text-slate-400">
            {response ? `${response.population} designs` : "ready"}
          </span>
        </header>

        <section className="grid gap-4 lg:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
          <aside className="rounded-lg border border-white/8 bg-black/25 p-4">
            <label className="text-xs uppercase tracking-[0.16em] text-slate-500">Prompt</label>
            <Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} className="mt-2 min-h-[132px] resize-none bg-black/30 text-slate-100" />

            <div className="mt-4 flex items-center justify-between rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2">
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <SlidersHorizontal className="size-4 text-slate-500" />
                Population
              </div>
              <input
                type="number"
                min={1}
                max={64}
                value={population}
                onChange={(event) => setPopulation(clamp(Number(event.target.value) || DEFAULT_POPULATION, 1, 64))}
                className="w-20 rounded border border-white/8 bg-black/30 px-2 py-1 text-right font-mono text-sm text-slate-100 outline-none"
              />
            </div>

            <Button onClick={generate} disabled={loading || !prompt.trim()} className="mt-4 h-10 w-full justify-between bg-[#79d165] text-[#08110b] hover:bg-[#8ee482]">
              {loading ? (
                <>
                  Generating
                  <LoaderCircle className="size-4 animate-spin" />
                </>
              ) : (
                <>
                  Generate Morphologies
                  <Play className="size-4" />
                </>
              )}
            </Button>

            {error ? (
              <div className="mt-4 rounded-lg border border-red-400/20 bg-red-500/10 p-3 text-sm text-red-100">
                {error}
              </div>
            ) : null}

            {ingest ? (
              <div className="mt-4 rounded-lg border border-white/8 bg-white/[0.03] p-3">
                <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Normalized Task</p>
                <p className="mt-2 text-sm text-slate-300">{ingest.er16_plan.task_goal}</p>
              </div>
            ) : null}

            <div className="mt-4 grid gap-2">
              {(response?.candidates ?? []).map((candidate) => (
                <CandidateCard
                  key={candidate.candidate_id}
                  candidate={candidate}
                  telemetry={response?.candidate_telemetry[candidate.candidate_id] ?? null}
                  selected={candidate.candidate_id === resolvedSelectedId}
                  onSelect={() => setSelectedId(candidate.candidate_id)}
                />
              ))}
            </div>
          </aside>

          <section className="grid gap-4">
            <div className="rounded-lg border border-white/8 bg-black/25 p-4">
              <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">Selected Morphology</p>
                  <h2 className="mt-1 text-xl font-semibold text-slate-100">
                    {selectedCandidate ? `${selectedCandidate.candidate_id} - ${selectedCandidate.embodiment_class}` : "No candidate"}
                  </h2>
                </div>
                {selectedCandidate ? (
                  <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 sm:grid-cols-4">
                    <span className="rounded border border-white/8 bg-black/30 px-3 py-2">{countDof(selectedCandidate)} DoF</span>
                    <span className="rounded border border-white/8 bg-black/30 px-3 py-2">{formatNumber(selectedCandidate.total_mass_kg)} kg</span>
                    <span className="rounded border border-white/8 bg-black/30 px-3 py-2">{formatNumber(selectedCandidate.actuator_torque_nm)} Nm</span>
                    <span className="rounded border border-white/8 bg-black/30 px-3 py-2">{Math.round((ranking?.total_score ?? selectedCandidate.confidence) * 100)} score</span>
                  </div>
                ) : null}
              </div>
              <MorphologySketch candidate={selectedCandidate} />
              {selectedCandidate ? <p className="mt-3 text-sm text-slate-400">{selectedCandidate.rationale}</p> : null}
            </div>

            <GrammarPanel response={response} />
          </section>
        </section>
      </div>
    </main>
  );
}
