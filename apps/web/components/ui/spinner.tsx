"use client";

interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  const sizeClass = size === "sm" ? "spinner-ring-sm" : size === "lg" ? "spinner-ring-lg" : "";

  return (
    <div className={`spinner-ring ${sizeClass} ${className}`} />
  );
}

interface LoadingOverlayProps {
  message?: string;
  submessage?: string;
}

export function LoadingOverlay({ message, submessage }: LoadingOverlayProps) {
  return (
    <div className="fixed inset-0 bg-zinc-950/90 backdrop-blur-sm flex flex-col items-center justify-center z-50">
      <div className="relative">
        <div className="absolute inset-0 bg-white/5 rounded-full blur-xl animate-pulse-glow" />
        <Spinner size="lg" />
      </div>
      {message && (
        <p className="mt-6 text-zinc-200 text-lg font-medium animate-cascade-in">
          {message}
        </p>
      )}
      {submessage && (
        <p className="mt-2 text-zinc-500 text-sm animate-cascade-in cascade-delay-2">
          {submessage}
        </p>
      )}
    </div>
  );
}
