export default function StatTile({ label, value, icon: Icon, tone = 'slate', sublabel, to, onClick }) {
  const toneRing = {
    red: 'bg-red-50 text-red-600',
    amber: 'bg-amber-50 text-amber-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    blue: 'bg-blue-50 text-blue-600',
    violet: 'bg-violet-50 text-violet-600',
    indigo: 'bg-brand-soft text-brand',
    slate: 'bg-slate-100 text-slate-500',
  }[tone] || 'bg-slate-100 text-slate-500';

  const interactive = to || onClick;
  return (
    <div
      onClick={onClick}
      className={`bg-surface border border-border rounded-xl shadow-sm p-4 flex items-start gap-3
        ${interactive ? 'cursor-pointer hover:border-border-strong hover:shadow transition-all' : ''}`}
    >
      {Icon && (
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${toneRing}`}>
          <Icon className="w-5 h-5" />
        </div>
      )}
      <div className="min-w-0">
        <p className="text-xs font-medium text-ink-subtle uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-bold text-ink tnum leading-tight mt-0.5">{value}</p>
        {sublabel && <p className="text-xs text-ink-subtle mt-0.5">{sublabel}</p>}
      </div>
    </div>
  );
}
