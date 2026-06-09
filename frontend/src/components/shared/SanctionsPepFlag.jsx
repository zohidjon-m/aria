import { Ban, Landmark } from 'lucide-react';
import Badge from '../ui/Badge';

// Supports both <SanctionsPepFlag type="sanctions"|"pep" /> and
// <SanctionsPepFlag hasSanctions hasPep /> call styles.
export default function SanctionsPepFlag({ type, hasSanctions, hasPep }) {
  const showSanctions = type === 'sanctions' || hasSanctions;
  const showPep = type === 'pep' || hasPep;
  if (!showSanctions && !showPep) return null;
  return (
    <span className="inline-flex items-center gap-1">
      {showSanctions && <Badge tone="red" icon={Ban}>Sanctions</Badge>}
      {showPep && <Badge tone="amber" icon={Landmark}>PEP</Badge>}
    </span>
  );
}
