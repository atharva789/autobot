"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AnimatePresence,
  LayoutGroup,
  motion,
  useMotionValue,
  useMotionTemplate,
  useTransform,
} from "motion/react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Component,
  Expand,
  LoaderCircle,
  MoveRight,
  Orbit,
  Package2,
  ScanSearch,
  Sparkles,
  Workflow,
} from "lucide-react";

import { RobotGlyph } from "@/components/RobotGlyph";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type {
  BOMOutput,
  Er16Plan,
  FallbackRanking,
  GenerateDesignsResponse,
  RobotDesignCandidate,
} from "@/lib/types";

type WorkspaceStage = "prompt" | "candidates" | "detail";
type DetailViewMode = "concept" | "wireframe" | "joints" | "components";

const EXAMPLE_PROMPTS = [
  "carry a storage bin up one flight of stairs",
  "lift a box from the floor onto a waist-height shelf",
  "traverse a warehouse aisle while balancing a crate",
];

const ACTIVITY_STEPS = [
  "Parsing task description",
  "Extracting design constraints",
  "Searching human reference motion",
  "Building morphology graph",
  "Validating kinematic tree",
  "Matching standard components",
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function topologyLabel(candidate: RobotDesignCandidate) {
  const parts = [
    candidate.embodiment_class,
    `${candidate.num_legs}L`,
    `${candidate.num_arms}A`,
    `${candidate.spine_dof}S`,
  ];
  return parts.join(" · ");
}

function CandidateMetrics({
  ranking,
}: {
  ranking?: FallbackRanking;
}) {
  if (!ranking) return null;

  const items = [
    { label: "Feasibility", value: ranking.kinematic_feasibility },
    { label: "Complexity", value: 1 - ranking.static_stability * 0.45 },
    { label: "Parts", value: ranking.bom_confidence },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-[11px] text-slate-300"
        >
          <span className="text-slate-500">{item.label}</span>{" "}
          <span className="text-slate-100">{Math.round(item.value * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

function ActivityRail({
  steps,
  visibleCount,
  expanded,
  onToggle,
}: {
  steps: string[];
  visibleCount: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <motion.aside
      layout
      className="studio-panel flex h-full min-h-[520px] flex-col gap-5 overflow-hidden px-4 py-5"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500">Activity</p>
          <h3 className="mt-1 text-sm font-medium text-slate-100">Synthesis stream</h3>
        </div>
        <Button variant="ghost" size="icon-sm" onClick={onToggle}>
          <Expand className="size-4" />
        </Button>
      </div>
      <div className="flex flex-1 flex-col gap-3">
        {steps.map((step, index) => {
          const active = index < visibleCount;
          return (
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: active ? 1 : 0.25, x: 0 }}
              transition={{ duration: 0.28, delay: active ? 0.03 * index : 0 }}
              className="flex items-start gap-3"
            >
              <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/8 bg-white/6">
                {active ? (
                  index === visibleCount - 1 ? (
                    <LoaderCircle className="size-3.5 animate-spin text-[#f7b267]" />
                  ) : (
                    <CheckCircle2 className="size-3.5 text-[#5dd6c0]" />
                  )
                ) : (
                  <CircleDashed className="size-3.5 text-slate-500" />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-sm text-slate-200">{step}</p>
                {expanded && (
                  <p className="mt-1 text-xs text-slate-500">
                    {active
                      ? "Streamed from the live design pipeline."
                      : "Queued for this generation pass."}
                  </p>
                )}
              </div>
            </motion.div>
          );
        })}
      </div>
    </motion.aside>
  );
}

function InteractiveCanvas({
  candidate,
  mode,
}: {
  candidate: RobotDesignCandidate;
  mode: DetailViewMode;
}) {
  const [dragging, setDragging] = useState(false);
  const [lastPoint, setLastPoint] = useState<{ x: number; y: number } | null>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const scale = useMotionValue(1);
  const backgroundGlow = useTransform(scale, [0.8, 1.8], [0.08, 0.16]);
  const background = useMotionTemplate`radial-gradient(circle at 50% 50%, rgba(247,178,103,${backgroundGlow}) 0%, rgba(8,17,25,0) 55%)`;

  return (
    <div
      className="relative h-[72vh] min-h-[620px] overflow-hidden rounded-[32px] border border-white/8 bg-[#081119]"
      onPointerDown={(event) => {
        setDragging(true);
        setLastPoint({ x: event.clientX, y: event.clientY });
      }}
      onPointerMove={(event) => {
        if (!dragging || !lastPoint) return;
        x.set(x.get() + (event.clientX - lastPoint.x));
        y.set(y.get() + (event.clientY - lastPoint.y));
        setLastPoint({ x: event.clientX, y: event.clientY });
      }}
      onPointerUp={() => {
        setDragging(false);
        setLastPoint(null);
      }}
      onPointerLeave={() => {
        setDragging(false);
        setLastPoint(null);
      }}
      onWheel={(event) => {
        event.preventDefault();
        const next = Math.max(0.8, Math.min(1.9, scale.get() - event.deltaY * 0.0012));
        scale.set(next);
      }}
    >
      <motion.div
        className="absolute inset-0"
        style={{ background }}
      />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(148,163,184,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.08)_1px,transparent_1px)] bg-[size:56px_56px]" />
      <motion.div
        className="absolute inset-0 flex items-center justify-center"
        style={{ x, y, scale }}
      >
        <motion.div
          layoutId={`candidate-preview-${candidate.candidate_id}`}
          className="h-[82%] w-[82%]"
        >
          <RobotGlyph candidate={candidate} mode={mode} className="h-full w-full" />
        </motion.div>
      </motion.div>
      <div className="pointer-events-none absolute bottom-5 left-5 rounded-full border border-white/8 bg-black/25 px-4 py-2 text-xs text-slate-300">
        Drag to pan • Scroll to zoom
      </div>
    </div>
  );
}

function CandidateCard({
  candidate,
  ranking,
  selected,
  preferred,
  unresolved,
  onSelect,
}: {
  candidate?: RobotDesignCandidate;
  ranking?: FallbackRanking;
  selected: boolean;
  preferred: boolean;
  unresolved: boolean;
  onSelect: () => void;
}) {
  return (
    <motion.button
      layout
      disabled={unresolved}
      onClick={onSelect}
      className={`studio-panel group relative flex h-[430px] flex-col overflow-hidden text-left transition-transform duration-300 ${unresolved ? "cursor-default" : "hover:-translate-y-1"} ${selected ? "ring-2 ring-[#f7b267]" : ""}`}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(93,214,192,0.08),transparent_45%),radial-gradient(circle_at_bottom,rgba(247,178,103,0.08),transparent_45%)]" />
      <div className="relative flex items-center justify-between px-5 pt-5">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500">
            {candidate ? `Model ${candidate.candidate_id}` : "Resolving"}
          </p>
          <h3 className="mt-2 text-2xl font-semibold text-slate-100">
            {candidate ? `Model ${candidate.candidate_id}` : "Synthesizing"}
          </h3>
        </div>
        {preferred && !unresolved ? (
          <div className="rounded-full border border-[#f7b267]/40 bg-[#f7b267]/12 px-3 py-1 text-[11px] text-[#f4d5ab]">
            Model preferred
          </div>
        ) : null}
      </div>

      <div className="relative mt-4 flex-1 px-5">
        <div className="absolute inset-x-5 top-0 bottom-0 rounded-[28px] border border-white/8 bg-[#081119]/80">
          {unresolved ? (
            <div className="flex h-full items-center justify-center">
              <div className="h-28 w-28 rounded-full border border-white/10 bg-white/4 p-4">
                <div className="h-full w-full animate-pulse rounded-full border border-dashed border-[#f7b267]/50" />
              </div>
            </div>
          ) : candidate ? (
            <motion.div
              layoutId={`candidate-preview-${candidate.candidate_id}`}
              className="h-full w-full p-6"
            >
              <RobotGlyph candidate={candidate} mode="concept" className="h-full w-full" />
            </motion.div>
          ) : null}
        </div>
      </div>

      <div className="relative flex flex-col gap-3 px-5 pb-5">
        {candidate ? (
          <>
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-300">{topologyLabel(candidate)}</span>
              <span className="text-sm text-slate-500">{candidate.actuator_class}</span>
            </div>
            <p className="line-clamp-2 text-sm text-slate-400">{candidate.rationale}</p>
            <CandidateMetrics ranking={ranking} />
          </>
        ) : (
          <div className="space-y-2">
            <div className="h-3 w-28 animate-pulse rounded-full bg-white/8" />
            <div className="h-3 w-3/4 animate-pulse rounded-full bg-white/8" />
            <div className="h-3 w-1/2 animate-pulse rounded-full bg-white/8" />
          </div>
        )}
      </div>
    </motion.button>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [stage, setStage] = useState<WorkspaceStage>("prompt");
  const [prompt, setPrompt] = useState("");
  const [activePrompt, setActivePrompt] = useState("");
  const [plan, setPlan] = useState<Er16Plan | null>(null);
  const [ingestJobId, setIngestJobId] = useState<string | null>(null);
  const [designs, setDesigns] = useState<GenerateDesignsResponse | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<"A" | "B" | "C" | null>(null);
  const [selectedDesignId, setSelectedDesignId] = useState<string | null>(null);
  const [bom, setBom] = useState<BOMOutput | null>(null);
  const [bomLoading, setBomLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activityExpanded, setActivityExpanded] = useState(false);
  const [visibleActivities, setVisibleActivities] = useState(0);
  const [resolvedCandidates, setResolvedCandidates] = useState(0);
  const [detailMode, setDetailMode] = useState<DetailViewMode>("concept");
  const [submitting, setSubmitting] = useState(false);
  const [continuing, setContinuing] = useState(false);

  useEffect(() => {
    if (stage === "prompt") {
      setVisibleActivities(0);
      return;
    }
    if (visibleActivities >= ACTIVITY_STEPS.length) return;
    const timer = window.setTimeout(
      () => setVisibleActivities((current) => Math.min(current + 1, ACTIVITY_STEPS.length)),
      stage === "detail" ? 120 : 260,
    );
    return () => window.clearTimeout(timer);
  }, [stage, visibleActivities]);

  useEffect(() => {
    if (!designs) {
      setResolvedCandidates(0);
      return;
    }
    if (resolvedCandidates >= designs.candidates.length) return;
    const timer = window.setTimeout(
      () => setResolvedCandidates((current) => current + 1),
      240,
    );
    return () => window.clearTimeout(timer);
  }, [designs, resolvedCandidates]);

  const selectedCandidate = useMemo(
    () => designs?.candidates.find((candidate) => candidate.candidate_id === selectedCandidateId) ?? null,
    [designs, selectedCandidateId],
  );

  const rankingMap = useMemo(() => {
    const entries = designs?.fallback_rankings ?? [];
    return new Map(entries.map((entry) => [entry.candidate_id, entry]));
  }, [designs]);

  async function handleSubmitPrompt(nextPrompt?: string) {
    const resolvedPrompt = (nextPrompt ?? prompt).trim();
    if (!resolvedPrompt) return;

    setSubmitting(true);
    setError(null);
    setStage("candidates");
    setActivePrompt(resolvedPrompt);
    setPlan(null);
    setDesigns(null);
    setSelectedCandidateId(null);
    setSelectedDesignId(null);
    setBom(null);

    try {
      const ingest = await api.ingest.start(resolvedPrompt);
      setPlan(ingest.er16_plan);
      setIngestJobId(ingest.job_id);
      await sleep(180);
      const generated = await api.designs.generate(ingest.job_id);
      setDesigns(generated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to assemble the design workspace.");
    } finally {
      setSubmitting(false);
    }
  }

  async function enterDetail(candidateId: "A" | "B" | "C") {
    if (!designs) return;
    const designId = designs.design_ids[candidateId];
    setSelectedCandidateId(candidateId);
    setSelectedDesignId(designId);
    setStage("detail");
    setBomLoading(true);
    setBom(null);
    try {
      const nextBom = await api.designs.getBom(designId);
      setBom(nextBom);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load the bill of materials.");
    } finally {
      setBomLoading(false);
    }
  }

  async function continueToProgram() {
    if (!selectedDesignId || !ingestJobId || !selectedCandidateId) return;
    setContinuing(true);
    setError(null);
    try {
      const evolution = await api.evolutions.create(`workspace-${Date.now()}`, ingestJobId);
      await api.designs.select(selectedDesignId, evolution.evolution_id);
      router.push(
        `/evolutions/${evolution.evolution_id}/program?draft=${encodeURIComponent(
          evolution.draft_content,
        )}&design=${selectedCandidateId}`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to open the program draft.");
    } finally {
      setContinuing(false);
    }
  }

  return (
    <LayoutGroup>
      <main className="studio-root min-h-screen overflow-hidden px-6 py-6 text-slate-100 md:px-8">
        <div className="studio-noise pointer-events-none absolute inset-0" />

        <motion.div layout className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-[1600px] flex-col">
          <motion.header layout className="mb-6 flex items-start justify-between gap-6">
            <motion.div layout className="flex items-center gap-4">
              <motion.div
                layoutId="brand-mark"
                className="flex h-14 w-14 items-center justify-center rounded-[18px] border border-white/10 bg-white/6 shadow-[0_12px_60px_rgba(0,0,0,0.3)]"
              >
                <Workflow className="size-6 text-[#f7b267]" />
              </motion.div>
              <div>
                <motion.h1
                  layoutId="brand-title"
                  className="font-mono text-lg uppercase tracking-[0.28em] text-slate-200"
                >
                  Morphology Studio
                </motion.h1>
                <p className="mt-1 text-sm text-slate-500">
                  Live robot concept synthesis with streamed design activity.
                </p>
              </div>
            </motion.div>

            {stage === "detail" ? (
              <motion.div
                layout
                className="flex items-center gap-3 rounded-full border border-white/8 bg-white/6 px-3 py-2"
              >
                <Button variant="ghost" size="sm" onClick={() => setStage("candidates")}>
                  <ArrowLeft className="size-4" />
                  Back
                </Button>
                <div className="hidden h-5 w-px bg-white/8 md:block" />
                <span className="hidden text-sm text-slate-400 md:block">Design review</span>
                <Button variant="outline" size="sm" disabled>
                  Export
                </Button>
              </motion.div>
            ) : null}
          </motion.header>

          <AnimatePresence mode="wait">
            {stage === "prompt" ? (
              <motion.section
                key="prompt"
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.42, ease: "easeOut" }}
                className="flex flex-1 flex-col items-center justify-center"
              >
                <div className="mx-auto flex max-w-[980px] flex-col items-center text-center">
                  <motion.div layoutId="brand-mark" className="mb-10 flex h-24 w-24 items-center justify-center rounded-[30px] border border-white/10 bg-white/6 shadow-[0_30px_120px_rgba(0,0,0,0.35)]">
                    <Orbit className="size-11 text-[#f7b267]" />
                  </motion.div>
                  <motion.h2
                    layoutId="brand-title"
                    className="max-w-4xl text-balance text-[clamp(3rem,5vw,5.2rem)] font-semibold leading-[0.95] tracking-[-0.04em] text-[#f4efe7]"
                  >
                    Design a robot around the task, not around a dashboard.
                  </motion.h2>
                  <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-400">
                    Describe the behavior you want. The workspace will assemble itself into candidate concepts, then expand the chosen design into an inspection studio.
                  </p>

                  <motion.div
                    layoutId="prompt-shell"
                    className="mt-14 w-full rounded-[34px] border border-white/10 bg-[#0a131c]/80 p-4 shadow-[0_30px_120px_rgba(0,0,0,0.35)] backdrop-blur-xl"
                  >
                    <div className="flex flex-col gap-4">
                      <Textarea
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value)}
                        placeholder='Describe the task, e.g. "carry a storage bin up a staircase with both hands."'
                        className="min-h-[132px] resize-none border-0 bg-transparent px-2 py-3 text-lg text-slate-100 shadow-none focus-visible:ring-0"
                      />
                      <div className="flex items-center justify-between gap-4">
                        <div className="flex flex-wrap gap-2">
                          {EXAMPLE_PROMPTS.map((example) => (
                            <button
                              key={example}
                              onClick={() => setPrompt(example)}
                              className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-400 transition hover:bg-white/10 hover:text-slate-200"
                            >
                              {example}
                            </button>
                          ))}
                        </div>
                        <Button
                          size="lg"
                          onClick={() => handleSubmitPrompt()}
                          disabled={submitting || !prompt.trim()}
                          className="h-14 rounded-full bg-[#f7b267] px-6 text-sm font-semibold text-[#091017] hover:bg-[#ffd1a0]"
                        >
                          {submitting ? (
                            <>
                              <LoaderCircle className="size-4 animate-spin" />
                              Building workspace
                            </>
                          ) : (
                            <>
                              Start synthesis
                              <MoveRight className="size-4" />
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                  </motion.div>
                </div>
              </motion.section>
            ) : null}

            {stage === "candidates" ? (
              <motion.section
                key="candidates"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.36 }}
                className="flex flex-1 flex-col"
              >
                <motion.div layoutId="prompt-shell" className="studio-panel mb-6 flex items-center gap-4 px-5 py-4">
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/8 bg-white/6">
                    <ScanSearch className="size-5 text-[#f7b267]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500">Active task</p>
                    <p className="truncate text-base text-slate-100">{activePrompt}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setStage("prompt")}>
                    Edit prompt
                  </Button>
                </motion.div>

                <div className="mb-6 flex flex-wrap gap-2">
                  {(plan?.affordances ?? ["payload handling", "stair traversal", "human-scale reach"]).slice(0, 6).map((chip) => (
                    <span key={chip} className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-slate-300">
                      {chip}
                    </span>
                  ))}
                </div>

                <div className="grid flex-1 grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(260px,320px)]">
                  <div className="grid min-h-[560px] grid-cols-1 gap-5 xl:grid-cols-3">
                    {["A", "B", "C"].map((candidateId, index) => {
                      const candidate = designs?.candidates.find((item) => item.candidate_id === candidateId);
                      const unresolved = !candidate || index >= resolvedCandidates;
                      const ranking = candidate ? rankingMap.get(candidate.candidate_id) : undefined;
                      return (
                        <CandidateCard
                          key={candidateId}
                          candidate={unresolved ? undefined : candidate}
                          ranking={ranking}
                          unresolved={unresolved}
                          selected={false}
                          preferred={designs?.model_preferred_id === candidateId}
                          onSelect={() => candidate && enterDetail(candidate.candidate_id)}
                        />
                      );
                    })}
                  </div>

                  <ActivityRail
                    steps={ACTIVITY_STEPS}
                    visibleCount={visibleActivities}
                    expanded={activityExpanded}
                    onToggle={() => setActivityExpanded((current) => !current)}
                  />
                </div>

                <motion.div
                  layoutId="commit-zone"
                  className="studio-panel mt-6 flex flex-wrap items-center justify-between gap-4 px-5 py-4"
                >
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500">Commitment zone</p>
                    <p className="mt-1 text-sm text-slate-300">
                      Choose a concept to open the inspection studio.
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    {["A", "B", "C"].map((candidateId) => (
                      <Button
                        key={candidateId}
                        variant={designs?.model_preferred_id === candidateId ? "default" : "outline"}
                        className={
                          designs?.model_preferred_id === candidateId
                            ? "bg-[#f7b267] text-[#091017] hover:bg-[#ffd1a0]"
                            : "border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
                        }
                        disabled={!designs}
                        onClick={() => designs && enterDetail(candidateId as "A" | "B" | "C")}
                      >
                        Inspect Model {candidateId}
                        <ChevronRight className="size-4" />
                      </Button>
                    ))}
                  </div>
                </motion.div>
              </motion.section>
            ) : null}

            {stage === "detail" && selectedCandidate ? (
              <motion.section
                key="detail"
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.34 }}
                className="flex flex-1 flex-col"
              >
                <motion.div layoutId="prompt-shell" className="studio-panel mb-6 flex items-center gap-4 px-5 py-4">
                  <Button variant="ghost" size="sm" onClick={() => setStage("candidates")}>
                    <ArrowLeft className="size-4" />
                    Concepts
                  </Button>
                  <div className="h-8 w-px bg-white/8" />
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500">Project</p>
                    <p className="text-base text-slate-100">
                      {activePrompt} · Model {selectedCandidate.candidate_id}
                    </p>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    <span className="rounded-full border border-white/8 bg-white/6 px-3 py-1 text-xs text-slate-300">
                      {topologyLabel(selectedCandidate)}
                    </span>
                    <Button
                      size="sm"
                      onClick={continueToProgram}
                      disabled={continuing}
                      className="bg-[#f7b267] text-[#091017] hover:bg-[#ffd1a0]"
                    >
                      {continuing ? (
                        <>
                          <LoaderCircle className="size-4 animate-spin" />
                          Opening draft
                        </>
                      ) : (
                        <>
                          Continue
                          <ArrowRight className="size-4" />
                        </>
                      )}
                    </Button>
                  </div>
                </motion.div>

                <div className="grid flex-1 grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <InteractiveCanvas candidate={selectedCandidate} mode={detailMode} />

                  <motion.aside layout className="studio-panel flex flex-col gap-4 px-5 py-5">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-[10px] uppercase tracking-[0.28em] text-slate-500">Inspector</p>
                        <h3 className="mt-1 text-lg font-medium text-slate-100">
                          Model {selectedCandidate.candidate_id}
                        </h3>
                      </div>
                      <span className="rounded-full border border-[#f7b267]/35 bg-[#f7b267]/10 px-3 py-1 text-xs text-[#f4d5ab]">
                        preferred {Math.round(selectedCandidate.confidence * 100)}%
                      </span>
                    </div>

                    <motion.div layoutId="commit-zone" className="rounded-[24px] border border-white/8 bg-white/5 p-3">
                      <p className="mb-3 text-[10px] uppercase tracking-[0.28em] text-slate-500">View mode</p>
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          { id: "concept", label: "Concept", icon: Sparkles },
                          { id: "wireframe", label: "Wireframe", icon: CircleDashed },
                          { id: "joints", label: "Joints", icon: Orbit },
                          { id: "components", label: "Components", icon: Component },
                        ].map((mode) => (
                          <Button
                            key={mode.id}
                            variant={detailMode === mode.id ? "default" : "outline"}
                            className={
                              detailMode === mode.id
                                ? "bg-[#f7b267] text-[#091017] hover:bg-[#ffd1a0]"
                                : "border-white/10 bg-white/5 text-slate-200 hover:bg-white/10"
                            }
                            onClick={() => setDetailMode(mode.id as DetailViewMode)}
                          >
                            <mode.icon className="size-4" />
                            {mode.label}
                          </Button>
                        ))}
                      </div>
                    </motion.div>

                    <details open className="studio-detail">
                      <summary>Overview</summary>
                      <p>{selectedCandidate.rationale}</p>
                    </details>
                    <details open className="studio-detail">
                      <summary>Why this design</summary>
                      <p>
                        {designs?.selection_rationale ??
                          "Selected because it balances task coverage, kinematics, and procurement confidence."}
                      </p>
                    </details>
                    <details open className="studio-detail">
                      <summary>Task coverage</summary>
                      <ul>
                        <li>Payload capacity: {selectedCandidate.payload_capacity_kg} kg</li>
                        <li>Actuator class: {selectedCandidate.actuator_class}</li>
                        <li>Sensor package: {selectedCandidate.sensor_package.join(", ") || "none"}</li>
                      </ul>
                    </details>
                    <details className="studio-detail">
                      <summary>Kinematics</summary>
                      <ul>
                        <li>Legs: {selectedCandidate.num_legs} × {selectedCandidate.leg_dof} DOF</li>
                        <li>Arms: {selectedCandidate.num_arms} × {selectedCandidate.arm_dof} DOF</li>
                        <li>Spine: {selectedCandidate.spine_dof} DOF</li>
                      </ul>
                    </details>
                    <details className="studio-detail">
                      <summary>Components</summary>
                      {bomLoading ? (
                        <p>Compiling bill of materials…</p>
                      ) : bom ? (
                        <ul>
                          <li>{bom.actuator_items.length} actuator lines</li>
                          <li>{bom.structural_items.length} structural lines</li>
                          <li>{bom.electronics_items.length} electronics lines</li>
                          <li>Procurement confidence: {Math.round(bom.procurement_confidence * 100)}%</li>
                        </ul>
                      ) : (
                        <p>No BOM available yet.</p>
                      )}
                    </details>
                    <details className="studio-detail">
                      <summary>Validation</summary>
                      <ul>
                        <li>
                          Fallback screening: {Math.round((rankingMap.get(selectedCandidate.candidate_id)?.total_score ?? 0) * 100)}%
                        </li>
                        <li>Retargetability: {Math.round((rankingMap.get(selectedCandidate.candidate_id)?.retargetability ?? 0) * 100)}%</li>
                        <li>Static stability: {Math.round((rankingMap.get(selectedCandidate.candidate_id)?.static_stability ?? 0) * 100)}%</li>
                      </ul>
                    </details>
                  </motion.aside>
                </div>
              </motion.section>
            ) : null}
          </AnimatePresence>

          {error ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
            >
              {error}
            </motion.div>
          ) : null}
        </motion.div>
      </main>
    </LayoutGroup>
  );
}
