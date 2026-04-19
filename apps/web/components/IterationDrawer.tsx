"use client";
import { useState } from "react";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Button } from "@/components/ui/button";
import { Download, Cpu, Printer, ShoppingCart, Loader2 } from "lucide-react";
import type { Iteration } from "@/lib/types";
import { api } from "@/lib/api";

interface Props {
  iteration: Iteration | null;
  designId?: string | null;
  open: boolean;
  onClose: () => void;
}

type ExportType = "mujoco" | "print" | "procurement";

export function IterationDrawer({ iteration, designId, open, onClose }: Props) {
  const [exporting, setExporting] = useState<ExportType | null>(null);
  const [exportResults, setExportResults] = useState<Record<string, unknown> | null>(null);

  const handleExport = async (type: ExportType) => {
    if (!designId) return;
    setExporting(type);
    try {
      let result;
      if (type === "mujoco") {
        result = await api.post<Record<string, unknown>>(`/designs/${designId}/export/mujoco`);
      } else if (type === "print") {
        result = await api.post<Record<string, unknown>>(`/designs/${designId}/export/print`);
      } else {
        result = await api.get<Record<string, unknown>>(`/designs/${designId}/procurement`);
      }
      setExportResults(result);
    } catch (err) {
      console.error(`Export ${type} failed:`, err);
    } finally {
      setExporting(null);
    }
  };

  if (!iteration) return null;
  return (
    <Drawer open={open} onOpenChange={(v) => !v && onClose()}>
      <DrawerContent className="bg-zinc-900 text-zinc-100 max-h-[80vh] overflow-y-auto rounded-t-xl">
        <DrawerHeader>
          <DrawerTitle>Iteration #{iteration.iter_num + 1}</DrawerTitle>
        </DrawerHeader>
        <div className="px-6 pb-6 flex flex-col gap-4">
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div><p className="text-zinc-500">Fitness</p><p className="font-mono">{iteration.fitness_score?.toFixed(3)}</p></div>
            <div><p className="text-zinc-500">Tracking err</p><p className="font-mono">{iteration.tracking_error?.toFixed(3)}</p></div>
            <div><p className="text-zinc-500">ER 1.6 prob</p><p className="font-mono">{iteration.er16_success_prob?.toFixed(3)}</p></div>
          </div>

          {designId && (
            <div className="border-t border-zinc-800 pt-4">
              <p className="text-zinc-400 text-sm mb-3 font-medium">Export Options</p>
              <div className="grid grid-cols-3 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-lg bg-zinc-800/50 border-zinc-700 hover:bg-zinc-700 text-zinc-200"
                  onClick={() => handleExport("mujoco")}
                  disabled={exporting !== null}
                >
                  {exporting === "mujoco" ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Cpu className="h-4 w-4 mr-2" />}
                  MuJoCo
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-lg bg-zinc-800/50 border-zinc-700 hover:bg-zinc-700 text-zinc-200"
                  onClick={() => handleExport("print")}
                  disabled={exporting !== null}
                >
                  {exporting === "print" ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Printer className="h-4 w-4 mr-2" />}
                  3D Print
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-lg bg-zinc-800/50 border-zinc-700 hover:bg-zinc-700 text-zinc-200"
                  onClick={() => handleExport("procurement")}
                  disabled={exporting !== null}
                >
                  {exporting === "procurement" ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <ShoppingCart className="h-4 w-4 mr-2" />}
                  BOM
                </Button>
              </div>
              {exportResults && (
                <pre className="mt-3 text-xs bg-zinc-800 rounded p-3 overflow-x-auto max-h-40">
                  {JSON.stringify(exportResults, null, 2)}
                </pre>
              )}
            </div>
          )}

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
            {iteration.controller_ckpt_url && (
              <a href={iteration.controller_ckpt_url} className="inline-flex items-center text-indigo-400 text-sm underline">
                <Download className="h-3 w-3 mr-1" /> Controller
              </a>
            )}
            {iteration.replay_mp4_url && (
              <a href={iteration.replay_mp4_url} className="inline-flex items-center text-indigo-400 text-sm underline">
                <Download className="h-3 w-3 mr-1" /> Replay
              </a>
            )}
          </div>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
