'use strict';
(function () {
  let portfolio = null, selected = 0, detail = 'overview', chartIndex = 0;
  let workspace = 'research', prepared = null, timer = null, renderingKey = '';
  let runBusy = false, configuredDemo = false, allocation = [];
  const offline = Boolean(window.PORTFOLIO_SNAPSHOT);
  const $ = id => document.getElementById(id);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (value, digits = 1) => Number.isFinite(value) ? value.toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : '—';
  const pct = value => Number.isFinite(value) ? fmt(value) + '%' : '—';
  const money = value => Number.isFinite(value) ? '$' + fmt(value, 2) : '—';
  const tone = rating => ['Strong Buy','Buy','Add','Constructive'].includes(rating) ? 'positive' : ['Reduce','Sell','Avoid','Defensive'].includes(rating) ? 'negative' : 'neutral';
  const pill = (rating, override) => '<span class="pill ' + (override || tone(rating)) + '">' + escape(rating) + '</span>';
  const list = items => '<ul class="list">' + (items || []).map(item => '<li>' + escape(item) + '</li>').join('') + '</ul>';
  const date = value => { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? String(value || '') : parsed.toLocaleString('en-US', {month:'short', day:'numeric', hour:'numeric', minute:'2-digit', timeZoneName:'short'}); };
  function setNotice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
  async function api(path, body) {
    const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), cache:'no-store'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) throw new Error('Your access session has expired. Reload this page to enter the access code.');
      throw new Error(typeof data.detail === 'string' ? data.detail : 'The request could not be completed. Check the holdings and try again.');
    }
    return data;
  }
  function remember(id) { try { if (id) sessionStorage.setItem('portfolio-rm-job', id); else sessionStorage.removeItem('portfolio-rm-job'); } catch (_) {} }
  function remembered() { try { return sessionStorage.getItem('portfolio-rm-job'); } catch (_) { return null; } }
  function resetPreview() { prepared = null; $('runBtn').disabled = true; $('holdingsPreview').hidden = true; $('intakeError').hidden = true; }
  function updateInputHint() {
    const mode = $('weighting').value;
    const hints = {weight:'Weights must total 100%. Use CASH for uninvested cash.',value:'USD market values. Allocation weights are calculated from the total.',shares:'USD-listed securities only. Weights use researched price × shares.',equal:'Tickers only. Each holding receives the same weight; cash is excluded.'};
    const placeholders = {weight:'Ticker, Weight\nAAPL, 25\nMSFT, 25\nNVDA, 20\nSPY, 25\nCASH, 5',value:'Ticker, Market value\nAAPL, 25000\nMSFT, 25000\nCASH, 5000',shares:'Ticker, Shares\nAAPL, 100\nMSFT, 50\nNVDA, 75',equal:'AAPL\nMSFT\nNVDA\nSPY'};
    $('weightingHint').textContent = hints[mode]; $('holdingsText').placeholder = placeholders[mode]; resetPreview();
  }
  async function reviewHoldings() {
    resetPreview(); $('reviewBtn').disabled = true;
    const text = $('holdingsText').value, weighting = $('weighting').value;
    try {
      const data = await api('/api/portfolio/parse', {text, weighting});
      if (text !== $('holdingsText').value || weighting !== $('weighting').value) return;
      prepared = data;
      const label = {weight:'Weight',value:'USD value',shares:'Shares',equal:'Weight'}[weighting];
      const amount = p => weighting === 'equal' ? pct(100 / data.positions.length) : weighting === 'weight' ? pct(p.amount) : weighting === 'value' ? money(p.amount) : fmt(p.amount, 4);
      $('holdingsPreview').innerHTML = '<p class="preview-title">' + data.positions.length + ' positions ready for review. Confirm the tickers below.</p><div class="preview-table"><table><thead><tr><th>Ticker</th><th class="number">' + label + '</th></tr></thead><tbody>' + data.positions.map(p => '<tr><td>' + escape(p.ticker) + '</td><td class="number">' + amount(p) + '</td></tr>').join('') + '</tbody></table></div>';
      $('holdingsPreview').hidden = false; $('runBtn').disabled = false;
    } catch (error) { $('intakeError').textContent = error.message; $('intakeError').hidden = false; }
    finally { $('reviewBtn').disabled = false; }
  }
  async function runResearch() {
    if (!prepared || runBusy || offline) return;
    runBusy = true; $('runBtn').disabled = true; $('reviewBtn').disabled = true; setNotice('');
    try {
      const result = await api('/api/portfolio', {positions:prepared.positions, weighting:prepared.weighting, mode:$('researchMode').value, question:$('question').value.trim()});
      portfolio = result; selected = 0; detail = 'overview'; chartIndex = 0; workspace = 'research'; renderingKey = '';
      remember(result.id); $('intake').hidden = true; $('cancelBtn').disabled = false;
      render(); schedulePoll();
    } catch (error) { $('intakeError').textContent = error.message; $('intakeError').hidden = false; $('runBtn').disabled = false; }
    finally { runBusy = false; $('reviewBtn').disabled = false; }
  }
  function schedulePoll() {
    clearTimeout(timer);
    if (portfolio && portfolio.status === 'running' && !offline) timer = setTimeout(poll, 1800);
  }
  async function poll() {
    if (!portfolio) return;
    const id = portfolio.id;
    try { const data = await api('/api/portfolio/' + id); if (portfolio.id !== id) return; portfolio = data; render(); }
    catch (error) { setNotice(error.message); }
    schedulePoll();
  }
  function editHoldings() {
    if (!portfolio || portfolio.status === 'running' || offline) return;
    $('weighting').value = portfolio.weighting; updateInputHint();
    $('holdingsText').value = portfolio.positions.map(p => p.ticker + (portfolio.weighting === 'equal' ? '' : ', ' + p.amount)).join('\n');
    $('researchMode').value = portfolio.mode; $('question').value = portfolio.question || '';
    $('intake').hidden = false; $('closeIntake').hidden = false; $('holdingsText').focus();
    $('intake').scrollIntoView({block:'start'});
  }
  function selectPosition(index, focusTab = false) {
    if (!portfolio || !Number.isInteger(index) || !portfolio.positions[index]) return;
    selected = index; chartIndex = 0; workspace = 'research'; renderingKey = ''; render();
    if (focusTab) $('holding-' + index)?.focus();
  }
  function render() {
    if (!portfolio) return;
    const a = portfolio.assessment, running = portfolio.status === 'running';
    $('results').hidden = false; $('editBtn').hidden = offline; $('editBtn').disabled = running;
    $('downloadBtn').hidden = offline || !['ready','partial'].includes(portfolio.status);
    $('downloadBtn').href = '/api/portfolio/' + portfolio.id + '/download';
    $('demoNotice').hidden = !(configuredDemo || portfolio.demo_mode);
    $('portfolioRating').textContent = portfolio.status === 'cancelled' ? 'Cancelled' : a.rating;
    $('portfolioRating').style.color = a.rating === 'Constructive' ? 'var(--green)' : a.rating === 'Defensive' ? 'var(--red)' : 'var(--navy)';
    $('portfolioSummary').textContent = portfolio.status === 'cancelled' ? 'This run was cancelled and its temporary reports were removed. Edit the holdings to begin again.' : a.summary;
    $('concentration').textContent = a.concentration;
    $('concentration').className = 'pill ' + (a.flags.length ? 'warning' : 'neutral');
    $('coverage').textContent = pct(a.coverage_pct);
    $('largest').innerHTML = a.largest ? escape(a.largest.ticker) + '<small>' + pct(a.largest.weight) + ' allocation</small>' : '—';
    $('thirdMetricLabel').textContent = a.total_value !== null ? 'Portfolio value' : 'Positions';
    $('thirdMetric').innerHTML = a.total_value !== null ? '$' + fmt(a.total_value, 0) + '<small>' + (portfolio.weighting === 'value' ? 'Provided values' : 'At research prices') + '</small>' : portfolio.positions.length + '<small>' + pct(a.cash_pct) + ' cash</small>';
    renderAllocation();
    $('progressRegion').hidden = !running; $('progressText').textContent = portfolio.stage;
    $('progress').value = 100 * portfolio.finished_count / portfolio.positions.length;
    $('reviewDate').textContent = (offline ? 'Saved review · ' : 'Review started · ') + date(portfolio.created_at);
    $('connectionStatus').textContent = portfolio.demo_mode ? 'Synthetic demo research' : running ? 'Research in progress' : 'Research snapshot';
    $('methodText').textContent = a.methodology;
    $('researchWorkspace').hidden = workspace !== 'research'; $('holdingsWorkspace').hidden = workspace !== 'holdings';
    for (const tab of ['research','holdings']) { $(tab + 'Tab').setAttribute('aria-selected', workspace === tab); $(tab + 'Tab').tabIndex = workspace === tab ? 0 : -1; }
    $('positionTabs').innerHTML = portfolio.positions.map((p,i) => '<button id="holding-' + i + '" class="holding-tab" data-position="' + i + '" data-status="' + p.status + '" role="tab" aria-selected="' + (i === selected) + '" aria-controls="selectedPosition" tabindex="' + (i === selected ? 0 : -1) + '" aria-label="' + escape(p.ticker + ', ' + (p.company_name || p.status)) + '" title="' + escape(p.ticker + ' · ' + (p.rating || p.status)) + '"><span class="ticker-avatar" aria-hidden="true">' + escape(p.ticker.length > 5 ? p.ticker.slice(0,3) : p.ticker) + '</span><span class="expanded-label">' + escape(p.ticker) + '</span></button>').join('');
    $('selectedPosition').setAttribute('aria-labelledby','holding-' + selected);
    renderHoldings();
    const key = JSON.stringify([portfolio.status === 'cancelled', portfolio.positions[selected], detail, chartIndex, offline]);
    if (key !== renderingKey) { renderingKey = key; renderPosition(); }
  }
  // A pie reads part-to-whole only while it has few parts: past five segments
  // the smallest holdings fold into Other, and the holdings table keeps every one.
  const SLICE_LIMIT = 5;
  function allocationSlices() {
    const held = portfolio.positions.filter(p => Number.isFinite(p.weight) && p.weight > 0).sort((a, b) => b.weight - a.weight);
    const named = held.length > SLICE_LIMIT ? held.slice(0, SLICE_LIMIT - 1) : held;
    const slices = named.map(p => ({ticker: p.ticker, name: p.company_name || '', weight: p.weight}));
    const rest = held.slice(named.length);
    if (rest.length) slices.push({ticker: 'Other', name: rest.length + ' smaller holdings', weight: rest.reduce((sum, p) => sum + p.weight, 0), count: rest.length, other: true});
    return slices;
  }
  function slicePath(start, end) {
    const at = (angle, radius) => (100 + radius * Math.sin(angle)).toFixed(2) + ' ' + (100 - radius * Math.cos(angle)).toFixed(2);
    const large = end - start > Math.PI ? 1 : 0;
    return 'M' + at(start, 94) + 'A94 94 0 ' + large + ' 1 ' + at(end, 94) + 'L' + at(end, 58) + 'A58 58 0 ' + large + ' 0 ' + at(start, 58) + 'Z';
  }
  function showSlice(index) {
    const slice = index === null ? null : allocation[index];
    $('allocation').classList.toggle('is-focused', Boolean(slice));
    $('allocation').querySelectorAll('[data-slice]').forEach(el => el.classList.toggle('on', Number(el.dataset.slice) === index));
    const held = allocation.reduce((sum, s) => sum + (s.count || 1), 0);
    $('allocationCenter').innerHTML = slice ? '<b>' + pct(slice.weight) + '</b><span>' + escape(slice.ticker) + '</span>' : '<b>' + held + '</b><span>holdings</span>';
  }
  function renderAllocation() {
    allocation = ['ready', 'partial'].includes(portfolio.status) ? allocationSlices() : [];
    // Two slices tell a reader less than the figures above already do.
    $('allocation').hidden = allocation.length < 3;
    if ($('allocation').hidden) return;
    const total = allocation.reduce((sum, s) => sum + s.weight, 0);
    const fill = (s, i) => 'var(--slice-' + (s.other ? 'other' : i + 1) + ')';
    let angle = 0;
    $('allocationPie').innerHTML = allocation.map((s, i) => { const start = angle; angle += 2 * Math.PI * s.weight / total; return '<path data-slice="' + i + '" d="' + slicePath(start, angle) + '" style="fill:' + fill(s, i) + '"></path>'; }).join('');
    $('allocationPie').setAttribute('aria-label', 'Allocation by weight: ' + allocation.map(s => s.ticker + ' ' + pct(s.weight)).join(', '));
    $('allocationLegend').innerHTML = allocation.map((s, i) => '<li data-slice="' + i + '"><span class="allocation-swatch" style="background:' + fill(s, i) + '"></span><span class="allocation-ticker">' + escape(s.ticker) + '</span><span class="allocation-name" title="' + escape(s.name) + '">' + escape(s.name) + '</span><span class="allocation-weight">' + pct(s.weight) + '</span></li>').join('');
    const other = allocation.find(s => s.other);
    $('allocationNote').textContent = other ? 'By weight. The ' + (allocation.length - 1) + ' largest holdings are shown; the other ' + other.count + ' are grouped as Other.' : 'By weight.';
    showSlice(null);
  }
  function renderHoldings() {
    const rows = portfolio.positions.map((p,i) => '<tr><td><button class="text-button" data-position="' + i + '">' + escape(p.ticker) + '</button><span class="company-cell">' + escape(p.company_name || (p.status === 'failed' ? 'Research unavailable' : 'Awaiting research')) + '</span></td><td class="number"><span class="weight-track"><span style="width:' + Math.min(100, Math.max(0,p.weight || 0)) + '%"></span></span>' + pct(p.weight) + '</td><td>' + pill(p.ticker === 'CASH' ? 'Cash' : p.rating || p.status) + '</td><td class="number">' + money(p.price) + '</td><td class="metadata">' + escape(p.as_of ? date(p.as_of) : '—') + '</td></tr>').join('');
    $('holdingsWorkspace').innerHTML = '<div class="card"><div class="table-wrap"><table><thead><tr><th>Holding</th><th class="number">Allocation</th><th>RM rating</th><th class="number">Research price</th><th>As of</th></tr></thead><tbody>' + rows + '</tbody></table></div><p class="holdings-footer">' + escape({weight:'Provided portfolio weights.',value:'Weights calculated from provided USD market values.',shares:'Weights calculated from shares × researched USD prices. Missing prices leave all weights pending.',equal:'Explicit equal weighting.'}[portfolio.weighting]) + ' Prices are research snapshots.</p></div>';
  }
  function nav() {
    const tabs = [['overview','Overview'],['charts','Charts'],['data','Key data & sources'],['report','Full RM report']];
    return '<div class="detail-nav"><div class="segmented" role="tablist" aria-label="Position research sections">' + tabs.map(([id,label]) => '<button id="detail-' + id + '" data-detail="' + id + '" role="tab" aria-controls="detailPanel" aria-selected="' + (detail === id) + '" tabindex="' + (detail === id ? 0 : -1) + '">' + label + '</button>').join('') + '</div></div>';
  }
  function renderPosition() {
    const p = portfolio.positions[selected];
    if (!p) return;
    const identity = '<div class="position-heading"><div class="position-identity"><div class="large-avatar" aria-hidden="true">' + escape(p.ticker.slice(0,5)) + '</div><div><div class="position-title"><h2>' + escape(p.ticker) + '</h2><span>' + escape(p.company_name) + '</span></div><p class="identity-meta">' + (p.exchange ? escape(p.exchange) + ' · USD · ' : '') + (p.weight !== null ? pct(p.weight) + ' of portfolio' : 'Weight pending prices') + '</p></div></div>' + (p.price ? '<div class="position-price">' + money(p.price) + '<small>As of ' + escape(date(p.as_of)) + '</small></div>' : '') + '</div>';
    if (p.ticker === 'CASH') {
      $('selectedPosition').innerHTML = identity + '<div class="card empty-position"><h2>Cash allocation</h2><p>' + pct(p.weight) + ' of the portfolio is held in USD cash. It is included in allocation and coverage, and excluded from the security-rating score.</p></div>'; return;
    }
    if (portfolio.status === 'cancelled' || p.status !== 'ready') {
      const title = portfolio.status === 'cancelled' ? 'Research cancelled' : p.status === 'failed' ? 'Research unavailable' : p.status === 'running' ? 'Building this position’s research.' : 'This holding is next in the queue.';
      const message = p.error || 'Each holding uses the same RM analysis. Completed positions can be opened while the rest are researched.';
      $('selectedPosition').innerHTML = identity + '<div class="card empty-position"><span class="eyebrow">' + escape(p.ticker) + '</span><h2>' + title + '</h2><p>' + escape(message) + '</p>' + (p.status === 'failed' && !offline && portfolio.status !== 'running' ? '<button class="button secondary" data-edit>Review holdings & retry</button>' : '') + '</div>'; return;
    }
    let content = '';
    if (detail === 'overview') content = overview(p);
    if (detail === 'charts') content = '<div class="card panel">' + chartPanel(p, true) + '</div>';
    if (detail === 'data') content = dataPanel(p);
    if (detail === 'report') content = reportPanel(p);
    $('selectedPosition').innerHTML = identity + nav() + '<section id="detailPanel" role="tabpanel" aria-labelledby="detail-' + detail + '">' + content + '</section>';
  }
  function overview(p) {
    const specialist = (label, finding) => '<div><div class="specialist-head"><span>' + label + '</span>' + pill(finding.rating) + '</div><p>' + escape(finding.summary) + '</p></div>';
    let html = '<div class="dashboard-grid"><div><article class="card panel"><div class="panel-heading"><h3>Investment view</h3>' + pill(p.rating) + '</div><p class="investment-copy">' + escape(p.summary) + '</p><div class="specialists">' + specialist('Technical',p.technical) + specialist('Fundamental',p.fundamental) + '</div></article>';
    html += '<article class="card panel chart-panel">' + chartPanel(p, false) + '</article></div><div><article class="card panel"><div class="panel-heading"><h3>Position & risk plan</h3><span class="eyebrow">' + escape(p.ticker) + '</span></div>' + levels(p) + '</article>';
    html += '<article class="card panel risk-panel"><h3>What needs attention</h3>' + list((p.risks || []).slice(0,3)) + '<h3>What would change the view</h3>' + list((p.change_conditions || []).slice(0,3)) + '</article></div></div>';
    return html;
  }
  function levels(p) {
    const plan = p.plan;
    if (!plan) return '<p class="help">No validated price plan is available for this holding. Review the full note for the investment rationale.</p>';
    const row = (label,value,cls) => '<div class="' + (cls || '') + '"><dt>' + label + '</dt><dd>' + value + '</dd></div>';
    return '<p class="plan-stance">' + escape(plan.stance) + '</p><dl class="levels">' + row('Target 2',money(plan.second_target),'level-positive') + row('Target 1',money(plan.first_target),'level-positive') + row('Research price',money(p.price),'current-price') + row('Entry zone',money(plan.entry_low) + ' – ' + money(plan.entry_high)) + row('Structural stop',money(plan.stop_level),'level-negative') + row('Reward / risk',fmt(plan.reward_risk,2) + '×') + '</dl><p class="help">' + escape(plan.confirmation) + '</p>';
  }
  function chartPanel(p, full) {
    const charts = p.charts || [];
    if (!charts.length) return '<div class="panel-heading"><h3>Chart evidence</h3></div><p class="help">No chart was produced from usable evidence. The research note lists the available sources and limitations.</p>';
    const index = Math.min(chartIndex, charts.length - 1), chart = charts[index];
    const controls = '<div class="chart-controls" aria-label="Available charts">' + charts.map((c,i) => '<button class="chart-choice" data-chart="' + i + '" aria-pressed="' + (i === index) + '">' + escape(c.title) + '</button>').join('') + '</div>';
    return '<div class="panel-heading"><h3>' + (full ? 'Technical evidence' : 'Chart evidence') + '</h3><span class="metadata">' + charts.length + ' views</span></div>' + (full ? controls : '<div class="field"><label for="chartSelect" class="sr-only">Select chart</label><select id="chartSelect">' + charts.map((c,i) => '<option value="' + i + '"' + (i === index ? ' selected' : '') + '>' + escape(c.title) + '</option>').join('') + '</select></div>') + '<figure style="margin:16px 0 0"><img class="chart-image" src="' + escape(chart.url) + '" alt="' + escape(p.ticker + ': ' + chart.title) + '" loading="lazy">' + (chart.insight ? '<figcaption class="chart-caption">' + escape(chart.insight) + '</figcaption>' : '') + '</figure>';
  }
  function dataPanel(p) {
    const safeSource = source => /^https?:\/\//i.test(source.locator || '') ? '<a href="' + escape(source.locator) + '" target="_blank" rel="noopener noreferrer">' + escape(source.name) + ' ↗</a>' : '<span>' + escape(source.name) + '</span>';
    return '<div class="data-grid"><div class="card"><div class="panel-heading panel" style="margin:0"><h3>Research data</h3>' + pill(p.rating) + '</div><div class="table-wrap"><table><tbody>' + (p.metrics || []).map(([label,value]) => '<tr><td>' + escape(label) + '</td><td class="number">' + escape(value) + '</td></tr>').join('') + '</tbody></table></div></div><div><article class="card panel"><div class="panel-heading"><h3>Sources</h3><span class="metadata">Confidence: ' + escape(p.confidence) + '</span></div><ul class="source-list">' + (p.sources || []).map(source => '<li>' + safeSource(source) + '<p>' + escape(source.supports) + '</p><span class="source-date">' + escape(date(source.retrieved_at)) + '</span></li>').join('') + '</ul></article><article class="card panel chart-panel"><h3>Evidence notes</h3><p class="help">' + escape(p.ycharts_status || '') + '</p>' + ((p.limitations || []).length ? list(p.limitations) : '<p class="help">No additional source limitations were reported by RM.</p>') + '</article></div></div>';
  }
  function reportPanel(p) {
    const downloadUrl = p.report_url + (offline ? '' : '?download=true');
    return '<div class="report-actions"><span class="metadata">Complete RM note · Original charts, evidence and report controls</span><div><a class="button secondary" href="' + escape(downloadUrl) + '" download="' + escape(p.ticker) + '_RM_Research.html">Download HTML</a><a class="button primary" href="' + escape(p.report_url) + '" target="_blank" rel="noopener">Open / save PDF ↗</a></div></div><iframe class="report-frame" title="' + escape(p.ticker) + ' complete RM research note" src="' + escape(p.report_url) + '" sandbox="allow-scripts allow-modals allow-downloads allow-popups allow-popups-to-escape-sandbox"></iframe>';
  }
  function keyTabs(event) {
    const tab = event.target.closest('[role="tab"]');
    if (!tab || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    const siblings = Array.from(tab.parentElement.querySelectorAll('[role="tab"]'));
    let index = siblings.indexOf(tab);
    index = event.key === 'Home' ? 0 : event.key === 'End' ? siblings.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + siblings.length) % siblings.length;
    const next = siblings[index]; event.preventDefault();
    const id = next.id; next.click(); $(id)?.focus();
  }
  async function boot() {
    $('holdingsText').addEventListener('input', resetPreview);
    $('weighting').addEventListener('change', updateInputHint);
    $('reviewBtn').addEventListener('click',reviewHoldings);
    $('runBtn').addEventListener('click',runResearch);
    $('editBtn').addEventListener('click',editHoldings);
    $('closeIntake').addEventListener('click',() => { $('intake').hidden = true; });
    $('fileInput').addEventListener('change',async event => {
      const file = event.target.files[0]; if (!file) return;
      resetPreview();
      if (file.size > 20000 || !/\.(csv|tsv)$/i.test(file.name)) { $('intakeError').textContent = 'Choose a CSV or TSV under 20 KB containing tickers and amounts only.'; $('intakeError').hidden = false; event.target.value = ''; return; }
      try { $('holdingsText').value = await file.text(); } catch (_) { $('intakeError').textContent = 'The file could not be read. Paste the holdings instead.'; $('intakeError').hidden = false; }
      event.target.value = '';
    });
    $('cancelBtn').addEventListener('click', async () => {
      if (!portfolio || offline) return;
      $('cancelBtn').disabled = true;
      try { await api('/api/portfolio/' + portfolio.id + '/cancel', {}); $('progressText').textContent = 'Stopping after the current holding'; }
      catch (error) { setNotice(error.message); $('cancelBtn').disabled = false; }
    });
    for (const tab of ['research','holdings']) $(tab + 'Tab').addEventListener('click',() => {workspace = tab; render();});
    $('results').addEventListener('click', event => {
      const position = event.target.closest('[data-position]');
      if (position) { selectPosition(Number(position.dataset.position), position.classList.contains('holding-tab')); return; }
      const section = event.target.closest('[data-detail]');
      if (section) { detail = section.dataset.detail; renderingKey = ''; render(); $('detail-' + detail)?.focus(); return; }
      const chart = event.target.closest('[data-chart]');
      if (chart) { chartIndex = Number(chart.dataset.chart); renderingKey = ''; render(); $('selectedPosition').querySelector('[data-chart="' + chartIndex + '"]')?.focus(); return; }
      if (event.target.closest('[data-edit]')) editHoldings();
    });
    $('results').addEventListener('change',event => { if (event.target.id === 'chartSelect') { chartIndex = Number(event.target.value); renderingKey = ''; render(); $('chartSelect')?.focus(); } });
    $('results').addEventListener('keydown',keyTabs);
    $('allocation').addEventListener('pointerover', event => { const slice = event.target.closest('[data-slice]'); showSlice(slice ? Number(slice.dataset.slice) : null); });
    $('allocation').addEventListener('pointerleave', () => showSlice(null));
    $('methodBtn').addEventListener('click',() => $('methodDialog').showModal());
    $('closeMethod').addEventListener('click',() => $('methodDialog').close());
    if (offline) {
      portfolio = window.PORTFOLIO_SNAPSHOT; $('intake').hidden = true; $('singleStockLink').hidden = true; $('backToResearch').hidden = true;
      document.querySelector('.wordmark').href = '#main'; render(); return;
    }
    // A fresh arrival starts a fresh portfolio. The remembered job exists so
    // that reloading mid-run reconnects to it rather than abandoning twenty
    // minutes of research -- but clicking through to this page again is a
    // request to evaluate a new set of holdings, and it was silently reopening
    // the last one instead, with the intake form hidden and no way to tell why.
    // Navigation type separates the two: a reload or a back/forward reconnects,
    // anything else clears and starts clean.
    const navigation = (performance.getEntriesByType('navigation')[0] || {}).type;
    const reconnecting = navigation === 'reload' || navigation === 'back_forward';
    if (!reconnecting) remember(null);
    const id = reconnecting ? remembered() : null;
    try {
      const health = await api('/api/health'); configuredDemo = !health.live_research;
      $('connectionStatus').textContent = configuredDemo ? 'Synthetic demo mode' : 'Live research available';
      $('demoNotice').hidden = !configuredDemo;
    } catch (error) { setNotice(error.message); $('connectionStatus').textContent = 'Connection unavailable'; }
    if (id && /^[0-9a-f]{32}$/.test(id)) {
      try { portfolio = await api('/api/portfolio/' + id); $('intake').hidden = true; render(); schedulePoll(); }
      catch (error) { remember(null); setNotice(error.message); }
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot); else boot();
})();
