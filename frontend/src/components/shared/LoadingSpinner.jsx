
export default function LoadingSpinner({ size = 'md', label }) {
  const sz = size === 'sm' ? 'w-4 h-4' : 'w-8 h-8'
  return (
    <div className="flex items-center gap-2">
      <div className={`${sz} border-2 border-slate-600 border-t-brand-primary rounded-full animate-spin`} />
      {label && <span className="text-slate-400 text-sm">{label}</span>}
    </div>
  )
}
