/**
 * Airtable AI Assistant - Content Script
 * Draggable and resizable sidebar with localStorage persistence
 */

// Configuration
const API_URL = 'http://localhost:8000';

// State
let isVisible = true;
let isMinimized = false;
let currentTheme = 'dark'; // 'dark' or 'light'
let conversationHistory = [];
let isDragging = false;
let isResizing = false;
let dragStart = { x: 0, y: 0 };
let initialPos = { x: 0, y: 0 };
let initialSize = { width: 0, height: 0 };

/**
 * Create and inject the sidebar HTML
 */
function createSidebar() {
  const sidebar = document.createElement('div');
  sidebar.id = 'ai-crm-sidebar';
  sidebar.innerHTML = `
    <div class="ai-header" id="ai-header">
      <div class="ai-header-top">
        <h2>AI Assistant</h2>
        <div class="ai-header-buttons">
          <button class="ai-theme-btn" id="ai-theme" title="Toggle theme">◐</button>
          <button class="ai-minimize-btn" id="ai-minimize" title="Minimize">−</button>
          <button class="ai-toggle-btn" id="ai-toggle" title="Close">×</button>
        </div>
      </div>
      <div class="ai-tabs">
        <button class="ai-tab active" data-tab="chat">Chat</button>
        <button class="ai-tab" data-tab="mappings">Mappings</button>
        <button class="ai-tab" data-tab="jobs">Jobs</button>
      </div>
    </div>

    <div class="ai-status" id="ai-status">
      Connecting to AI...
    </div>

    <!-- Chat Tab -->
    <div class="ai-tab-panel" id="tab-chat">
      <div class="ai-messages" id="ai-messages">
        <div class="ai-welcome">
          <h3>Welcome to AI Assistant</h3>
          <p>I can help you enrich LinkedIn profiles, search for contacts, and automate your CRM tasks.</p>

          <div class="ai-welcome-actions">
            <button class="ai-welcome-btn" data-action="enrich-current">
              <strong>Enrich Current Record</strong>
              Scrape LinkedIn profile for this contact
            </button>
            <button class="ai-welcome-btn" data-action="batch-enrich">
              <strong>Batch Enrichment</strong>
              Process all contacts missing LinkedIn data
            </button>
            <button class="ai-welcome-btn" data-action="help">
              <strong>Help</strong>
              Show available commands
            </button>
          </div>
        </div>
      </div>

      <div class="ai-input-container">
        <div class="ai-quick-actions">
          <button class="ai-quick-btn" data-action="scrape">Scrape Profile</button>
          <button class="ai-quick-btn" data-action="batch">Batch Process</button>
          <button class="ai-quick-btn" data-action="status">Status</button>
          <button class="ai-quick-btn" data-action="clear">Clear Chat</button>
        </div>

        <div class="ai-input-wrapper">
          <input
            type="text"
            id="ai-chat-input"
            placeholder="Ask me anything..."
            autocomplete="off"
          />
          <button id="ai-send-btn">Send</button>
        </div>
      </div>
    </div>

    <!-- Mappings Tab -->
    <div class="ai-tab-panel hidden" id="tab-mappings">
      <div class="jobs-container">
        <div class="mappings-tab-header">
          <span class="jobs-section-title">Field Mappings</span>
          <button class="jobs-start-btn mappings-create-btn" id="mappings-create-btn">+ Create Mapping</button>
        </div>
        <div id="mappings-list">
          <p class="jobs-schema-empty">No mappings saved yet.</p>
        </div>
      </div>
    </div>

    <!-- Jobs Tab -->
    <div class="ai-tab-panel hidden" id="tab-jobs">
      <div class="jobs-container">

        <section class="jobs-section">
          <h3 class="jobs-section-title">New Job</h3>
          <div class="jobs-field-row">
            <span class="jobs-label">Table</span>
            <span class="jobs-value" id="jobs-table-name">—</span>
          </div>
          <div class="jobs-field-row">
            <span class="jobs-label">View</span>
            <select class="jobs-select" id="jobs-view-select">
              <option value="">Navigate to a view</option>
            </select>
          </div>
          <div class="jobs-field-row">
            <span class="jobs-label">Mapping</span>
            <select class="jobs-select" id="jobs-mapping-select">
              <option value="">— none —</option>
            </select>
          </div>
          <div class="jobs-field-row">
            <span class="jobs-label">Batch Size</span>
            <div class="batch-size-group">
              <button class="batch-size-preset active" data-size="100">100</button>
              <button class="batch-size-preset" data-size="200">200</button>
              <button class="batch-size-preset" data-size="300">300</button>
              <input type="number" class="batch-size-custom" id="jobs-batch-size" value="100" min="1" max="1000">
            </div>
          </div>
          <button class="jobs-start-btn" id="jobs-start-btn">Create Job</button>
        </section>

        <!-- Preflight confirmation panel (hidden until preflight completes) -->
        <div class="preflight-panel hidden" id="preflight-panel">
          <div class="preflight-stats" id="preflight-stats"></div>
          <div class="preflight-actions">
            <button class="jobs-stop-btn preflight-cancel-btn" id="preflight-cancel">Cancel</button>
            <button class="jobs-start-btn preflight-confirm-btn" id="preflight-confirm">Confirm & Create</button>
          </div>
        </div>

        <section class="jobs-section">
          <h3 class="jobs-section-title">Job History</h3>
          <div id="jobs-history-list">
            <p class="jobs-schema-empty">No jobs yet.</p>
          </div>
        </section>

      </div>
    </div>

    <!-- Create Mapping Modal -->
    <div class="mapping-modal-overlay hidden" id="mapping-modal">
      <div class="mapping-modal">
        <div class="mapping-modal-header">
          <span>Create Mapping</span>
          <button class="mapping-modal-close" id="mapping-modal-close">×</button>
        </div>
        <div class="mapping-modal-body">
          <div id="mapping-modal-schema-section">
            <div class="spinner-wrap"><div class="spinner"></div></div>
          </div>
        </div>
      </div>
    </div>

    <div class="ai-resize-handle" id="ai-resize-handle" title="Drag to resize"></div>
  `;

  document.body.appendChild(sidebar);

  // Load saved position and size
  loadSidebarState();
}

/**
 * Parse current Airtable URL for base, table, and view IDs.
 * URL format: https://airtable.com/appXXX/tblXXX/viwXXX
 */
function parseAirtableUrl() {
  const parts = window.location.pathname.split('/').filter(Boolean);
  return {
    baseId:  parts.find(p => p.startsWith('app')) || null,
    tableId: parts.find(p => p.startsWith('tbl')) || null,
    viewId:  parts.find(p => p.startsWith('viw')) || null,
  };
}

// Cached canonical fields for use in dropdowns
let _canonicalFields = null;

/**
 * Fetch both Airtable table schema and canonical schema, then render the mapping UI.
 */
async function fetchSchemaFromApi(baseId, tableId) {
  const schemaSection = document.getElementById('jobs-schema-section');
  if (schemaSection) schemaSection.innerHTML = '<div class="spinner-wrap"><div class="spinner"></div></div>';

  try {
    const [tableRes, canonicalRes] = await Promise.all([
      fetch(`${API_URL}/schema?base_id=${baseId}&table_id=${tableId}`),
      fetch(`${API_URL}/canonical-schema`)
    ]);

    if (!tableRes.ok) throw new Error((await tableRes.json()).error || `HTTP ${tableRes.status}`);
    if (!canonicalRes.ok) throw new Error('Failed to load canonical schema');

    const tableData = await tableRes.json();
    const canonicalData = await canonicalRes.json();

    _canonicalFields = canonicalData.fields;
    renderMappingUI(tableData.fields, tableData.table_name, canonicalData.fields);
  } catch (e) {
    console.error('[Schema] API fetch failed:', e);
    if (schemaSection) schemaSection.innerHTML = `<p class="jobs-schema-empty">Error: ${e.message}</p>`;
  }

  // Load saved mappings into the Run Batch Job dropdown
  await loadSavedMappingsDropdown(baseId, tableId);
}

/**
 * Load saved mappings from DB and populate the mapping dropdown in Run Batch Job.
 */
async function loadSavedMappingsDropdown(baseId, tableId) {
  const select = document.getElementById('jobs-mapping-select');
  if (!select || !baseId || !tableId) return;

  try {
    const res = await fetch(`${API_URL}/mappings?base_id=${baseId}&table_id=${tableId}`);
    if (!res.ok) return;
    const data = await res.json();
    const mappings = data.mappings || [];

    select.innerHTML = mappings.length === 0
      ? '<option value="">— no saved mappings —</option>'
      : mappings.map(m => `<option value="${m.id}">${m.name}</option>`).join('');
  } catch (e) {
    console.error('[Mappings] Failed to load dropdown:', e);
  }
}

/**
 * Initialize the Mappings tab - load saved mappings list
 */
function initMappingsTab() {
  const { baseId, tableId } = parseAirtableUrl();
  loadMappingsList(baseId, tableId);
}

async function loadMappingsList(baseId, tableId) {
  const listEl = document.getElementById('mappings-list');
  if (!listEl) return;

  if (!baseId || !tableId) {
    listEl.innerHTML = '<p class="jobs-schema-empty">Navigate to a table to see mappings.</p>';
    return;
  }

  listEl.innerHTML = '<div class="spinner-wrap"><div class="spinner"></div></div>';

  try {
    const res = await fetch(`${API_URL}/mappings?base_id=${baseId}&table_id=${tableId}`);
    const data = await res.json();
    const mappings = data.mappings || [];

    if (mappings.length === 0) {
      listEl.innerHTML = '<p class="jobs-schema-empty">No mappings saved for this table.</p>';
      return;
    }

    listEl.innerHTML = mappings.map(m => `
      <div class="mapping-list-row" data-id="${m.id}">
        <div class="mapping-list-info">
          <span class="mapping-list-name">${m.name}</span>
          <span class="mapping-list-meta">${Object.keys(m.mappings).length} fields · ${new Date(m.created_at).toLocaleDateString()}</span>
        </div>
        <button class="mapping-list-delete jobs-icon-btn" data-id="${m.id}" title="Delete">✕</button>
      </div>
    `).join('');

    // Delete buttons
    listEl.querySelectorAll('.mapping-list-delete').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.id;
        await fetch(`${API_URL}/mappings/${id}`, { method: 'DELETE' });
        loadMappingsList(baseId, tableId);
        loadSavedMappingsDropdown(baseId, tableId);
      });
    });
  } catch (e) {
    listEl.innerHTML = `<p class="jobs-schema-empty">Error loading mappings.</p>`;
  }
}

/**
 * Open the Create Mapping modal and load schema into it
 */
async function openMappingModal() {
  const { baseId, tableId } = parseAirtableUrl();
  const modal = document.getElementById('mapping-modal');
  if (!modal) return;

  modal.classList.remove('hidden');

  if (!baseId || !tableId) {
    document.getElementById('mapping-modal-schema-section').innerHTML =
      '<p class="jobs-schema-empty">Navigate to a table first.</p>';
    return;
  }

  try {
    const [tableRes, canonicalRes] = await Promise.all([
      fetch(`${API_URL}/schema?base_id=${baseId}&table_id=${tableId}`),
      fetch(`${API_URL}/canonical-schema`)
    ]);
    const tableData = await tableRes.json();
    const canonicalData = await canonicalRes.json();
    _canonicalFields = canonicalData.fields;

    // Render mapping UI into modal
    const container = document.getElementById('mapping-modal-schema-section');
    renderMappingUI(tableData.fields, tableData.table_name, canonicalData.fields, container);
  } catch (e) {
    document.getElementById('mapping-modal-schema-section').innerHTML =
      `<p class="jobs-schema-empty">Error: ${e.message}</p>`;
  }
}

function closeMappingModal() {
  document.getElementById('mapping-modal')?.classList.add('hidden');
}

/**
 * Initialize the Jobs tab - detect current Airtable context
 */
function initJobsTab() {
  const { baseId, tableId, viewId } = parseAirtableUrl();

  const tableNameDisplay = document.getElementById('jobs-table-name');
  if (tableNameDisplay) {
    tableNameDisplay.textContent = tableId || 'Not detected';
    tableNameDisplay.title = baseId ? `Base: ${baseId}` : '';
  }

  const viewSelect = document.getElementById('jobs-view-select');
  if (viewSelect) {
    viewSelect.innerHTML = viewId
      ? `<option value="${viewId}">${viewId}</option>`
      : '<option value="">Navigate to a view in Airtable</option>';
  }

  if (baseId && tableId) {
    loadSavedMappingsDropdown(baseId, tableId);
  }

  // Batch size preset buttons
  document.querySelectorAll('.batch-size-preset').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.batch-size-preset').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('jobs-batch-size').value = btn.dataset.size;
    });
  });

  // Custom input clears preset selection
  const customInput = document.getElementById('jobs-batch-size');
  if (customInput && !customInput.dataset.bound) {
    customInput.dataset.bound = 'true';
    customInput.addEventListener('input', () => {
      document.querySelectorAll('.batch-size-preset').forEach(b => b.classList.remove('active'));
    });
  }

  const startBtn = document.getElementById('jobs-start-btn');
  if (startBtn && !startBtn.dataset.bound) {
    startBtn.dataset.bound = 'true';
    startBtn.addEventListener('click', handleCreateJob);
  }

  const confirmBtn = document.getElementById('preflight-confirm');
  if (confirmBtn && !confirmBtn.dataset.bound) {
    confirmBtn.dataset.bound = 'true';
    confirmBtn.addEventListener('click', confirmCreateJob);
  }

  const cancelBtn = document.getElementById('preflight-cancel');
  if (cancelBtn && !cancelBtn.dataset.bound) {
    cancelBtn.dataset.bound = 'true';
    cancelBtn.addEventListener('click', cancelPreflight);
  }

  if (baseId && tableId) {
    loadJobHistory(baseId, tableId);
  }
}

/**
 * Render the field mapping UI.
 * Left column = Airtable fields, right = canonical field dropdowns.
 * Auto-matches by name similarity.
 */
function renderMappingUI(airtableFields, tableName, canonicalFields, container) {
  const schemaSection = container || document.getElementById('jobs-schema-section');
  if (!schemaSection) return;

  if (!airtableFields || airtableFields.length === 0) {
    schemaSection.innerHTML = '<p class="jobs-schema-empty">Could not load schema.</p>';
    return;
  }

  // Build canonical options grouped by group
  const groups = [...new Set(canonicalFields.map(f => f.group))];
  const optionsHTML = `
    <option value="">— skip —</option>
    ${groups.map(g => `
      <optgroup label="${g.toUpperCase()}">
        ${canonicalFields.filter(f => f.group === g).map(f =>
          `<option value="${f.key}" title="${f.description}">${f.label}</option>`
        ).join('')}
      </optgroup>
    `).join('')}
  `;

  // Auto-match: normalize names and find closest canonical key
  function autoMatch(airtableFieldName) {
    const normalized = airtableFieldName.toLowerCase().replace(/[\s_\-]/g, '');
    const match = canonicalFields.find(cf => {
      const cfNorm = cf.label.toLowerCase().replace(/[\s_\-]/g, '');
      const keyNorm = cf.key.toLowerCase().replace(/[\s_\-]/g, '');
      return cfNorm === normalized || keyNorm === normalized ||
             cfNorm.includes(normalized) || normalized.includes(cfNorm);
    });
    return match ? match.key : '';
  }

  // Log choices data so user can verify API is returning them
  const selectFields = airtableFields.filter(f => f.options && f.options.choices);
  console.log(`[Mapping] ${selectFields.length} select fields with choices:`,
    selectFields.map(f => ({ name: f.name, choices: f.options.choices.map(c => c.name) }))
  );

  // Render choices inline as colored dots + names (expandable)
  function choicesTag(f) {
    if (!f.options || !f.options.choices) return '';
    const choices = f.options.choices;
    // Show first 3 inline, rest collapsed
    const visible = choices.slice(0, 3);
    const overflow = choices.length - visible.length;

    const dots = visible.map(c => {
      const color = c.color ? airtableColorToHex(c.color) : 'var(--surface)';
      return `<span class="choice-pill" style="background:${color}" title="${c.name}">${c.name}</span>`;
    }).join('');

    const more = overflow > 0 ? `<span class="choice-more">+${overflow}</span>` : '';
    return `<div class="mapping-choices-row">${dots}${more}</div>`;
  }

  // Airtable color name → hex (common ones)
  function airtableColorToHex(name) {
    const map = {
      red: '#ff6b6b', orange: '#ff9500', yellow: '#ffd60a', green: '#30d158',
      teal: '#5ac8fa', blue: '#0a84ff', purple: '#bf5af2', pink: '#ff375f',
      gray: '#8e8e93', cyan: '#32ade6', yellowLight: '#ffe082', greenLight: '#a5d6a7',
      blueLight: '#90caf9', purpleLight: '#ce93d8', redLight: '#ef9a9a',
      orangeLight: '#ffcc80',
    };
    // Airtable uses names like "redBright", "greenLight", etc
    const key = Object.keys(map).find(k => name && name.toLowerCase().includes(k.toLowerCase()));
    return key ? map[key] : 'var(--surface)';
  }

  schemaSection.innerHTML = `
    <div class="mapping-toolbar">
      <label class="mapping-toggle-label">
        <input type="checkbox" id="mapping-show-all" checked>
        Show all fields
      </label>
    </div>
    <div class="mapping-header">
      <span class="mapping-col-label">${tableName} Field</span>
      <span></span>
      <span class="mapping-col-label">Maps To (Canonical)</span>
    </div>
    <div class="jobs-mapping-rows" id="jobs-mapping-rows">
      ${airtableFields.map(f => {
        const matched = autoMatch(f.name);
        const matchedOptions = matched
          ? optionsHTML.replace(`value="${matched}"`, `value="${matched}" selected`)
          : optionsHTML;
        return `
          <div class="mapping-row" data-field-id="${f.id}" data-mapped="${matched ? 'true' : 'false'}">
            <span class="mapping-airtable-field">
              ${f.name}
              <span class="mapping-meta">
                <small class="mapping-type">${f.type}</small>
              </span>
              ${choicesTag(f)}
            </span>
            <span class="mapping-arrow">→</span>
            <select class="mapping-select jobs-select"
              data-airtable-field="${f.name}"
              data-airtable-id="${f.id}"
              data-airtable-type="${f.type}"
              data-airtable-choices="${f.options?.choices ? encodeURIComponent(JSON.stringify(f.options.choices.map(c => c.name))) : ''}">
              ${matchedOptions}
            </select>
          </div>
        `;
      }).join('')}
    </div>
    <div class="mapping-actions">
      <button class="jobs-icon-btn" id="mapping-auto-btn">⚡ Auto</button>
      <button class="jobs-icon-btn" id="mapping-clear-btn">✕ Clear</button>
    </div>
    <div class="mapping-save-row">
      <input type="text" class="mapping-name-input" id="mapping-name-input" placeholder="Mapping name..." maxlength="60">
      <button class="jobs-start-btn mapping-save-btn" id="mapping-save-btn">Save Mapping</button>
    </div>
  `;

  // Show all / mapped only toggle
  const showAllToggle = document.getElementById('mapping-show-all');
  function applyVisibilityFilter() {
    const showAll = showAllToggle.checked;
    document.querySelectorAll('.mapping-row').forEach(row => {
      const sel = row.querySelector('.mapping-select');
      const hasValue = sel && sel.value !== '';
      row.style.display = (showAll || hasValue) ? '' : 'none';
    });
  }
  showAllToggle.addEventListener('change', applyVisibilityFilter);

  // Hide unmapped by default on first render if >15 fields
  if (airtableFields.length > 15) {
    showAllToggle.checked = false;
    applyVisibilityFilter();
  }

  // Update visibility when a select changes
  document.querySelectorAll('.mapping-select').forEach(sel => {
    sel.addEventListener('change', () => {
      sel.closest('.mapping-row').dataset.mapped = sel.value ? 'true' : 'false';
      applyVisibilityFilter();
    });
  });

  // Auto button: re-run auto-match and refresh visibility
  document.getElementById('mapping-auto-btn')?.addEventListener('click', () => {
    document.querySelectorAll('.mapping-select').forEach(sel => {
      sel.value = autoMatch(sel.dataset.airtableField);
      sel.closest('.mapping-row').dataset.mapped = sel.value ? 'true' : 'false';
    });
    applyVisibilityFilter();
  });

  // Clear button
  document.getElementById('mapping-clear-btn')?.addEventListener('click', () => {
    document.querySelectorAll('.mapping-select').forEach(sel => {
      sel.value = '';
      sel.closest('.mapping-row').dataset.mapped = 'false';
    });
    applyVisibilityFilter();
  });

  // Save button - use direct reference since it was just created via innerHTML
  const saveBtn = document.getElementById('mapping-save-btn');
  if (saveBtn) {
    saveBtn.addEventListener('click', saveMappingConfig);
  } else {
    console.error('[Mapping] Save button not found in DOM');
  }
}

/**
 * Collect mapping from UI, prompt for a name, and save to DB via API.
 */
async function saveMappingConfig() {
  console.log('[Mapping] saveMappingConfig called');
  const { baseId, tableId } = parseAirtableUrl();
  if (!baseId || !tableId) {
    showToast('Cannot detect table — navigate to a grid view first', 'error');
    return;
  }

  const rows = document.querySelectorAll('.mapping-row');
  const mapping = {};
  rows.forEach(row => {
    const sel = row.querySelector('.mapping-select');
    if (sel && sel.value) {
      const choicesRaw = sel.dataset.airtableChoices;
      mapping[sel.dataset.airtableId] = {
        airtable_name: sel.dataset.airtableField,
        airtable_type: sel.dataset.airtableType || 'singleLineText',
        choices: choicesRaw ? JSON.parse(decodeURIComponent(choicesRaw)) : [],
        canonical_key: sel.value
      };
    }
  });

  if (Object.keys(mapping).length === 0) {
    showToast('No fields mapped — nothing to save', 'error');
    return;
  }

  const nameInput = document.getElementById('mapping-name-input');
  const name = nameInput?.value?.trim();
  if (!name) {
    nameInput?.focus();
    showToast('Enter a name for this mapping first', 'error');
    return;
  }

  const saveBtn = document.getElementById('mapping-save-btn');
  const originalText = saveBtn?.innerHTML;
  if (saveBtn) { saveBtn.disabled = true; saveBtn.innerHTML = '<span class="btn-spinner"><span class="spinner sm"></span>Saving</span>'; }

  try {
    const res = await fetch(`${API_URL}/mappings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_id: baseId, table_id: tableId, name, mappings: mapping })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    showToast(`Mapping "${name}" saved — ${Object.keys(mapping).length} fields`, 'success');
    if (nameInput) nameInput.value = '';
    closeMappingModal();
    loadMappingsList(baseId, tableId);
    await loadSavedMappingsDropdown(baseId, tableId);
  } catch (e) {
    console.error('[Mappings] Save failed:', e);
    showToast(`Failed to save mapping: ${e.message}`, 'error');
  } finally {
    if (saveBtn) { saveBtn.disabled = false; saveBtn.innerHTML = originalText; }
  }
}

// Stores preflight result while user is on confirmation panel
let _preflightData = null;

async function handleCreateJob() {
  const { baseId, tableId, viewId } = parseAirtableUrl();
  const batchSize = parseInt(document.getElementById('jobs-batch-size')?.value || '100');
  const mappingId = document.getElementById('jobs-mapping-select')?.value;

  if (!viewId) {
    showToast('Navigate to a view in Airtable first', 'error');
    return;
  }
  if (!mappingId) {
    showToast('Select a mapping before creating a job', 'error');
    return;
  }

  const startBtn = document.getElementById('jobs-start-btn');
  const originalHtml = startBtn.innerHTML;
  startBtn.disabled = true;
  startBtn.innerHTML = '<span class="btn-spinner"><span class="spinner sm"></span>Checking</span>';

  try {
    const res = await fetch(`${API_URL}/jobs/preflight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_id: baseId, table_id: tableId, view_id: viewId, batch_size: batchSize })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    _preflightData = { baseId, tableId, viewId, batchSize, mappingId, ...data };

    // Show confirmation panel
    const panel = document.getElementById('preflight-panel');
    const stats = document.getElementById('preflight-stats');
    stats.innerHTML = `
      <div class="preflight-row"><span class="preflight-label">Records</span><span class="preflight-value">${data.record_count.toLocaleString()}</span></div>
      <div class="preflight-row"><span class="preflight-label">Batch size</span><span class="preflight-value">${batchSize}</span></div>
      <div class="preflight-row"><span class="preflight-label">Batches</span><span class="preflight-value">${data.batch_count}</span></div>
    `;
    panel.classList.remove('hidden');
    startBtn.innerHTML = originalHtml;
    startBtn.disabled = false;
  } catch (e) {
    showToast(`Preflight failed: ${e.message}`, 'error');
    startBtn.innerHTML = originalHtml;
    startBtn.disabled = false;
  }
}

async function confirmCreateJob() {
  if (!_preflightData) return;
  const { baseId, tableId, viewId, batchSize, mappingId } = _preflightData;

  const confirmBtn = document.getElementById('preflight-confirm');
  const originalHtml = confirmBtn.innerHTML;
  confirmBtn.disabled = true;
  confirmBtn.innerHTML = '<span class="btn-spinner"><span class="spinner sm"></span>Creating</span>';

  try {
    const res = await fetch(`${API_URL}/jobs/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_id: baseId, table_id: tableId, view_id: viewId, mapping_id: parseInt(mappingId), batch_size: batchSize })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    showToast(`Job #${data.job_id} created — ${data.total_batches} batches`, 'success');
    document.getElementById('preflight-panel').classList.add('hidden');
    _preflightData = null;
    loadJobHistory(baseId, tableId);
  } catch (e) {
    showToast(`Failed to create job: ${e.message}`, 'error');
    confirmBtn.innerHTML = originalHtml;
    confirmBtn.disabled = false;
  }
}

function cancelPreflight() {
  document.getElementById('preflight-panel').classList.add('hidden');
  _preflightData = null;
}

let _jobPollTimer = null;

async function loadJobHistory(baseId, tableId) {
  if (_jobPollTimer) { clearTimeout(_jobPollTimer); _jobPollTimer = null; }
  const listEl = document.getElementById('jobs-history-list');
  if (!listEl || !baseId || !tableId) return;

  listEl.innerHTML = '<div class="spinner-wrap"><div class="spinner"></div></div>';

  try {
    const res = await fetch(`${API_URL}/jobs?base_id=${baseId}&table_id=${tableId}`);
    const data = await res.json();
    const jobs = data.jobs || [];

    if (jobs.length === 0) {
      listEl.innerHTML = '<p class="jobs-schema-empty">No jobs yet.</p>';
      return;
    }

    listEl.innerHTML = jobs.map(job => {
      const canRun   = ['pending', 'paused'].includes(job.status);
      const canPause = job.status === 'running';
      const actionBtn = canRun
        ? `<button class="batch-action-btn job-action-btn" data-job-id="${job.id}" data-action="run" title="Run job">▶</button>`
        : canPause
          ? `<button class="batch-action-btn job-action-btn" data-job-id="${job.id}" data-action="pause" title="Pause job">⏸</button>`
          : '';
      return `
      <div class="job-history-card" data-job-id="${job.id}">
        <div class="job-history-header">
          <span class="job-history-id">#${job.id}</span>
          <span class="job-status-badge job-status-${job.status}">${job.status}</span>
          <span class="job-history-meta">${job.total_records?.toLocaleString() ?? '?'} records · ${job.total_batches ?? '?'} batches</span>
          <span class="job-history-date">${new Date(job.created_at).toLocaleDateString()}</span>
          ${actionBtn}
        </div>
        <div class="job-progress-section">
          <div class="job-progress-track">
            <div class="job-progress-fill" id="job-progress-fill-${job.id}" style="width:0%"></div>
          </div>
          <div class="job-progress-stats" id="job-progress-stats-${job.id}">—</div>
        </div>
        <div class="job-batches-list" id="job-batches-${job.id}">
          <div class="spinner-wrap"><div class="spinner"></div></div>
        </div>
      </div>`;
    }).join('');

    // Wire job-level run/pause buttons
    listEl.querySelectorAll('.job-action-btn').forEach(btn => {
      btn.addEventListener('click', (e) => { e.stopPropagation(); handleJobAction(btn); });
    });

    // Load batches + compute stats for each job
    jobs.forEach(job => loadJobBatches(job));

    // Auto-refresh while any job is still running (silent in-place update)
    if (jobs.some(j => j.status === 'running')) {
      _jobPollTimer = setTimeout(() => silentlyRefreshJobStats(baseId, tableId), 10000);
    }
  } catch (e) {
    listEl.innerHTML = '<p class="jobs-schema-empty">Error loading jobs.</p>';
  }
}

async function silentlyRefreshJobStats(baseId, tableId) {
  if (_jobPollTimer) { clearTimeout(_jobPollTimer); _jobPollTimer = null; }
  try {
    const res = await fetch(`${API_URL}/jobs?base_id=${baseId}&table_id=${tableId}`);
    const data = await res.json();
    const jobs = data.jobs || [];

    let anyRunning = false;
    for (const job of jobs) {
      if (job.status === 'running') anyRunning = true;

      // Update status badge in-place
      const card = document.querySelector(`.job-history-card[data-job-id="${job.id}"]`);
      if (!card) continue;

      const badge = card.querySelector('.job-status-badge');
      if (badge && badge.textContent !== job.status) {
        badge.className = `job-status-badge job-status-${job.status}`;
        badge.textContent = job.status;
      }

      // Update action button (e.g. running→pause becomes pending→run after pause)
      const existingBtn = card.querySelector('.job-action-btn');
      const canRun   = ['pending', 'paused'].includes(job.status);
      const canPause = job.status === 'running';
      const headerEl = card.querySelector('.job-history-header');
      if (existingBtn) {
        if (!canRun && !canPause) {
          existingBtn.remove();
        } else {
          const newAction = canRun ? 'run' : 'pause';
          const newIcon   = canRun ? '▶' : '⏸';
          const newTitle  = canRun ? 'Run job' : 'Pause job';
          if (existingBtn.dataset.action !== newAction) {
            existingBtn.dataset.action = newAction;
            existingBtn.title = newTitle;
            existingBtn.innerHTML = newIcon;
          }
        }
      } else if ((canRun || canPause) && headerEl) {
        const btn = document.createElement('button');
        btn.className = 'batch-action-btn job-action-btn';
        btn.dataset.jobId = job.id;
        btn.dataset.action = canRun ? 'run' : 'pause';
        btn.title = canRun ? 'Run job' : 'Pause job';
        btn.innerHTML = canRun ? '▶' : '⏸';
        btn.addEventListener('click', (e) => { e.stopPropagation(); handleJobAction(btn); });
        headerEl.appendChild(btn);
      }

      // Refresh batch stats (updates progress bar + stats text in-place)
      await loadJobBatches(job);
    }

    if (anyRunning) {
      _jobPollTimer = setTimeout(() => silentlyRefreshJobStats(baseId, tableId), 10000);
    }
  } catch (e) {
    // Silent failure — don't disrupt the UI on a background poll error
  }
}

async function loadJobBatches(job) {
  const jobId = typeof job === 'object' ? job.id : job;
  const totalRecords = typeof job === 'object' ? (job.total_records || 0) : 0;
  const batchesEl = document.getElementById(`job-batches-${jobId}`);
  if (!batchesEl) return;

  try {
    const res = await fetch(`${API_URL}/jobs/${jobId}/batches`);
    const data = await res.json();
    const batches = data.batches || [];

    // Aggregate stats across all batches
    const agg = batches.reduce((acc, b) => {
      acc.processed += b.processed || 0;
      acc.hits      += b.hits      || 0;
      acc.misses    += b.misses    || 0;
      acc.failed    += b.failed    || 0;
      return acc;
    }, { processed: 0, hits: 0, misses: 0, failed: 0 });

    const fillEl  = document.getElementById(`job-progress-fill-${jobId}`);
    const statsEl = document.getElementById(`job-progress-stats-${jobId}`);
    if (fillEl && totalRecords > 0) {
      fillEl.style.width = `${Math.min(100, Math.round(agg.processed / totalRecords * 100))}%`;
    }
    if (statsEl) {
      const pct = totalRecords > 0 ? ` (${Math.min(100, Math.round(agg.processed / totalRecords * 100))}%)` : '';
      statsEl.innerHTML =
        `<span class="jps-count">${agg.processed}${totalRecords > 0 ? '/' + totalRecords : ''}${pct}</span>` +
        ` <span class="jps-hits">✓ ${agg.hits}</span>` +
        ` <span class="jps-miss">— ${agg.misses}</span>` +
        ` <span class="jps-fail">✗ ${agg.failed}</span>`;
    }

    if (batches.length === 0) {
      batchesEl.innerHTML = '<p class="jobs-schema-empty" style="padding:4px 0">No batches.</p>';
      return;
    }

    batchesEl.innerHTML = batches.map(b => {
      const pct = b.total > 0 ? Math.round((b.processed / b.total) * 100) : 0;
      return `
      <div class="batch-row-wrap">
        <div class="batch-row" data-batch-id="${b.id}" data-status="${b.status}" data-expanded="false">
          <span class="batch-chevron">›</span>
          <span class="batch-number">B${b.batch_number}</span>
          <span class="batch-status-dot batch-dot-${b.status}"></span>
          <span class="batch-records">${b.total} records</span>
          <span class="batch-progress">${b.processed > 0 ? `${b.processed}/${b.total}` : ''}</span>
        </div>
        <div class="batch-detail" id="batch-detail-${b.id}">
          <div class="batch-detail-inner">
            <div class="batch-progress-bar-wrap">
              <div class="batch-progress-bar" style="width:${pct}%"></div>
            </div>
            <div class="batch-stats-grid">
              <div class="batch-stat">
                <span class="batch-stat-label">Total</span>
                <span class="batch-stat-value">${b.total}</span>
              </div>
              <div class="batch-stat">
                <span class="batch-stat-label">Processed</span>
                <span class="batch-stat-value batch-stat-processed">${b.processed}</span>
              </div>
              <div class="batch-stat">
                <span class="batch-stat-label">Hits</span>
                <span class="batch-stat-value batch-stat-hits">${b.hits ?? 0}</span>
              </div>
              <div class="batch-stat">
                <span class="batch-stat-label">Misses</span>
                <span class="batch-stat-value batch-stat-misses">${b.misses ?? 0}</span>
              </div>
              <div class="batch-stat">
                <span class="batch-stat-label">Errors</span>
                <span class="batch-stat-value batch-stat-errors">${b.failed ?? 0}</span>
              </div>
              <div class="batch-stat">
                <span class="batch-stat-label">Progress</span>
                <span class="batch-stat-value">${pct}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>`;
    }).join('');

    // Wire row click → expand/collapse
    batchesEl.querySelectorAll('.batch-row').forEach(row => {
      row.addEventListener('click', () => toggleBatchDetail(row));
    });
  } catch (e) {
    batchesEl.innerHTML = '<p class="jobs-schema-empty">Error loading batches.</p>';
  }
}

function toggleBatchDetail(row) {
  const batchId = row.dataset.batchId;
  const detail = document.getElementById(`batch-detail-${batchId}`);
  if (!detail) return;
  const isOpen = row.dataset.expanded === 'true';
  row.dataset.expanded = isOpen ? 'false' : 'true';
  detail.classList.toggle('open', !isOpen);
  row.querySelector('.batch-chevron')?.classList.toggle('open', !isOpen);
}


async function handleJobAction(btn) {
  const jobId = btn.dataset.jobId;
  const action = btn.dataset.action; // 'run' or 'pause'
  btn.disabled = true;

  try {
    if (action === 'run') {
      const res = await fetch(`${API_URL}/jobs/${jobId}/run`, { method: 'POST' });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Failed to start job');
      }
      showToast(`Job #${jobId} started`, 'success');
    } else {
      const res = await fetch(`${API_URL}/jobs/${jobId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'paused' })
      });
      if (!res.ok) throw new Error('Failed to pause job');
      showToast(`Job #${jobId} paused`, 'success');
    }
    // Reload job history to refresh status badge + button
    const { baseId, tableId } = parseAirtableUrl();
    if (baseId && tableId) loadJobHistory(baseId, tableId);
  } catch (e) {
    showToast(`${e.message}`, 'error');
    btn.disabled = false;
  }
}

/**
 * Initialize the extension
 */
function init() {
  // Create sidebar
  createSidebar();

  // Load theme preference
  loadTheme();

  // Set up event listeners
  setupEventListeners();

  // Check backend connection
  checkBackendConnection();

  console.log('AI Assistant initialized');
}

/**
 * Set up all event listeners
 */
function setupEventListeners() {
  // Toggle sidebar
  const toggleBtn = document.getElementById('ai-toggle');
  toggleBtn.addEventListener('click', toggleSidebar);

  // Minimize sidebar
  const minimizeBtn = document.getElementById('ai-minimize');
  minimizeBtn.addEventListener('click', minimizeSidebar);

  // Theme toggle
  const themeBtn = document.getElementById('ai-theme');
  themeBtn.addEventListener('click', toggleTheme);

  // Tab switching
  document.querySelectorAll('.ai-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      const targetTab = e.currentTarget.dataset.tab;
      document.querySelectorAll('.ai-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.ai-tab-panel').forEach(p => p.classList.add('hidden'));
      e.currentTarget.classList.add('active');
      document.getElementById(`tab-${targetTab}`).classList.remove('hidden');
      if (targetTab === 'mappings') initMappingsTab();
      if (targetTab === 'jobs') initJobsTab();
    });
  });

  // Create Mapping button
  document.getElementById('mappings-create-btn')?.addEventListener('click', openMappingModal);

  // Close modal
  document.getElementById('mapping-modal-close')?.addEventListener('click', closeMappingModal);

  // Dragging
  const header = document.getElementById('ai-header');
  header.addEventListener('mousedown', startDragging);

  // Resizing
  const resizeHandle = document.getElementById('ai-resize-handle');
  resizeHandle.addEventListener('mousedown', startResizing);

  // Global mouse events for drag and resize
  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onMouseUp);

  // Send message
  const sendBtn = document.getElementById('ai-send-btn');
  const input = document.getElementById('ai-chat-input');

  sendBtn.addEventListener('click', handleSendMessage);
  input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      handleSendMessage();
    }
  });

  // Quick action buttons
  const quickBtns = document.querySelectorAll('.ai-quick-btn');
  quickBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.getAttribute('data-action');
      handleQuickAction(action);
    });
  });

  // Welcome action buttons
  const welcomeBtns = document.querySelectorAll('.ai-welcome-btn');
  welcomeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.getAttribute('data-action');
      handleQuickAction(action);
    });
  });
}

/**
 * Toggle sidebar visibility
 */
function toggleSidebar() {
  const sidebar = document.getElementById('ai-crm-sidebar');
  isVisible = !isVisible;

  if (isVisible) {
    sidebar.classList.remove('hidden');
  } else {
    sidebar.classList.add('hidden');
  }
}

/**
 * Minimize/maximize sidebar
 */
function minimizeSidebar() {
  const sidebar = document.getElementById('ai-crm-sidebar');
  isMinimized = !isMinimized;

  if (isMinimized) {
    sidebar.classList.add('minimized');
  } else {
    sidebar.classList.remove('minimized');
  }

  saveSidebarState();
}

/**
 * Start dragging
 */
function startDragging(e) {
  // Don't drag if clicking on buttons or if minimized
  if (e.target.closest('button') || isMinimized) {
    if (isMinimized && e.target.closest('.ai-header')) {
      // Click anywhere on minimized header to maximize
      minimizeSidebar();
    }
    return;
  }

  isDragging = true;
  const sidebar = document.getElementById('ai-crm-sidebar');
  const rect = sidebar.getBoundingClientRect();

  dragStart = {
    x: e.clientX,
    y: e.clientY
  };

  initialPos = {
    x: rect.left,
    y: rect.top
  };

  e.preventDefault();
}

/**
 * Start resizing
 */
function startResizing(e) {
  isResizing = true;
  const sidebar = document.getElementById('ai-crm-sidebar');
  const rect = sidebar.getBoundingClientRect();

  dragStart = {
    x: e.clientX,
    y: e.clientY
  };

  initialSize = {
    width: rect.width,
    height: rect.height
  };

  e.preventDefault();
  e.stopPropagation();
}

/**
 * Handle mouse move (drag or resize)
 */
function onMouseMove(e) {
  if (isDragging) {
    const sidebar = document.getElementById('ai-crm-sidebar');
    const deltaX = e.clientX - dragStart.x;
    const deltaY = e.clientY - dragStart.y;

    let newX = initialPos.x + deltaX;
    let newY = initialPos.y + deltaY;

    // Keep within viewport
    newX = Math.max(0, Math.min(newX, window.innerWidth - sidebar.offsetWidth));
    newY = Math.max(0, Math.min(newY, window.innerHeight - sidebar.offsetHeight));

    sidebar.style.left = newX + 'px';
    sidebar.style.top = newY + 'px';
    sidebar.style.right = 'auto';
    sidebar.style.bottom = 'auto';
  }
  else if (isResizing) {
    const sidebar = document.getElementById('ai-crm-sidebar');
    const deltaX = e.clientX - dragStart.x;
    const deltaY = e.clientY - dragStart.y;

    let newWidth = initialSize.width + deltaX;
    let newHeight = initialSize.height + deltaY;

    // Apply constraints
    newWidth = Math.max(300, Math.min(newWidth, window.innerWidth * 0.9));
    newHeight = Math.max(400, Math.min(newHeight, window.innerHeight * 0.9));

    sidebar.style.width = newWidth + 'px';
    sidebar.style.height = newHeight + 'px';
  }
}

/**
 * Handle mouse up (stop drag or resize)
 */
function onMouseUp() {
  if (isDragging || isResizing) {
    isDragging = false;
    isResizing = false;
    saveSidebarState();
  }
}

/**
 * Save sidebar state to localStorage
 */
function saveSidebarState() {
  const sidebar = document.getElementById('ai-crm-sidebar');
  const state = {
    left: sidebar.style.left,
    top: sidebar.style.top,
    width: sidebar.style.width,
    height: sidebar.style.height,
    minimized: isMinimized
  };

  localStorage.setItem('ai-sidebar-state', JSON.stringify(state));
}

/**
 * Load sidebar state from localStorage
 */
function loadSidebarState() {
  const saved = localStorage.getItem('ai-sidebar-state');

  if (saved) {
    try {
      const state = JSON.parse(saved);
      const sidebar = document.getElementById('ai-crm-sidebar');

      if (state.left && state.top) {
        sidebar.style.left = state.left;
        sidebar.style.top = state.top;
        sidebar.style.right = 'auto';
      }

      if (state.width) sidebar.style.width = state.width;
      if (state.height) sidebar.style.height = state.height;

      if (state.minimized) {
        isMinimized = true;
        sidebar.classList.add('minimized');
      }
    } catch (e) {
      console.error('Failed to load sidebar state:', e);
    }
  }
}

/**
 * Toggle between light and dark theme
 */
function toggleTheme() {
  const sidebar = document.getElementById('ai-crm-sidebar');

  if (currentTheme === 'dark') {
    currentTheme = 'light';
    sidebar.classList.add('theme-light');
  } else {
    currentTheme = 'dark';
    sidebar.classList.remove('theme-light');
  }

  saveTheme();
}

/**
 * Save theme preference to localStorage
 */
function saveTheme() {
  localStorage.setItem('ai-theme', currentTheme);
}

/**
 * Load theme preference from localStorage or system preference
 */
function loadTheme() {
  const saved = localStorage.getItem('ai-theme');
  const sidebar = document.getElementById('ai-crm-sidebar');

  if (saved) {
    currentTheme = saved;
  } else {
    // Detect system preference
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    currentTheme = prefersDark ? 'dark' : 'light';
  }

  if (currentTheme === 'light') {
    sidebar.classList.add('theme-light');
  } else {
    sidebar.classList.remove('theme-light');
  }
}

/**
 * Check backend connection
 */
async function checkBackendConnection() {
  const statusEl = document.getElementById('ai-status');

  try {
    const response = await fetch(`${API_URL}/health`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (response.ok) {
      statusEl.textContent = 'Connected';
      statusEl.className = 'ai-status connected';
    } else {
      throw new Error('Backend not responding');
    }
  } catch (error) {
    statusEl.textContent = 'Disconnected - Backend not running';
    statusEl.className = 'ai-status error';
    console.error('Backend connection failed:', error);
  }
}

/**
 * Handle sending a message
 */
async function handleSendMessage() {
  console.log('🔧 handleSendMessage called');
  const input = document.getElementById('ai-chat-input');
  const message = input.value.trim();

  if (!message) return;

  // Clear input
  input.value = '';

  // Add user message to chat
  addMessage(message, 'user');

  // Get Airtable context
  const context = getAirtableContext();
  console.log('🔧 Sending message to backend:', message, 'context:', context);

  // Show typing indicator
  showTypingIndicator();

  // Send to backend
  try {
    console.log('🔧 Fetching:', `${API_URL}/chat`);
    const response = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        context: context,
        history: conversationHistory
      })
    });

    hideTypingIndicator();

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    // Check if backend wants to show a panel
    if (data.show_panel) {
      // Update conversation history BEFORE showing panel
      // This ensures the agent remembers the enrichment request
      conversationHistory.push(
        { role: 'user', content: message },
        { role: 'assistant', content: data.response || 'Starting enrichment workflow...' }
      );

      handlePanelRequest(data.show_panel);
      return; // Panel will handle adding completion message
    }

    // Add assistant response
    addMessage(data.response, 'assistant');

    // Update conversation history
    conversationHistory.push(
      { role: 'user', content: message },
      { role: 'assistant', content: data.response }
    );

  } catch (error) {
    hideTypingIndicator();
    addMessage(`Error: ${error.message}. Make sure the backend is running at ${API_URL}`, 'error');
    console.error('Chat error:', error);
  }
}

/**
 * Handle quick action buttons
 */
async function handleQuickAction(action) {
  switch (action) {
    case 'scrape':
    case 'enrich-current':
      handleScrapeProfile();
      break;

    case 'batch':
    case 'batch-enrich':
      handleBatchEnrich();
      break;

    case 'status':
      handleStatus();
      break;

    case 'clear':
      clearChat();
      break;

    case 'help':
      showHelp();
      break;

    default:
      console.log('Unknown action:', action);
  }
}

/**
 * Handle scraping current profile
 */
async function handleScrapeProfile() {
  console.log('🔧 handleScrapeProfile called');
  const context = getAirtableContext();
  console.log('🔧 Context:', context);

  if (!context.recordId) {
    addMessage('Please open a record to scrape its LinkedIn profile', 'system');
    return;
  }

  addMessage('Enriching LinkedIn profile for current record...', 'system');
  showTypingIndicator();

  try {
    // Use unified agent endpoint - orchestrator will classify intent and route
    console.log('🔧 Sending to agent:', `${API_URL}/agent/invoke`, 'with context:', context);
    const response = await fetch(`${API_URL}/agent/invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: 'Enrich this LinkedIn profile for the current record',
        context: context
      })
    });
    console.log('🔧 Agent response:', response);

    hideTypingIndicator();

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      const errorMsg = errorData.detail || errorData.message || `Server error (${response.status})`;
      addMessage(`❌ Error: ${errorMsg}`, 'error');
      showToast(`Enrichment failed: ${errorMsg}`, 'error');
      return;
    }

    const data = await response.json();

    // Check if agent needs approval (workflow interrupted)
    if (data.needs_approval && data.show_panel) {
      handlePanelRequest(data.show_panel);
      return; // Wait for panel response
    }

    // Agent completed successfully
    if (data.success) {
      const message = data.message || 'Operation completed successfully';
      addMessage(`✅ ${message}`, 'assistant');
      showToast(message, 'success');
    } else if (data.response) {
      addMessage(data.response, 'assistant');
    }

  } catch (error) {
    hideTypingIndicator();
    addMessage(`❌ Error: ${error.message}. Make sure the backend is running.`, 'error');
    showToast('Failed to connect to backend. Check if server is running.', 'error');
  }
}

/**
 * Handle batch enrichment
 */
async function handleBatchEnrich() {
  addMessage('Starting batch enrichment...', 'system');
  showTypingIndicator();

  try {
    // Use unified agent endpoint - orchestrator will classify as batch enrichment
    const context = getAirtableContext();
    const response = await fetch(`${API_URL}/agent/invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: 'Batch enrich all records in this view',
        context: context
      })
    });

    hideTypingIndicator();

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      const errorMsg = errorData.detail || errorData.message || `Server error (${response.status})`;
      addMessage(`❌ Error: ${errorMsg}`, 'error');
      showToast(`Batch enrichment failed: ${errorMsg}`, 'error');
      return;
    }

    const data = await response.json();

    // Check if agent needs approval (workflow interrupted)
    if (data.needs_approval && data.show_panel) {
      handlePanelRequest(data.show_panel);
      return; // Wait for panel response
    }

    // Agent completed successfully
    if (data.success) {
      const message = data.message || 'Batch enrichment completed';
      addMessage(`✅ ${message}`, 'assistant');
      showToast(message, 'success');
    } else if (data.response) {
      addMessage(data.response, 'assistant');
    }

  } catch (error) {
    hideTypingIndicator();
    addMessage(`❌ Error: ${error.message}. Make sure the backend is running.`, 'error');
    showToast('Failed to connect to backend. Check if server is running.', 'error');
  }
}

/**
 * Handle status check
 */
async function handleStatus() {
  await checkBackendConnection();

  const context = getAirtableContext();
  let statusMsg = `**Status:**\n`;
  statusMsg += `- Current Table: ${context.tableName || 'Unknown'}\n`;
  statusMsg += `- Current Record: ${context.recordId || 'None'}\n`;
  statusMsg += `- URL: ${window.location.href}\n`;

  addMessage(statusMsg, 'system');
}

/**
 * Show help message
 */
function showHelp() {
  const helpMsg = `**Available Commands:**

• **Scrape Profile** - Extract LinkedIn data for current record
• **Batch Process** - Enrich all contacts missing LinkedIn data
• **Status** - Check connection and current context
• **Clear Chat** - Clear conversation history

You can also type natural language queries like:
- "Find LinkedIn profiles for all contacts"
- "Scrape this person's profile"
- "Show me enrichment statistics"

**Sidebar Controls:**
- Drag the header to move
- Drag bottom-right corner to resize
- Click − to minimize
- Position/size is saved automatically`;

  addMessage(helpMsg, 'system');
}

/**
 * Clear chat history
 */
function clearChat() {
  const messagesEl = document.getElementById('ai-messages');
  messagesEl.innerHTML = '';
  conversationHistory = [];
  addMessage('Chat cleared', 'system');
}

/**
 * Add a message to the chat
 */
function addMessage(text, type = 'assistant') {
  const messagesEl = document.getElementById('ai-messages');

  const messageEl = document.createElement('div');
  messageEl.className = `ai-message ${type}`;

  // Convert markdown-style formatting
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\n/g, '<br>');

  messageEl.innerHTML = text;
  messagesEl.appendChild(messageEl);

  // Scroll to bottom
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/**
 * Show typing indicator
 */
function showTypingIndicator() {
  const messagesEl = document.getElementById('ai-messages');

  const typingEl = document.createElement('div');
  typingEl.className = 'ai-typing';
  typingEl.id = 'ai-typing-indicator';
  typingEl.innerHTML = '<span></span><span></span><span></span>';

  messagesEl.appendChild(typingEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/**
 * Hide typing indicator
 */
function hideTypingIndicator() {
  const typingEl = document.getElementById('ai-typing-indicator');
  if (typingEl) {
    typingEl.remove();
  }
}

/**
 * Get current Airtable context
 */
function getAirtableContext() {
  const url = window.location.href;
  const context = {
    url: url,
    tableName: null,
    recordId: null,
    viewId: null
  };

  // Parse Airtable URL
  // Format: https://airtable.com/{baseId}/{tableName}/{viewId}/{recordId}
  const match = url.match(/airtable\.com\/([^\/]+)\/([^\/]+)(?:\/([^\/]+))?(?:\/([^\/]+))?/);

  if (match) {
    context.baseId = match[1];
    context.tableName = match[2];
    context.viewId = match[3];
    context.recordId = match[4];
  }

  return context;
}

/**
 * Handle HITL panel display from backend
 */
function handlePanelRequest(panelInfo) {
  // Support both old and new backend data structures
  const panelType = panelInfo.type || panelInfo.panel_type;
  const panelData = panelInfo.data;
  const workflowId = panelInfo.thread_id || panelInfo.agent_id;
  const recordId = panelInfo.record_id || panelData?.record_id;

  console.log('[Panel] Showing panel:', { panelType, workflowId, recordId });

  // Handle approval panels (enrichment workflow)
  if (panelType === 'approval') {
    showInlineApproval(panelData, recordId);
    return;
  }

  // Handle inline approval (legacy)
  if (panelType === 'inline_approval') {
    showInlineApproval(panelData, recordId);
    return;
  }

  // Handle modal panels (field mapping, etc.)
  if (!window.HITLPanelManager) {
    console.error('HITL Panel Manager not loaded');
    return;
  }

  // Show modal panel and wait for user response
  window.HITLPanelManager.showPanel(
    panelType,
    panelData,
    workflowId,
    async (response) => {
      // Send response back to backend
      await sendPanelResponse(response, recordId);
    }
  );
}

/**
 * Show inline approval UI with editable text preview
 */
function showInlineApproval(data, recordId) {
  const { record_name, update_count, update_fields, similar_profiles_report } = data;

  // Extract recordId from data if not provided
  const finalRecordId = recordId || data.record_id;

  // Show title
  addMessage(`📊 **Ready to update ${record_name}** (${update_count} fields)`, 'info');

  // Convert fields to "Field: Value" format
  const fieldText = Object.entries(update_fields)
    .map(([field, value]) => `${field}: ${value}`)
    .join('\n');

  // Create editable text area inline in chat
  const chatBox = document.getElementById('ai-messages');
  const container = document.createElement('div');
  container.style.cssText = `
    margin: 10px 0;
    padding: 12px;
    background: #f9fafb;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
  `;

  // Instructions
  const instructions = document.createElement('div');
  instructions.style.cssText = `
    font-size: 13px;
    color: #6b7280;
    margin-bottom: 8px;
  `;
  instructions.textContent = 'Preview of updates:';
  container.appendChild(instructions);

  // Read-only textarea
  const textarea = document.createElement('textarea');
  textarea.value = fieldText;
  textarea.readOnly = true;
  textarea.rows = Math.min(update_count, 15);
  textarea.style.cssText = `
    width: 100%;
    padding: 10px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    font-family: 'Consolas', 'Monaco', monospace;
    resize: vertical;
    margin-bottom: 10px;
    background: #f9fafb;
    cursor: default;
  `;

  container.appendChild(textarea);

  // Similar profiles info
  if (similar_profiles_report?.available) {
    const reportInfo = document.createElement('div');
    reportInfo.style.cssText = `
      margin-bottom: 10px;
      padding: 8px;
      background: #f0f9ff;
      border: 1px solid #bae6fd;
      border-radius: 4px;
      font-size: 12px;
      color: #0c4a6e;
    `;
    reportInfo.textContent = `🔗 ${similar_profiles_report.count} similar profiles found`;
    container.appendChild(reportInfo);
  }

  // Button container
  const btnContainer = document.createElement('div');
  btnContainer.style.cssText = `
    display: flex;
    gap: 8px;
  `;

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = '❌ Cancel';
  cancelBtn.style.cssText = `
    padding: 8px 16px;
    background: #f3f4f6;
    color: #374151;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  `;
  cancelBtn.onclick = () => {
    container.remove();
    addMessage('❌ Update cancelled', 'info');
    sendPanelResponse({ status: 'cancelled' }, finalRecordId);
  };

  const saveBtn = document.createElement('button');
  saveBtn.textContent = '✅ Save to Airtable';
  saveBtn.style.cssText = `
    padding: 8px 16px;
    background: #22c55e;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
  `;
  saveBtn.onclick = async () => {
    // Disable buttons
    cancelBtn.disabled = true;
    saveBtn.disabled = true;
    cancelBtn.style.opacity = '0.5';
    saveBtn.style.opacity = '0.5';

    // Remove container
    container.remove();

    // Show loading toast (not message)
    showToast('⏳ Writing to Airtable...', 'info');

    // Send to backend with original fields (no parsing needed - read-only)
    await sendPanelResponse({
      status: 'approved',
      edited_fields: update_fields
    }, finalRecordId);
  };

  btnContainer.appendChild(cancelBtn);
  btnContainer.appendChild(saveBtn);
  container.appendChild(btnContainer);

  // Add to chat
  if (chatBox) {
    chatBox.appendChild(container);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
}

/**
 * Show download button for similar profiles report
 */
function showDownloadButton(filename, count) {
  const chatBox = document.getElementById('ai-messages');

  const container = document.createElement('div');
  container.style.cssText = `
    margin: 10px 0;
    padding: 12px;
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 8px;
  `;

  const text = document.createElement('div');
  text.style.cssText = `
    font-size: 13px;
    color: #0c4a6e;
    margin-bottom: 10px;
  `;
  text.textContent = `🔗 Found ${count} similar profile${count !== 1 ? 's' : ''} in network`;

  const button = document.createElement('button');
  button.textContent = '💾 Save Similar Profiles Report';
  button.style.cssText = `
    padding: 8px 16px;
    background: #0ea5e9;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
  `;

  button.onclick = async () => {
    try {
      button.disabled = true;
      button.textContent = '⏳ Downloading...';
      button.style.opacity = '0.6';

      // Download the file
      const response = await fetch(`${API_URL}/download/report/${filename}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Create blob and trigger download
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      // Update button
      button.textContent = '✅ Downloaded!';
      button.style.background = '#22c55e';

      // Remove button after 2 seconds
      setTimeout(() => {
        container.remove();
      }, 2000);

    } catch (error) {
      console.error('Download failed:', error);
      button.textContent = '❌ Download failed';
      button.style.background = '#dc2626';
      button.disabled = false;
      setTimeout(() => {
        button.textContent = '💾 Save Similar Profiles Report';
        button.style.background = '#0ea5e9';
        button.style.opacity = '1';
      }, 2000);
    }
  };

  container.appendChild(text);
  container.appendChild(button);

  if (chatBox) {
    chatBox.appendChild(container);
    chatBox.scrollTop = chatBox.scrollHeight;
  }
}

/**
 * Send panel response back to backend
 */
async function sendPanelResponse(response, recordId) {
  try {
    // Extract approval status and fields from response
    const approved = response.status === 'approved';
    const modifiedFields = response.edited_fields || null;

    // Call /resume endpoint with correct structure
    const res = await fetch(`${API_URL}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        record_id: recordId,
        approved: approved,
        modified_fields: modifiedFields
      })
    });

    // Check for HTTP errors
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }));
      const errorMsg = errorData.detail || errorData.message || `Server error (${res.status})`;
      console.error('HITL response failed:', errorMsg);
      addMessage(`❌ Error: ${errorMsg}`, 'error');
      showToast(`Failed to update record: ${errorMsg}`, 'error');
      return;
    }

    const result = await res.json();
    console.log('Panel response received:', result);

    // Show success/error message
    if (result.success) {
      // Show success message
      addMessage(result.response, 'assistant');
      showToast('Update complete!', 'success');

      // Update conversation history so agent remembers this enrichment
      conversationHistory.push({
        role: 'assistant',
        content: result.response
      });

      // Show download button for similar profiles report if available
      if (result.similar_profiles_report && result.similar_profiles_report.available) {
        const report = result.similar_profiles_report;
        showDownloadButton(report.filename, report.count);
      }
    } else {
      // Show error message
      const errorMsg = result.response || 'Update failed';
      addMessage(`❌ ${errorMsg}`, 'error');
      showToast(errorMsg, 'error');

      // Update conversation history for failures too
      conversationHistory.push({
        role: 'assistant',
        content: errorMsg
      });
    }

  } catch (error) {
    console.error('Failed to send panel response:', error);
    addMessage('❌ Error: Failed to send response to backend', 'error');
    showToast('Failed to connect to backend. Check if server is running.', 'error');
  }
}

/**
 * Show toast notification
 * @param {string} message - Message to display
 * @param {string} type - 'success', 'error', 'info', 'warning'
 */
function showToast(message, type = 'info') {
  // Create toast container if it doesn't exist
  let toastContainer = document.getElementById('crm-agent-toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'crm-agent-toast-container';
    toastContainer.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 999999;
      display: flex;
      flex-direction: column;
      gap: 10px;
    `;
    document.body.appendChild(toastContainer);
  }

  // Create toast element
  const toast = document.createElement('div');
  toast.style.cssText = `
    min-width: 250px;
    max-width: 400px;
    padding: 12px 16px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.4;
    color: white;
    animation: slideIn 0.3s ease-out;
    cursor: pointer;
  `;

  // Set color based on type
  const colors = {
    success: '#10b981',
    error: '#ef4444',
    warning: '#f59e0b',
    info: '#3b82f6'
  };
  toast.style.backgroundColor = colors[type] || colors.info;

  // Add icon based on type
  const icons = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ'
  };
  const icon = icons[type] || icons.info;

  toast.innerHTML = `
    <div style="display: flex; align-items: center; gap: 8px;">
      <span style="font-size: 16px; font-weight: bold;">${icon}</span>
      <span>${message}</span>
    </div>
  `;

  // Add click to dismiss
  toast.addEventListener('click', () => {
    toast.style.animation = 'slideOut 0.3s ease-in';
    setTimeout(() => toast.remove(), 300);
  });

  // Auto-dismiss after 5 seconds
  setTimeout(() => {
    if (toast.parentNode) {
      toast.style.animation = 'slideOut 0.3s ease-in';
      setTimeout(() => toast.remove(), 300);
    }
  }, 5000);

  toastContainer.appendChild(toast);
}

// Add toast animations to page
if (!document.getElementById('crm-agent-toast-styles')) {
  const style = document.createElement('style');
  style.id = 'crm-agent-toast-styles';
  style.textContent = `
    @keyframes slideIn {
      from {
        transform: translateX(400px);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
    @keyframes slideOut {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(400px);
        opacity: 0;
      }
    }
  `;
  document.head.appendChild(style);
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
