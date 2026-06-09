
export default function HumanReviewBanner() {
  return (
    <div className="flex items-start gap-2 bg-amber-900/40 border border-amber-600 rounded p-3 mb-3">
      <span className="text-amber-400 text-lg shrink-0">⚠</span>
      <div>
        <p className="text-amber-300 font-bold text-sm">HUMAN REVIEW REQUIRED</p>
        <p className="text-amber-200 text-xs mt-0.5">
          Agent recommendation is advisory only. Officer must independently verify all findings before taking any action.
        </p>
      </div>
    </div>
  )
}
