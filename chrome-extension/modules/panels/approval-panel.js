/**
 * Simple Approval Panel (for testing HITL flow)
 *
 * Shows a message and asks user to approve or reject.
 */

function renderApprovalPanel(data, callbacks) {
  const { onConfirm, onCancel } = callbacks;

  // Extract data
  const title = data.title || 'Approval Required';
  const message = data.message || 'Please review and approve this action.';
  const confirmText = data.confirmText || 'Approve';
  const cancelText = data.cancelText || 'Reject';

  // Create panel element
  const panel = document.createElement('div');
  panel.className = 'hitl-panel';

  panel.innerHTML = `
    <div class="hitl-panel-header">
      <h2 class="hitl-panel-title">${escapeHtml(title)}</h2>
    </div>

    <div class="hitl-panel-body">
      <div class="hitl-panel-message">
        ${escapeHtml(message)}
      </div>
    </div>

    <div class="hitl-panel-footer">
      <button class="hitl-btn hitl-btn-secondary" id="approval-cancel">
        ${escapeHtml(cancelText)}
      </button>
      <button class="hitl-btn hitl-btn-primary" id="approval-confirm">
        ${escapeHtml(confirmText)}
      </button>
    </div>
  `;

  // Add event listeners
  const confirmBtn = panel.querySelector('#approval-confirm');
  const cancelBtn = panel.querySelector('#approval-cancel');

  confirmBtn.addEventListener('click', () => {
    onConfirm({
      approved: true,
      timestamp: new Date().toISOString()
    });
  });

  cancelBtn.addEventListener('click', () => {
    onCancel();
  });

  return panel;
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
  window.HITLPanelManager.registerPanelRenderer('approval', renderApprovalPanel);
  console.log('Approval panel registered');
}
