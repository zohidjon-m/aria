const TONES = {
  red: 'bg-red-50 text-red-700 border-red-200',
  amber: 'bg-amber-50 text-amber-700 border-amber-200',
  emerald: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  blue: 'bg-blue-50 text-blue-700 border-blue-200',
  violet: 'bg-violet-50 text-violet-700 border-violet-200',
  slate: 'bg-slate-100 text-slate-600 border-slate-200',
  indigo: 'bg-brand-soft text-brand border-indigo-200',
};

const DOT = {
  red: 'bg-red-500',
  amber: 'bg-amber-500',
  emerald: 'bg-emerald-500',
  blue: 'bg-blue-500',
  violet: 'bg-violet-500',
  slate: 'bg-slate-400',
  indigo: 'bg-brand',
};

export default function Badge({ tone = 'slate', dot = false, icon: Icon, className = '', children }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium
      uppercase tracking-wide whitespace-nowrap ${TONES[tone] || TONES.slate} ${className}`}>
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${DOT[tone] || DOT.slate}`} />}
      {Icon && <Icon className="w-3 h-3" />}
      {children}
    </span>
  );
}
