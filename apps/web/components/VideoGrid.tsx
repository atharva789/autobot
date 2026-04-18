"use client";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { SkeletonVideo } from "@/components/ui/skeleton";

interface VideoItem {
  id: string;
  title: string;
  thumbnail: string;
  duration?: string;
  isSelected?: boolean;
}

interface VideoGridProps {
  videos: VideoItem[];
  selectedId?: string;
  onSelect?: (id: string) => void;
  loading?: boolean;
  loadingCount?: number;
}

function VideoCard({
  video,
  isSelected,
  onSelect,
  index,
}: {
  video: VideoItem;
  isSelected: boolean;
  onSelect: () => void;
  index: number;
}) {
  return (
    <button
      onClick={onSelect}
      className={`tile-glow rounded-lg overflow-hidden text-left transition-all duration-200 animate-cascade-in hover:scale-[1.02] hover:border-white/20 ${
        isSelected ? "ring-2 ring-emerald-500 border-emerald-500/50" : ""
      }`}
      style={{ animationDelay: `${index * 0.05}s` }}
    >
      <div className="relative aspect-video bg-zinc-900">
        <img
          src={video.thumbnail}
          alt={video.title}
          className="w-full h-full object-cover"
          loading="lazy"
        />
        {video.duration && (
          <span className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] px-1.5 py-0.5 rounded">
            {video.duration}
          </span>
        )}
        {isSelected && (
          <div className="absolute inset-0 bg-emerald-500/20 flex items-center justify-center">
            <Badge className="bg-emerald-600 text-white">Selected</Badge>
          </div>
        )}
      </div>
      <div className="p-2">
        <p className="text-xs text-zinc-300 line-clamp-2 leading-tight">
          {video.title}
        </p>
      </div>
    </button>
  );
}

export function VideoGrid({
  videos,
  selectedId,
  onSelect,
  loading = false,
  loadingCount = 8,
}: VideoGridProps) {
  if (loading) {
    return (
      <div className="video-grid">
        {Array.from({ length: loadingCount }).map((_, i) => (
          <SkeletonVideo
            key={i}
            className={`animate-cascade-in`}
            style={{ animationDelay: `${i * 0.05}s` } as React.CSSProperties}
          />
        ))}
      </div>
    );
  }

  if (videos.length === 0) {
    return (
      <div className="tile-glow rounded-xl p-8 text-center">
        <p className="text-zinc-500">No videos found</p>
      </div>
    );
  }

  return (
    <div className="video-grid">
      {videos.map((video, index) => (
        <VideoCard
          key={video.id}
          video={video}
          isSelected={selectedId === video.id}
          onSelect={() => onSelect?.(video.id)}
          index={index}
        />
      ))}
    </div>
  );
}
