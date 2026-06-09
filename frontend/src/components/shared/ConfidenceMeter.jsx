// Accepts a 0-100 `value` (preferred) or legacy 0-100 `score`.
export default function ConfidenceMeter({ value, score }) {
  const raw = value ?? score ?? 0;
  const pct = Math.max(0, Math.min(100, Math.round(raw)));
  const color = pct >= 70 ? 'bg-red-500' : pct >= 35 ? 'bg-amber-500' : 'bg-emerald-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-surface-2 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold text-ink-muted tnum w-9 text-right">{pct}%</span>
    </div>
  );
}
