/**
 * HITL Panel Manager
 *
 * Manages the lifecycle of HITL panels:
 * - Injection into DOM
 * - Rendering based on panel type
 * - User interaction handling
 * - Cleanup and removal
 */

// Panel renderer registry
const panelRenderers = {};

// Current active panel
let activePanel = null;

/**
 * Register a panel renderer
 *
 * @param {string} panelType - Type of panel (e.g., 'approval', 'field_mapping')
 * @param {Function} renderer - Function that renders the panel
 */
function registerPanelRenderer(panelType, renderer) {
  panelRenderers[panelType] = renderer;
  console.log(`Registered panel renderer: ${panelType}`);
}

/**
 * Show a panel to the user
 *
 * @param {string} panelType - Type of panel to show
 * @param {Object} data - Data to populate the panel
 * @param {string} agentId - Agent identifier
 * @param {Function} onResponse - Callback when user responds
 */
function showPanel(panelType, data, agentId, onResponse) {
  // Hide any existing panel first
  if (activePanel) {
    hidePanel();
  }

  // Get renderer for this panel type
  const renderer = panelRenderers[panelType];
  if (!renderer) {
    console.error(`No renderer registered for panel type: ${panelType}`);
    return;
  }

  // Create panel container
  const panelContainer = document.createElement('div');
  panelContainer.id = 'hitl-panel-container';
  panelContainer.className = 'hitl-panel-container';

  // Theme handled by CSS only - no JavaScript needed

  // Create panel overlay (backdrop)
  const overlay = document.createElement('div');
  overlay.className = 'hitl-panel-overlay';
  overlay.onclick = (e) => {
    // Only close if clicking directly on overlay, not its children
    if (e.target === overlay) {
      handleCancel();
    }
  };

  // Create panel content wrapper
  const panelWrapper = document.createElement('div');
  panelWrapper.className = 'hitl-panel-wrapper';

  // Render panel content using registered renderer
  const panelContent = renderer(data, {
    onConfirm: (response) => handleConfirm(response),
    onCancel: () => handleCancel()
  });

  panelWrapper.appendChild(panelContent);
  overlay.appendChild(panelWrapper);
  panelContainer.appendChild(overlay);

  // Add to DOM (body level for full-screen fixed overlay)
  document.body.appendChild(panelContainer);

  // Store reference
  activePanel = {
    container: panelContainer,
    type: panelType,
    agentId: agentId,
    onResponse: onResponse
  };

  // Animate in
  requestAnimationFrame(() => {
    panelContainer.classList.add('active');
  });

  // Response handlers
  function handleConfirm(response) {
    if (onResponse) {
      onResponse({
        status: 'confirmed',
        data: response
      });
    }
    hidePanel();
  }

  function handleCancel() {
    if (onResponse) {
      onResponse({
        status: 'cancelled'
      });
    }
    hidePanel();
  }
}

/**
 * Hide the currently active panel
 */
function hidePanel() {
  if (!activePanel) return;

  const container = activePanel.container;

  // Animate out
  container.classList.remove('active');

  // Remove from DOM after animation
  setTimeout(() => {
    if (container.parentNode) {
      container.parentNode.removeChild(container);
    }
  }, 250); // Match CSS transition time

  activePanel = null;
}

/**
 * Get the currently active panel (if any)
 *
 * @returns {Object|null} Active panel info or null
 */
function getActivePanel() {
  return activePanel;
}

/**
 * Check if a panel is currently active
 *
 * @returns {boolean} True if panel is active
 */
function isPanelActive() {
  return activePanel !== null;
}

// Export functions
window.HITLPanelManager = {
  registerPanelRenderer,
  showPanel,
  hidePanel,
  getActivePanel,
  isPanelActive
};

console.log('HITL Panel Manager loaded');
