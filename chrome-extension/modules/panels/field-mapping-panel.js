/**
 * Field Mapping Panel
 *
 * Allows users to configure how LinkedIn data maps to Airtable fields.
 * Features:
 * - Enable/disable fields
 * - Select source field from dropdown
 * - Configure overwrite behavior
 * - Save configuration to localStorage
 */

function renderFieldMappingPanel(data, callbacks) {
  const { onConfirm, onCancel } = callbacks;

  // Extract data
  const baseId = data.base_id;
  const tableId = data.table_id;
  const airtableFields = data.airtable_fields || [];
  const linkedinFields = data.linkedin_fields || [];
  const suggestions = data.suggestions || {};

  // State for form
  const formState = {};

  // Initialize form state from suggestions
  airtableFields.forEach(field => {
    const suggestion = suggestions[field.name] || {};
    formState[field.name] = {
      enabled: suggestion.enabled || false,
      source: suggestion.source || '',
      overwrite: suggestion.overwrite || 'empty_only'
    };
  });

  // Create panel element
  const panel = document.createElement('div');
  panel.className = 'hitl-panel';

  // Build field rows HTML
  const fieldRowsHTML = airtableFields.map(field => {
    const state = formState[field.name];
    const fieldId = `field-${field.name.replace(/\s+/g, '-')}`;

    return `
      <div class="field-mapping-row" data-field="${escapeHtml(field.name)}">
        <div class="field-mapping-header">
          <label class="field-checkbox-label">
            <input
              type="checkbox"
              class="hitl-form-checkbox field-enabled-checkbox"
              data-field="${escapeHtml(field.name)}"
              ${state.enabled ? 'checked' : ''}
            />
            <span class="field-name">${escapeHtml(field.name)}</span>
            <span class="field-type">${escapeHtml(field.type)}</span>
          </label>
        </div>

        <div class="field-mapping-controls ${state.enabled ? '' : 'disabled'}">
          <div class="hitl-form-group">
            <label class="hitl-form-label">← Source from LinkedIn</label>
            <select
              class="hitl-form-select field-source-select"
              data-field="${escapeHtml(field.name)}"
              ${state.enabled ? '' : 'disabled'}
            >
              <option value="">-- Select LinkedIn field --</option>
              ${linkedinFields.map(lf => `
                <option value="${escapeHtml(lf)}" ${state.source === lf ? 'selected' : ''}>
                  ${escapeHtml(lf)}
                </option>
              `).join('')}
            </select>
          </div>

          <div class="hitl-form-group">
            <label class="hitl-form-label">Overwrite Mode</label>
            <select
              class="hitl-form-select field-overwrite-select"
              data-field="${escapeHtml(field.name)}"
              ${state.enabled ? '' : 'disabled'}
            >
              <option value="empty_only" ${state.overwrite === 'empty_only' ? 'selected' : ''}>
                Only if empty
              </option>
              <option value="always" ${state.overwrite === 'always' ? 'selected' : ''}>
                Always replace
              </option>
            </select>
          </div>
        </div>
      </div>
    `;
  }).join('');

  panel.innerHTML = `
    <div class="hitl-panel-header">
      <h2 class="hitl-panel-title">Configure Field Mapping</h2>
      <p class="hitl-panel-subtitle">
        Map LinkedIn data → Airtable fields
      </p>
    </div>

    <div class="hitl-panel-body">
      <div class="hitl-panel-message info">
        <strong>How it works:</strong> Select which Airtable fields to update, then choose which LinkedIn field to pull data from.
        Your configuration will be saved for future enrichments.
      </div>

      <div class="airtable-fields-header">
        <span class="airtable-fields-icon">📋</span>
        <strong class="airtable-fields-title">Your Airtable Fields</strong>
      </div>

      <div class="field-mapping-list">
        ${fieldRowsHTML}
      </div>
    </div>

    <div class="hitl-panel-footer">
      <button class="hitl-btn hitl-btn-secondary" id="field-mapping-cancel">
        Cancel
      </button>
      <button class="hitl-btn hitl-btn-primary" id="field-mapping-save">
        Save Configuration
      </button>
    </div>
  `;

  // Add event listeners
  setupEventListeners();

  return panel;

  // Helper functions
  function setupEventListeners() {
    // Checkbox toggle
    panel.querySelectorAll('.field-enabled-checkbox').forEach(checkbox => {
      checkbox.addEventListener('change', (e) => {
        const fieldName = e.target.dataset.field;
        const row = panel.querySelector(`.field-mapping-row[data-field="${fieldName}"]`);
        const controls = row.querySelector('.field-mapping-controls');
        const selects = controls.querySelectorAll('select');

        formState[fieldName].enabled = e.target.checked;

        if (e.target.checked) {
          controls.classList.remove('disabled');
          selects.forEach(s => s.disabled = false);
        } else {
          controls.classList.add('disabled');
          selects.forEach(s => s.disabled = true);
        }
      });
    });

    // Source field selection
    panel.querySelectorAll('.field-source-select').forEach(select => {
      select.addEventListener('change', (e) => {
        const fieldName = e.target.dataset.field;
        formState[fieldName].source = e.target.value;
      });
    });

    // Overwrite mode selection
    panel.querySelectorAll('.field-overwrite-select').forEach(select => {
      select.addEventListener('change', (e) => {
        const fieldName = e.target.dataset.field;
        formState[fieldName].overwrite = e.target.value;
      });
    });

    // Cancel button
    const cancelBtn = panel.querySelector('#field-mapping-cancel');
    cancelBtn.addEventListener('click', () => {
      onCancel();
    });

    // Save button
    const saveBtn = panel.querySelector('#field-mapping-save');
    saveBtn.addEventListener('click', () => {
      // Build config object
      const config = {
        base_id: baseId,
        table_id: tableId,
        mappings: {}
      };

      // Only include enabled mappings
      Object.keys(formState).forEach(fieldName => {
        const state = formState[fieldName];
        if (state.enabled && state.source) {
          config.mappings[fieldName] = {
            source: state.source,
            enabled: true,
            overwrite: state.overwrite
          };
        }
      });

      // Validate: at least one field enabled
      if (Object.keys(config.mappings).length === 0) {
        alert('Please enable at least one field mapping');
        return;
      }

      // Save to localStorage for episodic memory
      if (window.HITLStorage) {
        window.HITLStorage.saveFieldMappingConfig(baseId, tableId, config);
      }

      onConfirm(config);
    });
  }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Register this panel renderer
if (window.HITLPanelManager) {
  window.HITLPanelManager.registerPanelRenderer('field_mapping', renderFieldMappingPanel);
  console.log('Field mapping panel registered');
}
