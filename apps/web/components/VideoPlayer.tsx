interface Props { src: string | null; }
export function VideoPlayer({ src }: Props) {
  if (!src) return <div className="w-full aspect-video bg-zinc-800 rounded animate-pulse" />;
  return <video src={src} autoPlay loop muted className="w-full rounded" />;
}
