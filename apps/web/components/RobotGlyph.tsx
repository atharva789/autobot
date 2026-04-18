"use client";

import { motion } from "motion/react";

import { cn } from "@/lib/utils";
import type { RobotDesignCandidate } from "@/lib/types";

type ViewMode = "concept" | "wireframe" | "joints" | "components";

interface RobotGlyphProps {
  candidate: RobotDesignCandidate;
  mode?: ViewMode;
  className?: string;
  animated?: boolean;
}

function limbAnchors(candidate: RobotDesignCandidate) {
  const torsoTop = 68;
  const torsoBottom = 136;
  const shoulderY = 82;
  const hipY = 132;
  const centerX = 120;
  const shoulderSpread = candidate.num_arms > 1 ? 34 : 0;
  const hipSpread = Math.max(18, candidate.num_legs > 2 ? 54 : 28);

  const arms = Array.from({ length: candidate.num_arms }, (_, index) => ({
    x: candidate.num_arms === 1 ? centerX + 38 : centerX + (index === 0 ? -shoulderSpread : shoulderSpread),
    y: shoulderY,
  }));

  const legs = Array.from({ length: candidate.num_legs }, (_, index) => {
    if (candidate.num_legs <= 1) return { x: centerX, y: hipY };
    const step = candidate.num_legs === 2 ? hipSpread : (hipSpread * 2) / (candidate.num_legs - 1);
    return {
      x: centerX - hipSpread + step * index,
      y: hipY,
    };
  });

  return { torsoTop, torsoBottom, centerX, arms, legs };
}

export function RobotGlyph({
  candidate,
  mode = "concept",
  className,
  animated = true,
}: RobotGlyphProps) {
  const anchors = limbAnchors(candidate);
  const stroke = mode === "wireframe" ? "#94a3b8" : "#f7b267";
  const accent = mode === "components" ? "#5dd6c0" : "#f97316";
  const fill =
    mode === "wireframe" ? "transparent" : mode === "components" ? "rgba(34, 211, 238, 0.12)" : "rgba(247, 178, 103, 0.14)";
  const torsoWidth = candidate.has_torso ? 42 + candidate.spine_dof * 6 : 20;
  const torsoHeight = candidate.has_torso ? 58 + candidate.spine_dof * 8 : 18;

  return (
    <div className={cn("relative h-full w-full", className)}>
      <svg viewBox="0 0 240 220" className="h-full w-full">
        <defs>
          <linearGradient id="glyphGlow" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f9fafb" stopOpacity="0.9" />
            <stop offset="50%" stopColor={accent} stopOpacity="0.85" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.6" />
          </linearGradient>
        </defs>

        <rect x="8" y="8" width="224" height="204" rx="28" fill="rgba(10,18,24,0.25)" stroke="rgba(148,163,184,0.08)" />
        <path d="M24 182 H216" stroke="rgba(148,163,184,0.15)" strokeDasharray="6 8" />

        <motion.g
          initial={animated ? { opacity: 0, scale: 0.92, y: 6 } : false}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
        >
          <motion.circle
            cx={anchors.centerX}
            cy={40}
            r={15}
            fill={fill}
            stroke="url(#glyphGlow)"
            strokeWidth="2.5"
          />

          <motion.rect
            x={anchors.centerX - torsoWidth / 2}
            y={anchors.torsoTop}
            width={torsoWidth}
            height={torsoHeight}
            rx={mode === "wireframe" ? 12 : 18}
            fill={fill}
            stroke="url(#glyphGlow)"
            strokeWidth="2.5"
          />

          <line
            x1={anchors.centerX}
            y1={55}
            x2={anchors.centerX}
            y2={anchors.torsoTop}
            stroke={stroke}
            strokeWidth="3"
            strokeLinecap="round"
          />

          {anchors.arms.map((arm, index) => (
            <g key={`arm-${index}`}>
              <line
                x1={anchors.centerX + (index === 0 && candidate.num_arms > 1 ? -torsoWidth / 2 + 4 : torsoWidth / 2 - 4)}
                y1={84}
                x2={arm.x}
                y2={132}
                stroke={stroke}
                strokeWidth={mode === "wireframe" ? 3 : 5}
                strokeLinecap="round"
              />
              <line
                x1={arm.x}
                y1={132}
                x2={arm.x + (index % 2 === 0 ? -10 : 10)}
                y2={176}
                stroke={mode === "components" ? accent : stroke}
                strokeWidth={mode === "wireframe" ? 3 : 5}
                strokeLinecap="round"
              />
              {(mode === "joints" || mode === "components") && (
                <>
                  <circle cx={arm.x} cy={132} r="4.5" fill={accent} />
                  <circle cx={arm.x + (index % 2 === 0 ? -10 : 10)} cy={176} r="4.5" fill={accent} />
                </>
              )}
            </g>
          ))}

          {anchors.legs.map((leg, index) => (
            <g key={`leg-${index}`}>
              <line
                x1={leg.x}
                y1={anchors.torsoBottom}
                x2={leg.x + (index % 2 === 0 ? -6 : 6)}
                y2={176}
                stroke={stroke}
                strokeWidth={mode === "wireframe" ? 3 : 5}
                strokeLinecap="round"
              />
              <line
                x1={leg.x + (index % 2 === 0 ? -6 : 6)}
                y1={176}
                x2={leg.x + (index % 2 === 0 ? -14 : 14)}
                y2={198}
                stroke={mode === "components" ? accent : stroke}
                strokeWidth={mode === "wireframe" ? 3 : 5}
                strokeLinecap="round"
              />
              {(mode === "joints" || mode === "components") && (
                <>
                  <circle cx={leg.x + (index % 2 === 0 ? -6 : 6)} cy={176} r="4.5" fill={accent} />
                  <circle cx={leg.x + (index % 2 === 0 ? -14 : 14)} cy={198} r="4.5" fill={accent} />
                </>
              )}
            </g>
          ))}
        </motion.g>
      </svg>
    </div>
  );
}
