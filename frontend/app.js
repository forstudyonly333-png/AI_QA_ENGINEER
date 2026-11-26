/* AI QA Engineer Frontend Controller */

const AGENTS_META = [
  { id: 'code_loader', name: 'Code Loader Agent', icon: '📂', desc: 'Scans directory, ignores venv/.git, reads requirements & README.' },
  { id: 'code_analyzer', name: 'Code Analyzer Agent', icon: '🌳', desc: 'Parses Python AST once to extract functions, classes, and imports.' },
  { id: 'bug_analyzer', name: 'Bug Analyzer Agent', icon: '🪲', desc: 'Finds bare excepts, hardcoded secrets, prints, and long functions.' },
  { id: 'test_generator', name: 'Test Generator Agent', icon: '🧪', desc: 'Builds suggested test scenarios and starter pytest skeletons.' },
  { id: 'report_agent', name: 'Report Agent', icon: '📄', desc: 'Exports quality scores and structured JSON & HTML reports.' },
  { id: 'ai_reviewer', name: 'AI Reviewer Agent', icon: '✨', desc: 'Generates Gemini architectural review and top 3 action items.' },
];

const STATE = {
  workspacePath: '',
  currentBrowsePath: '',
  latestBugs: [],
  activeBugFilter: 'all',
  pollTimer: null,
};

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function generateJobId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  return 'job-' + Date.now() + '-' + Math.random().toString(16).slice(2, 8);
}

async function safeFetchJson(url, options = {}, timeoutMs = 95000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const rawText = await response.text();
    let parsed = null;
    if (rawText && rawText.trim()) {
      try {
        parsed = JSON.parse(rawText);
      } catch (jsonErr) {
        throw new Error(`Invalid JSON response from server (HTTP ${response.status}).`);
      }
    }
    if (!response.ok) {
      const serverMsg = parsed && typeof parsed === 'object' ? parsed.message || parsed.detail : '';
      throw new Error(serverMsg || `Server returned HTTP ${response.status}`);
    }
    if (!parsed || typeof parsed !== 'object') {
      throw new Error('Server returned an empty or invalid response payload.');
    }
    return parsed;
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Request timed out while waiting for the backend.');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function showBanner(el, type, text) {
  if (!el) return;
  el.className = `status-banner status-${type}`;
  el.textContent = text;
}

function renderWorkflowCards(stages = null) {
  const grid = document.getElementById('workflowGrid');
  if (!grid) return;
  const stageMap = new Map();
  if (Array.isArray(stages)) {
    stages.forEach((s) => {
      if (s && s.id) stageMap.set(s.id, s);
    });
  }

  grid.innerHTML = AGENTS_META.map((agent, idx) => {
    const st = stageMap.get(agent.id);
    const status = st ? String(st.status || 'pending').toLowerCase() : 'idle';
    let badgeClass = 'badge-neutral';
    let label = 'Idle';
    if (status === 'completed') {
      badgeClass = 'badge-success';
      label = st.duration_ms ? `Done (${st.duration_ms}ms)` : 'Completed';
    } else if (status === 'running') {
      badgeClass = 'badge-ai';
      label = 'Running...';
    } else if (status === 'failed') {
      badgeClass = 'badge-error';
      label = 'Failed';
    } else if (status === 'skipped') {
      badgeClass = 'badge-warning';
      label = 'Skipped';
    } else if (status === 'pending') {
      badgeClass = 'badge-neutral';
      label = 'Queued';
    }
    const detail = st && st.detail ? st.detail : 'Waiting for project analysis';

    return `
      <div class="card card-hover agent-card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
          <span class="agent-step-num">Step 0${idx + 1}</span>
          <span class="badge ${badgeClass}">${escapeHtml(label)}</span>
        </div>
        <div class="agent-icon">${agent.icon}</div>
        <h3 class="agent-name">${escapeHtml(agent.name)}</h3>
        <p class="agent-desc">${escapeHtml(agent.desc)}</p>
        <div class="agent-detail">${escapeHtml(detail)}</div>
      </div>
    `;
  }).join('');
}

function updateProgressPanel(stages) {
  if (!Array.isArray(stages) || stages.length === 0) return;
  const doneCount = stages.filter((s) => ['completed', 'failed', 'skipped'].includes(s.status)).length;
  const runningStage = stages.find((s) => s.status === 'running');
  const pct = Math.round((doneCount / stages.length) * 100);
  document.getElementById('progressFill').style.width = `${pct}%`;
  document.getElementById('progressPercentLabel').textContent = `${pct}%`;
  document.getElementById('progressStageLabel').textContent = runningStage
    ? `Running: ${runningStage.name} — ${runningStage.detail || ''}`
    : pct === 100
      ? 'Pipeline stages finished'
      : 'Preparing agents...';
}

function renderBugsList() {
  const container = document.getElementById('bugFindingsBody');
  const bugs = STATE.latestBugs || [];
  const filtered = STATE.activeBugFilter === 'all'
    ? bugs
    : bugs.filter((b) => String(b.severity || 'info').toLowerCase() === STATE.activeBugFilter);

  if (filtered.length === 0) {
    container.innerHTML = `<p style="color:var(--text-secondary);margin:0;">No findings match the selected filter (${escapeHtml(STATE.activeBugFilter)}).</p>`;
    return;
  }

  container.innerHTML = filtered.slice(0, 150).map((b) => {
    const sev = String(b.severity || 'info').toLowerCase();
    const badgeCls = sev === 'critical' ? 'badge-error' : sev === 'warning' ? 'badge-warning' : 'badge-ai';
    const fileLabel = b.file_name || (b.file ? String(b.file).split(/[\\/]/).pop() : 'Unknown file');
    const lineTxt = b.line ? `Line ${b.line}` : 'File-level';
    const fnTxt = b.function ? ` · fn <code>${escapeHtml(b.function)}()</code>` : '';
    return `
      <div class="finding-item">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
          <span class="badge ${badgeCls}">${escapeHtml(sev.toUpperCase())}</span>
          <span style="font-size:0.78rem;color:var(--text-secondary);">${escapeHtml(fileLabel)} · ${escapeHtml(lineTxt)}${fnTxt}</span>
        </div>
        <div style="font-size:0.86rem;font-weight:600;color:var(--text-main);">${escapeHtml(b.bug || 'Issue detected')}</div>
      </div>
    `;
  }).join('');
}

function renderAnalysisDashboard(data) {
  const analysis = data && typeof data.analysis === 'object' && data.analysis ? data.analysis : {};
  const project = analysis.project && typeof analysis.project === 'object' ? analysis.project : {};
  const bugs = Array.isArray(data.bug) ? data.bug : [];
  const tests = Array.isArray(data.test_cases) ? data.test_cases : [];
  const report = data && typeof data.report === 'object' && data.report ? data.report : {};
  const aiDetails = data && typeof data.ai_review_details === 'object' && data.ai_review_details ? data.ai_review_details : {};
  const errors = Array.isArray(data.errors) ? data.errors : [];

  document.getElementById('analyzerEmptyState').classList.add('hidden');
  document.getElementById('resultsSection').classList.remove('hidden');

  // 1. Project Information
  const fw = project.framework || 'None';
  document.getElementById('projFrameworkBadge').textContent = fw === 'None' ? 'Python' : `Python · ${fw}`;
  const reqs = Array.isArray(project.requirements) ? project.requirements : [];
  document.getElementById('projectInfoBody').innerHTML = `
    <div style="display:grid;gap:8px;">
      <div><strong>Project:</strong> ${escapeHtml(project.project_name || 'N/A')}</div>
      <div><strong>Path:</strong> <code style="font-size:0.78rem;word-break:break-all;">${escapeHtml(data.project_path || project.project_path || '')}</code></div>
      <div><strong>Framework:</strong> ${escapeHtml(fw)}</div>
      <div><strong>Duration:</strong> ${escapeHtml(data.duration_ms || 0)} ms</div>
      <div><strong>Dependencies (${reqs.length}):</strong>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;">
          ${reqs.length ? reqs.slice(0, 14).map((r) => `<span class="badge badge-neutral">${escapeHtml(r)}</span>`).join('') : '<span style="color:var(--text-secondary);">None listed</span>'}
        </div>
      </div>
    </div>
  `;

  // 2. Code Metrics + Visual Composition Bars
  const score = typeof report.quality_score === 'number' ? report.quality_score : '--';
  const scoreBadge = document.getElementById('qualityScoreBadge');
  scoreBadge.textContent = `Quality Score: ${score}/100`;
  scoreBadge.className = typeof score === 'number'
    ? score >= 80 ? 'badge badge-success' : score >= 50 ? 'badge badge-warning' : 'badge badge-error'
    : 'badge badge-neutral';

  const totalLines = Number(analysis.total_lines || 0);
  const blankLines = Number(analysis.total_blank_lines || 0);
  const commentLines = Number(analysis.total_comments || 0);
  const codeLines = Math.max(0, totalLines - blankLines - commentLines);
  const safeDenom = Math.max(1, totalLines);

  const critCount = bugs.filter((b) => b.severity === 'critical').length;
  const warnCount = bugs.filter((b) => b.severity === 'warning').length;
  const infoCount = bugs.filter((b) => b.severity === 'info').length;

  document.getElementById('codeMetricsBody').innerHTML = `
    <div class="metric-mini-grid">
      <div class="metric-mini"><div class="metric-mini-val">${escapeHtml(analysis.total_files ?? 0)}</div><div class="metric-mini-lbl">Python Files (${escapeHtml(analysis.parsed_files ?? 0)} parsed)</div></div>
      <div class="metric-mini"><div class="metric-mini-val">${escapeHtml(totalLines)}</div><div class="metric-mini-lbl">Total Lines</div></div>
      <div class="metric-mini"><div class="metric-mini-val">${escapeHtml(analysis.total_functions ?? 0)}</div><div class="metric-mini-lbl">Functions</div></div>
      <div class="metric-mini"><div class="metric-mini-val">${escapeHtml(analysis.total_classes ?? 0)}</div><div class="metric-mini-lbl">Classes</div></div>
      <div class="metric-mini"><div class="metric-mini-val">${escapeHtml(analysis.total_imports ?? 0)}</div><div class="metric-mini-lbl">Imports</div></div>
      <div class="metric-mini"><div class="metric-mini-val">${escapeHtml(bugs.length)}</div><div class="metric-mini-lbl">Findings (${critCount} critical)</div></div>
    </div>
    <div class="bar-row">
      <div class="bar-label-row"><span>Code Lines (${codeLines})</span><span>${Math.round((codeLines / safeDenom) * 100)}%</span></div>
      <div class="bar-bg"><div class="bar-val" style="width:${Math.round((codeLines / safeDenom) * 100)}%;background:linear-gradient(90deg,var(--pink-primary),var(--purple-deep));"></div></div>
    </div>
    <div class="bar-row">
      <div class="bar-label-row"><span>Comments (${commentLines}) &amp; Blank Lines (${blankLines})</span><span>${Math.round(((commentLines + blankLines) / safeDenom) * 100)}%</span></div>
      <div class="bar-bg"><div class="bar-val" style="width:${Math.round(((commentLines + blankLines) / safeDenom) * 100)}%;background:#A78BFA;"></div></div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
      <span class="badge badge-error">Critical: ${critCount}</span>
      <span class="badge badge-warning">Warnings: ${warnCount}</span>
      <span class="badge badge-ai">Info: ${infoCount}</span>
    </div>
  `;

  // 3. Function Analysis
  const functions = Array.isArray(analysis.functions) ? analysis.functions : [];
  document.getElementById('functionCountBadge').textContent = `${functions.length} functions`;
  document.getElementById('functionAnalysisBody').innerHTML = functions.length
    ? `<table class="data-table">
        <thead><tr><th>Function</th><th>File</th><th>Lines</th><th>Status</th></tr></thead>
        <tbody>
          ${functions.slice(0, 100).map((f) => `
            <tr>
              <td><code>${escapeHtml(f.name)}(${escapeHtml((f.parameters || []).join(', '))})</code></td>
              <td>${escapeHtml(f.file_name || f.file || '')}:${escapeHtml(f.line || '')}</td>
              <td>${escapeHtml(f.lines || '-')}</td>
              <td>${f.has_docstring ? '<span class="badge badge-success">Docstring</span>' : '<span class="badge badge-warning">No Docstring</span>'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`
    : '<p style="color:var(--text-secondary);margin:0;">No functions detected.</p>';

  // 4. Class Analysis
  const classes = Array.isArray(analysis.classes) ? analysis.classes : [];
  document.getElementById('classCountBadge').textContent = `${classes.length} classes`;
  document.getElementById('classAnalysisBody').innerHTML = classes.length
    ? `<table class="data-table">
        <thead><tr><th>Class</th><th>File</th><th>Bases</th><th>Methods</th></tr></thead>
        <tbody>
          ${classes.slice(0, 80).map((c) => `
            <tr>
              <td><strong>${escapeHtml(c.name)}</strong></td>
              <td>${escapeHtml(c.file_name || c.file || '')}:${escapeHtml(c.line || '')}</td>
              <td>${escapeHtml((c.bases || []).join(', ') || 'object')}</td>
              <td>${escapeHtml(c.method_count ?? (c.methods || []).length)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`
    : '<p style="color:var(--text-secondary);margin:0;">No classes detected.</p>';

  // 5. Import Analysis
  const imports = Array.isArray(analysis.imports) ? analysis.imports : [];
  document.getElementById('importCountBadge').textContent = `${imports.length} imports`;
  document.getElementById('importAnalysisBody').innerHTML = imports.length
    ? imports.slice(0, 100).map((imp) => `
        <div class="finding-item" style="padding:8px 10px;">
          <div style="font-size:0.84rem;font-weight:600;"><code>${escapeHtml(imp.module || '')}</code></div>
          <div style="font-size:0.76rem;color:var(--text-secondary);">${escapeHtml(imp.file_name || '')}:${escapeHtml(imp.line || '')} · ${escapeHtml(imp.type || 'import')}</div>
        </div>
      `).join('')
    : '<p style="color:var(--text-secondary);margin:0;">No imports found.</p>';

  // 6. Bug Findings
  STATE.latestBugs = bugs;
  STATE.activeBugFilter = 'all';
  renderBugsList();

  // 7. Generated Test Cases
  document.getElementById('testCasesBody').innerHTML = tests.length
    ? tests.slice(0, 60).map((tc) => `
        <div class="finding-item">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px;">
            <strong><code>${escapeHtml(tc.function || 'function')}()</code></strong>
            <span style="font-size:0.76rem;color:var(--text-secondary);">${escapeHtml(tc.file || '')}:${escapeHtml(tc.line || '')}</span>
          </div>
          <ul style="margin:4px 0 6px;padding-left:18px;font-size:0.82rem;color:var(--text-secondary);">
            ${(tc.test_scenarios || []).map((s) => `<li>${escapeHtml(s)}</li>`).join('')}
          </ul>
          ${tc.sample_pytest ? `<pre class="code-pre" style="padding:8px;font-size:0.74rem;max-height:110px;">${escapeHtml(tc.sample_pytest)}</pre>` : ''}
        </div>
      `).join('')
    : '<p style="color:var(--text-secondary);margin:0;">No suggested test cases generated.</p>';

  // 8. AI Review Card + Full Section
  renderAiReview(aiDetails, data.ai_review);

  // Errors / Notices
  const errorsPanel = document.getElementById('errorsPanel');
  if (errors.length > 0) {
    errorsPanel.classList.remove('hidden');
    document.getElementById('errorsCountBadge').textContent = `${errors.length} notice(s)`;
    document.getElementById('errorsListBody').innerHTML = errors.map((e) => `
      <div class="finding-item">
        <span class="badge badge-warning">${escapeHtml(e.stage || 'pipeline')}</span>
        <span style="font-size:0.84rem;margin-left:8px;">${escapeHtml(e.file ? `${e.file}: ` : '')}${escapeHtml(e.message || e.error || 'Warning')}</span>
      </div>
    `).join('');
  } else {
    errorsPanel.classList.add('hidden');
  }

  // Update Reports & Workflow & Stats
  if (Array.isArray(data.stages)) {
    renderWorkflowCards(data.stages);
  }
  loadLatestReport();
  loadStats();
}

function renderAiReview(aiDetails, fallbackText) {
  const details = aiDetails && typeof aiDetails === 'object' ? aiDetails : {};
  const status = String(details.status || 'unavailable').toLowerCase();

  const miniBadge = document.getElementById('aiMiniStatusBadge');
  const fullBadge = document.getElementById('aiReviewStateBadge');
  let badgeClass = 'badge-neutral';
  let label = 'Awaiting Analysis';
  if (status === 'completed') {
    badgeClass = 'badge-success';
    label = 'Review Completed';
  } else if (status === 'unavailable') {
    badgeClass = 'badge-warning';
    label = 'Review Unavailable';
  } else if (status === 'failed') {
    badgeClass = 'badge-error';
    label = 'Review Failed';
  }

  miniBadge.className = `badge ${badgeClass}`;
  miniBadge.textContent = label;
  fullBadge.className = `badge ${badgeClass}`;
  fullBadge.textContent = label;

  const summaryText = details.summary || fallbackText || 'No AI review text returned.';
  document.getElementById('aiSummaryCardBody').innerHTML = `<p style="margin:0;white-space:pre-wrap;">${escapeHtml(summaryText)}</p>`;
  document.getElementById('aiReviewSummary').textContent = summaryText;
  document.getElementById('aiReviewModelNote').textContent = details.model
    ? `Model: ${details.model}`
    : 'Gemini AI Reviewer';

  document.getElementById('aiArchFeedback').textContent = details.architecture_feedback || '—';
  document.getElementById('aiMaintainability').textContent = details.maintainability || '—';

  const secList = Array.isArray(details.security_observations) ? details.security_observations : [];
  document.getElementById('aiSecurityList').innerHTML = secList.length
    ? secList.map((item) => `<li>${escapeHtml(item)}</li>`).join('')
    : '<li>No additional AI security observations returned.</li>';

  const actions = Array.isArray(details.action_items) ? details.action_items : [];
  document.getElementById('aiActionList').innerHTML = actions.length
    ? actions.map((item) => `<li>${escapeHtml(item)}</li>`).join('')
    : '<li>No action items returned.</li>';
}

async function loadHealth() {
  try {
    const data = await safeFetchJson('/api/health', {}, 8000);
    STATE.workspacePath = data.workspace_path || '';
    const badge = document.getElementById('heroAiStatusBadge');
    if (data.ai_configured) {
      badge.className = 'badge badge-success';
      badge.textContent = `Gemini Ready (${data.ai_model || 'gemini-3.8-flash'})`;
    } else {
      badge.className = 'badge badge-warning';
      badge.textContent = 'Gemini API Key Missing (Static Analysis Active)';
    }
  } catch (err) {
    console.warn('Health check failed:', err);
  }
}

async function loadStats() {
  try {
    const data = await safeFetchJson('/api/stats', {}, 8000);
    document.getElementById('statProjects').textContent = String(data.projects_analyzed ?? 0);
    document.getElementById('statIssues').textContent = String(data.issues_detected ?? 0);
    document.getElementById('statTests').textContent = String(data.test_cases_generated ?? 0);
    document.getElementById('statAgents').textContent = String(data.analysis_agents ?? 6);
    document.getElementById('statProjectsNote').textContent = data.has_data
      ? 'Recorded across real backend runs'
      : 'No runs recorded yet';
  } catch (err) {
    console.warn('Stats load failed:', err);
  }
}

async function loadLatestReport() {
  const statusBadge = document.getElementById('reportStatusBadge');
  const metaBody = document.getElementById('reportMetaBody');
  const preview = document.getElementById('jsonReportPreview');
  try {
    const report = await safeFetchJson('/reports/latest', {}, 8000);
    statusBadge.className = 'badge badge-success';
    statusBadge.textContent = `Score: ${report.quality_score ?? '--'}/100`;
    const s = report.summary || {};
    metaBody.innerHTML = `
      <div><strong>Project:</strong> ${escapeHtml((report.project || {}).project_name || 'N/A')}</div>
      <div><strong>Generated:</strong> ${escapeHtml(report.generated_at || 'Saved on disk')}</div>
      <div style="margin-top:6px;">
        Files: <strong>${escapeHtml(s.total_files ?? 0)}</strong> ·
        Bugs: <strong>${escapeHtml(s.total_bugs ?? 0)}</strong> ·
        Suggested Tests: <strong>${escapeHtml(s.total_test_cases ?? 0)}</strong>
      </div>
    `;
    preview.textContent = JSON.stringify(report, null, 2).slice(0, 6000);
  } catch (err) {
    statusBadge.className = 'badge badge-neutral';
    statusBadge.textContent = 'Not Generated';
    metaBody.textContent = 'No report saved yet. Run a project analysis to generate JSON and HTML reports.';
    preview.textContent = 'No report generated yet.';
  }
}

function stopPolling() {
  if (STATE.pollTimer) {
    clearInterval(STATE.pollTimer);
    STATE.pollTimer = null;
  }
}

async function handleAnalyzeSubmit(e) {
  e.preventDefault();
  const projectPath = document.getElementById('projectPath').value.trim();
  const statusBox = document.getElementById('statusBox');
  const submitBtn = document.getElementById('submitBtn');
  const submitSpinner = document.getElementById('submitSpinner');
  const submitBtnText = document.getElementById('submitBtnText');
  const progressPanel = document.getElementById('progressPanel');

  if (!projectPath) {
    showBanner(statusBox, 'error', 'Please enter a valid project directory path.');
    return;
  }

  const jobId = generateJobId();
  submitBtn.disabled = true;
  submitSpinner.classList.remove('hidden');
  submitBtnText.textContent = 'Analyzing...';
  showBanner(statusBox, 'info', 'Running 6-agent static analysis & AI review pipeline...');
  progressPanel.classList.remove('hidden');
  document.getElementById('progressFill').style.width = '10%';
  document.getElementById('progressPercentLabel').textContent = '10%';
  document.getElementById('progressStageLabel').textContent = 'Starting Code Loader Agent...';

  stopPolling();
  STATE.pollTimer = setInterval(async () => {
    try {
      const prog = await safeFetchJson(`/analyze/status/${encodeURIComponent(jobId)}`, {}, 5000);
      if (prog && Array.isArray(prog.stages) && prog.stages.length > 0) {
        renderWorkflowCards(prog.stages);
        updateProgressPanel(prog.stages);
      }
    } catch (_) {
      // Non-fatal polling skip
    }
  }, 450);

  try {
    const data = await safeFetchJson(
      '/analyze',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_path: projectPath, job_id: jobId }),
      },
      100000
    );

    if (data.status === 'error') {
      if (Array.isArray(data.stages)) renderWorkflowCards(data.stages);
      throw new Error(data.message || 'Project analysis failed.');
    }

    document.getElementById('progressFill').style.width = '100%';
    document.getElementById('progressPercentLabel').textContent = '100%';
    document.getElementById('progressStageLabel').textContent = 'Analysis pipeline complete';

    if (data.status === 'partial') {
      showBanner(statusBox, 'warning', data.message || 'Analysis completed with warnings or partial results.');
    } else {
      showBanner(statusBox, 'success', data.message || 'Analysis completed successfully!');
    }

    renderAnalysisDashboard(data);
  } catch (err) {
    showBanner(statusBox, 'error', `Analysis Error: ${err.message}`);
  } finally {
    stopPolling();
    submitBtn.disabled = false;
    submitSpinner.classList.add('hidden');
    submitBtnText.textContent = 'Start Analysis';
  }
}

async function runDebugger() {
  const lang = document.getElementById('debugLanguage').value;
  const code = document.getElementById('rawCodeInput').value;
  const debugBtn = document.getElementById('debugBtn');
  const debugSpinner = document.getElementById('debugSpinner');
  const debugBtnText = document.getElementById('debugBtnText');
  const debugStatus = document.getElementById('debugStatus');
  const resultSection = document.getElementById('debugResultSection');

  if (lang !== 'python') {
    showBanner(
      debugStatus,
      'warning',
      `${lang.toUpperCase()} debugging is planned on our roadmap and is not yet implemented. Switch to Python to run AST validation & AI auto-fix.`
    );
    return;
  }

  if (!code.trim()) {
    showBanner(debugStatus, 'error', 'Please paste a Python code snippet before running the debugger.');
    return;
  }

  debugBtn.disabled = true;
  debugSpinner.classList.remove('hidden');
  debugBtnText.textContent = 'Validating...';
  showBanner(debugStatus, 'info', 'Running AST syntax validation and Gemini auto-fix...');
  resultSection.classList.add('hidden');

  try {
    const data = await safeFetchJson(
      '/debug-snippet',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: lang }),
      },
      35000
    );

    if (data.status === 'error') {
      throw new Error(data.error_message || data.message || 'Debugger failed.');
    }

    resultSection.classList.remove('hidden');
    document.getElementById('debugExplanation').textContent = data.explanation || 'Analysis finished.';
    document.getElementById('codeBefore').textContent = code;
    document.getElementById('codeAfter').textContent = data.fixed_code || code;

    const diffWrap = document.getElementById('debugDiffWrap');
    if (data.diff && data.diff.trim()) {
      diffWrap.classList.remove('hidden');
      document.getElementById('debugDiff').textContent = data.diff;
    } else {
      diffWrap.classList.add('hidden');
    }

    if (data.validation_status && !data.has_error) {
      showBanner(debugStatus, 'success', 'Code passed Python AST validation cleanly!');
    } else if (data.validation_status) {
      showBanner(debugStatus, 'success', 'Syntax error fixed and verified with Python AST validation!');
    } else {
      showBanner(debugStatus, 'warning', data.explanation || data.validation_error || 'Syntax error detected.');
    }
  } catch (err) {
    showBanner(debugStatus, 'error', `Debugging Failed: ${err.message}`);
  } finally {
    debugBtn.disabled = false;
    debugSpinner.classList.add('hidden');
    debugBtnText.textContent = '⚡ Analyze & Auto-Fix';
  }
}

// Directory Browser Modal
async function openBrowseModal(targetPath = '') {
  const modal = document.getElementById('browseModal');
  modal.classList.remove('hidden');
  await loadBrowseDirectory(targetPath || STATE.workspacePath || '');
}

async function loadBrowseDirectory(path) {
  const listEl = document.getElementById('browseFolderList');
  const currentEl = document.getElementById('browseCurrentPath');
  const driveRow = document.getElementById('browseDriveRow');
  const upBtn = document.getElementById('browseUpBtn');

  listEl.innerHTML = '<div style="padding:14px;color:var(--text-secondary);">Loading directories...</div>';
  try {
    const query = path ? `?path=${encodeURIComponent(path)}` : '';
    const data = await safeFetchJson(`/api/browse${query}`, {}, 10000);
    if (data.status === 'error') {
      listEl.innerHTML = `<div style="padding:14px;color:var(--error);">${escapeHtml(data.message)}</div>`;
      return;
    }

    STATE.currentBrowsePath = data.current_path || '';
    currentEl.textContent = STATE.currentBrowsePath;
    upBtn.disabled = !data.parent_path;
    upBtn.onclick = () => {
      if (data.parent_path) loadBrowseDirectory(data.parent_path);
    };

    driveRow.innerHTML = (data.drives || []).map((drv) => `
      <button type="button" class="pill-btn" data-drive="${escapeHtml(drv)}">${escapeHtml(drv)}</button>
    `).join('');
    driveRow.querySelectorAll('[data-drive]').forEach((btn) => {
      btn.addEventListener('click', () => loadBrowseDirectory(btn.getAttribute('data-drive')));
    });

    const dirs = Array.isArray(data.directories) ? data.directories : [];
    listEl.innerHTML = dirs.length
      ? dirs.map((d) => `
          <div class="folder-row" data-folder="${escapeHtml(d.path)}">
            <span>📁 ${escapeHtml(d.name)}</span>
            <span style="font-size:0.75rem;color:var(--text-secondary);">Open →</span>
          </div>
        `).join('')
      : '<div style="padding:14px;color:var(--text-secondary);">No subdirectories inside this folder.</div>';

    listEl.querySelectorAll('[data-folder]').forEach((row) => {
      row.addEventListener('click', () => loadBrowseDirectory(row.getAttribute('data-folder')));
    });
  } catch (err) {
    listEl.innerHTML = `<div style="padding:14px;color:var(--error);">${escapeHtml(err.message)}</div>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  renderWorkflowCards(null);
  loadHealth();
  loadStats();
  loadLatestReport();

  // Mobile Menu Toggle
  const mobileMenuBtn = document.getElementById('mobileMenuBtn');
  const mobileDrawer = document.getElementById('mobileDrawer');
  mobileMenuBtn.addEventListener('click', () => {
    const isOpen = mobileDrawer.classList.toggle('open');
    mobileMenuBtn.setAttribute('aria-expanded', String(isOpen));
  });
  mobileDrawer.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => mobileDrawer.classList.remove('open'));
  });

  // Analyzer Form
  document.getElementById('analyzeForm').addEventListener('submit', handleAnalyzeSubmit);
  document.getElementById('useWorkspaceBtn').addEventListener('click', () => {
    document.getElementById('projectPath').value = STATE.workspacePath || './';
  });
  document.getElementById('clearResultsBtn').addEventListener('click', () => {
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('analyzerEmptyState').classList.remove('hidden');
    document.getElementById('statusBox').className = 'status-banner hidden';
    document.getElementById('progressPanel').classList.add('hidden');
    renderWorkflowCards(null);
  });

  // Bug Severity Filters
  document.getElementById('bugFilterRow').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-bug-filter]');
    if (!btn) return;
    STATE.activeBugFilter = btn.getAttribute('data-bug-filter') || 'all';
    renderBugsList();
  });

  // Browse Modal
  const browseModal = document.getElementById('browseModal');
  document.getElementById('browseBtn').addEventListener('click', () => openBrowseModal(document.getElementById('projectPath').value));
  document.getElementById('closeBrowseModalBtn').addEventListener('click', () => browseModal.classList.add('hidden'));
  document.getElementById('cancelBrowseBtn').addEventListener('click', () => browseModal.classList.add('hidden'));
  document.getElementById('selectCurrentFolderBtn').addEventListener('click', () => {
    if (STATE.currentBrowsePath) {
      document.getElementById('projectPath').value = STATE.currentBrowsePath;
    }
    browseModal.classList.add('hidden');
  });

  // Debugger
  document.getElementById('debugBtn').addEventListener('click', runDebugger);
  document.getElementById('debugLanguage').addEventListener('change', (e) => {
    const notice = document.getElementById('roadmapNotice');
    if (e.target.value !== 'python') {
      showBanner(notice, 'warning', `${e.target.value.toUpperCase()} is on the long-term roadmap (Python → C → C++ → Java → JS → HTML → CSS → R) and is not yet implemented.`);
    } else {
      notice.className = 'status-banner hidden';
    }
  });
  document.getElementById('loadSampleBugBtn').addEventListener('click', () => {
    document.getElementById('debugLanguage').value = 'python';
    document.getElementById('roadmapNotice').className = 'status-banner hidden';
    document.getElementById('rawCodeInput').value =
      'def calculate_discount(price, percent)\n    if price < 0:\n        return 0\n    return price - (price * percent / 100)\n';
  });
  document.getElementById('loadValidSampleBtn').addEventListener('click', () => {
    document.getElementById('debugLanguage').value = 'python';
    document.getElementById('roadmapNotice').className = 'status-banner hidden';
    document.getElementById('rawCodeInput').value =
      'def add_numbers(a: int, b: int) -> int:\n    """Return the sum of two integers."""\n    return a + b\n';
  });

  // Reports
  document.getElementById('refreshLatestReportBtn').addEventListener('click', loadLatestReport);
});
