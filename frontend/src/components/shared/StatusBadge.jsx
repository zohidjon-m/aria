import Badge from '../ui/Badge';

const TONE = {
  open: 'blue',
  under_review: 'amber',
  escalated: 'red',
  dismissed: 'slate',
  resolved: 'emerald',
  closed_clean: 'emerald',
  closed_sar: 'violet',
};

export default function StatusBadge({ status }) {
  const label = status ? status.replace(/_/g, ' ') : '?';
  return <Badge tone={TONE[status] || 'slate'} dot>{label}</Badge>;
}
