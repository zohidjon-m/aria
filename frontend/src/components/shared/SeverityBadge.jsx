
const COLORS = {
  critical: 'bg-red-900 text-red-200 border border-red-700',
  high: 'bg-orange-900 text-orange-200 border border-orange-700',
  medium: 'bg-yellow-900 text-yellow-200 border border-yellow-700',
  low: 'bg-green-900 text-green-200 border border-green-700',
}

export default function SeverityBadge({ severity }) {
  const cls = COLORS[severity] || 'bg-slate-700 text-slate-300'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono font-bold uppercase tracking-wide ${cls}`}>
      {severity || '?'}
    </span>
  )
}
