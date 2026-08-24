/**
 * Transaction and Analytics API service layer.
 *
 * All functions throw on non-OK HTTP responses so callers can
 * display explicit error states without masking failures.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

async function _get(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`[${res.status}] ${text || res.statusText}`);
  }
  return res.json();
}

async function _post(url, body = {}) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`[${res.status}] ${text || res.statusText}`);
  }
  return res.json();
}

// ── Transactions ───────────────────────────────────────────────────────────────

/**
 * Get latest transactions (feed).
 * @param {{ limit?: number, offset?: number, sortBy?: 'value_usd_desc' | 'amount_desc' | 'latest', chain?: string }} opts
 */
export const getLatestTransactions = async ({ limit = 200, offset = 0, sortBy = 'value_usd_desc', chain } = {}) => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), sort_by: sortBy });
  if (chain && chain !== 'all') params.set('chain', chain);
  try {
    return await _get(`${API_BASE}/transactions/?${params}`);
  } catch (err) {
    if (sortBy === 'value_usd_desc') {
      const fallbackParams = new URLSearchParams({ limit: String(limit), offset: String(offset), sort_by: 'amount_desc' });
      if (chain && chain !== 'all') fallbackParams.set('chain', chain);
      return await _get(`${API_BASE}/transactions/?${fallbackParams}`);
    }
    throw err;
  }
};

/**
 * Get graph data for visualization.
 * @param {{ search?: string, center?: string, hops?: number, maxEdges?: number, minValue?: number, chain?: string }} opts
 */
export const getGraphData = ({ search, center, hops = 2, maxEdges = 300, minValue = 0, chain } = {}) => {
  const params = new URLSearchParams({ hops: String(hops), max_edges: String(maxEdges), min_value: String(minValue) });
  if (search) params.set('search', search);
  if (center) params.set('center', center);
  if (chain && chain !== 'all') params.set('chain', chain);
  return _get(`${API_BASE}/transactions/graph?${params}`);
};

/**
 * Get analytics summary.
 */
export const getAnalytics = () => _get(`${API_BASE}/transactions/analytics`);

// ── Clusters ────────────────────────────────────────────────────────────────────

/**
 * Get all clusters.
 * @param {{ limit?: number, minSize?: number }} opts
 */
export const getClusters = ({ limit = 1000, minSize = 2 } = {}) => {
  const params = new URLSearchParams({ limit: String(limit), min_size: String(minSize) });
  // We request only summary payloads here; detailed data is fetched per-cluster.
  return _get(`${API_BASE}/clusters/?${params}`);
};

/**
 * Get clusters summary.
 */
export const getClustersSummary = () => _get(`${API_BASE}/clusters/summary`);

/**
 * Trigger clustering run.
 */
export const runClustering = () => _post(`${API_BASE}/clusters/run`);

/**
 * Get owner by address.
 */
export const getOwnerByAddress = (address) => _get(`${API_BASE}/clusters/owner-by-address/${address}`);

/**
 * Get cluster details by ID.
 * @param {string} clusterId
 */
export async function getCluster(clusterId) {
  const url = new URL(`${API_BASE}/clusters/${clusterId}`);
  const resp = await fetch(url.toString());
  if (!resp.ok) {
    throw new Error(`Failed to fetch cluster ${clusterId}: ${resp.status}`);
  }
  return resp.json();
}
/**
 * Create or update owner list entry.
 * @param {object} ownerData - Owner information with addresses
 */
export const createOwnerListEntry = (ownerData) => _post(`${API_BASE}/clusters/owner-list`, ownerData);

// ── Placement ───────────────────────────────────────────────────────────────────

/**
 * Get placement detection runs.
 */
export const getPlacementRuns = () => _get(`${API_BASE}/placement/runs`);

/**
 * Get placement summary.
 * @param {{ runId?: string, beforeDate?: string }} opts
 */
export const getPlacementSummary = ({ runId, beforeDate } = {}) => {
  const params = new URLSearchParams();
  if (runId) params.set('run_id', runId);
  if (beforeDate) params.set('beforeDate', beforeDate);
  return _get(`${API_BASE}/placement/summary?${params}`);
};

/**
 * Get placement alerts.
 * @param {{ limit?: number, minConfidence?: number, runId?: string, beforeDate?: string, chain?: string }} opts
 */
export const getPlacements = ({ limit = 5000, minConfidence = 0.0, runId, beforeDate, chain } = {}) => {
  const params = new URLSearchParams({ limit: String(limit), min_confidence: String(minConfidence) });
  if (runId) params.set('run_id', runId);
  if (beforeDate) params.set('before_date', beforeDate);
  if (chain) params.set('chain', chain);
  return _get(`${API_BASE}/placement/?${params}`);
};

// ── Layering ────────────────────────────────────────────────────────────────────

/**
 * Get layering analysis runs.
 */
export const getLayeringRuns = () => _get(`${API_BASE}/layering/runs`);

/**
 * Get layering summary.
 * @param {{ runId?: string }} opts
 */
export const getLayeringSummary = ({ runId } = {}) => {
  const params = new URLSearchParams();
  if (runId) params.set('run_id', runId);
  return _get(`${API_BASE}/layering/summary?${params}`);
};

/**
 * Get layering alerts.
 * @param {{ limit?: number, minConfidence?: number, runId?: string, chain?: string }} opts
 */
export const getLayeringAlerts = ({ limit = 5000, minConfidence = 0.0, runId, chain } = {}) => {
  const params = new URLSearchParams({ limit: String(limit), min_confidence: String(minConfidence) });
  if (runId) params.set('run_id', runId);
  if (chain) params.set('chain', chain);
  return _get(`${API_BASE}/layering/?${params}`);
};

// ── Integration ─────────────────────────────────────────────────────────────────

/**
 * Get integration analysis runs.
 */
export const getIntegrationRuns = () => _get(`${API_BASE}/integration/runs`);

/**
 * Get integration summary.
 * @param {{ runId?: string, beforeDate?: string }} opts
 */
export const getIntegrationSummary = ({ runId, beforeDate } = {}) => {
  const params = new URLSearchParams();
  if (runId) params.set('run_id', runId);
  if (beforeDate) params.set('beforeDate', beforeDate);
  return _get(`${API_BASE}/integration/summary?${params}`);
};

/**
 * Get integration alerts.
 * @param {{ runId?: string, beforeDate?: string, limit?: number, minScore?: number, signal?: string, chain?: string }} opts
 */
export const getIntegrationAlerts = ({ runId, beforeDate, limit = 10000, minScore = 0.0, signal, chain } = {}) => {
  const params = new URLSearchParams({ limit: String(limit), minScore: String(minScore) });
  if (runId) params.set('run_id', runId);
  if (beforeDate) params.set('beforeDate', beforeDate);
  if (signal) params.set('signal', signal);
  if (chain) params.set('chain', chain);
  return _get(`${API_BASE}/integration/?${params}`);
};

// ── Chain of Custody ────────────────────────────────────────────────────────────

/**
 * Get chain of custody for an entity (Placement → Layering → Integration).
 * @param {string} entityId
 */
export const getChainOfCustody = (entityId) => _get(`${API_BASE}/chain-of-custody/${entityId}`);

/**
 * Post integration feedback for an entity.
 * @param {string} entityId
 * @param {object} feedback
 */
export const postIntegrationFeedback = (entityId, feedback) => _post(`${API_BASE}/chain-of-custody/${entityId}/feedback`, feedback);

// ── Database Labels & Evaluation ────────────────────────────────────────────────

/**
 * Pull labeled wallet addresses directly from the database table (wallet_labels).
 * @param {{ label?: string, category?: string, chain?: string, source?: string, limit?: number }} opts
 */
export const getDatabaseLabels = ({ label, category, chain, source, limit = 1000 } = {}) => {
  const params = new URLSearchParams({ limit: String(limit) });
  if (label) params.set('label', label);
  if (category) params.set('category', category);
  if (chain) params.set('chain', chain);
  if (source) params.set('source', source);
  return _get(`${API_BASE}/testing/labels?${params}`);
};

/**
 * Synchronize / seed ground truth and owner registry labels directly into the database.
 * @param {Array} wallets
 */
export const syncDatabaseLabels = (wallets = null) => _post(`${API_BASE}/testing/labels/sync`, { wallets });

/**
 * Run evaluation directly against database-labeled addresses.
 * @param {{ label?: string, category?: string, chain?: string, source?: string, limit?: number }} opts
 */
export const evaluateFromDatabase = (opts = {}) => _post(`${API_BASE}/testing/evaluate-from-db`, opts);

/**
 * Pull labels from database and automatically relabel all wallet clusters.
 */
export const syncClusterLabelsFromDb = () => _post(`${API_BASE}/clusters/sync-labels-from-db`);

/**
 * Get all owner labels and address mappings from database.
 */
export const getAllClusterLabels = () => _get(`${API_BASE}/clusters/labels/all`);

