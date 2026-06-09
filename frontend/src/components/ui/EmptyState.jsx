export default function EmptyState({ icon: Icon, title = 'Nothing here', message, action, tone = 'slate' }) {
  const isError = tone === 'error';
  return (
    <div className={`flex flex-col items-center justify-center text-center py-12 px-4 rounded-xl border border-dashed
      ${isError ? 'border-red-200 bg-red-50/40' : 'border-border bg-surface-2/40'}`}>
      {Icon && <Icon className={`w-8 h-8 mb-2 ${isError ? 'text-red-400' : 'text-ink-subtle'}`} />}
      <p className={`text-sm font-medium ${isError ? 'text-red-700' : 'text-ink'}`}>{title}</p>
      {message && <p className="text-xs text-ink-subtle mt-1 max-w-sm">{message}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
