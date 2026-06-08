import HumanReviewBanner from './shared/HumanReviewBanner';
import ConfidenceMeter from './shared/ConfidenceMeter';

const RECOMMENDATION_LABELS = {
  escalate: { label: 'ESCALATE', cls: 'bg-red-900 text-red-300 border border-red-700' },
  needs_investigation: { label: 'NEEDS INVESTIGATION', cls: 'bg-amber-900 text-amber-300 border border-amber-700' },
  investigate: { label: 'NEEDS INVESTIGATION', cls: 'bg-amber-900 text-amber-300 border border-amber-700' },
  likely_false_positive: { label: 'LIKELY FALSE POSITIVE', cls: 'bg-green-900 text-green-300 border border-green-700' },
};

function SourceRefChip({ ref: refStr }) {
  return (
    <span className="font-mono text-xs bg-dark-bg border border-dark-border rounded px-1 py-0.5 text-gray-400 mr-1 inline-block">
      {refStr}
    </span>
  );
}

export default function AgentProposalPanel({ run, onViewTrace }) {
  if (!run) return null;

  const output = run.output || {};
  const validation = run.validation || {};

  const recommendation = output.recommendation || output.action;
  const recMeta = RECOMMENDATION_LABELS[recommendation] || {
    label: recommendation || 'UNKNOWN',
    cls: 'bg-gray-800 text-gray-300 border border-gray-600',
  };

  const confidence = output.confidence_score ?? output.confidence ?? null;
  const claims = output.factual_claims || [];
  const limitations = output.limitations || [];
  const validationStatus = validation.status || 'not_run';
  const unsupportedCount = validation.unsupported_claim_count ?? 0;

  return (
    <div>
      <HumanReviewBanner />
      <div className="mt-3">
        <div className="flex items-center gap-3 mb-3">
          <span className={`text-xs font-bold px-2 py-1 rounded uppercase tracking-wide ${recMeta.cls}`}>
            {recMeta.label}
          </span>
          {confidence !== null && (
            <div className="flex-1">
              <ConfidenceMeter score={confidence} />
            </div>
          )}
        </div>

        {confidence !== null && (
          <div className="text-xs text-gray-500 mb-3">Confidence: {confidence}/100</div>
        )}

        {output.summary && (
          <div className="text-xs text-gray-300 bg-dark-bg rounded p-2 mb-3 leading-relaxed">
            {output.summary}
          </div>
        )}

        {claims.length > 0 && (
          <div className="mb-3">
            <div className="text-xs uppercase tracking-wide text-gray-500 mb-1 font-semibold">Factual Claims</div>
            {claims.map((c, i) => (
              <div key={i} className="mb-2">
                <div className="text-xs text-gray-300 mb-0.5">{c.statement || c}</div>
                {c.evidence_refs?.length > 0 && (
                  <div>
                    {c.evidence_refs.map((r, j) => <SourceRefChip key={j} ref={r} />)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {limitations.length > 0 && (
          <div className="mb-3">
            <div className="text-xs uppercase tracking-wide text-gray-500 mb-1 font-semibold">Limitations</div>
            {limitations.map((l, i) => (
              <div key={i} className="flex gap-1 text-xs text-amber-400 mb-0.5">
                <span>&#9888;</span>
                <span>{typeof l === 'string' ? l : l.description || JSON.stringify(l)}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs text-gray-500">Validation:</span>
          <span className={`text-xs font-semibold px-1 py-0.5 rounded ${
            validationStatus === 'passed' ? 'bg-green-900 text-green-300' :
            validationStatus === 'failed' ? 'bg-red-900 text-red-300' :
            'bg-gray-800 text-gray-400'
          }`}>
            {validationStatus.toUpperCase()}
          </span>
          {unsupportedCount > 0 && (
            <span className="text-xs text-amber-400">{unsupportedCount} unsupported claim(s)</span>
          )}
        </div>

        <button
          onClick={onViewTrace}
          className="text-xs text-brand-primary hover:underline"
        >
          View Full Trace &rarr;
        </button>
      </div>
    </div>
  );
}
