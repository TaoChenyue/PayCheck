// paycheck-react/src/components/EmptyState.tsx
import { useCallback, useRef, useState, type DragEvent } from "react";
import type { AggregatedData } from "../types";

interface EmptyStateProps {
  onDataLoaded: (data: AggregatedData) => void;
}

export default function EmptyState({ onDataLoaded }: EmptyStateProps) {
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File) => {
      setError("");
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string) as AggregatedData;
          if (!data.all_transactions || !data.summary) {
            setError("无效的报告文件：缺少必要字段");
            return;
          }
          onDataLoaded(data);
        } catch {
          setError("文件解析失败，请确认是有效的 JSON 文件");
        }
      };
      reader.readAsText(file);
    },
    [onDataLoaded]
  );

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith(".json")) {
        handleFile(file);
      } else {
        setError("请拖入 report.json 文件");
      }
    },
    [handleFile]
  );

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        minHeight: "100vh", background: "#f0f2f5", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 32, color: "#1a1a2e", marginBottom: 8 }}>PayCheck</h1>
      <p style={{ color: "#666", marginBottom: 24 }}>账单分析报告</p>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        style={{
          width: 400, padding: 48, border: `2px dashed ${dragOver ? "#1a1a2e" : "#d9d9d9"}`,
          borderRadius: 12, background: dragOver ? "#f0f5ff" : "#fff",
          textAlign: "center", cursor: "pointer", transition: "all 0.2s", maxWidth: "90vw"
        }}
      >
        <p style={{ fontSize: 18, color: "#1a1a2e", marginBottom: 8 }}>
          拖拽 report.json 到此处
        </p>
        <p style={{ fontSize: 13, color: "#999" }}>或点击选择文件</p>
      </div>
      {error && <p style={{ color: "#ff4d4f", marginTop: 12, fontSize: 14 }}>{error}</p>}
      <input
        ref={fileRef}
        type="file"
        accept=".json"
        style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
      />
    </div>
  );
}
