/**
 * HITL Storage Utilities
 *
 * Handles persistent storage of HITL configurations using localStorage.
 * Provides episodic memory for field mappings per Airtable base/table.
 */

const STORAGE_PREFIX = 'hitl-config-';

/**
 * Save field mapping configuration for a specific base/table
 *
 * @param {string} baseId - Airtable base ID
 * @param {string} tableId - Airtable table ID
 * @param {Object} config - Field mapping configuration
 */
function saveFieldMappingConfig(baseId, tableId, config) {
  const key = `${STORAGE_PREFIX}${baseId}-${tableId}`;

  const storageData = {
    baseId,
    tableId,
    config,
    savedAt: new Date().toISOString(),
    version: '1.0'
  };

  try {
    localStorage.setItem(key, JSON.stringify(storageData));
    console.log(`Saved field mapping config for ${baseId}/${tableId}`);
    return true;
  } catch (error) {
    console.error('Failed to save field mapping config:', error);
    return false;
  }
}

/**
 * Load field mapping configuration for a specific base/table
 *
 * @param {string} baseId - Airtable base ID
 * @param {string} tableId - Airtable table ID
 * @returns {Object|null} Saved configuration or null if not found
 */
function loadFieldMappingConfig(baseId, tableId) {
  const key = `${STORAGE_PREFIX}${baseId}-${tableId}`;

  try {
    const data = localStorage.getItem(key);
    if (!data) {
      return null;
    }

    const storageData = JSON.parse(data);
    console.log(`Loaded field mapping config for ${baseId}/${tableId}`);
    return storageData.config;
  } catch (error) {
    console.error('Failed to load field mapping config:', error);
    return null;
  }
}

/**
 * Check if field mapping configuration exists for a base/table
 *
 * @param {string} baseId - Airtable base ID
 * @param {string} tableId - Airtable table ID
 * @returns {boolean} True if configuration exists
 */
function hasFieldMappingConfig(baseId, tableId) {
  const key = `${STORAGE_PREFIX}${baseId}-${tableId}`;
  return localStorage.getItem(key) !== null;
}

/**
 * Delete field mapping configuration for a base/table
 *
 * @param {string} baseId - Airtable base ID
 * @param {string} tableId - Airtable table ID
 * @returns {boolean} True if successfully deleted
 */
function deleteFieldMappingConfig(baseId, tableId) {
  const key = `${STORAGE_PREFIX}${baseId}-${tableId}`;

  try {
    localStorage.removeItem(key);
    console.log(`Deleted field mapping config for ${baseId}/${tableId}`);
    return true;
  } catch (error) {
    console.error('Failed to delete field mapping config:', error);
    return false;
  }
}

/**
 * Get all saved field mapping configurations
 *
 * @returns {Array} Array of saved configurations with metadata
 */
function getAllFieldMappingConfigs() {
  const configs = [];

  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(STORAGE_PREFIX)) {
        const data = localStorage.getItem(key);
        if (data) {
          const storageData = JSON.parse(data);
          configs.push({
            baseId: storageData.baseId,
            tableId: storageData.tableId,
            savedAt: storageData.savedAt,
            fieldCount: Object.keys(storageData.config.mappings || {}).length
          });
        }
      }
    }
  } catch (error) {
    console.error('Failed to list field mapping configs:', error);
  }

  return configs;
}

// Export functions
window.HITLStorage = {
  saveFieldMappingConfig,
  loadFieldMappingConfig,
  hasFieldMappingConfig,
  deleteFieldMappingConfig,
  getAllFieldMappingConfigs
};

console.log('HITL Storage utilities loaded');
