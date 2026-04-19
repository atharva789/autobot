"use client";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { RobotDesignCandidate, FallbackRanking, BOMOutput } from "@/lib/types";
import { api } from "@/lib/api";

interface DesignSelectorProps {
  candidates: RobotDesignCandidate[];
  designIds: Record<"A" | "B" | "C", string>;
  modelPreferredId: "A" | "B" | "C";
  rankings: FallbackRanking[];
  onSelect: (designId: string, candidateId: "A" | "B" | "C") => void;
  disabled?: boolean;
  initialSelectedId?: "A" | "B" | "C" | null;
}

function ScoreBar({ score, label }: { score: number; label: string }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-zinc-400">{label}</span>
      <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-blue-500 to-emerald-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right text-zinc-300">{pct}%</span>
    </div>
  );
}

function DesignCard({
  candidate,
  ranking,
  isModelPreferred,
  isSelected,
  onSelect,
  onViewBom,
  disabled,
  index,
}: {
  candidate: RobotDesignCandidate;
  ranking: FallbackRanking | undefined;
  isModelPreferred: boolean;
  isSelected: boolean;
  onSelect: () => void;
  onViewBom: () => void;
  disabled?: boolean;
  index: number;
}) {
  return (
    <div
      className={`tile-glow rounded-xl p-5 cursor-pointer transition-all duration-300 animate-cascade-in hover:scale-[1.02] ${
        isSelected
          ? "ring-2 ring-emerald-500 border-emerald-500/50"
          : isModelPreferred
          ? "ring-1 ring-blue-500/50"
          : ""
      }`}
      style={{ animationDelay: `${index * 0.1}s` }}
      onClick={disabled ? undefined : onSelect}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-zinc-100">
            Design {candidate.candidate_id}
          </span>
          {isModelPreferred && (
            <Badge variant="secondary" className="bg-blue-600 text-white">
              AI Recommended
            </Badge>
          )}
          {isSelected && (
            <Badge variant="secondary" className="bg-emerald-600 text-white">
              Selected
            </Badge>
          )}
        </div>
        <Badge variant="outline" className="text-zinc-300">
          {candidate.embodiment_class}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm mb-3">
        <div className="text-zinc-400">
          Legs: <span className="text-zinc-200">{candidate.num_legs}</span>
        </div>
        <div className="text-zinc-400">
          Arms: <span className="text-zinc-200">{candidate.num_arms}</span>
        </div>
        <div className="text-zinc-400">
          Mass: <span className="text-zinc-200">{candidate.total_mass_kg}kg</span>
        </div>
        <div className="text-zinc-400">
          DOF:{" "}
          <span className="text-zinc-200">
            {candidate.num_legs * candidate.leg_dof +
              candidate.num_arms * candidate.arm_dof +
              candidate.spine_dof}
          </span>
        </div>
      </div>

      <p className="text-xs text-zinc-400 mb-3 line-clamp-2">{candidate.rationale}</p>

      {ranking && (
        <div className="space-y-1.5 mb-3">
          <ScoreBar score={ranking.kinematic_feasibility} label="Kinematic" />
          <ScoreBar score={ranking.static_stability} label="Stability" />
          <ScoreBar score={ranking.retargetability} label="Retarget" />
          <ScoreBar score={ranking.bom_confidence} label="BOM Ready" />
        </div>
      )}

      <div className="flex gap-2">
        <Button
          size="sm"
          variant={isSelected ? "default" : "outline"}
          onClick={(e) => {
            e.stopPropagation();
            onSelect();
          }}
          disabled={disabled}
          className={`flex-1 transition-all ${isSelected ? "bg-emerald-600 hover:bg-emerald-500" : ""}`}
        >
          {isSelected ? "Selected" : "Select"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={(e) => {
            e.stopPropagation();
            onViewBom();
          }}
          className="text-zinc-400 hover:text-zinc-200"
        >
          View BOM
        </Button>
      </div>
    </div>
  );
}

function BomModal({
  bom,
  onClose,
}: {
  bom: BOMOutput | null;
  onClose: () => void;
}) {
  if (!bom) return null;

  return (
    <div className="fixed inset-0 bg-zinc-950/90 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-scale-in">
      <div className="tile-glow rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-auto p-6">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xl font-semibold text-zinc-100 flex items-center gap-2">
            <span className="w-2 h-2 bg-emerald-500 rounded-full" />
            BOM - Design {bom.candidate_id}
          </h3>
          <Button variant="ghost" size="sm" onClick={onClose} className="text-zinc-400 hover:text-zinc-200">
            Close
          </Button>
        </div>

        <div className="space-y-4">
          <div className="flex gap-4 text-sm">
            <div className="text-zinc-400">
              Confidence:{" "}
              <span className="text-emerald-400">
                {Math.round(bom.procurement_confidence * 100)}%
              </span>
            </div>
            {bom.total_cost_usd && (
              <div className="text-zinc-400">
                Est. Cost:{" "}
                <span className="text-zinc-100">
                  ${bom.total_cost_usd.toFixed(2)}
                </span>
              </div>
            )}
          </div>

          {bom.missing_items.length > 0 && (
            <div className="bg-amber-950/30 border border-amber-700/50 rounded p-3">
              <div className="text-amber-400 text-sm font-medium mb-1">
                Needs Manual Review
              </div>
              <ul className="text-amber-300/80 text-xs list-disc list-inside">
                {bom.missing_items.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          <BomSection title="Actuators" items={bom.actuator_items} />
          <BomSection title="Structural" items={bom.structural_items} />
          <BomSection title="Electronics" items={bom.electronics_items} />
          <BomSection title="Fasteners" items={bom.fastener_items} />
        </div>
      </div>
    </div>
  );
}

function BomSection({
  title,
  items,
}: {
  title: string;
  items: BOMOutput["actuator_items"];
}) {
  if (items.length === 0) return null;

  return (
    <div className="animate-cascade-in">
      <h4 className="text-sm font-medium text-zinc-300 mb-2 flex items-center gap-2">
        <span className="w-1.5 h-1.5 bg-zinc-500 rounded-full" />
        {title}
      </h4>
      <div className="bg-zinc-900/50 rounded-lg overflow-hidden border border-zinc-800/50">
        <table className="w-full text-xs">
          <thead className="bg-zinc-800/50">
            <tr className="text-zinc-400">
              <th className="text-left p-3">Part</th>
              <th className="text-left p-3">Qty</th>
              <th className="text-left p-3">Vendor</th>
              <th className="text-right p-3">Cost</th>
            </tr>
          </thead>
          <tbody className="text-zinc-300">
            {items.map((item, i) => (
              <tr key={i} className="border-t border-zinc-800/30 hover:bg-zinc-800/30 transition-colors">
                <td className="p-3">{item.part_name}</td>
                <td className="p-3">{item.quantity}</td>
                <td className="p-3 text-zinc-500">{item.vendor ?? "-"}</td>
                <td className="p-3 text-right">
                  {item.unit_price_usd ? `$${item.unit_price_usd.toFixed(2)}` : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function DesignSelector({
  candidates,
  designIds,
  modelPreferredId,
  rankings,
  onSelect,
  disabled,
  initialSelectedId = null,
}: DesignSelectorProps) {
  const [selectedId, setSelectedId] = useState<"A" | "B" | "C" | null>(initialSelectedId);
  const [bomData, setBomData] = useState<BOMOutput | null>(null);
  const [bomLoading, setBomLoading] = useState(false);

  async function handleViewBom(candidateId: "A" | "B" | "C") {
    setBomLoading(true);
    try {
      const bom = await api.designs.getBom(designIds[candidateId]);
      setBomData(bom);
    } catch (err) {
      console.error("Failed to load BOM:", err);
    } finally {
      setBomLoading(false);
    }
  }

  function handleSelect(candidateId: "A" | "B" | "C") {
    setSelectedId(candidateId);
    onSelect(designIds[candidateId], candidateId);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-zinc-100">
          Robot Design Candidates
        </h2>
        <Badge variant="outline" className="text-zinc-400">
          {selectedId ? `Design ${selectedId} selected` : "Select a design"}
        </Badge>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {candidates.map((candidate, index) => {
          const ranking = rankings.find(
            (r) => r.candidate_id === candidate.candidate_id
          );
          return (
            <DesignCard
              key={candidate.candidate_id}
              candidate={candidate}
              ranking={ranking}
              isModelPreferred={candidate.candidate_id === modelPreferredId}
              isSelected={selectedId === candidate.candidate_id}
              onSelect={() => handleSelect(candidate.candidate_id)}
              onViewBom={() => handleViewBom(candidate.candidate_id)}
              disabled={disabled || bomLoading}
              index={index}
            />
          );
        })}
      </div>

      <BomModal bom={bomData} onClose={() => setBomData(null)} />
    </div>
  );
}
