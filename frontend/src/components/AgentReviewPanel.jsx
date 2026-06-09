import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileText,
  GitBranch,
  ListChecks,
  Upload,
} from 'lucide-react';
import { getAgentReview, postBankExport, postHumanDecision } from '../api/client';
import Badge from './ui/Badge';
import Button from './ui/Button';
import ErrorMessage from './shared/ErrorMessage';
import ConfidenceMeter from './shared/ConfidenceMeter';

const TABS = ['Why', 'Evidence', 'Workflow', 'Decision'];

const REC_TONE = {
  escalate: 'red',
  needs_investigation: 'amber',
  investigate: 'amber',
  open_case: 'red',
  continue_investigation: 'amber',
  return_to_triage: 'blue',
  likely_false_positive: 'emerald',
  record_risk_score_for_human_review: 'violet',
  draft_for_human_review: 'violet',
};

const PHASE_TONE = {
  created: 'slate',
  context_loaded: 'blue',
  planning: 'blue',
  tool_requested: 'violet',
  tool_executed: 'violet',
  observing: 'blue',
  revising: 'amber',
  validating: 'amber',
  proposed: 'emerald',
  failed_safe: 'red',
  tool: 'violet',
  observation: 'blue',
};

function titleize(value) {
  return String(value || 'Unknown').replace(/_/g, ' ');
}

function confidencePercent(value) {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return null;
  return Math.round(numeric <= 1 ? numeric * 100 : numeric);
}

function formatDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function sourceLabel(ref) {
  if (!ref) return '';
  if (typeof ref === 'string') return ref;
  const table = ref.table || ref.source_table || ref.source || ref.entity_type;
  const key = ref.key || ref.source_key || ref.record_key || ref.entity_id;
  return [table, key].filter(Boolean).join('#') || JSON.stringify(ref);
}

function refList(item) {
  if (!item || typeof item !== 'object') return [];
  return item.source_refs || item.evidence_refs || [];
}

function refKey(ref) {
  return sourceLabel(ref);
}

function claimMatchesReason(reason, claim) {
  const reasonRefs = refList(reason).map(refKey).filter(Boolean);
  const claimRefs = refList(claim).map(refKey).filter(Boolean);
  if (!reasonRefs.length || !claimRefs.length) return false;
  return claimRefs.some(ref => reasonRefs.includes(ref));
}

function statementText(item) {
  if (typeof item === 'string') return item;
  return item?.statement || item?.description || JSON.stringify(item);
}

function formatFields(value) {
  if (Array.isArray(value)) return value.join(', ');
  return value || '';
}

function nextActionLabel(review) {
  if (!review.latest_human_decision) return 'Record human decision';
  if (!review.latest_export) return 'Export decision record';
  return 'No pending officer action';
}

function SourceRefChips({ refs }) {
  if (!refs?.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {refs.slice(0, 5).map((ref, index) => (
        <span key={index} className="font-mono text-[11px] bg-surface-2 border border-border rounded px-1.5 py-0.5 text-ink-muted">
          {sourceLabel(ref)}
        </span>
      ))}
    </div>
  );
}

function EmptyLine({ children }) {
  return <p className="text-sm text-ink-subtle">{children}</p>;
}

function SummaryMetric({ label, value }) {
  const rendered = value === null || value === undefined || value === '' ? '-' : value;
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-ink-subtle">{label}</div>
      <div className="text-sm font-medium text-ink truncate">{rendered}</div>
    </div>
  );
}

function WarningList({ title, items }) {
  if (!items?.length) return null;
  return (
    <div className="border border-amber-200 bg-amber-50/70 rounded-lg p-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-amber-800 mb-2">
        <AlertTriangle className="w-3.5 h-3.5" /> {title}
      </div>
      <div className="space-y-1">
        {items.map((item, index) => (
          <div key={index} className="text-sm text-amber-900">
            {statementText(item)}
          </div>
        ))}
      </div>
    </div>
  );
}

function ReasoningSection({ review }) {
  const reasoning = review.reasoning || [];
  const claims = review.claims || [];
  const unmatchedClaims = claims.filter(claim => !reasoning.some(reason => claimMatchesReason(reason, claim)));
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        {reasoning.length ? reasoning.map((item, index) => {
          const supportingClaims = claims.filter(claim => claimMatchesReason(item, claim));
          return (
            <div key={index} className="grid grid-cols-[1.75rem_1fr] gap-3 border-b border-border pb-3 last:border-b-0 last:pb-0">
              <div className="w-7 h-7 rounded-full bg-brand-soft text-brand flex items-center justify-center text-xs font-semibold tnum">{index + 1}</div>
              <div className="min-w-0">
                <p className="text-sm text-ink leading-relaxed">{statementText(item)}</p>
                <SourceRefChips refs={refList(item)} />
                {supportingClaims.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {supportingClaims.map((claim, claimIndex) => (
                      <div key={claimIndex} className="border border-border bg-surface-2/60 rounded-lg px-2.5 py-1.5">
                        <p className="text-xs text-ink-muted">{statementText(claim)}</p>
                        <SourceRefChips refs={refList(claim)} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        }) : <EmptyLine>No reasoning was stored for this run.</EmptyLine>}
      </div>

      {unmatchedClaims.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-2">
            <ListChecks className="w-3.5 h-3.5" /> Additional Grounded Claims
          </div>
          <div className="space-y-2">
            {unmatchedClaims.map((item, index) => (
              <div key={index} className="border border-border rounded-lg px-3 py-2">
                <p className="text-sm text-ink-muted">{statementText(item)}</p>
                <SourceRefChips refs={refList(item)} />
              </div>
            ))}
          </div>
        </div>
      )}

      <WarningList title="Limitations" items={review.limitations} />
      <WarningList title="Missing Data" items={review.missing_data} />
    </div>
  );
}

function EvidenceSection({ evidence }) {
  if (!evidence?.length) return <EmptyLine>No evidence records were stored for this run.</EmptyLine>;
  return (
    <div className="overflow-x-auto border border-border rounded-lg">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-ink-subtle uppercase tracking-wide bg-surface-2/60">
            <th className="font-medium px-3 py-2">Source</th>
            <th className="font-medium px-3 py-2">Record</th>
            <th className="font-medium px-3 py-2">Fields</th>
            <th className="font-medium px-3 py-2">Preview</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {evidence.map((item, index) => (
            <tr key={item.evidence_id || index}>
              <td className="px-3 py-2 font-mono text-xs text-ink-muted">{item.source || item.source_table || '-'}</td>
              <td className="px-3 py-2 font-mono text-xs text-ink">{item.record_key || item.source_key || item.evidence_id || '-'}</td>
              <td className="px-3 py-2 text-xs text-ink-muted max-w-[12rem] truncate">{formatFields(item.fields || item.columns) || '-'}</td>
              <td className="px-3 py-2 text-xs text-ink-muted max-w-[18rem] truncate">{item.payload_preview || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WorkflowSection({ review, onViewTrace }) {
  const timeline = review.workflow_timeline || [];
  const findings = review.validation_findings || [];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3 text-sm">
        <SummaryMetric label="Runtime events" value={review.trace_summary?.runtime_event_count ?? 0} />
        <SummaryMetric label="Tool calls" value={review.trace_summary?.tool_call_count ?? 0} />
        <SummaryMetric label="Observations" value={review.trace_summary?.observation_count ?? 0} />
      </div>

      {timeline.length ? (
        <div className="space-y-2">
          {timeline.map((item, index) => (
            <details key={index} className="border border-border rounded-lg px-3 py-2">
              <summary className="cursor-pointer list-none">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={PHASE_TONE[item.phase] || 'slate'}>{titleize(item.phase)}</Badge>
                      {item.tool_name && <span className="font-mono text-xs text-violet-700">{item.tool_name}</span>}
                      {item.status && <span className="text-xs text-ink-subtle">{titleize(item.status)}</span>}
                    </div>
                    <div className="text-sm font-medium text-ink mt-1">{titleize(item.label)}</div>
                    {item.description && <div className="text-xs text-ink-muted mt-0.5 truncate">{item.description}</div>}
                  </div>
                  <span className="text-xs text-ink-subtle mt-1">Details</span>
                </div>
              </summary>
              <div className="mt-2 space-y-1.5 text-xs text-ink-muted">
                {item.audit_id && <div>Audit ID: <span className="font-mono">{item.audit_id}</span></div>}
                {item.policy_decisions?.length > 0 && <div>Policy decisions: {item.policy_decisions.map(p => p.decision || p.policy).join(', ')}</div>}
                {item.data_completeness && <div>Completeness: {item.data_completeness.complete ? 'complete' : 'partial'}{item.data_completeness.rows_returned !== undefined ? `, ${item.data_completeness.rows_returned} row(s)` : ''}</div>}
                {item.error && <div className="text-red-700">Error: {item.error}</div>}
                <details className="mt-2">
                  <summary className="cursor-pointer text-ink-subtle">Raw event</summary>
                  <pre className="mt-1 bg-surface-2 rounded-lg p-2 overflow-x-auto font-mono">{JSON.stringify(item.raw, null, 2)}</pre>
                </details>
              </div>
            </details>
          ))}
        </div>
      ) : <EmptyLine>No workflow timeline is available for this run.</EmptyLine>}

      {findings.length > 0 && (
        <div className="border border-border rounded-lg px-3 py-2">
          <div className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-2">Validation findings</div>
          <div className="space-y-1.5">
            {findings.map((item, index) => (
              <div key={index} className="text-xs text-ink-muted">
                {statementText(item)}
              </div>
            ))}
          </div>
        </div>
      )}

      <Button type="button" size="sm" variant="ghost" icon={ArrowRight} onClick={onViewTrace} disabled={!onViewTrace}>Open Full Trace</Button>
    </div>
  );
}

function DecisionSection({
  review,
  decision,
  setDecision,
  rationale,
  setRationale,
  deciding,
  exporting,
  onDecision,
  onExport,
}) {
  const decisions = review.human_decisions || [];
  const exports = review.exports || [];
  const canExport = decisions.length > 0;
  return (
    <div className="space-y-4">
      <form onSubmit={onDecision} className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium text-ink">
          <ClipboardCheck className="w-4 h-4" /> Record human decision
        </div>
        <select
          value={decision}
          onChange={e => setDecision(e.target.value)}
          className="w-full bg-surface border border-border rounded-lg px-2.5 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-brand/30"
        >
          <option value="approve">Approve proposal</option>
          <option value="reject">Reject proposal</option>
          <option value="needs_more_information">Needs more information</option>
          <option value="defer">Defer decision</option>
        </select>
        <textarea
          value={rationale}
          onChange={e => setRationale(e.target.value)}
          placeholder="Decision rationale"
          rows={3}
          className="w-full bg-surface border border-border rounded-lg px-2.5 py-2 text-sm text-ink placeholder:text-ink-subtle focus:outline-none focus:ring-2 focus:ring-brand/30"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" size="sm" icon={CheckCircle2} loading={deciding}>Record Decision</Button>
          <Button type="button" size="sm" variant="secondary" icon={Upload} onClick={onExport} loading={exporting} disabled={!canExport}>Export Decision</Button>
          {!canExport && <span className="text-xs text-ink-subtle">Record a human decision before export.</span>}
        </div>
      </form>

      <div>
        <div className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-2">Decision history</div>
        {decisions.length ? (
          <div className="space-y-2">
            {decisions.map(item => (
              <div key={item.decision_id} className="border border-border rounded-lg px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-ink">{titleize(item.decision)}</span>
                  <span className="text-xs text-ink-subtle">{formatDate(item.created_at)}</span>
                </div>
                {item.rationale && <p className="text-ink-muted mt-1">{item.rationale}</p>}
              </div>
            ))}
          </div>
        ) : <EmptyLine>No human decision has been recorded.</EmptyLine>}
      </div>

      <div>
        <div className="text-xs font-semibold text-ink-subtle uppercase tracking-wide mb-2">Export history</div>
        {exports.length ? (
          <div className="space-y-2">
            {exports.map(item => (
              <div key={item.export_id} className="border border-border rounded-lg px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-ink">{item.destination || 'bank system'}</span>
                  <Badge tone="emerald">{titleize(item.status)}</Badge>
                </div>
                <p className="text-xs text-ink-subtle mt-1">{formatDate(item.created_at)} - {item.export_id}</p>
              </div>
            ))}
          </div>
        ) : <EmptyLine>No export record has been created.</EmptyLine>}
      </div>
    </div>
  );
}

export default function AgentReviewPanel({ runId, onViewTrace }) {
  const [review, setReview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [decision, setDecision] = useState('approve');
  const [rationale, setRationale] = useState('');
  const [deciding, setDeciding] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [tab, setTab] = useState('Why');

  function loadReview() {
    if (!runId) return;
    setLoading(true);
    setError(null);
    return getAgentReview(runId)
      .then(setReview)
      .catch(e => setError(e.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadReview(); setTab('Why'); }, [runId]);

  async function handleDecision(e) {
    e.preventDefault();
    if (!runId) return;
    setDeciding(true);
    setError(null);
    try {
      await postHumanDecision(runId, { decision, rationale: rationale.trim() || null });
      setRationale('');
      await loadReview();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setDeciding(false);
    }
  }

  async function handleExport() {
    if (!runId) return;
    setExporting(true);
    setError(null);
    try {
      await postBankExport(runId);
      await loadReview();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setExporting(false);
    }
  }

  if (!runId) {
    return <p className="text-sm text-ink-subtle">No agent run selected.</p>;
  }
  if (loading && !review) {
    return <p className="text-sm text-ink-subtle">Loading review...</p>;
  }
  if (!review) {
    return error ? <ErrorMessage message={error} /> : null;
  }

  const confidence = confidencePercent(review.confidence);
  const recTone = REC_TONE[review.recommendation] || 'slate';
  const latestDecision = review.latest_human_decision;
  const latestExport = review.latest_export;

  return (
    <div className="space-y-4">
      {error && <ErrorMessage message={error} />}

      <div className="border border-border rounded-lg overflow-hidden">
        <div className="bg-surface-2 px-3 py-2 flex flex-wrap items-center gap-2">
          <Badge tone="indigo" icon={GitBranch}>{titleize(review.workflow || review.agent_name)}</Badge>
          <Badge tone={recTone} dot>{titleize(review.recommendation)}</Badge>
          <Badge tone={review.validation?.status === 'passed' ? 'emerald' : 'amber'}>Validation: {review.validation?.status || 'not run'}</Badge>
        </div>
        <div className="p-3 space-y-3">
          {confidence !== null && (
            <div>
              <div className="flex items-center justify-between text-xs text-ink-subtle mb-1">
                <span>Confidence</span>
                <span className="tnum">{confidence}/100</span>
              </div>
              <ConfidenceMeter value={confidence} />
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <SummaryMetric label="Stop reason" value={titleize(review.stop_reason)} />
            <SummaryMetric label="Status" value={titleize(review.status)} />
            <SummaryMetric label="Subject" value={`${review.subject?.type || '-'} ${review.subject?.id || ''}`} />
            <SummaryMetric label="Created" value={formatDate(review.created_at) || '-'} />
          </div>
          <div className="border-t border-border pt-3">
            <div className="text-[11px] uppercase tracking-wide text-ink-subtle mb-1">Required human action</div>
            <p className="text-sm text-ink leading-relaxed">{review.required_human_action}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
        <div className="border border-border rounded-lg px-3 py-2">
          <div className="text-ink-subtle uppercase tracking-wide mb-1">Latest decision</div>
          <div className="font-medium text-ink">{latestDecision ? titleize(latestDecision.decision) : 'Not recorded'}</div>
        </div>
        <div className="border border-border rounded-lg px-3 py-2">
          <div className="text-ink-subtle uppercase tracking-wide mb-1">Export status</div>
          <div className="font-medium text-ink">{latestExport ? titleize(latestExport.status) : 'Not exported'}</div>
        </div>
        <div className="border border-border rounded-lg px-3 py-2">
          <div className="text-ink-subtle uppercase tracking-wide mb-1">Next action</div>
          <div className="font-medium text-ink">{nextActionLabel(review)}</div>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(item => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={`px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors ${
              tab === item ? 'border-brand text-brand' : 'border-transparent text-ink-subtle hover:text-ink'
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === 'Why' && <ReasoningSection review={review} />}
      {tab === 'Evidence' && <EvidenceSection evidence={review.evidence} />}
      {tab === 'Workflow' && <WorkflowSection review={review} onViewTrace={onViewTrace} />}
      {tab === 'Decision' && (
        <DecisionSection
          review={review}
          decision={decision}
          setDecision={setDecision}
          rationale={rationale}
          setRationale={setRationale}
          deciding={deciding}
          exporting={exporting}
          onDecision={handleDecision}
          onExport={handleExport}
        />
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-subtle">
        <FileText className="w-3.5 h-3.5" />
        <span>{review.evidence?.length || 0} evidence record(s)</span>
        <Database className="w-3.5 h-3.5 ml-1" />
        <span>{review.audit_ids?.length || 0} audit ID(s)</span>
      </div>
    </div>
  );
}
