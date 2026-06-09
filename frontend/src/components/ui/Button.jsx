const VARIANTS = {
  primary: 'bg-brand text-white hover:bg-brand-hover border border-transparent shadow-sm',
  secondary: 'bg-surface text-ink-muted hover:bg-surface-2 border border-border-strong',
  danger: 'bg-red-600 text-white hover:bg-red-700 border border-transparent shadow-sm',
  ghost: 'bg-transparent text-ink-muted hover:bg-surface-2 border border-transparent',
};

const SIZES = {
  sm: 'text-xs px-2.5 py-1.5 gap-1',
  md: 'text-sm px-3.5 py-2 gap-1.5',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  icon: Icon,
  loading = false,
  disabled = false,
  className = '',
  children,
  ...props
}) {
  return (
    <button
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center font-medium rounded-lg transition-colors
        disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2
        focus-visible:ring-brand/40 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {loading ? (
        <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : (
        Icon && <Icon className="w-4 h-4" />
      )}
      {children}
    </button>
  );
}
