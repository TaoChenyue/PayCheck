// paycheck-react/src/components/common/Pagination.tsx

interface PaginationProps {
  page: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  pageSizeOptions?: number[];
}

export default function Pagination({
  page,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50, 100],
}: PaginationProps) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 16, paddingTop: 12, borderTop: "1px solid #f0f0f0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button className="page-btn" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          ‹ 上一页
        </button>
        <span style={{ fontSize: 13, color: "#666", minWidth: 60, textAlign: "center" }}>
          {page} / {totalPages}
        </span>
        <button className="page-btn" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          下一页 ›
        </button>
      </div>
      <select
        className="page-size-select"
        value={pageSize}
        onChange={(e) => { onPageSizeChange(Number(e.target.value)); }}
        style={{ padding: "4px 8px", border: "1px solid #d9d9d9", borderRadius: 4, fontSize: 13 }}
      >
        {pageSizeOptions.map((n) => (
          <option key={n} value={n}>{n} 条/页</option>
        ))}
      </select>
    </div>
  );
}
