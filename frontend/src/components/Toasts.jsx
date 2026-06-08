import React from 'react';
import { X, AlertCircle, CheckCircle2, Info } from 'lucide-react';

const TYPE_STYLES = {
  error: 'border-red-500/40 bg-red-500/10 text-red-200',
  success: 'border-green-500/40 bg-green-500/10 text-green-200',
  info: 'border-brand-primary/40 bg-brand-primary/10 text-brand-primary',
};

const ICONS = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info,
};

const Toasts = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
      {toasts.map((t) => {
        const Icon = ICONS[t.type] || Info;
        const style = TYPE_STYLES[t.type] || TYPE_STYLES.info;
        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-lg border ${style} px-4 py-3 shadow-lg backdrop-blur-sm animate-in fade-in slide-in-from-right-2`}
          >
            <Icon size={18} className="mt-0.5 shrink-0" />
            <div className="flex-1 text-sm font-medium">{t.message}</div>
            <button
              onClick={() => onDismiss(t.id)}
              className="shrink-0 rounded p-0.5 text-slate-400 hover:text-white"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default Toasts;
