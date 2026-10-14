import React, { useEffect, useState } from 'react';
import { RefreshCw, ArrowRight, FileCheck2 } from 'lucide-react';
import { getResearchOverview, RESEARCH_API_URL, type ResearchOverview } from '../api/research';
import { useLanguage } from '../i18n/LanguageContext';
import { displayValue } from '../i18n/displayValue';
import { StatusBadge } from '../components/StatusBadge';

const names = ['','Bộ kiểm tra nền tảng','Tài liệu quản trị dự án','Hợp đồng an toàn','Danh mục hành động','Hợp đồng dữ liệu trạng thái','Hợp đồng dữ liệu quan sát','Hợp đồng bằng chứng','Kịch bản thực nghiệm','Dữ liệu chuẩn để đánh giá','Cấu hình thực nghiệm','Mạng thực nghiệm','Ứng dụng mục tiêu A','Ứng dụng mục tiêu B','Mục tiêu đối chứng','Nhập báo cáo khám phá','Xử lý báo cáo ZAP','Xử lý báo cáo Nuclei','Chuẩn hóa quan sát','Kho tri thức và trạng thái','Giao tiếp bộ lập kế hoạch','Lập kế hoạch theo quy tắc','Lập kế hoạch bằng mô hình ngôn ngữ','Môi trường học tăng cường','Mô hình phần thưởng','Phương pháp Q-learning','Phương án DQN/PPO','Bộ lập kế hoạch kết hợp','Bộ chạy thực nghiệm','Tính các chỉ số đánh giá','Đánh giá trên tập kiểm tra','Phân tích thống kê','Bảng điều khiển nghiên cứu','Tạo báo cáo','Gói tái lập kết quả','Kiểm tra tổng thể'];
const groupOf = (id: string) => { const n = Number(id.slice(-3)); return n <= 10 ? 'foundation' : n <= 14 ? 'lab' : n <= 19 ? 'data' : n <= 27 ? 'planning' : 'evaluation'; };
const groups = [['all','Tất cả nhóm','All groups'],['foundation','Nền tảng','Foundation'],['lab','Môi trường','Lab'],['data','Dữ liệu và quan sát','Data and observations'],['planning','Lập kế hoạch','Planning'],['evaluation','Đánh giá và báo cáo','Evaluation and reporting']];

export const ResearchPage: React.FC<{onViewRuns: () => void}> = ({onViewRuns}) => {
  const {lang} = useLanguage(); const vi = lang === 'vi';
  const [data, setData] = useState<ResearchOverview | null>(null);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(true);
  const [revision, setRevision] = useState(0); const [query, setQuery] = useState('');
  const [group, setGroup] = useState('all'); const [state, setState] = useState('all');
  const [packageId, setPackageId] = useState('');
  useEffect(() => {
    const controller = new AbortController(); let active = true;
    setBusy(true); setError('');
    getResearchOverview(controller.signal).then(result => { if (active) setData(result); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : 'UNKNOWN'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; controller.abort(); };
  }, [revision]);
  const scope = (value: string) => value === 'READ_ONLY_WEB_EXISTING' ? (vi ? 'Đã có trang xem dữ liệu' : 'Existing data viewer')
    : value === 'OFFLINE_MODULE' ? (vi ? 'Có mô-đun ngoại tuyến · chưa nối thực thi' : 'Offline module · execution not connected')
    : (vi ? 'Đang theo dõi từ tài liệu' : 'Tracked from documentation');
  const tasks = data?.tasks.filter(t => (group === 'all' || groupOf(t.id) === group) && (state === 'all' || t.status === state) && `${t.id} ${t.name} ${names[Number(t.id.slice(-3))]}`.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi'))) ?? [];
  const packages = data?.evaluations.packages ?? [];
  const selected = packages.find(p => p.run_id === packageId) ?? packages[0];
  return <main className="research-page">
    <div className="research-heading"><div><div className="cc-eyebrow">{vi ? 'Đề tài / Tiến độ và kết quả' : 'Research / Progress and results'}</div><h2>{vi ? 'Tiến độ đề tài' : 'Research progress'}</h2><p>{vi ? 'Theo dõi 35 nhiệm vụ chính, mã nguồn liên quan và kết quả đánh giá ngoại tuyến từ dự án.' : 'Track the 35 canonical tasks, associated modules and saved offline evaluation results.'}</p></div>
      <button className="cc-button" onClick={() => setRevision(n => n + 1)} disabled={busy}><RefreshCw size={16} className={busy ? 'animate-spin' : ''}/>{vi ? 'Cập nhật dữ liệu' : 'Refresh'}</button>
    </div>
    <p className="research-note">{vi ? 'Trang này kết nối dữ liệu tiến độ và kết quả đã lưu. Có mã nguồn không đồng nghĩa đã nối thực thi hoặc đã kiểm chứng toàn bộ nhiệm vụ.' : 'This page connects saved progress and results. Module presence does not establish execution integration or full task validation.'}</p>
    {error && <section className="research-panel" role="alert"><h3>{vi ? 'Chưa lấy được dữ liệu tiến độ' : 'Research data unavailable'}</h3><p>{vi ? 'Kiểm tra dịch vụ xem dữ liệu, rồi bấm Cập nhật dữ liệu.' : 'Check the read-only viewer service, then refresh.'}</p><p className="research-source">{RESEARCH_API_URL} · {error}</p>{data && <p>{vi ? 'Dữ liệu bên dưới là lần tải trước.' : 'The data below is from the previous fetch.'}</p>}</section>}
    {busy && !data && <p role="status" className="research-empty">{vi ? 'Đang đọc dữ liệu dự án…' : 'Reading project data…'}</p>}
    {data && <>
      <div className="research-summary">
        <div className="research-stat"><strong>{data.tasks.length || '—'}</strong><span>{vi ? 'Nhiệm vụ đọc được' : 'Tasks read'}</span></div>
        <div className="research-stat"><strong>{data.tasks.length ? data.tasks.filter(t => t.status === 'IMPLEMENTED').length : '—'}</strong><span>{vi ? 'Được ghi là đã triển khai' : 'Recorded as implemented'}</span></div>
        <div className="research-stat"><strong>{data.tasks.length ? data.tasks.filter(t => t.status === 'VALIDATED').length : '—'}</strong><span>{vi ? 'Được ghi là đã kiểm chứng' : 'Recorded as validated'}</span></div>
        <div className="research-stat"><strong>{data.evaluations.state === 'ERROR' ? '—' : packages.length}</strong><span>{vi ? 'Gói kết quả ngoại tuyến' : 'Offline result packages'}</span></div>
      </div>
      {(data.errors.length > 0 || data.evaluations.errors.length > 0) && <details className="research-panel"><summary>{vi ? 'Một số nguồn dữ liệu chưa đọc được' : 'Some data sources could not be read'}</summary>{[...data.errors,...data.evaluations.errors].map((e,i) => <p className="research-source" key={i}>{e.source} · {e.code}</p>)}</details>}
      <section className="research-panel" aria-label={vi ? 'Kết quả đánh giá ngoại tuyến' : 'Offline evaluation results'}>
        <div className="research-heading"><div><h3><FileCheck2 size={20} className="inline mr-2"/>{vi ? 'Kết quả đánh giá ngoại tuyến' : 'Offline evaluation results'}</h3><p>{vi ? 'Số liệu đọc từ các gói đã lưu; dữ liệu mô phỏng được ghi nhãn riêng.' : 'Metrics are read from saved packages; simulated data is explicitly labeled.'}</p></div><button className="cc-button" onClick={onViewRuns}>{vi ? 'Xem bằng chứng các phiên' : 'View run evidence'}<ArrowRight size={16}/></button></div>
        {packages.length === 0 ? <p className="research-empty">{vi ? (data.evaluations.state === 'ERROR' ? 'Chưa đọc được thư mục kết quả.' : 'Chưa có gói kết quả trong thư mục được chỉ định.') : 'No readable result packages available.'}</p> : <>
          <div className="research-filters"><label>{vi ? 'Gói kết quả' : 'Result package'}<select value={selected?.run_id ?? ''} onChange={e => setPackageId(e.target.value)}>{packages.map(p => <option key={p.run_id} value={p.run_id}>{p.run_id}</option>)}</select></label></div>
          {selected && <><div className="flex flex-wrap gap-3 items-center"><StatusBadge status={selected.verification.state}/><span className="cc-chip">{selected.source.provenance ? displayValue(selected.source.provenance,lang) : (vi ? 'Nguồn dữ liệu chưa xác minh' : 'Unverified source')}</span></div>
            <p className="cc-caption mt-3">{vi ? 'Xác minh ở đây chỉ đối chiếu mã băm và cấu trúc tệp bằng mã băm vừa đọc; chưa xác thực bên tạo gói hay kết luận khoa học.' : 'Verification compares file hashes and envelopes using the currently read hash; it does not authenticate the producer or validate scientific claims.'}</p>
            {selected.verification.error_code && <p role="alert" className="cc-stale mt-3">{vi ? 'Không thể xác minh gói: ' : 'Package verification failed: '}{selected.verification.error_code}</p>}
            {selected.verification.state === 'VERIFIED' && selected.metrics && <div className="overflow-x-auto mt-4"><table className="w-full text-sm text-left"><caption className="text-left pb-3 cc-caption">{vi ? 'Chỉ số của bài đánh giá mô phỏng ngoại tuyến' : 'Metrics from offline simulated evaluation'}</caption><thead><tr>{(vi ? ['Tập dữ liệu','Phương pháp','Tỷ lệ đạt tiêu chí','Số bước trung bình','Chi phí trung bình (đơn vị mô phỏng)'] : ['Split','Candidate','Criterion success rate','Mean steps','Mean cost (simulated credits)']).map(h => <th key={h} className="p-3 border-b">{h}</th>)}</tr></thead><tbody>{selected.metrics.map(row => <tr key={`${row.split}-${row.candidate_id}`}><td className="p-3 border-b">{row.split === 'test' ? (vi ? 'Kiểm tra' : 'Test') : (vi ? 'Hiệu chỉnh' : 'Validation')}</td><td className="p-3 border-b">{row.candidate_id === 'synthetic-review' ? (vi ? 'Xem xét mô phỏng' : 'Simulated review') : (vi ? 'Ngẫu nhiên mô phỏng' : 'Simulated random')}</td>{['success_rate','mean_steps','mean_cost_credits'].map(key => <td className="p-3 border-b" key={key}>{key === 'success_rate' ? `${(row.values[key].mean * 100).toLocaleString(vi ? 'vi-VN' : 'en-US',{maximumFractionDigits:2})}%` : row.values[key].mean.toLocaleString(vi ? 'vi-VN' : 'en-US',{maximumFractionDigits:2})}</td>)}</tr>)}</tbody></table></div>}
            <details className="mt-4 research-source"><summary>{vi ? 'Nguồn và mã băm của gói' : 'Package source and hash'}</summary><p>{selected.source.path}</p><p>SHA-256: {selected.source.sha256 ?? '—'}</p></details>
          </>}
        </>}
      </section>
      <section aria-label={vi ? 'Danh sách nhiệm vụ' : 'Task inventory'}>
        <h3 className="text-xl font-semibold">{vi ? 'Các nhiệm vụ chính' : 'Canonical tasks'}</h3>
        <div className="research-filters"><label>{vi ? 'Tìm nhiệm vụ' : 'Find a task'}<input value={query} onChange={e => setQuery(e.target.value)} placeholder={vi ? 'Mã hoặc tên nhiệm vụ…' : 'Task ID or name…'}/></label><label>{vi ? 'Nhóm công việc' : 'Group'}<select value={group} onChange={e => setGroup(e.target.value)}>{groups.map(g => <option key={g[0]} value={g[0]}>{g[vi ? 1 : 2]}</option>)}</select></label><label>{vi ? 'Trạng thái trong tài liệu' : 'Documented status'}<select value={state} onChange={e => setState(e.target.value)}><option value="all">{vi ? 'Tất cả trạng thái' : 'All statuses'}</option>{['VALIDATED','IMPLEMENTED','SPEC_ONLY','DEFERRED','UNRESOLVED','BLOCKED','TBD'].map(s => <option key={s} value={s}>{displayValue(s,lang)}</option>)}</select></label></div>
        <p className="cc-caption mb-3" role="status">{vi ? `Hiển thị ${tasks.length} / ${data.tasks.length} nhiệm vụ` : `Showing ${tasks.length} / ${data.tasks.length} tasks`}</p>
        <div className="research-task-grid">{tasks.map(task => <article key={task.id} className="research-task"><div className="research-task-top"><code>{task.id}</code><StatusBadge status={task.status}/></div><h4>{vi ? names[Number(task.id.slice(-3))] || task.name : task.name}</h4><p>{scope(task.integration_scope)}</p><details><summary>{vi ? 'Mã nguồn và phụ thuộc' : 'Modules and dependencies'}</summary><p>{vi ? 'Tên trong nguồn' : 'Source name'}: {task.name}</p><p>{vi ? 'Phụ thuộc' : 'Depends on'}: {task.dependencies.length ? task.dependencies.map(d => d === 'all-required' ? (vi ? 'Tất cả nhiệm vụ bắt buộc' : 'All required tasks') : d).join(', ') : (vi ? 'Không có' : 'None')}</p>{task.module_ids.map(id => { const m = data.modules.find(m => m.id === id); return m && <p key={id}><code>{m.path}</code> · {m.availability === 'PRESENT' ? (vi ? 'Có tệp' : 'File present') : (vi ? 'Chưa đọc được tệp' : 'File unavailable')}</p>; })}</details></article>)}</div>
        {tasks.length === 0 && <p className="research-empty">{vi ? 'Không có nhiệm vụ phù hợp bộ lọc.' : 'No tasks match the filters.'}</p>}
      </section>
      <footer className="research-panel research-source"><p>{vi ? 'Nguồn trạng thái' : 'Status source'}: {data.task_source.path}</p><p>{vi ? 'Đọc lúc' : 'Read at'}: {data.generated_at_utc}</p><details><summary>{vi ? 'Mã băm nguồn để đối chiếu' : 'Source hash for reference'}</summary>SHA-256: {data.task_source.sha256 ?? '—'}</details><p className="mt-2">{vi ? 'Trạng thái toàn nhiệm vụ được giữ theo nguồn. Nhiệm vụ 026 và 032 vẫn tạm hoãn; trang này không xác nhận hoàn tất hay tự nâng trạng thái.' : 'Task status follows the canonical source. Tasks 026 and 032 remain deferred; this viewer does not approve or promote task status.'}</p></footer>
    </>}
  </main>;
};
