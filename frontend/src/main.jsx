import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  BarChart3,
  Briefcase,
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
  ['Projects', Briefcase],
  ['Repositories', FolderGit2],
  ['Reports', FileDown],
  ['Chat', MessageSquare],
  ['Imports', Import],
  ['Settings', Settings],
];

function App() {
  const [view, setView] = useState('Dashboard');
  const [workspace, setWorkspace] = useState(null);
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  async function loadWorkspaces() {
    const rows = await api('/api/workspaces');
    setWorkspaces(rows);
    const active = rows.find((item) => item.is_active) || rows[0];
    if (active) setWorkspace(active);
    return rows;
  }

  useEffect(() => {
    loadWorkspaces()
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const openReports = () => setView('Reports');
    window.addEventListener('navigate-reports', openReports);
    return () => window.removeEventListener('navigate-reports', openReports);
  }, []);

  if (loading) return <ShellLoading />;
  if (!workspace?.onboarding_complete) {
    return <Onboarding workspace={workspace} onDone={async (next) => { setWorkspace(next); await loadWorkspaces(); }} />;
  }

  const Page = {
    Dashboard,
    Timeline: TimelinePage,
    'Work Log': WorkLog,
    Projects,
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
        <WorkspaceSwitcher
          workspace={workspace}
          workspaces={workspaces}
          onChanged={async (next) => {
            setWorkspace(next);
            await loadWorkspaces();
            setRefreshKey((value) => value + 1);
          }}
        />
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
        <Page key={`${workspace.id}-${view}-${refreshKey}`} workspace={workspace} setWorkspace={setWorkspace} reloadWorkspaces={loadWorkspaces} refreshKey={refreshKey} refresh={() => setRefreshKey((v) => v + 1)} />
      </main>
    </div>
  );
}

function ShellLoading() {
  return <div className="center-screen">Starting local work memory...</div>;
}

function WorkspaceSwitcher({ workspace, workspaces, onChanged }) {
  const [newName, setNewName] = useState('');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    name: workspace?.name || '',
    workspace_type: workspace?.workspace_type || '',
    description: workspace?.description || '',
    report_audience: workspace?.report_audience || '',
  });
  const [message, setMessage] = useState('');

  useEffect(() => {
    setDraft({
      name: workspace?.name || '',
      workspace_type: workspace?.workspace_type || '',
      description: workspace?.description || '',
      report_audience: workspace?.report_audience || '',
    });
  }, [workspace]);

  async function selectWorkspace(id) {
    const next = await api(`/api/workspaces/${id}/select`, { method: 'POST' });
    await onChanged(next);
  }

  async function createWorkspace() {
    setMessage('');
    if (!newName.trim()) return;
    try {
      const created = await api('/api/workspaces', { method: 'POST', body: { name: newName, workspace_type: 'Other' } });
      setNewName('');
      await selectWorkspace(created.id);
    } catch (err) {
      setMessage(err.message);
    }
  }

  async function saveWorkspace() {
    setMessage('');
    try {
      const saved = await api(`/api/workspaces/${workspace.id}`, { method: 'PUT', body: draft });
      setEditing(false);
      await onChanged(saved);
    } catch (err) {
      setMessage(err.message);
    }
  }

  return (
    <div className="workspace-switcher">
      <label>Workspace</label>
      <select value={workspace?.id || ''} onChange={(event) => selectWorkspace(event.target.value)}>
        {workspaces.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
      <div className="mini-form">
        <input placeholder="New workspace" value={newName} onChange={(event) => setNewName(event.target.value)} />
        <button onClick={createWorkspace}>Add</button>
      </div>
      <button onClick={() => setEditing(!editing)}>{editing ? 'Close' : 'Edit Workspace'}</button>
      {editing && (
        <div className="mini-form stacked">
          <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
          <select value={draft.workspace_type || ''} onChange={(event) => setDraft({ ...draft, workspace_type: event.target.value })}>
            <option value="">Type</option>
            {['Employment', 'Freelance', 'Internship', 'Client', 'Personal', 'Academic', 'Business', 'Other'].map((kind) => <option key={kind}>{kind}</option>)}
          </select>
          <input placeholder="Report audience" value={draft.report_audience || ''} onChange={(event) => setDraft({ ...draft, report_audience: event.target.value })} />
          <textarea placeholder="Description" value={draft.description || ''} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
          <button className="primary" onClick={saveWorkspace}>Save Workspace</button>
        </div>
      )}
      {message && <p className="error">{message}</p>}
    </div>
  );
}

function Onboarding({ workspace, onDone }) {
  const [step, setStep] = useState(1);
  const [name, setName] = useState(workspace?.name || 'Ride Yanga');
  const [displayName, setDisplayName] = useState(workspace?.user_name || 'Alfy');
  const [roleTitle, setRoleTitle] = useState('');
  const [reportAudience, setReportAudience] = useState('');
  const [ai, setAi] = useState({ available: false, models: [], message: 'Checking Ollama...' });
  const [selectedModel, setSelectedModel] = useState('');
  const [repos, setRepos] = useState([]);
  const [repoForm, setRepoForm] = useState({ name: '', local_path: '', role: 'USER_APP', promotes_to_repository_id: '' });
  const [files, setFiles] = useState([]);
  const [message, setMessage] = useState('');
  const [testMessage, setTestMessage] = useState('');

  useEffect(() => {
    api('/api/ai/status').then((status) => {
      setAi(status);
      if (status.selected_model && status.models?.includes(status.selected_model)) {
        setSelectedModel(status.selected_model);
      }
    });
    api('/api/repositories').then(setRepos);
    api('/api/settings').then((data) => {
      setRoleTitle(data.settings?.profile_role_title || '');
      setReportAudience(data.settings?.default_report_audience || data.style_profile?.audience || '');
      setDisplayName(data.settings?.profile_display_name || workspace?.user_name || 'Alfy');
    });
  }, []);

  async function saveWorkspace(done = false) {
    await api('/api/settings', { method: 'PUT', body: { key: 'profile_display_name', value: displayName } });
    await api('/api/settings', { method: 'PUT', body: { key: 'profile_role_title', value: roleTitle } });
    const next = await api('/api/workspaces/default', {
      method: 'PUT',
      body: { name, workspace_type: workspace?.workspace_type, report_audience: reportAudience, onboarding_complete: done },
    });
    return next;
  }

  async function saveModel() {
    if (selectedModel) {
      await api('/api/settings', { method: 'PUT', body: { key: 'selected_model', value: selectedModel } });
    }
    setStep(4);
  }

  async function refreshModels() {
    const status = await api('/api/ai/status');
    setAi(status);
    if (status.selected_model && status.models?.includes(status.selected_model)) {
      setSelectedModel(status.selected_model);
    }
  }

  async function testConnection() {
    const result = await api('/api/ai/test', { method: 'POST', body: { model: selectedModel } });
    setTestMessage(result.available ? `Connection test succeeded with ${result.selected_model || selectedModel || 'Evidence Only Mode'}.` : result.message);
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
            <p>A local-first workspace for recording work, reviewing extracted work items, preserving evidence, searching history, and generating grounded reports.</p>
            <button className="primary" onClick={() => setStep(2)}>Start</button>
          </>
        )}
        {step === 2 && (
          <>
            <h1>Create Workspace</h1>
            <label>Display name</label>
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            <label>Role title</label>
            <input placeholder="Optional" value={roleTitle} onChange={(event) => setRoleTitle(event.target.value)} />
            <label>Workspace name</label>
            <input value={name} onChange={(event) => setName(event.target.value)} />
            <label>Default report audience</label>
            <input placeholder="Stakeholder, supervisor, client, management..." value={reportAudience} onChange={(event) => setReportAudience(event.target.value)} />
            <button className="primary" onClick={async () => { await saveWorkspace(); setStep(3); }}>Continue</button>
          </>
        )}
        {step === 3 && (
          <>
            <h1>AI Setup</h1>
            <StatusPill ok={ai.available} label={ai.available ? 'Ollama connected' : 'Evidence Only Mode available'} />
            <p>{ai.message}</p>
            <p className="muted">Provider: Ollama</p>
            <p className="muted">Selected model: {selectedModel || ai.selected_model || 'Evidence Only Mode'}</p>
            <div className="row">
              <button onClick={refreshModels}><RefreshCw size={16} />Refresh Models</button>
              <button onClick={testConnection}><Bot size={16} />Test Connection</button>
            </div>
            {ai.models?.length ? (
              <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
                <option value="">Evidence Only Mode</option>
                {ai.models.map((model) => <option key={model}>{model}</option>)}
              </select>
            ) : (
              <p className="muted">You can still log work, scan repositories, search history, and generate deterministic drafts.</p>
            )}
            {testMessage && <Notice>{testMessage}</Notice>}
            <button className="primary" onClick={saveModel}>Continue</button>
          </>
        )}
        {step === 4 && (
          <>
            <h1>Register Git Repositories</h1>
            <p className="muted">Optional developer evidence. You can skip this and still log work, import documents, search history, and generate reports.</p>
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
            <p>Import previous reports, work notes, project documents, or summaries. Supported: DOCX, PDF, Markdown, TXT.</p>
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
        <Metric label="Developer Evidence" value={data.this_week.git_commits} />
        <Metric label="Areas Worked On" value={data.this_week.areas_worked_on.length} />
        <Metric label="Confirmed Work Items" value={data.this_week.confirmed_work_items} />
      </div>
      <div className="content-grid">
        <Panel title="Work Focus">
          <Metric label="Issues Resolved" value={data.this_week.bugs_resolved} compact />
          <Metric label="Investigations / Research" value={data.this_week.investigations} compact />
          <Metric label="Deliverables / Features" value={data.this_week.features_worked_on} compact />
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
        <Panel title="Developer Evidence Health">
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

function Projects({ workspace }) {
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState({ name: '', description: '', status: 'ACTIVE', category: '', start_date: '', end_date: '' });
  const [editingId, setEditingId] = useState(null);
  const [message, setMessage] = useState('');

  useEffect(() => { loadProjects(); }, [workspace?.id]);

  async function loadProjects(includeArchived = true) {
    setProjects(await api(`/api/projects?include_archived=${includeArchived}`));
  }

  async function saveProject() {
    setMessage('');
    try {
      if (editingId) {
        const saved = await api(`/api/projects/${editingId}`, { method: 'PUT', body: form });
        setProjects(projects.map((project) => project.id === saved.id ? saved : project));
      } else {
        const created = await api('/api/projects', { method: 'POST', body: form });
        setProjects([...projects, created]);
      }
      setForm({ name: '', description: '', status: 'ACTIVE', category: '', start_date: '', end_date: '' });
      setEditingId(null);
    } catch (err) {
      setMessage(err.message);
    }
  }

  function editProject(project) {
    setEditingId(project.id);
    setForm({
      name: project.name || '',
      description: project.description || '',
      status: project.status || 'ACTIVE',
      category: project.category || '',
      start_date: project.start_date || '',
      end_date: project.end_date || '',
    });
  }

  async function archiveProject(project) {
    const saved = await api(`/api/projects/${project.id}/archive`, { method: 'POST' });
    setProjects(projects.map((item) => item.id === saved.id ? saved : item));
  }

  return (
    <Section title="Projects" intro={`Organise work inside ${workspace?.name || 'this workspace'}. Existing work can stay unassigned until you classify it.`}>
      <div className="form-grid">
        <input placeholder="Project name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        <input placeholder="Category" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} />
        <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
          {['ACTIVE', 'PAUSED', 'COMPLETED', 'ARCHIVED'].map((status) => <option key={status}>{status}</option>)}
        </select>
        <input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} />
        <input type="date" value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} />
      </div>
      <textarea placeholder="Description" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
      {message && <p className="error">{message}</p>}
      <button className="primary" disabled={!form.name.trim()} onClick={saveProject}>{editingId ? 'Save Project' : 'Create Project'}</button>
      {editingId && <button onClick={() => { setEditingId(null); setForm({ name: '', description: '', status: 'ACTIVE', category: '', start_date: '', end_date: '' }); }}>Cancel Edit</button>}
      <div className="cards">
        {projects.length ? projects.map((project) => (
          <article className="card" key={project.id}>
            <div className="row"><h3>{project.name}</h3><StatusPill ok={project.status === 'ACTIVE'} label={project.status} /></div>
            <p>{project.description || 'No description.'}</p>
            <p className="muted">{project.category || 'No category'}{project.start_date ? ` - ${project.start_date}` : ''}{project.end_date ? ` to ${project.end_date}` : ''}</p>
            <button onClick={() => editProject(project)}>Edit</button>
            {project.status !== 'ARCHIVED' && <button onClick={() => archiveProject(project)}>Archive</button>}
          </article>
        )) : <Empty text="No projects in this workspace yet." />}
      </div>
    </Section>
  );
}

function WorkLog({ workspace }) {
  const [rawText, setRawText] = useState('');
  const [result, setResult] = useState(null);
  const [items, setItems] = useState([]);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState('');
  useEffect(() => {
    api('/api/projects').then(setProjects);
  }, [workspace?.id]);
  useEffect(() => { api('/api/work-items?status=REVIEW').then(setItems); }, [result, workspace?.id]);
  async function submit() {
    const next = await api('/api/work-logs', { method: 'POST', body: { raw_text: rawText, project_id: projectId ? Number(projectId) : null } });
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
    <Section title="Log Work" intro={`Paste messy notes, a Codex summary, or a quick memory dump for ${workspace?.name || 'this workspace'}. The raw text is preserved exactly.`}>
      <label>Project</label>
      <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
        <option value="">Unassigned</option>
        {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
      </select>
      <textarea className="work-box" placeholder="What did you work on?" value={rawText} onChange={(event) => setRawText(event.target.value)} />
      <button className="primary" disabled={!rawText.trim()} onClick={submit}><Plus size={18} />Extract Work Items</button>
      {result && <Notice>{result.extracted_items.length} review item(s) created via {result.analysis_mode}. {result.analysis_model ? `Model: ${result.analysis_model}.` : ''}</Notice>}
      <h2>Review Queue</h2>
      {items.length ? items.map((item) => <ReviewCard key={item.id} item={item} projects={projects} onSave={save} onConfirm={confirm} onIgnore={ignore} />) : <Empty text="No inferred work waiting for review." />}
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

function TimelinePage({ workspace }) {
  const [timeline, setTimeline] = useState([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState('');
  useEffect(() => { api('/api/projects').then(setProjects); }, [workspace?.id]);
  useEffect(() => {
    const suffix = projectId ? `?project_id=${projectId}` : '';
    api(`/api/timeline${suffix}`).then(setTimeline);
  }, [projectId, workspace?.id]);
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
      <div className="form-grid">
        <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
          <option value="">All projects</option>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
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

function Reports({ workspace }) {
  const [types, setTypes] = useState([]);
  const [reports, setReports] = useState([]);
  const [preview, setPreview] = useState(null);
  const [projects, setProjects] = useState([]);
  const today = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ report_type: 'Weekly Work Report', date_from: today, date_to: today, project_id: null, include_inferred_ids: [] });
  useEffect(() => {
    api('/api/reports/types').then((items) => { setTypes(items); setForm((f) => ({ ...f, report_type: items[1] || items[0] })); });
    api('/api/projects').then(setProjects);
    loadReports();
  }, [workspace?.id]);
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
        <select value={form.project_id || ''} onChange={(e) => setForm({ ...form, project_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">Entire workspace</option>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
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
    const firstAnalysis = result.find((item) => !item.duplicate)?.analysis_mode || 'EVIDENCE_ONLY';
    setMessage(`Imported ${result.filter((item) => !item.duplicate).length} new file(s) via ${firstAnalysis}.`);
    setDocs(await api('/api/imports'));
  }
  return (
    <Section title="Imports" intro="Import historical work documents, previous reports, work notes, or project documents for local extraction and search.">
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

function Chat({ workspace }) {
  const [message, setMessage] = useState('');
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const workspaceName = workspace?.name || 'this workspace';
  const suggestions = [
    'What work did I complete this week?',
    `Summarise my work for ${workspaceName}.`,
    'What issues did I resolve this month?',
    'Create CV evidence from my confirmed work.',
    'What remains pending?',
  ];
  async function send(text = message) {
    if (!text.trim()) return;
    setMessages([...messages, { role: 'user', content: text }]);
    setMessage('');
    const response = await api('/api/chat', { method: 'POST', body: { message: text, conversation_id: conversationId } });
    setConversationId(response.conversation_id);
    setMessages((current) => [...current, { role: 'assistant', content: response.answer, evidence: `${response.evidence_summary} (${response.analysis_mode})` }]);
  }
  return (
    <Section title="Chat" intro={`Ask about work in ${workspaceName}. Answers are grounded in local evidence.`}>
      {!messages.length && <div className="suggestions">{suggestions.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}</div>}
      <div className="chat-log">{messages.map((m, i) => <div key={i} className={`message ${m.role}`}><p>{m.content}</p>{m.evidence && <small>{m.evidence}</small>}</div>)}</div>
      <div className="chat-input">
        <input placeholder={`Ask about ${workspaceName}`} value={message} onChange={(e) => setMessage(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} />
        <button className="primary" onClick={() => send()}><Bot size={16} />Send</button>
      </div>
    </Section>
  );
}

function SettingsPage({ workspace, setWorkspace }) {
  const [status, setStatus] = useState(null);
  const [settings, setSettings] = useState({});
  const [workspaceForm, setWorkspaceForm] = useState({
    name: workspace?.name || '',
    user_name: workspace?.user_name || '',
    role_title: '',
    report_audience: '',
  });
  const [testMessage, setTestMessage] = useState('');
  useEffect(() => {
    api('/api/ai/status').then(setStatus);
    api('/api/settings').then((data) => {
      setSettings(data.settings);
      setWorkspaceForm({
        name: workspace?.name || '',
        user_name: data.settings?.profile_display_name || workspace?.user_name || '',
        role_title: data.settings?.profile_role_title || '',
        workspace_type: workspace?.workspace_type || '',
        description: workspace?.description || '',
        report_audience: data.settings?.default_report_audience || data.style_profile?.audience || '',
      });
    });
  }, [workspace]);
  async function save(key, value) {
    setSettings({ ...settings, [key]: value });
    await api('/api/settings', { method: 'PUT', body: { key, value } });
  }
  async function refreshModels() {
    setStatus(await api('/api/ai/status'));
  }
  async function testConnection() {
    const result = await api('/api/ai/test', { method: 'POST', body: { model: settings.selected_model || status?.selected_model || '' } });
    setTestMessage(result.available ? `Connection test succeeded with ${result.selected_model || settings.selected_model || 'Evidence Only Mode'}.` : result.message);
    setStatus(await api('/api/ai/status'));
  }
  async function saveWorkspaceProfile() {
    await api('/api/settings', { method: 'PUT', body: { key: 'profile_display_name', value: workspaceForm.user_name } });
    await api('/api/settings', { method: 'PUT', body: { key: 'profile_role_title', value: workspaceForm.role_title } });
    const next = await api('/api/workspaces/default', {
      method: 'PUT',
      body: {
        name: workspaceForm.name,
        workspace_type: workspaceForm.workspace_type,
        description: workspaceForm.description,
        report_audience: workspaceForm.report_audience,
      },
    });
    setWorkspace(next);
    setSettings({
      ...settings,
      profile_display_name: workspaceForm.user_name,
      profile_role_title: workspaceForm.role_title,
      default_report_audience: workspaceForm.report_audience,
    });
  }
  return (
    <Section title="Settings">
      <Panel title="Profile and Workspace">
        <label>Display name</label>
        <input value={workspaceForm.user_name} onChange={(e) => setWorkspaceForm({ ...workspaceForm, user_name: e.target.value })} />
        <label>Role title</label>
        <input placeholder="Optional" value={workspaceForm.role_title} onChange={(e) => setWorkspaceForm({ ...workspaceForm, role_title: e.target.value })} />
        <label>Workspace name</label>
        <input value={workspaceForm.name} onChange={(e) => setWorkspaceForm({ ...workspaceForm, name: e.target.value })} />
        <label>Workspace type</label>
        <select value={workspaceForm.workspace_type || ''} onChange={(e) => setWorkspaceForm({ ...workspaceForm, workspace_type: e.target.value })}>
          <option value="">Type</option>
          {['Employment', 'Freelance', 'Internship', 'Client', 'Personal', 'Academic', 'Business', 'Other'].map((kind) => <option key={kind}>{kind}</option>)}
        </select>
        <label>Default report audience</label>
        <input placeholder="Stakeholder, supervisor, client, management..." value={workspaceForm.report_audience} onChange={(e) => setWorkspaceForm({ ...workspaceForm, report_audience: e.target.value })} />
        <label>Workspace description</label>
        <textarea value={workspaceForm.description || ''} onChange={(e) => setWorkspaceForm({ ...workspaceForm, description: e.target.value })} />
        <button className="primary" onClick={saveWorkspaceProfile}>Save Profile</button>
      </Panel>
      <Panel title="AI Provider">
        <StatusPill ok={status?.available} label={status?.available ? 'Connected' : 'Unavailable'} />
        <p className="muted">{status?.message}</p>
        <p className="muted">Provider: Ollama</p>
        <p className="muted">Selected model: {settings.selected_model || status?.selected_model || 'Evidence Only Mode'}</p>
        <div className="row">
          <button onClick={refreshModels}><RefreshCw size={16} />Refresh Models</button>
          <button onClick={testConnection}><Bot size={16} />Test Connection</button>
        </div>
        <label>Selected Ollama model</label>
        <select value={settings.selected_model || ''} onChange={(e) => save('selected_model', e.target.value)}>
          <option value="">Evidence Only Mode</option>
          {status?.models?.map((model) => <option key={model}>{model}</option>)}
        </select>
        {status?.models?.length ? <List items={status.models} /> : <p className="muted">No local Ollama models were discovered.</p>}
        {testMessage && <Notice>{testMessage}</Notice>}
      </Panel>
      <Panel title="Git Ignore Patterns">
        <textarea value={settings.git_ignore_patterns || ''} onChange={(e) => save('git_ignore_patterns', e.target.value)} />
      </Panel>
      <Panel title="Data Location">
        <p className="muted">SQLite data is stored under the configured ALFY_DATA_DIR, defaulting to your local user profile.</p>
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

function ReviewCard({ item, projects = [], onSave, onConfirm, onIgnore }) {
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
        <select value={draft.project_id || ''} onChange={(e) => setDraft({ ...draft, project_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">Unassigned</option>
          {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
      </div>
      <textarea value={draft.summary || ''} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} />
      <p className="muted">{item.project_name || 'Unassigned'} - {item.area} - {item.work_type} - {item.work_date}</p>
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
        <p className="muted">{item.project_name || 'Unassigned'}</p>
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
