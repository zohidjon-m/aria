
const COLORS = {
  open: 'bg-blue-900 text-blue-200 border border-blue-700',
  under_review: 'bg-amber-900 text-amber-200 border border-amber-700',
  escalated: 'bg-red-900 text-red-300 border border-red-600 font-bold',
  dismissed: 'bg-slate-700 text-slate-400 border border-slate-600',
  resolved: 'bg-green-900 text-green-200 border border-green-700',
  closed_clean: 'bg-green-900 text-green-200 border border-green-700',
  closed_sar: 'bg-purple-900 text-purple-200 border border-purple-700',
}

export default function StatusBadge({ status }) {
  const cls = COLORS[status] || 'bg-slate-700 text-slate-300'
  const label = status ? status.replace(/_/g, ' ') : '?'
  return (
    <span className={`px-2 py-0.5 rounded text-xs uppercase tracking-wide ${cls}`}>
      {label}
    </span>
  )
}
