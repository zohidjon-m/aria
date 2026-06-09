export default function PageHeader({ title, subtitle, breadcrumb, actions }) {
  return (
    <div className="mb-5">
      {breadcrumb && <div className="mb-1.5 text-xs text-ink-subtle">{breadcrumb}</div>}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-ink truncate">{title}</h1>
          {subtitle && <p className="text-sm text-ink-muted mt-0.5">{subtitle}</p>}
        </div>
        {actions && <div className="shrink-0 flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}
