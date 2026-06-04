// paycheck-react/src/components/common/TagSelect.tsx
import { useState, useRef, useEffect, useCallback } from "react";

interface TagSelectProps {
  placeholder: string;
  values: string[];
  suggestions: string[];
  onChange: (values: string[]) => void;
}

export default function TagSelect({ placeholder, values, suggestions, onChange }: TagSelectProps) {
  const [input, setInput] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const available = suggestions.filter(
    (v) => !values.includes(v) && (!input || v.includes(input))
  );

  const addValue = useCallback(
    (v: string) => {
      if (!values.includes(v)) {
        onChange([...values, v]);
      }
      setInput("");
      setShowDropdown(false);
    },
    [values, onChange]
  );

  const removeValue = useCallback(
    (v: string) => {
      onChange(values.filter((x) => x !== v));
    },
    [values, onChange]
  );

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, []);

  return (
    <div ref={wrapRef} style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
      <div style={{ position: "relative", display: "inline-block" }}>
        <input
          type="text"
          placeholder={placeholder}
          value={input}
          onChange={(e) => { setInput(e.target.value); setShowDropdown(true); }}
          onFocus={() => setShowDropdown(true)}
          onKeyDown={(e) => { if (e.key === "Escape") setShowDropdown(false); }}
          style={{ padding: "4px 8px", border: "1px solid #d9d9d9", borderRadius: 4, fontSize: 13, maxWidth: 140 }}
        />
        {showDropdown && available.length > 0 && (
          <div
            style={{
              position: "absolute", top: "100%", left: 0, zIndex: 1000,
              background: "#fff", border: "1px solid #d9d9d9", borderRadius: 4,
              maxHeight: 180, overflowY: "auto", minWidth: 150,
              boxShadow: "0 2px 8px rgba(0,0,0,0.12)"
            }}
          >
            {available.map((v) => (
              <div
                key={v}
                onClick={() => addValue(v)}
                style={{ padding: "5px 10px", cursor: "pointer", fontSize: 13, borderBottom: "1px solid #f5f5f5" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#f0f5ff")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "")}
              >
                {v}
              </div>
            ))}
          </div>
        )}
      </div>
      {values.map((v) => (
        <span
          key={v}
          style={{
            display: "inline-flex", alignItems: "center", gap: 2,
            background: "#e6f7ff", border: "1px solid #91d5ff", borderRadius: 4,
            padding: "1px 8px", fontSize: 12, lineHeight: 1.6, color: "#1a1a2e"
          }}
        >
          {v}
          <span
            onClick={() => removeValue(v)}
            style={{ cursor: "pointer", marginLeft: 2, color: "#999", userSelect: "none", fontSize: 14 }}
          >
            ×
          </span>
        </span>
      ))}
    </div>
  );
}
