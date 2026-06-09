import { useNavigate } from 'react-router-dom';
import { Briefcase } from 'lucide-react';

export default function CaseIndicator({ hasCase, caseId }) {
  const navigate = useNavigate();
  if (!hasCase) return null;
  return (
    <button
      onClick={e => { e.stopPropagation(); if (caseId) navigate(`/cases/${caseId}`); }}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-slate-200 bg-slate-100
        text-slate-600 text-xs font-medium hover:bg-slate-200 transition-colors"
      title="Linked case"
    >
      <Briefcase className="w-3 h-3" /> Case
    </button>
  );
}
