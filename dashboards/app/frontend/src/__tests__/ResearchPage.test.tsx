import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ResearchPage } from '../pages/ResearchPage';
import { LanguageProvider } from '../i18n/LanguageContext';
import { displayValue } from '../i18n/displayValue';
import { parseResearchOverview, type ResearchOverview } from '../api/research';

const fixture: ResearchOverview = {
  schema_version: 1, generated_at_utc: '2026-10-13T00:00:00Z', state: 'OK',
  integration: {scope: 'READ_ONLY_OVERVIEW', fully_connected: false, execution_enabled: false, status_authority: 'TASKS.md'},
  task_source: {path: 'TASKS.md', modified_at_utc: '2026-10-13T00:00:00Z', sha256: 'a'.repeat(64)},
  tasks: [
    {id: 'TASK-019', name: 'Knowledge state store', status: 'IMPLEMENTED', dependencies: ['TASK-018'], integration_scope: 'OFFLINE_MODULE', module_ids: ['state']},
    {id: 'TASK-032', name: 'Dashboard', status: 'DEFERRED', dependencies: ['TASK-028'], integration_scope: 'READ_ONLY_WEB_EXISTING', module_ids: []},
  ],
  modules: [{id: 'state', path: 'runtime/knowledge_state_store.py', task_ids: ['TASK-019'], availability: 'PRESENT', integration_scope: 'OFFLINE_MODULE'}],
  errors: [], evaluations: {state: 'OK', root: 'runtime/evaluation-runs', packages: [], errors: []},
};

afterEach(() => vi.unstubAllGlobals());
describe('Vietnamese read-only research workspace', () => {
  it('shows canonical deferred status, filters tasks and sends only a GET request', async () => {
    const fetcher = vi.fn().mockResolvedValue({ok: true, json: async () => structuredClone(fixture)});
    vi.stubGlobal('fetch', fetcher);
    const onViewRuns = vi.fn();
    render(<LanguageProvider initialLang="vi"><ResearchPage onViewRuns={onViewRuns}/></LanguageProvider>);
    await screen.findByRole('heading', {name: 'Kho tri thức và trạng thái'});
    expect(screen.getByTitle('DEFERRED')).toHaveTextContent('Tạm hoãn');
    expect(screen.getByText('Có mô-đun ngoại tuyến · chưa nối thực thi')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Trạng thái trong tài liệu'), {target: {value: 'DEFERRED'}});
    expect(screen.queryByRole('heading', {name: 'Kho tri thức và trạng thái'})).not.toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Bảng điều khiển nghiên cứu'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Xem bằng chứng các phiên'}));
    expect(onViewRuns).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0][1]).not.toHaveProperty('method');
  });

  it('marks cached results stale if a later refresh fails', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ok:true, json:async () => structuredClone(fixture)}).mockRejectedValueOnce(new Error('offline'));
    vi.stubGlobal('fetch', fetcher);
    render(<LanguageProvider initialLang="vi"><ResearchPage onViewRuns={() => {}}/></LanguageProvider>);
    await screen.findByRole('heading', {name:'Kho tri thức và trạng thái'});
    fireEvent.click(screen.getByRole('button', {name:'Cập nhật dữ liệu'}));
    await screen.findByRole('alert');
    expect(screen.getByText('Dữ liệu bên dưới là lần tải trước.')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name:'Kho tri thức và trạng thái'})).toBeInTheDocument();
  });

  it('does not invent zero counts when the service is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(<LanguageProvider initialLang="vi"><ResearchPage onViewRuns={() => {}}/></LanguageProvider>);
    await screen.findByRole('alert');
    expect(screen.queryByText('Nhiệm vụ đọc được')).not.toBeInTheDocument();
  });

  it('refuses incompatible execution claims and malformed metric envelopes', () => {
    expect(parseResearchOverview(structuredClone(fixture)).tasks).toHaveLength(2);
    expect(() => parseResearchOverview({...fixture, integration: {...fixture.integration, fully_connected: true}})).toThrow();
    expect(() => parseResearchOverview({...fixture, tasks:[fixture.tasks[0],fixture.tasks[0]]})).toThrow();
    expect(() => parseResearchOverview({...fixture, evaluations:{...fixture.evaluations,packages:[{run_id:'x',source:fixture.task_source,verification:{state:'VERIFIED',error_code:null},metrics:[{split:'test',candidate_id:'x',values:{}}]}]}})).toThrow();
  });

  it('translates known reasons while retaining unknown audit identifiers', async () => {
    expect(displayValue('MISSING_API_KEY','vi')).toBe('Chưa cấu hình khóa API');
    expect(displayValue('COMPLETED','vi')).toBe('Đã kết thúc');
    expect(displayValue('TASK-032','vi')).toBe('TASK-032');
    expect(displayValue('__proto__','vi')).toBe('__proto__');
    expect(displayValue('constructor','vi')).toBe('constructor');
    expect(displayValue('COMPLETED','en')).toBe('COMPLETED');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async () => structuredClone(fixture)}));
    render(<LanguageProvider initialLang="vi"><ResearchPage onViewRuns={() => {}}/></LanguageProvider>);
    await waitFor(() => expect(document.documentElement.lang).toBe('vi'));
  });

  it('rejects promoted deferred tasks and unverified or inconsistent metrics', () => {
    for (const id of ['TASK-026', 'TASK-032']) {
      expect(() => parseResearchOverview({...fixture, tasks: [{...fixture.tasks[1], id, status: 'VALIDATED'}]})).toThrow();
    }
    const pkg = {
      run_id: 'RUN-EVAL-' + 'a'.repeat(32),
      source: {...fixture.task_source, provenance: 'SIMULATED_FIXTURE'},
      verification: {state: 'VERIFIED', error_code: null as string | null,
        hash_basis: 'SELF_COMPUTED_NOT_TRUSTED_PRODUCER_PIN', experimental_claims: 'UNRESOLVED'},
      metrics: ['validation', 'test'].flatMap(split => ['synthetic-review', 'synthetic-random'].map(candidate_id => ({
        split, candidate_id, values: {
          success_rate: {mean: 0.5, ci_low: 0.1 as number | null, ci_high: 0.9 as number | null},
          mean_steps: {mean: 2, ci_low: null, ci_high: null},
          mean_cost_credits: {mean: 3, ci_low: null, ci_high: null},
        },
      }))),
    };
    const parse = (p: unknown) => parseResearchOverview({...fixture, evaluations: {...fixture.evaluations, packages: [p]}});
    expect(parse(pkg).evaluations.packages).toHaveLength(1);
    expect(parse({...pkg, verification: {...pkg.verification, state: 'FAILED', error_code: 'HASH_MISMATCH'}, metrics: null}).evaluations.packages[0].metrics).toBeNull();
    expect(() => parse({...pkg, verification: {...pkg.verification, state: 'FAILED'}})).toThrow();
    expect(() => parse({...pkg, metrics: null})).toThrow();
    expect(() => parse({...pkg, verification: {...pkg.verification, experimental_claims: 'VALIDATED'}})).toThrow();
    expect(() => parse({...pkg, verification: {...pkg.verification, error_code: 'HASH_MISMATCH'}})).toThrow();
    for (const metric of [
      {mean: -1, ci_low: null, ci_high: null},
      {mean: 1.1, ci_low: null, ci_high: null},
      {mean: 0.5, ci_low: null, ci_high: 0.9},
      {mean: 0.5, ci_low: 0.7, ci_high: 0.9},
      {mean: 0.5, ci_low: 0.1, ci_high: 0.4},
    ]) {
      const broken = structuredClone(pkg);
      broken.metrics[0].values.success_rate = metric;
      expect(() => parse(broken)).toThrow();
    }
  });
});
