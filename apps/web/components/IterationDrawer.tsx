"use client";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import type { Iteration } from "@/lib/types";

interface Props {
  iteration: Iteration | null;
  open: boolean;
  onClose: () => void;
}

export function IterationDrawer({ iteration, open, onClose }: Props) {
  if (!iteration) return null;
  return (
    <Drawer open={open} onOpenChange={(v) => !v && onClose()}>
      <DrawerContent className="bg-zinc-900 text-zinc-100 max-h-[80vh] overflow-y-auto">
        <DrawerHeader>
          <DrawerTitle>Iteration #{iteration.iter_num + 1}</DrawerTitle>
        </DrawerHeader>
        <div className="px-6 pb-6 flex flex-col gap-4">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div><p className="text-zinc-500">Fitness</p><p className="font-mono">{iteration.fitness_score?.toFixed(3)}</p></div>
            <div><p className="text-zinc-500">Tracking err</p><p className="font-mono">{iteration.tracking_error?.toFixed(3)}</p></div>
            <div><p className="text-zinc-500">ER 1.6 prob</p><p className="font-mono">{iteration.er16_success_prob?.toFixed(3)}</p></div>
          </div>
          {iteration.reasoning_log && (
            <div>
              <p className="text-zinc-500 text-sm mb-1">Agent reasoning</p>
              <p className="text-sm text-zinc-300 whitespace-pre-wrap">{iteration.reasoning_log}</p>
            </div>
          )}
          {iteration.train_py_diff && (
            <div>
              <p className="text-zinc-500 text-sm mb-1">train.py diff</p>
              <pre className="text-xs bg-zinc-800 rounded p-3 overflow-x-auto">{iteration.train_py_diff}</pre>
            </div>
          )}
          {iteration.replay_mp4_url && (
            <div>
              <p className="text-zinc-500 text-sm mb-1">Replay</p>
              <video src={iteration.replay_mp4_url} controls className="w-full rounded" />
            </div>
          )}
          <div className="flex gap-2">
            {iteration.controller_ckpt_url && <a href={iteration.controller_ckpt_url} className="text-indigo-400 text-sm underline">Download controller</a>}
            {iteration.replay_mp4_url && <a href={iteration.replay_mp4_url} className="text-indigo-400 text-sm underline">Download replay</a>}
          </div>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
