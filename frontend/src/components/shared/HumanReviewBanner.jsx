import { ShieldAlert } from 'lucide-react';

export default function HumanReviewBanner() {
  return (
    <div className="flex items-start gap-2.5 bg-amber-50 border border-amber-200 rounded-lg p-3">
      <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
      <div>
        <p className="text-amber-800 font-semibold text-sm">Human review required</p>
        <p className="text-amber-700 text-xs mt-0.5 leading-relaxed">
          Agent recommendation is advisory only. The officer must independently verify all findings before taking action.
        </p>
      </div>
    </div>
  );
}
