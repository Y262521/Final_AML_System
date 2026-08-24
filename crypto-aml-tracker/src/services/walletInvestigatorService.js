/**
 * Wallet Extraction and 3-Stage AML Investigation Service
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

/**
 * Fetch available data extraction sources.
 */
export const getExtractionSources = () => _get(`${API_BASE}/wallet-investigator/sources`);

/**
 * Fetch sample investigative target wallets.
 */
export const getSampleWallets = () => _get(`${API_BASE}/wallet-investigator/sample-wallets`);

/**
 * Fetch recent investigations in this session.
 */
export const getRecentInvestigations = () => _get(`${API_BASE}/wallet-investigator/recent`);

/**
 * Pre-flight check: Check if wallet is loaded in local database.
 * @param {string} address
 * @param {string} [chain]
 */
export const checkWalletDatabase = (address, chain = 'ethereum') => 
  _get(`${API_BASE}/wallet-investigator/check/${address}?chain=${encodeURIComponent(chain)}`);

/**
 * Extract on-chain transactions for a wallet from a source.
 * @param {{ address: string, chain?: string, source?: string, limit?: number, include_token_transfers?: boolean }} payload
 */
export const extractWalletData = (payload) => _post(`${API_BASE}/wallet-investigator/extract`, payload);

/**
 * Run full 3-Stage AML Investigation on target wallet.
 * @param {{ address: string, chain?: string, source?: string, limit?: number, force_refresh?: boolean }} payload
 */
export const investigateWallet = (payload) => _post(`${API_BASE}/wallet-investigator/investigate`, payload);
