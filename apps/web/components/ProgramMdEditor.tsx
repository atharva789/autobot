"use client";
import dynamic from "next/dynamic";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface Props {
  value: string;
  onChange: (v: string) => void;
}

export function ProgramMdEditor({ value, onChange }: Props) {
  return (
    <MonacoEditor
      height="400px"
      language="markdown"
      theme="vs-dark"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      options={{ wordWrap: "on", minimap: { enabled: false }, fontSize: 14 }}
    />
  );
}
