export default function Spinner({ size = 'md', label, className = '' }) {
  const sz = size === 'sm' ? 'w-4 h-4 border-2' : size === 'lg' ? 'w-8 h-8 border-[3px]' : 'w-5 h-5 border-2';
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className={`${sz} border-brand/30 border-t-brand rounded-full animate-spin`} />
      {label && <span className="text-sm text-ink-subtle">{label}</span>}
    </div>
  );
}

export function LoadingBlock({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center py-16">
      <Spinner size="lg" label={label} />
    </div>
  );
}
