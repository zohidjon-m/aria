import Badge from '../ui/Badge';

const TONE = { critical: 'red', high: 'amber', medium: 'amber', low: 'emerald' };

export default function SeverityBadge({ severity }) {
  return <Badge tone={TONE[severity] || 'slate'} dot>{severity || '?'}</Badge>;
}
