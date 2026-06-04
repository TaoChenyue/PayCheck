// paycheck-react/src/utils/format.ts

export function fmtNum(n: number | string): string {
  const num = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(num)) return "0.00";
  return num.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtYuan(n: number | string): string {
  return "¥" + fmtNum(n);
}
