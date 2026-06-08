
export default function SanctionsPepFlag({ hasSanctions, hasPep }) {
  if (!hasSanctions && !hasPep) return null
  return (
    <span className="flex items-center gap-1">
      {hasSanctions && (
        <span className="px-1.5 py-0.5 bg-red-800 border border-red-600 text-red-200 text-xs font-bold rounded flex items-center gap-0.5">
          <span>⚑</span> SANCTIONS
        </span>
      )}
      {hasPep && (
        <span className="px-1.5 py-0.5 bg-orange-800 border border-orange-600 text-orange-200 text-xs font-bold rounded flex items-center gap-0.5">
          <span>⚑</span> PEP
        </span>
      )}
    </span>
  )
}
