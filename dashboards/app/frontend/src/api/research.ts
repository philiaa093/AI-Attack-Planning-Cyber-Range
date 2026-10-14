export const RESEARCH_API_URL: string = import.meta.env.VITE_RESEARCH_API_URL ?? 'http://127.0.0.1:8001';
export interface ResearchTask {
  id: string; name: string; status: string; dependencies: string[];
  integration_scope: string; module_ids: string[];
}
interface Source { path: string; modified_at_utc: string | null; sha256: string | null; provenance?: string | null }
interface Metric { mean: number; ci_low: number | null; ci_high: number | null }
export interface EvaluationPackage {
  run_id: string; source: Source;
  verification: { state: string; error_code: string | null; hash_basis: string; experimental_claims: string };
  metrics: { split: string; candidate_id: string; values: Record<string, Metric> }[] | null;
}
export interface ResearchOverview {
  schema_version: 1; generated_at_utc: string; state: string;
  integration: { scope: string; fully_connected: false; execution_enabled: false; status_authority: string };
  task_source: Source; tasks: ResearchTask[];
  modules: { id: string; path: string; task_ids: string[]; availability: string; integration_scope: string }[];
  errors: { code: string; source: string }[];
  evaluations: { state: string; root: string; packages: EvaluationPackage[]; errors: { code: string; source: string }[] };
}

// Reject incompatible responses instead of presenting a fabricated empty result.
export function parseResearchOverview(value: unknown): ResearchOverview {
  const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
  const text = (v: unknown): v is string => typeof v === 'string' && v.length <= 512;
  const texts = (v: unknown): boolean => Array.isArray(v) && v.length <= 35 && v.every(text);
  const nullable = (v: unknown): boolean => v === null || text(v);
  const source = (v: unknown): boolean => object(v) && text(v.path) && nullable(v.sha256) && nullable(v.modified_at_utc) && (v.provenance === undefined || nullable(v.provenance));
  const errors = (v: unknown): boolean => Array.isArray(v) && v.length <= 100 && v.every(e => object(e) && text(e.code) && text(e.source));
  const bad = () => { throw new Error('INVALID_RESEARCH_RESPONSE'); };
  if (!object(value) || value.schema_version !== 1 || !text(value.generated_at_utc) || !text(value.state) ||
      !object(value.integration) || value.integration.fully_connected !== false || value.integration.execution_enabled !== false ||
      !source(value.task_source) || !Array.isArray(value.tasks) || value.tasks.length > 35 ||
      !value.tasks.every(t => object(t) && text(t.id) && /^TASK-\d{3}$/.test(t.id) && text(t.name) && text(t.status) && texts(t.dependencies) && texts(t.module_ids) && text(t.integration_scope)) ||
      !Array.isArray(value.modules) || value.modules.length > 64 || !value.modules.every(m => object(m) && text(m.id) && text(m.path) && texts(m.task_ids) && text(m.availability) && text(m.integration_scope)) ||
      !errors(value.errors) || !object(value.evaluations) || !text(value.evaluations.state) || !errors(value.evaluations.errors) ||
      !Array.isArray(value.evaluations.packages) || value.evaluations.packages.length > 32) return bad();
  const ids = value.tasks.map(t => (t as ResearchTask).id);
  if (new Set(ids).size !== ids.length) return bad();
  if (value.tasks.some(t => ['TASK-026', 'TASK-032'].includes(t.id) && t.status !== 'DEFERRED')) return bad();
  for (const p of value.evaluations.packages) {
    if (!object(p) || !text(p.run_id) || !source(p.source) || !object(p.verification) || !['VERIFIED', 'FAILED'].includes(String(p.verification.state)) || !nullable(p.verification.error_code)) return bad();
    if (p.verification.state === 'VERIFIED' && (!object(p.source) || p.source.provenance !== 'SIMULATED_FIXTURE')) return bad();
    if (p.verification.hash_basis !== 'SELF_COMPUTED_NOT_TRUSTED_PRODUCER_PIN' ||
        p.verification.experimental_claims !== 'UNRESOLVED') return bad();
    if (p.verification.state === 'FAILED' && p.metrics !== null) return bad();
    if (p.verification.state === 'VERIFIED' && (p.metrics === null || p.verification.error_code !== null)) return bad();
    if (p.metrics !== null) {
      if (!Array.isArray(p.metrics) || p.metrics.length !== 4) return bad();
      const seen = new Set<string>();
      for (const row of p.metrics) {
        if (!object(row) || !text(row.split) || !text(row.candidate_id) || !object(row.values)) return bad();
        if (!['validation', 'test'].includes(row.split) || !['synthetic-review', 'synthetic-random'].includes(row.candidate_id) || seen.has(`${row.split}:${row.candidate_id}`)) return bad();
        seen.add(`${row.split}:${row.candidate_id}`);
        for (const key of ['success_rate', 'mean_steps', 'mean_cost_credits']) {
          const metric = row.values[key];
          if (!object(metric) || typeof metric.mean !== 'number' || !Number.isFinite(metric.mean) ||
              ![metric.ci_low, metric.ci_high].every(n => n === null || typeof n === 'number' && Number.isFinite(n))) return bad();
          if (metric.mean < 0 || metric.mean > 1e12 || (key === 'success_rate' && metric.mean > 1) ||
              (metric.ci_low === null) !== (metric.ci_high === null)) return bad();
          if (typeof metric.ci_low === 'number' && typeof metric.ci_high === 'number' &&
              (Math.abs(metric.ci_low) > 1e12 || Math.abs(metric.ci_high) > 1e12 ||
               metric.ci_low > metric.mean || metric.mean > metric.ci_high)) return bad();
        }
      }
    }
  }
  return value as unknown as ResearchOverview;
}

export async function getResearchOverview(signal?: AbortSignal): Promise<ResearchOverview> {
  const response = await fetch(`${RESEARCH_API_URL}/api/research/overview`, { signal, cache: 'no-store' });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return parseResearchOverview(await response.json());
}
