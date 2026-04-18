"use client";
import type { CSSProperties } from "react";

interface SkeletonProps {
  className?: string;
  style?: CSSProperties;
}

export function Skeleton({ className = "", style }: SkeletonProps) {
  return (
    <div className={`skeleton-shimmer rounded ${className}`} style={style} />
  );
}

export function SkeletonCard({ className = "", style }: SkeletonProps) {
  return (
    <div className={`tile-glow rounded-xl p-4 ${className}`} style={style}>
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <div className="space-y-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <div className="mt-4 flex gap-2">
        <Skeleton className="h-8 flex-1 rounded-md" />
        <Skeleton className="h-8 w-20 rounded-md" />
      </div>
    </div>
  );
}

export function SkeletonVideo({ className = "", style }: SkeletonProps) {
  return (
    <div className={`tile-glow rounded-lg overflow-hidden ${className}`} style={style}>
      <Skeleton className="aspect-video w-full" />
      <div className="p-2 space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </div>
  );
}
