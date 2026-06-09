export default function Card({ title, subtitle, actions, icon: Icon, className = '', bodyClassName = '', children }) {
  return (
    <div className={`bg-surface border border-border rounded-xl shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2 min-w-0">
            {Icon && <Icon className="w-4 h-4 text-ink-subtle shrink-0" />}
            <div className="min-w-0">
              {title && <h3 className="text-sm font-semibold text-ink truncate">{title}</h3>}
              {subtitle && <p className="text-xs text-ink-subtle truncate">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="shrink-0 flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={bodyClassName || 'p-4'}>{children}</div>
    </div>
  );
}
