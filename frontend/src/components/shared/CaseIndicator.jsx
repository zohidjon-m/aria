
import { useNavigate } from 'react-router-dom'

export default function CaseIndicator({ hasCase, caseId }) {
  const navigate = useNavigate()
  if (!hasCase) return null
  return (
    <button
      onClick={e => { e.stopPropagation(); if (caseId) navigate(`/cases/${caseId}`) }}
      className="px-1.5 py-0.5 bg-slate-700 border border-slate-500 text-slate-300 text-xs rounded flex items-center gap-0.5 hover:bg-slate-600"
      title="Has linked case"
    >
      🗂 Case
    </button>
  )
}
