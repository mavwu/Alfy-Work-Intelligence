import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  BarChart3,
  Bot,
  FileDown,
  FileText,
  FolderGit2,
  History,
  Home,
  Import,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Settings,
} from 'lucide-react';
import './styles.css';
import { api, apiBase } from './services/api.js';

const navItems = [
  ['Dashboard', Home],
  ['Timeline', History],
  ['Work Log', Plus],
  ['Repositories', FolderGit2],
  ['Reports', FileDown],
  ['Chat', MessageSquare],
  ['Imports', Import],
  ['Settings', Settings],
];

function App() {
  const [view, setView] = useState('Dashboard');
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    api('/api/workspaces/default')
      .then(setWorkspace)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const openReports = () => setView('Reports');
    window.addEventListener('navigate-reports', openReports);
    return () => window.removeEventListener('navigate-reports', openReports);
  }, []);

  if (loading) return <ShellLoading />;
  if (!workspace?.onboarding_complete) {
    return <Onboarding workspace={workspace} onDone={(next) => setWorkspace(next)} />;
  }

  const Page = {
    Dashboard,
    Timeline: TimelinePage,
    'Work Log': WorkLog,
    Repositories,
    Reports,
    Chat,
    Imports,
    Settings: SettingsPage,
  }[view];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">A</div>
          <div>
            <strong>Alfy Work Intelligence</strong>
            <span>{workspace.name}</span>
          </div>
        </div>
        <nav>
          {navItems.map(([label, Icon]) => (
            <button key={label} className={view === label ? 'active' : ''} onClick={() => setView(label)} title={label}>
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <button className="primary sticky-action" onClick={() => setView('Work Log')}>
          <Plus size={18} />
          Log Work
        </button>
      </aside>
      <main className="main">
        <Page refreshKey={refreshKey} refresh={() => setRefreshKey((v) => v + 1)} />
      </main>
    </div>
  );
}

function ShellLoading() {
  return <div className="center-screen">Starting local work memory...</div>;
}

function Onboarding({ workspace, onDone }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState(workspace?.name || 'Ride Yanga');
  const [ai, setAi] = useState({ available: false, models: [], message: 'Checking Ollama...' });
  const [selectedModel, setSelectedModel] = useState('');
  const [repos, setRepos] = useState([]);
  const [repoForm, setRepoForm] = useState({ name: '', local_path: '', role: 'USER_APP', promotes_to_repository_id: '' });
  const [files, setFiles] = useState([]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    api('/api/ai/status').then((status) => {
      setAi(status);
      if (status.models?.[0]) setSelectedModel(status.models[0]);
    });
    api('/api/repositories').then(setRepos);
  }, []);

  async function saveWorkspace(done = false) {
    const next = await api('/api/workspaces/default', {
      method: 'PUT',
      body: { name, user_name: 'Alfy', onboarding_complete: done },
    });
    return next;
  }

  async function saveModel() {
    if (selectedModel) {
      await api('/api/settings', { method: 'PUT', body: { key: 'selected_model', value: selectedModel } });
    }
    setStep(4);
  }

  async function addRepo() {
    setMessage('');
    try {
      const payload = { ...repoForm, promotes_to_repository_id: repoForm.promotes_to_repository_id ? Number(repoForm.promotes_to_repository_id) : null };
      const created = await api('/api/repositories', { method: 'POST', body: payload });
      setRepos([...repos, created]);
      setRepoForm({ name: '', local_path: '', role: 'USER_APP', promotes_to_repository_id: '' });
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function uploadHistory() {
    if (!files.length) {
      setStep(6);
      return;
    }
    const form = new FormData();
    [...files].forEach((file) => form.append('files', file));
    await fetch(`${apiBase}/api/imports`, { method: 'POST', body: form });
    setStep(6);
  }

  async function finish() {
    const next = await saveWorkspace(true);
    onDone(next);
  }

  return (
    <div className="onboarding">
      <div className="onboarding-panel">
        <div className="stepper">Step {step} of 6</div>
        {step === 1 && (
          <>
            <h1>Welcome to Alfy Work Intelligence</h1>
            <p>A local-first timeline for engineering work, Git evidence, reports, and grounded Ride Yanga updates.</p>
            <button className="primary" onClick={() => setStep(2)}>Start</button>
          </>
        )}
        {step === 2 && (
          <>
            <h1>Create Workspace</h1>
            <label>Workspace name</label>
            <input value={name} onChange={(event) => setName(event.target.value)} />
            <button className="primary" onClick={async () => { await saveWorkspace(); setStep(3); }}>Continue</button>
          </>
        )}
        {step === 3 && (
          <>
            <h1>AI Setup</h1>
            <StatusPill ok={ai.available} label={ai.available ? 'Ollama connected' : 'Evidence Only Mode available'} />
            <p>{ai.message}</p>
            {ai.models?.length ? (
              <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
                {ai.models.map((model) => <option key={model}>{model}</option>)}
              </select>
            ) : (
              <p className="muted">You can still log work, scan repositories, search history, and generate deterministic drafts.</p>
            )}
            <button className="primary" onClick={saveModel}>Continue</button>
          </>
        )}
        {step === 4 && (
          <>
            <h1>Register Repositories</h1>
            <div className="form-grid">
              <input placeholder="Display name" value={repoForm.name} onChange={(e) => setRepoForm({ ...repoForm, name: e.target.value })} />
              <input placeholder="Local path" value={repoForm.local_path} onChange={(e) => setRepoForm({ ...repoForm, local_path: e.target.value })} />
              <select value={repoForm.role} onChange={(e) => setRepoForm({ ...repoForm, role: e.target.value })}>
                {['USER_APP', 'DRIVER_APP', 'DASHBOARD_API', 'WORKING_SANDBOX', 'OTHER'].map((role) => <option key={role}>{role}</option>)}
              </select>
              {repoForm.role === 'WORKING_SANDBOX' && (
                <select value={repoForm.promotes_to_repository_id} onChange={(e) => setRepoForm({ ...repoForm, promotes_to_repository_id: e.target.value })}>
                  <option value="">Promotes to...</option>
                  {repos.filter((repo) => repo.role === 'DASHBOARD_API').map((repo) => <option key={repo.id} value={repo.id}>{repo.name}</option>)}
                </select>
              )}
            </div>
            {message && <p className="error">{message}</p>}
            <button onClick={addRepo}>Add Repository</button>
            <List items={repos.map((repo) => `${repo.name} - ${repo.role}`)} />
            <button className="primary" onClick={() => setStep(5)}>Continue</button>
          </>
        )}
        {step === 5 && (
          <>
            <h1>Historical Import</h1>
            <p>Import April, May, June, or later reports and summaries. Supported: DOCX, PDF, Markdown, TXT.</p>
            <input type="file" multiple accept=".docx,.pdf,.md,.txt" onChange={(event) => setFiles(event.target.files)} />
            <button className="primary" onClick={uploadHistory}>Continue</button>
          </>
        )}
        {step === 6 && (
          <>
            <h1>Ready</h1>
            <p>Your local workspace is ready. Start with Log Work, scan repositories, or import more reports.</p>
            <button className="primary" onClick={finish}>Open Dashboard</button>
          </>
        )}
      </div>
    </div>
  );
}

function Dashboard() {
  const [data, setData] = useState(null);
  useEffect(() => { api('/api/dashboard').then(setData); }, []);
  if (!data) return <Section title="Dashboard"><Loading /></Section>;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  return (
    <section>
      <h1>{greeting}, {data.greeting_name}</h1>
      <div className="metric-grid">
        <Metric label="Work Days Logged" value={data.this_week.work_days_logged} />
        <Metric label="Git Commits" value={data.this_week.git_commits} />
        <Metric label="Areas Worked On" value={data.this_week.areas_worked_on.length} />
        <Metric label="Confirmed Work Items" value={data.this_week.confirmed_work_items} />
      </div>
      <div className="content-grid">
        <Panel title="Major Focus">
          <Metric label="Bugs Resolved" value={data.this_week.bugs_resolved} compact />
          <Metric label="Investigations" value={data.this_week.investigations} compact />
          <Metric label="Features Worked On" value={data.this_week.features_worked_on} compact />
          <Metric label="Pending Items" value={data.this_week.pending_items} compact />
        </Panel>
        <Panel title="Report Status">
          <p>{data.weekly_report_generated ? 'Weekly report generated' : 'Weekly report not generated'}</p>
          <button className="primary" onClick={() => window.dispatchEvent(new CustomEvent('navigate-reports'))}><FileText size={16} />Generate Weekly Report</button>
        </Panel>
      </div>
      <Panel title="Recent Work">
        {data.recent_work.length ? data.recent_work.map((item) => <WorkItemCard key={item.id} item={item} />) : <Empty text="No work logged this week yet." />}
      </Panel>
      <div className="content-grid">
        <Panel title="AI Insight">
          <p>{data.ai_insight || 'No evidence-backed insight is available yet.'}</p>
        </Panel>
        <Panel title="Repository Scan Health">
          {data.repository_health.length ? data.repository_health.map((repo) => (
            <div className="row" key={repo.id}>
              <span>{repo.name}</span>
              <span className="muted">{repo.last_scanned_at ? `Last scanned ${new Date(repo.last_scanned_at).toLocaleString()}` : 'Not scanned yet'}</span>
            </div>
          )) : <Empty text="No repositories registered." />}
        </Panel>
      </div>
    </section>
  );
}

function WorkLog() {
  const [rawText, setRawText] = useState('');
  const [result, setResult] = useState(null);
  const [items, setItems] = useState([]);
  useEffect(() => { api('/api/work-items?status=REVIEW').then(setItems); }, [result]);
  async function submit() {
    const next = await api('/api/work-logs', { method: 'POST', body: { raw_text: rawText } });
    setResult(next);
    setRawText('');
  }
  async function confirm(id) {
    await api(`/api/work-items/${id}/confirm`, { method: 'POST' });
    setItems(items.filter((item) => item.id !== id));
  }
  async function save(updated) {
    const saved = await api(`/api/work-items/${updated.id}`, { method: 'PUT', body: updated });
    setItems(items.map((item) => item.id === saved.id ? saved : item));
  }
  async function ignore(id) {
    await api(`/api/work-items/${id}/ignore`, { method: 'POST' });
    setItems(items.filter((item) => item.id !== id));
  }
  return (
    <Section title="Log Work" intro="Paste messy notes, a Codex summary, or a quick memory dump. The raw text is preserved exactly.">
      <textarea className="work-box" placeholder="What did you work on?" value={rawText} onChange={(event) => setRawText(event.target.value)} />
      <button className="primary" disabled={!rawText.trim()} onClick={submit}><Plus size={18} />Extract Work Items</button>
      {result && <Notice>{result.extracted_items.length} review item(s) created from the saved raw log.</Notice>}
      <h2>Review Queue</h2>
      {items.length ? items.map((item) => <ReviewCard key={item.id} item={item} onSave={save} onConfirm={confirm} onIgnore={ignore} />) : <Empty text="No inferred work waiting for review." />}
    </Section>
  );
}

function Repositories() {
  const [repos, setRepos] = useState([]);
  const [form, setForm] = useState({ name: '', local_path: '', role: 'USER_APP', promotes_to_repository_id: '' });
  const [job, setJob] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api('/api/repositories').then(setRepos); }, []);
  async function addRepo() {
    setError('');
    try {
      const created = await api('/api/repositories', { method: 'POST', body: { ...form, promotes_to_repository_id: form.promotes_to_repository_id ? Number(form.promotes_to_repository_id) : null } });
      setRepos([...repos, created]);
      setForm({ name: '', local_path: '', role: 'USER_APP', promotes_to_repository_id: '' });
    } catch (err) { setError(err.message); }
  }
  async function scan(repo) {
    const started = await api('/api/git/scan', { method: 'POST', body: { repository_id: repo.id } });
    setJob({ id: started.job_id, message: 'Starting scan...' });
    const interval = setInterval(async () => {
      const next = await api(`/api/jobs/${started.job_id}`);
      setJob(next);
      if (next.status !== 'RUNNING') {
        clearInterval(interval);
        api('/api/repositories').then(setRepos);
      }
    }, 1000);
  }
  return (
    <Section title="Repositories" intro="Register local Git folders. Scans are read-only and preserve source code on this machine.">
      <div className="form-grid">
        <input placeholder="Display name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input placeholder="C:/path/to/repo" value={form.local_path} onChange={(e) => setForm({ ...form, local_path: e.target.value })} />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {['USER_APP', 'DRIVER_APP', 'DASHBOARD_API', 'WORKING_SANDBOX', 'OTHER'].map((role) => <option key={role}>{role}</option>)}
        </select>
        {form.role === 'WORKING_SANDBOX' && (
          <select value={form.promotes_to_repository_id} onChange={(e) => setForm({ ...form, promotes_to_repository_id: e.target.value })}>
            <option value="">Canonical destination</option>
            {repos.filter((repo) => repo.role === 'DASHBOARD_API').map((repo) => <option key={repo.id} value={repo.id}>{repo.name}</option>)}
          </select>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      <button onClick={addRepo}><Plus size={16} />Register Repository</button>
      {job && <Notice>{job.status === 'FAILED' ? `${job.message}: ${job.error}` : `${job.message} ${job.progress ? `(${job.progress}%)` : ''}`}</Notice>}
      <div className="cards">
        {repos.map((repo) => (
          <article className="card" key={repo.id}>
            <h3>{repo.name}</h3>
            <p className="muted">{repo.role}</p>
            <p>{repo.local_path}</p>
            <p className="muted">{repo.last_scanned_at ? `Last scanned ${new Date(repo.last_scanned_at).toLocaleString()}` : 'Not scanned yet'}</p>
            <button onClick={() => scan(repo)}><RefreshCw size={16} />Scan Now</button>
          </article>
        ))}
      </div>
    </Section>
  );
}

function TimelinePage() {
  const [timeline, setTimeline] = useState([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  useEffect(() => { api('/api/timeline').then(setTimeline); }, []);
  async function search() {
    if (query.trim()) setResults(await api(`/api/search?q=${encodeURIComponent(query)}`));
  }
  return (
    <Section title="Timeline">
      <div className="searchbar">
        <Search size={18} />
        <input placeholder="Search work history" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} />
        <button onClick={search}>Search</button>
      </div>
      {results.length > 0 && <Panel title="Search Results">{results.map((row) => <EvidenceRow key={`${row.content_type}-${row.content_id}`} row={row} />)}</Panel>}
      {timeline.length ? timeline.map((group) => (
        <Panel key={group.month} title={group.month}>
          {group.items.map((item) => <WorkItemCard key={item.id} item={item} />)}
        </Panel>
      )) : <Empty text="No timeline entries yet." />}
    </Section>
  );
}

function Reports() {
  const [types, setTypes] = useState([]);
  const [reports, setReports] = useState([]);
  const [preview, setPreview] = useState(null);
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ report_type: 'Weekly Work Report', date_from: today, date_to: today, include_inferred_ids: [] });
  useEffect(() => { api('/api/reports/types').then((items) => { setTypes(items); setForm((f) => ({ ...f, report_type: items[1] || items[0] })); }); loadReports(); }, []);
  function loadReports() { api('/api/reports').then(setReports); }
  async function loadPreview() { setPreview(await api('/api/reports/preview', { method: 'POST', body: form })); }
  async function generate() {
    const report = await api('/api/reports', { method: 'POST', body: form });
    setReports([report, ...reports]);
  }
  async function approve(report) {
    const next = await api(`/api/reports/${report.id}/approve`, { method: 'PUT', body: { draft_markdown: report.draft_markdown, use_as_style_reference: false } });
    setReports(reports.map((item) => item.id === next.id ? next : item));
  }
  return (
    <Section title="Reports" intro="Generate drafts from confirmed evidence. Inferred work is shown for review before inclusion.">
      <div className="form-grid">
        <select value={form.report_type} onChange={(e) => setForm({ ...form, report_type: e.target.value })}>{types.map((type) => <option key={type}>{type}</option>)}</select>
        <input type="date" value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value })} />
        <input type="date" value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} />
      </div>
      <button onClick={loadPreview}>Review Evidence</button>
      <button className="primary" onClick={generate}><FileDown size={16} />Generate Draft</button>
      {preview && (
        <Panel title="Evidence Selection">
          <h3>Confirmed</h3>
          {preview.confirmed.length ? preview.confirmed.map((item) => <WorkItemCard key={item.id} item={item} />) : <Empty text="No confirmed work for this period." />}
          <h3>Inferred Needs Review</h3>
          {preview.inferred_needs_review.length ? preview.inferred_needs_review.map((item) => <WorkItemCard key={item.id} item={item} />) : <Empty text="No inferred work waiting in this period." />}
        </Panel>
      )}
      <Panel title="Drafts and Approved Reports">
        {reports.map((report) => <ReportCard key={report.id} report={report} onApprove={approve} />)}
      </Panel>
    </Section>
  );
}

function Imports() {
  const [files, setFiles] = useState([]);
  const [docs, setDocs] = useState([]);
  const [message, setMessage] = useState('');
  useEffect(() => { api('/api/imports').then(setDocs); }, []);
  async function upload() {
    const form = new FormData();
    [...files].forEach((file) => form.append('files', file));
    const result = await fetch(`${apiBase}/api/imports`, { method: 'POST', body: form }).then((r) => r.json());
    setMessage(`Imported ${result.filter((item) => !item.duplicate).length} new file(s).`);
    setDocs(await api('/api/imports'));
  }
  return (
    <Section title="Imports" intro="Import historical Ride Yanga reports and summaries for local extraction and search.">
      <input type="file" multiple accept=".docx,.pdf,.md,.txt" onChange={(e) => setFiles(e.target.files)} />
      <button className="primary" disabled={!files.length} onClick={upload}><Import size={16} />Import Files</button>
      {message && <Notice>{message}</Notice>}
      <div className="cards">
        {docs.map((doc) => (
          <article className="card" key={doc.id}>
            <h3>{doc.filename}</h3>
            <p>{doc.document_type}</p>
            <p className="muted">{doc.reporting_period || 'No period detected'}</p>
          </article>
        ))}
      </div>
    </Section>
  );
}

function Chat() {
  const [message, setMessage] = useState('');
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const suggestions = ['What did I do this week?', 'Give me an update for my boss.', 'What bugs did I fix this month?', 'What Ride Yanga achievements could support my CV?'];
  async function send(text = message) {
    if (!text.trim()) return;
    setMessages([...messages, { role: 'user', content: text }]);
    setMessage('');
    const response = await api('/api/chat', { method: 'POST', body: { message: text, conversation_id: conversationId } });
    setConversationId(response.conversation_id);
    setMessages((current) => [...current, { role: 'assistant', content: response.answer, evidence: response.evidence_summary }]);
  }
  return (
    <Section title="Chat" intro="Ask about your Ride Yanga work. Answers are grounded in local evidence.">
      {!messages.length && <div className="suggestions">{suggestions.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>}
      <div className="chat-log">{messages.map((m, i) => <div key={i} className={`message ${m.role}`}><p>{m.content}</p>{m.evidence && <small>{m.evidence}</small>}</div>)}</div>
      <div className="chat-input">
        <input placeholder="Ask about your Ride Yanga work" value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} />
        <button className="primary" onClick={() => send()}><Bot size={16} />Send</button>
      </div>
    </Section>
  );
}

function SettingsPage() {
  const [status, setStatus] = useState(null);
  const [settings, setSettings] = useState({});
  useEffect(() => { api('/api/ai/status').then(setStatus); api('/api/settings').then((data) => setSettings(data.settings)); }, []);
  async function save(key, value) {
    setSettings({ ...settings, [key]: value });
    await api('/api/settings', { method: 'PUT', body: { key, value } });
  }
  return (
    <Section title="Settings">
      <Panel title="AI Provider">
        <StatusPill ok={status?.available} label={status?.available ? 'Connected' : 'Unavailable'} />
        <p className="muted">{status?.message}</p>
        <label>Selected Ollama model</label>
        <select value={settings.selected_model || ''} onChange={(e) => save('selected_model', e.target.value)}>
          <option value="">Evidence Only Mode</option>
          {status?.models?.map((model) => <option key={model}>{model}</option>)}
        </select>
      </Panel>
      <Panel title="Git Ignore Patterns">
        <textarea value={settings.git_ignore_patterns || ''} onChange={(e) => save('git_ignore_patterns', e.target.value)} />
      </Panel>
      <Panel title="Data Location">
        <p className="muted">SQLite data is stored under the configured ALFY_DATA_DIR, defaulting to your Windows user profile.</p>
      </Panel>
    </Section>
  );
}

function ReportCard({ report, onApprove }) {
  const [text, setText] = useState(report.draft_markdown);
  const [instruction, setInstruction] = useState('');
  const [revisions, setRevisions] = useState([]);
  const [currentReport, setCurrentReport] = useState(report);
  useEffect(() => {
    setCurrentReport(report);
    setText(report.draft_markdown);
    api(`/api/reports/${report.id}/revisions`).then(setRevisions).catch(() => setRevisions([]));
  }, [report]);
  async function refine() {
    if (!instruction.trim()) return;
    const result = await api(`/api/reports/${report.id}/refine`, { method: 'POST', body: { instruction } });
    setCurrentReport(result.report);
    setText(result.report.draft_markdown);
    setInstruction('');
    setRevisions(await api(`/api/reports/${report.id}/revisions`));
  }
  async function restore(revisionId) {
    const restored = await api(`/api/reports/${report.id}/revisions/${revisionId}/restore`, { method: 'POST' });
    setCurrentReport(restored);
    setText(restored.draft_markdown);
  }
  return (
    <article className="card wide">
      <div className="row"><h3>{currentReport.title}</h3><StatusPill ok={currentReport.status === 'APPROVED'} label={currentReport.status} /></div>
      <textarea className="draft" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="refine-box">
        <input value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Refine this report..." />
        <button onClick={refine}>Refine</button>
      </div>
      {revisions.length > 0 && (
        <details className="revision-list">
          <summary>Revisions ({revisions.length})</summary>
          {revisions.map((revision) => (
            <div className="row" key={revision.id}>
              <span>Revision {revision.revision_number}: {revision.reason}</span>
              <button onClick={() => restore(revision.id)}>Restore</button>
            </div>
          ))}
        </details>
      )}
      <button onClick={() => onApprove({ ...currentReport, draft_markdown: text })}>Approve</button>
      <a className="button-link" href={`${apiBase}/api/reports/${report.id}/export/docx`}>{currentReport.status === 'APPROVED' ? 'DOCX' : 'Draft DOCX'}</a>
      <a className="button-link" href={`${apiBase}/api/reports/${report.id}/export/pptx`}>{currentReport.status === 'APPROVED' ? 'PPTX' : 'Draft PPTX'}</a>
    </article>
  );
}

function ReviewCard({ item, onSave, onConfirm, onIgnore }) {
  const [draft, setDraft] = useState(item);
  useEffect(() => setDraft(item), [item]);
  return (
    <article className="card wide">
      <div className="row"><h3>{item.title}</h3><StatusPill label={item.evidence_confidence} /></div>
      <div className="form-grid">
        <input value={draft.title || ''} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
        <input type="date" value={draft.work_date || ''} onChange={(e) => setDraft({ ...draft, work_date: e.target.value })} />
        <input value={draft.area || ''} onChange={(e) => setDraft({ ...draft, area: e.target.value })} placeholder="Area" />
        <input value={draft.work_type || ''} onChange={(e) => setDraft({ ...draft, work_type: e.target.value })} placeholder="Work type" />
      </div>
      <textarea value={draft.summary || ''} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} />
      <p className="muted">{item.area} - {item.work_type} - {item.work_date}</p>
      <button onClick={() => onSave(draft)}>Save Edits</button>
      <button className="primary" onClick={() => onConfirm(item.id)}>Confirm</button>
      <button onClick={() => onIgnore(item.id)}>Ignore</button>
    </article>
  );
}

function WorkItemCard({ item }) {
  return (
    <article className="timeline-item">
      <div>
        <strong>{item.title}</strong>
        <p>{item.summary}</p>
      </div>
      <span className="muted">{item.work_date} - {item.status}</span>
    </article>
  );
}

function EvidenceRow({ row }) {
  return <div className="timeline-item"><strong>{row.title}</strong><p>{row.body?.slice(0, 220)}</p><span className="muted">{row.source}</span></div>;
}

function Section({ title, intro, children }) {
  return <section><h1>{title}</h1>{intro && <p className="intro">{intro}</p>}{children}</section>;
}

function Panel({ title, children }) {
  return <div className="panel"><h2>{title}</h2>{children}</div>;
}

function Metric({ label, value, compact }) {
  return <div className={compact ? 'metric compact' : 'metric'}><span>{label}</span><strong>{value}</strong></div>;
}

function StatusPill({ ok, label }) {
  return <span className={`pill ${ok ? 'ok' : ''}`}>{label}</span>;
}

function Empty({ text }) {
  return <p className="empty">{text}</p>;
}

function Loading() {
  return <p className="muted">Loading...</p>;
}

function Notice({ children }) {
  return <div className="notice">{children}</div>;
}

function List({ items }) {
  return <ul className="plain-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

createRoot(document.getElementById('root')).render(<App />);
