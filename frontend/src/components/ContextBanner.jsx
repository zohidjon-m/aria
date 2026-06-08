import React from 'react';
import { X, Users, AlertOctagon, Briefcase } from 'lucide-react';

const ContextBanner = ({ context, onClear }) => {
  if (!context) return null;

  let icon = null;
  let label = '';
  if (context.type === 'customer') {
    icon = <Users size={14} />;
    label = `Analyzing customer: ${context.data.full_name} (ID ${context.data.customer_id})`;
  } else if (context.type === 'alert') {
    icon = <AlertOctagon size={14} />;
    label = `Analyzing alert #${context.data.alert_id} — ${context.data.rule_name}`;
  } else if (context.type === 'case') {
    icon = <Briefcase size={14} />;
    label = `Analyzing case #${context.data.case_id} (${context.data.case_type})`;
  }

  return (
    <div className="mx-4 mt-3 flex items-center justify-between rounded-lg border border-brand-primary/30 bg-brand-primary/10 px-3 py-2 text-xs text-brand-primary">
      <div className="flex items-center gap-2 truncate">
        {icon}
        <span className="truncate font-medium">{label}</span>
      </div>
      <button
        onClick={onClear}
        className="ml-2 rounded p-1 text-slate-400 transition hover:bg-slate-700/50 hover:text-white"
        title="Clear context"
      >
        <X size={14} />
      </button>
    </div>
  );
};

export default ContextBanner;
