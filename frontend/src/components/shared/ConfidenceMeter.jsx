
export default function ConfidenceMeter({ value }) {
  const pct = Math.round((value || 0) * 100)
  const color = pct >= 70 ? 'bg-red-500' : pct >= 35 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-slate-700 rounded overflow-hidden">
        <div className={`h-full ${color} rounded`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-slate-300 w-8 text-right">{pct}%</span>
    </div>
  )
}
