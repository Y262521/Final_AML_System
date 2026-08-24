import { useState, useEffect, useCallback, useMemo } from 'react';
import Loader from '../components/common/Loader';
import ChainBadge from '../components/chain/ChainBadge';
import CourtReportDocument from '../components/intelligence/CourtReportDocument';
import {
  getExtractionSources,
  getSampleWallets,
  getRecentInvestigations,
  investigateWallet,
  extractWalletData,
  checkWalletDatabase,
} from '../services/walletInvestigatorService';

const CHAINS = [
  { id: 'ethereum', label: 'Ethereum', asset: 'ETH', icon: '⟠', color: '#627EEA' },
  { id: 'bnb', label: 'BNB Chain', asset: 'BNB', icon: '🟡', color: '#F3BA2F' },
  { id: 'polygon', label: 'Polygon', asset: 'POL', icon: '🟣', color: '#8247E5' },
  { id: 'arbitrum', label: 'Arbitrum', asset: 'ETH', icon: '🔵', color: '#2D374B' },
  { id: 'base', label: 'Base', asset: 'ETH', icon: '🔷', color: '#0052FF' },
  { id: 'bitcoin', label: 'Bitcoin', asset: 'BTC', icon: '₿', color: '#F7931A' },
  { id: 'litecoin', label: 'Litecoin', asset: 'LTC', icon: 'Ł', color: '#A6A9AA' },
  { id: 'dogecoin', label: 'Dogecoin', asset: 'DOGE', icon: 'Ð', color: '#C2A633' },
  { id: 'bitcoin_cash', label: 'Bitcoin Cash', asset: 'BCH', icon: 'Ƀ', color: '#8DC351' },
  { id: 'solana', label: 'Solana', asset: 'SOL', icon: '◎', color: '#14F195' },
];

const DEFAULT_SOURCES = [
  { id: 'local_db', name: 'Local AML Warehouse', description: 'Indexed MariaDB & MongoDB cluster', status: 'online' },
  { id: 'alchemy', name: 'Alchemy RPC Gateway', description: 'Live blockchain node extraction', status: 'online' },
  { id: 'sqd', name: 'Subsquid (SQD) Portal', description: 'Multi-chain lake (200+ networks)', status: 'online' },
  { id: 'aws_s3', name: 'AWS Open Data Lake', description: 'Historical blockchain parquets', status: 'standby' },
  { id: 'bigquery', name: 'Google BigQuery', description: 'Cloud public data warehouse', status: 'standby' },
];

const formatUSD = (val) => {
  const n = Number(val || 0);
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const formatCrypto = (val, asset = 'ETH') => {
  const n = Number(val || 0);
  return `${n.toLocaleString('en-US', { maximumFractionDigits: 4 })} ${asset}`;
};

const truncateHash = (hash, front = 8, back = 6) => {
  if (!hash) return '-';
  if (hash.length <= front + back) return hash;
  return `${hash.slice(0, front)}...${hash.slice(-back)}`;
};

export default function WalletInvestigator({ initialAddress = '', onNavigateToGraph }) {
  const [addressInput, setAddressInput] = useState(initialAddress || '');
  const [selectedChain, setSelectedChain] = useState('ethereum');
  const [selectedSource, setSelectedSource] = useState('local_db');
  const [limit, setLimit] = useState(100);
  const [activeTab, setActiveTab] = useState('typology'); // 'typology', 'graph', 'transactions', 'dossier'
  
  // Data Sources & Sample Wallets
  const [sources, setSources] = useState(DEFAULT_SOURCES);
  const [samples, setSamples] = useState([]);
  const [recentList, setRecentList] = useState([]);

  // Database Pre-Check States
  const [dbCheckLoading, setDbCheckLoading] = useState(false);
  const [dbCheckResult, setDbCheckResult] = useState(null);

  // Execution & Investigation States
  const [loading, setLoading] = useState(false);
  const [progressStep, setProgressStep] = useState(0); // 0: idle, 1: checking db, 2: extracting/loading, 3: placement, 4: layering, 5: integration, 6: done
  const [investigationData, setInvestigationData] = useState(null);
  const [error, setError] = useState(null);

  // Table filtering & search
  const [txSearch, setTxSearch] = useState('');
  const [txStageFilter, setTxStageFilter] = useState('all');

  // Load sources and sample wallets on mount
  useEffect(() => {
    getExtractionSources().then(res => {
      if (res?.sources) setSources(res.sources);
    }).catch(() => {});

    getSampleWallets().then(res => {
      if (res?.samples) setSamples(res.samples);
    }).catch(() => {});

    getRecentInvestigations().then(res => {
      if (res?.recent) setRecentList(res.recent);
    }).catch(() => {});
  }, []);

  // Pre-flight database check whenever address or chain changes (debounced)
  useEffect(() => {
    const trimmed = (addressInput || '').trim();
    if (!trimmed || trimmed.length < 6) {
      setDbCheckResult(null);
      setDbCheckLoading(false);
      return;
    }

    setDbCheckLoading(true);
    const timer = setTimeout(() => {
      checkWalletDatabase(trimmed, selectedChain)
        .then((res) => {
          setDbCheckResult(res);
        })
        .catch((err) => {
          console.warn('Pre-flight DB check failed:', err);
          setDbCheckResult(null);
        })
        .finally(() => {
          setDbCheckLoading(false);
        });
    }, 350);

    return () => clearTimeout(timer);
  }, [addressInput, selectedChain]);

  // Auto-trigger if initialAddress provided
  useEffect(() => {
    if (initialAddress && initialAddress.trim().length > 6) {
      setAddressInput(initialAddress);
      handleExecuteInvestigation(initialAddress);
    }
  }, [initialAddress]);

  const handleExecuteInvestigation = async (addrToUse) => {
    const targetAddr = (addrToUse || addressInput || '').trim();
    if (!targetAddr) {
      setError('Please insert a valid wallet address to extract.');
      return;
    }

    setError(null);
    setLoading(true);
    setProgressStep(1); // 1. Checking Local Database

    try {
      // Step 1: Pre-flight check database
      const checkRes = await checkWalletDatabase(targetAddr, selectedChain).catch(() => null);
      if (checkRes) setDbCheckResult(checkRes);

      await new Promise(r => setTimeout(r, 220));
      setProgressStep(2); // 2. Extracting from Source or Local Cache

      await new Promise(r => setTimeout(r, 250));
      setProgressStep(3); // 3. Placement Profiling

      await new Promise(r => setTimeout(r, 200));
      setProgressStep(4); // 4. Layering Analysis

      await new Promise(r => setTimeout(r, 200));
      setProgressStep(5); // 5. Integration Analysis

      // Execute API Investigation
      const res = await investigateWallet({
        address: targetAddr,
        chain: selectedChain,
        source: selectedSource,
        limit: Number(limit),
      });

      setProgressStep(6);
      setInvestigationData(res);

      // Refresh recent list
      getRecentInvestigations().then(r => {
        if (r?.recent) setRecentList(r.recent);
      }).catch(() => {});

    } catch (err) {
      console.error('Investigation failed:', err);
      setError(err.message || 'Failed to complete wallet extraction and investigation.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSample = (sample) => {
    setAddressInput(sample.address);
    if (sample.chain) setSelectedChain(sample.chain);
    handleExecuteInvestigation(sample.address);
  };

  // Filtered transactions for Ledger Tab
  const filteredTxs = useMemo(() => {
    if (!investigationData?.transactions) return [];
    const list = investigationData.transactions;
    const q = txSearch.toLowerCase().trim();
    const addr = (investigationData.address || '').toLowerCase();

    return list.filter(tx => {
      // Stage filter
      if (txStageFilter === 'placement') {
        if ((tx.to_address || '').toLowerCase() !== addr) return false;
      } else if (txStageFilter === 'layering') {
        if ((tx.from_address || '').toLowerCase() !== addr) return false;
      } else if (txStageFilter === 'integration') {
        const dest = (tx.to_address || '').toLowerCase();
        const isCex = ['0x28c6c06298d514db089934071355e5743bf21d60', '0x742d35cc6634c0532925a3b844bc454e4438f44e'].includes(dest);
        if (!isCex && (tx.from_address || '').toLowerCase() !== addr) return false;
      }

      // Search query
      if (!q) return true;
      return (
        (tx.tx_hash || '').toLowerCase().includes(q) ||
        (tx.from_address || '').toLowerCase().includes(q) ||
        (tx.to_address || '').toLowerCase().includes(q)
      );
    });
  }, [investigationData, txSearch, txStageFilter]);

  return (
    <div className="nbe-page" style={{ paddingBottom: '60px' }}>
      
      {/* ── Page Header ── */}
      <div className="nbe-header no-print">
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '28px' }}>⚡</span>
            <div>
              <div className="nbe-header-title">Wallet Extraction & AML Investigation</div>
              <div className="nbe-header-sub">
                Live multi-chain on-chain data extraction with automated 3-Stage AML Typology profiling (Placement · Layering · Integration).
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            padding: '6px 14px',
            background: 'rgba(201,168,76,0.08)',
            border: '1px solid rgba(201,168,76,0.25)',
            borderRadius: '8px',
            fontSize: '12px',
            color: '#C9A84C',
            fontWeight: '600',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 6px #22c55e' }}></span>
            Active Engine: NBE Multi-Chain Extractor v2.4
          </div>
        </div>
      </div>

      {/* ── Extraction Control Console ── */}
      <div className="no-print" style={{
        background: 'linear-gradient(135deg, #0D1628 0%, #101D32 100%)',
        border: '1px solid rgba(201,168,76,0.22)',
        borderRadius: '14px',
        padding: '24px',
        boxShadow: '0 8px 30px rgba(0,0,0,0.35)',
      }}>
        <div style={{ fontSize: '13px', fontWeight: '700', color: '#C8B98A', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>📥</span> Extract Target From Blockchain Source
        </div>

        {/* Input Controls Row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto auto auto', gap: '14px', alignItems: 'center' }}>
          
          {/* Target Address Input */}
          <div style={{ position: 'relative' }}>
            <input
              type="text"
              placeholder="Insert Wallet Address (0x..., bc1..., 1..., sol...)"
              value={addressInput}
              onChange={(e) => setAddressInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleExecuteInvestigation(); }}
              style={{
                width: '100%',
                padding: '12px 42px 12px 16px',
                background: '#070D19',
                border: '1px solid rgba(201,168,76,0.3)',
                borderRadius: '9px',
                color: '#E2D9C8',
                fontSize: '13px',
                fontFamily: 'monospace',
                boxSizing: 'border-box',
                outline: 'none',
                transition: 'border 0.2s',
              }}
              onFocus={(e) => e.target.style.borderColor = '#C9A84C'}
              onBlur={(e) => e.target.style.borderColor = 'rgba(201,168,76,0.3)'}
            />
            {addressInput && (
              <button
                onClick={() => setAddressInput('')}
                style={{
                  position: 'absolute',
                  right: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  color: '#64748B',
                  cursor: 'pointer',
                  fontSize: '14px',
                }}
                title="Clear input"
              >
                ✕
              </button>
            )}
          </div>

          {/* Chain Selector */}
          <select
            value={selectedChain}
            onChange={(e) => setSelectedChain(e.target.value)}
            style={{
              padding: '12px 16px',
              background: '#070D19',
              border: '1px solid rgba(201,168,76,0.3)',
              borderRadius: '9px',
              color: '#E2D9C8',
              fontSize: '13px',
              fontWeight: '600',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {CHAINS.map(c => (
              <option key={c.id} value={c.id}>
                {c.icon} {c.label} ({c.asset})
              </option>
            ))}
          </select>

          {/* Extraction Source Selector */}
          <select
            value={selectedSource}
            onChange={(e) => setSelectedSource(e.target.value)}
            style={{
              padding: '12px 16px',
              background: '#070D19',
              border: '1px solid rgba(201,168,76,0.3)',
              borderRadius: '9px',
              color: '#E2D9C8',
              fontSize: '13px',
              fontWeight: '600',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {sources.map(s => (
              <option key={s.id} value={s.id}>
                📡 {s.name}
              </option>
            ))}
          </select>

          {/* Extraction Limit */}
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            style={{
              padding: '12px 14px',
              background: '#070D19',
              border: '1px solid rgba(201,168,76,0.3)',
              borderRadius: '9px',
              color: '#8A9DB5',
              fontSize: '13px',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value={50}>50 Txs</option>
            <option value={100}>100 Txs</option>
            <option value={250}>250 Txs</option>
            <option value={500}>500 Txs</option>
          </select>

          {/* Action Button */}
          <button
            onClick={() => handleExecuteInvestigation()}
            disabled={loading}
            style={{
              padding: '12px 24px',
              background: loading ? '#64748B' : 'linear-gradient(135deg, #C9A84C 0%, #A68732 100%)',
              color: '#070D19',
              border: 'none',
              borderRadius: '9px',
              fontSize: '13px',
              fontWeight: '700',
              letterSpacing: '0.04em',
              cursor: loading ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 4px 14px rgba(201,168,76,0.3)',
              transition: 'transform 0.15s, box-shadow 0.15s',
            }}
            onMouseEnter={(e) => { if (!loading) e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={(e) => { if (!loading) e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            {loading ? 'Extracting...' : '⚡ Extract & Investigate'}
          </button>
        </div>

        {/* ── Pre-Flight Database Check Status Banner ── */}
        {dbCheckLoading && (
          <div style={{
            marginTop: '14px',
            padding: '10px 16px',
            background: 'rgba(201,168,76,0.06)',
            border: '1px solid rgba(201,168,76,0.2)',
            borderRadius: '8px',
            fontSize: '12px',
            color: '#C8B98A',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}>
            <span style={{ animation: 'spin 1s linear infinite' }}>⏳</span>
            <span>Checking local database records for <strong style={{ fontFamily: 'monospace' }}>{addressInput}</strong>...</span>
          </div>
        )}

        {!dbCheckLoading && dbCheckResult && (
          <div style={{
            marginTop: '14px',
            padding: '12px 18px',
            background: dbCheckResult.is_loaded ? 'rgba(34,197,94,0.08)' : 'rgba(100,116,139,0.08)',
            border: `1px solid ${dbCheckResult.is_loaded ? 'rgba(34,197,94,0.3)' : 'rgba(100,116,139,0.25)'}`,
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            flexWrap: 'wrap',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '12px' }}>
              <span style={{
                padding: '3px 8px',
                borderRadius: '5px',
                fontSize: '10px',
                fontWeight: '800',
                letterSpacing: '0.04em',
                background: dbCheckResult.is_loaded ? 'rgba(34,197,94,0.2)' : 'rgba(100,116,139,0.2)',
                color: dbCheckResult.is_loaded ? '#4ADE80' : '#94A3B8',
              }}>
                {dbCheckResult.is_loaded ? '✓ LOCAL DB HIT' : '○ LOCAL DB MISS'}
              </span>

              <span style={{ color: dbCheckResult.is_loaded ? '#E2D9C8' : '#CBD5E1' }}>
                {dbCheckResult.is_loaded ? (
                  <>
                    Wallet is already loaded in local warehouse with <strong style={{ color: '#4ADE80' }}>{dbCheckResult.transaction_count} indexed transactions</strong>.
                    {dbCheckResult.cluster && <span> (Belongs to <strong style={{ color: '#C8B98A' }}>{dbCheckResult.cluster.name}</strong>)</span>}
                  </>
                ) : (
                  <>
                    Wallet is not yet loaded in local database. Will extract telemetry from <strong style={{ color: '#C8B98A' }}>{sources.find(s => s.id === selectedSource)?.name || selectedSource}</strong>.
                  </>
                )}
              </span>
            </div>

            <div style={{ fontSize: '11px', color: '#8A9DB5' }}>
              {dbCheckResult.is_loaded ? '⚡ Fast Local Investigation' : '📡 Live Blockchain Extraction'}
            </div>
          </div>
        )}

        {/* Quick Sample Chips */}
        <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11px', color: '#64748B', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Quick Investigative Targets:
          </span>
          {samples.map((s, idx) => (
            <button
              key={idx}
              onClick={() => handleSelectSample(s)}
              style={{
                background: 'rgba(201,168,76,0.06)',
                border: '1px solid rgba(201,168,76,0.18)',
                borderRadius: '6px',
                padding: '4px 10px',
                fontSize: '11px',
                color: '#C8B98A',
                cursor: 'pointer',
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(201,168,76,0.15)'}
              onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(201,168,76,0.06)'}
              title={`${s.address} (${s.typologyHint})`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Error Banner ── */}
      {error && (
        <div className="no-print" style={{
          background: 'rgba(239,68,68,0.12)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: '10px',
          padding: '14px 20px',
          color: '#F87171',
          fontSize: '13px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
        }}>
          <span>⚠️</span> {error}
        </div>
      )}

      {/* ── Extraction Animation Pipeline ── */}
      {loading && (
        <div className="no-print" style={{
          background: '#0D1628',
          border: '1px solid rgba(201,168,76,0.2)',
          borderRadius: '12px',
          padding: '24px',
          textAlign: 'center',
        }}>
          <div style={{ fontSize: '15px', fontWeight: '700', color: '#C9A84C', marginBottom: '16px' }}>
            Checking Local Database & Profiling 3-Stage AML Typology...
          </div>
          
          <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
            {[
              { step: 1, label: `1. Check Local DB (${dbCheckResult?.is_loaded ? 'Hit' : 'Miss'})` },
              { step: 2, label: `2. ${dbCheckResult?.is_loaded ? 'Load Indexed Records' : 'Extract From Source'}` },
              { step: 3, label: '3. Placement Profiling' },
              { step: 4, label: '4. Layering Hops' },
              { step: 5, label: '5. Integration Exits' },
              { step: 6, label: '6. Generate Dossier' },
            ].map(item => {
              const isDone = progressStep > item.step;
              const isCurrent = progressStep === item.step;
              return (
                <div
                  key={item.step}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: '600',
                    background: isDone ? 'rgba(34,197,94,0.15)' : isCurrent ? 'rgba(201,168,76,0.2)' : 'rgba(255,255,255,0.03)',
                    border: `1px solid ${isDone ? '#22c55e' : isCurrent ? '#C9A84C' : 'rgba(255,255,255,0.08)'}`,
                    color: isDone ? '#4ADE80' : isCurrent ? '#C9A84C' : '#64748B',
                    transition: 'all 0.3s',
                  }}
                >
                  {isDone ? '✓ ' : isCurrent ? '⏳ ' : '○ '}
                  {item.label}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Investigation Results Dashboard ── */}
      {investigationData && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* 1. Executive AML Verdict Card (Screen Only) */}
          <div className="no-print" style={{
            background: 'linear-gradient(135deg, #0D1628 0%, #132240 100%)',
            border: `1px solid ${investigationData.composite_risk.color}55`,
            borderRadius: '16px',
            padding: '24px 30px',
            boxShadow: `0 8px 32px rgba(0,0,0,0.4), 0 0 20px ${investigationData.composite_risk.color}15`,
            display: 'grid',
            gridTemplateColumns: 'auto 1fr auto',
            gap: '24px',
            alignItems: 'center',
          }}>
            {/* Risk Badge Dial */}
            <div style={{
              width: '100px',
              height: '100px',
              borderRadius: '50%',
              background: `radial-gradient(circle, ${investigationData.composite_risk.color}22 0%, #070D19 80%)`,
              border: `3px solid ${investigationData.composite_risk.color}`,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: `0 0 20px ${investigationData.composite_risk.color}40`,
            }}>
              <div style={{ fontSize: '24px', fontWeight: '800', color: investigationData.composite_risk.color, lineHeight: 1 }}>
                {investigationData.composite_risk.score}
              </div>
              <div style={{ fontSize: '9px', fontWeight: '700', color: '#8A9DB5', letterSpacing: '0.08em', marginTop: '4px' }}>
                AML SCORE
              </div>
            </div>

            {/* Verdict Details */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                <span style={{
                  padding: '4px 10px',
                  background: `${investigationData.composite_risk.color}22`,
                  border: `1px solid ${investigationData.composite_risk.color}66`,
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: '800',
                  color: investigationData.composite_risk.color,
                  letterSpacing: '0.06em',
                }}>
                  {investigationData.composite_risk.level} AML THREAT
                </span>
                <span style={{ fontSize: '12px', color: '#64748B' }}>
                  Target: <span style={{ color: '#E2D9C8', fontFamily: 'monospace' }}>{investigationData.address}</span>
                </span>
                <ChainBadge chain={investigationData.chain} />
              </div>

              <div style={{ fontSize: '15px', fontWeight: '600', color: '#E2D9C8', marginBottom: '8px' }}>
                {investigationData.composite_risk.typology_summary}
              </div>

              <div style={{ display: 'flex', gap: '20px', fontSize: '12px', color: '#8A9DB5', flexWrap: 'wrap', alignItems: 'center' }}>
                <span>Source: <strong style={{ color: '#C8B98A' }}>{investigationData.source_used}</strong></span>
                <span>Analyzed Txs: <strong style={{ color: '#E2D9C8' }}>{investigationData.total_transactions_analyzed}</strong></span>
                <span>Latency: <strong style={{ color: '#4ADE80' }}>{investigationData.execution_time_ms} ms</strong></span>
                <span>Confidence: <strong style={{ color: '#C8B98A' }}>{Math.round(investigationData.composite_risk.confidence * 100)}%</strong></span>
                {investigationData.persisted_to_database && (
                  <span style={{
                    padding: '2px 8px',
                    background: 'rgba(34,197,94,0.12)',
                    border: '1px solid rgba(34,197,94,0.3)',
                    borderRadius: '6px',
                    fontSize: '11px',
                    color: '#4ADE80',
                    fontWeight: '600',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}>
                    💾 {investigationData.new_transactions_persisted > 0 ? `Indexed ${investigationData.new_transactions_persisted} New Txs in Local DB` : 'Indexed in Local DB'}
                  </span>
                )}
              </div>
            </div>

            {/* Quick Actions */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {onNavigateToGraph && (
                <button
                  onClick={() => onNavigateToGraph(investigationData.address)}
                  style={{
                    padding: '8px 16px',
                    background: 'rgba(201,168,76,0.12)',
                    border: '1px solid rgba(201,168,76,0.3)',
                    borderRadius: '8px',
                    color: '#C9A84C',
                    fontSize: '12px',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  🕸 View in Graph Explorer
                </button>
              )}
              <button
                onClick={() => setActiveTab('dossier')}
                style={{
                  padding: '8px 16px',
                  background: activeTab === 'dossier' ? 'rgba(201,168,76,0.25)' : 'rgba(255,255,255,0.06)',
                  border: `1px solid ${activeTab === 'dossier' ? '#C9A84C' : 'rgba(255,255,255,0.15)'}`,
                  borderRadius: '8px',
                  color: activeTab === 'dossier' ? '#C9A84C' : '#E2D9C8',
                  fontSize: '12px',
                  fontWeight: '700',
                  cursor: 'pointer',
                }}
              >
                📋 View Court Dossier
              </button>
            </div>
          </div>

          {/* 2. 3-Stage Typology Progress Bar Cards (Screen Only) */}
          <div className="no-print" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
            
            {/* Stage 1: Placement Card */}
            <div style={{
              background: '#0D1628',
              border: `1px solid ${investigationData.placement_stage.threat_color}44`,
              borderRadius: '12px',
              padding: '18px 20px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.25)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '18px' }}>⟁</span>
                  <span style={{ fontSize: '13px', fontWeight: '700', color: '#E2D9C8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    1. Placement
                  </span>
                </div>
                <span style={{
                  padding: '3px 8px',
                  borderRadius: '5px',
                  fontSize: '11px',
                  fontWeight: '700',
                  background: `${investigationData.placement_stage.threat_color}22`,
                  color: investigationData.placement_stage.threat_color,
                }}>
                  {investigationData.placement_stage.threat_level} ({investigationData.placement_stage.score})
                </span>
              </div>
              <div style={{ fontSize: '12px', color: '#8A9DB5', marginBottom: '10px' }}>
                Ingress volume: <strong style={{ color: '#E2D9C8' }}>{formatCrypto(investigationData.placement_stage.total_incoming_volume_native, investigationData.native_asset)}</strong> ({formatUSD(investigationData.placement_stage.total_incoming_volume_usd)})
              </div>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {investigationData.placement_stage.behaviors.map((b, i) => (
                  <span key={i} style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '4px', background: 'rgba(201,168,76,0.1)', color: '#C8B98A', border: '1px solid rgba(201,168,76,0.2)' }}>
                    {b.label} ({Math.round(b.confidence * 100)}%)
                  </span>
                ))}
              </div>
            </div>

            {/* Stage 2: Layering Card */}
            <div style={{
              background: '#0D1628',
              border: `1px solid ${investigationData.layering_stage.threat_color}44`,
              borderRadius: '12px',
              padding: '18px 20px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.25)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '18px' }}>⧉</span>
                  <span style={{ fontSize: '13px', fontWeight: '700', color: '#E2D9C8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    2. Layering
                  </span>
                </div>
                <span style={{
                  padding: '3px 8px',
                  borderRadius: '5px',
                  fontSize: '11px',
                  fontWeight: '700',
                  background: `${investigationData.layering_stage.threat_color}22`,
                  color: investigationData.layering_stage.threat_color,
                }}>
                  {investigationData.layering_stage.threat_level} ({investigationData.layering_stage.score})
                </span>
              </div>
              <div style={{ fontSize: '12px', color: '#8A9DB5', marginBottom: '10px' }}>
                Transit speed: <strong style={{ color: '#E2D9C8' }}>{Math.round(investigationData.layering_stage.pass_through_ratio * 100)}% pass-through</strong> ({investigationData.layering_stage.peel_chain_hops} peel hops)
              </div>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {investigationData.layering_stage.behaviors.map((b, i) => (
                  <span key={i} style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '4px', background: 'rgba(201,168,76,0.1)', color: '#C8B98A', border: '1px solid rgba(201,168,76,0.2)' }}>
                    {b.label} ({Math.round(b.confidence * 100)}%)
                  </span>
                ))}
              </div>
            </div>

            {/* Stage 3: Integration Card */}
            <div style={{
              background: '#0D1628',
              border: `1px solid ${investigationData.integration_stage.threat_color}44`,
              borderRadius: '12px',
              padding: '18px 20px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.25)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '18px' }}>💰</span>
                  <span style={{ fontSize: '13px', fontWeight: '700', color: '#E2D9C8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    3. Integration
                  </span>
                </div>
                <span style={{
                  padding: '3px 8px',
                  borderRadius: '5px',
                  fontSize: '11px',
                  fontWeight: '700',
                  background: `${investigationData.integration_stage.threat_color}22`,
                  color: investigationData.integration_stage.threat_color,
                }}>
                  {investigationData.integration_stage.threat_level} ({investigationData.integration_stage.score})
                </span>
              </div>
              <div style={{ fontSize: '12px', color: '#8A9DB5', marginBottom: '10px' }}>
                Exit exits: <strong style={{ color: '#E2D9C8' }}>{investigationData.integration_stage.destinations.join(', ') || 'No CEX exit'}</strong>
              </div>
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                {investigationData.integration_stage.behaviors.map((b, i) => (
                  <span key={i} style={{ fontSize: '10px', padding: '2px 8px', borderRadius: '4px', background: 'rgba(201,168,76,0.1)', color: '#C8B98A', border: '1px solid rgba(201,168,76,0.2)' }}>
                    {b.label} ({Math.round(b.confidence * 100)}%)
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* 3. Investigation Navigation Tabs (Screen Only) */}
          <div className="no-print" style={{
            display: 'flex',
            gap: '8px',
            borderBottom: '1px solid rgba(201,168,76,0.18)',
            paddingBottom: '2px',
          }}>
            {[
              { id: 'typology', label: '🔎 3-Stage AML Deep Dive', icon: '🔎' },
              { id: 'graph', label: '🕸 Fund Flow Graph', icon: '🕸' },
              { id: 'transactions', label: `📜 Extracted Ledger (${investigationData.transactions.length})`, icon: '📜' },
              { id: 'dossier', label: '⚖️ Court Evidence Dossier', icon: '⚖️' },
            ].map(t => {
              const active = activeTab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  style={{
                    padding: '10px 20px',
                    background: active ? 'rgba(201,168,76,0.14)' : 'transparent',
                    border: 'none',
                    borderBottom: active ? '3px solid #C9A84C' : '3px solid transparent',
                    color: active ? '#E2D9C8' : '#8A9DB5',
                    fontSize: '13px',
                    fontWeight: active ? '700' : '500',
                    cursor: 'pointer',
                    borderRadius: '6px 6px 0 0',
                    transition: 'all 0.15s',
                  }}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* ── TAB CONTENT ── */}
          
          {/* TAB 1: 3-Stage AML Deep Dive */}
          {activeTab === 'typology' && (
            <div className="no-print" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              
              {/* Placement Section */}
              <div style={{ background: '#0D1628', border: '1px solid rgba(201,168,76,0.14)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ fontSize: '14px', fontWeight: '700', color: '#C8B98A', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>⟁</span> Stage 1: Placement Investigation Findings
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                  {investigationData.placement_stage.reasons.map((r, i) => (
                    <div key={i} style={{ fontSize: '13px', color: '#E2D9C8', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                      <span style={{ color: '#C9A84C' }}>•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
                {investigationData.placement_stage.supporting_txs?.length > 0 && (
                  <div style={{ fontSize: '11px', color: '#64748B' }}>
                    Supporting Ingress Hashes: {investigationData.placement_stage.supporting_txs.map(h => truncateHash(h, 10, 6)).join(', ')}
                  </div>
                )}
              </div>

              {/* Layering Section */}
              <div style={{ background: '#0D1628', border: '1px solid rgba(201,168,76,0.14)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ fontSize: '14px', fontWeight: '700', color: '#C8B98A', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>⧉</span> Stage 2: Layering Investigation Findings
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                  {investigationData.layering_stage.reasons.map((r, i) => (
                    <div key={i} style={{ fontSize: '13px', color: '#E2D9C8', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                      <span style={{ color: '#C9A84C' }}>•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
                {investigationData.layering_stage.supporting_txs?.length > 0 && (
                  <div style={{ fontSize: '11px', color: '#64748B' }}>
                    Supporting Layering Hashes: {investigationData.layering_stage.supporting_txs.map(h => truncateHash(h, 10, 6)).join(', ')}
                  </div>
                )}
              </div>

              {/* Integration Section */}
              <div style={{ background: '#0D1628', border: '1px solid rgba(201,168,76,0.14)', borderRadius: '12px', padding: '20px' }}>
                <div style={{ fontSize: '14px', fontWeight: '700', color: '#C8B98A', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>💰</span> Stage 3: Integration Investigation Findings
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                  {investigationData.integration_stage.reasons.map((r, i) => (
                    <div key={i} style={{ fontSize: '13px', color: '#E2D9C8', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                      <span style={{ color: '#C9A84C' }}>•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
                {investigationData.integration_stage.supporting_txs?.length > 0 && (
                  <div style={{ fontSize: '11px', color: '#64748B' }}>
                    Supporting Exit Hashes: {investigationData.integration_stage.supporting_txs.map(h => truncateHash(h, 10, 6)).join(', ')}
                  </div>
                )}
              </div>

            </div>
          )}

          {/* TAB 2: Fund Flow Graph */}
          {activeTab === 'graph' && (
            <div className="no-print" style={{
              background: '#070D19',
              border: '1px solid rgba(201,168,76,0.18)',
              borderRadius: '14px',
              padding: '24px',
              minHeight: '400px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontSize: '13px', fontWeight: '700', color: '#E2D9C8' }}>
                  Fund Routing Topology: Ingress (Placement) ➔ Target Node ➔ Hops (Layering) ➔ Exits (Integration)
                </div>
                <div style={{ fontSize: '11px', color: '#8A9DB5' }}>
                  {investigationData.graph.nodes.length} Nodes · {investigationData.graph.edges.length} Transfers
                </div>
              </div>

              {/* Graphical representation */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1.2fr 1fr',
                gap: '24px',
                padding: '20px',
                background: '#0D1628',
                borderRadius: '12px',
                border: '1px solid rgba(201,168,76,0.1)',
              }}>
                {/* Feeder Nodes Column */}
                <div>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: '#F59E0B', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    Ingress Feeders (Placement)
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {investigationData.graph.nodes.filter(n => n.type === 'sender').slice(0, 5).map((n, i) => (
                      <div key={i} style={{ padding: '8px 12px', background: '#070D19', border: '1px solid rgba(245,158,11,0.3)', borderRadius: '6px', fontSize: '11px', color: '#E2D9C8', fontFamily: 'monospace' }}>
                        {n.label}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Target Node Column */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: '#C9A84C', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    Target Under Investigation
                  </div>
                  <div style={{
                    padding: '16px 24px',
                    background: 'linear-gradient(135deg, #132240 0%, #0D1628 100%)',
                    border: '2px solid #C9A84C',
                    borderRadius: '12px',
                    textAlign: 'center',
                    boxShadow: '0 0 20px rgba(201,168,76,0.25)',
                  }}>
                    <div style={{ fontSize: '13px', fontWeight: '700', color: '#C8B98A', fontFamily: 'monospace', marginBottom: '4px' }}>
                      {truncateHash(investigationData.address, 10, 8)}
                    </div>
                    <div style={{ fontSize: '11px', color: '#8A9DB5' }}>
                      Chain: {investigationData.chain.toUpperCase()}
                    </div>
                    <div style={{ marginTop: '8px', fontSize: '11px', fontWeight: '700', color: investigationData.composite_risk.color }}>
                      {investigationData.composite_risk.level} THREAT
                    </div>
                  </div>
                </div>

                {/* Exit Nodes Column */}
                <div>
                  <div style={{ fontSize: '11px', fontWeight: '700', color: '#EF4444', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    Downstream / Exits (Integration)
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {investigationData.graph.nodes.filter(n => n.type === 'receiver' || n.type === 'intermediary').slice(0, 5).map((n, i) => (
                      <div key={i} style={{ padding: '8px 12px', background: '#070D19', border: '1px solid rgba(239,68,68,0.3)', borderRadius: '6px', fontSize: '11px', color: '#E2D9C8', fontFamily: 'monospace' }}>
                        {n.label}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Extracted Ledger */}
          {activeTab === 'transactions' && (
            <div className="no-print" style={{ background: '#0D1628', border: '1px solid rgba(201,168,76,0.14)', borderRadius: '12px', padding: '20px' }}>
              
              {/* Filter Controls */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', gap: '12px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <input
                    type="text"
                    placeholder="Search hash or counterparty..."
                    value={txSearch}
                    onChange={(e) => setTxSearch(e.target.value)}
                    style={{
                      padding: '8px 14px',
                      background: '#070D19',
                      border: '1px solid rgba(201,168,76,0.2)',
                      borderRadius: '6px',
                      color: '#E2D9C8',
                      fontSize: '12px',
                      outline: 'none',
                    }}
                  />
                  <select
                    value={txStageFilter}
                    onChange={(e) => setTxStageFilter(e.target.value)}
                    style={{
                      padding: '8px 12px',
                      background: '#070D19',
                      border: '1px solid rgba(201,168,76,0.2)',
                      borderRadius: '6px',
                      color: '#E2D9C8',
                      fontSize: '12px',
                    }}
                  >
                    <option value="all">All Stages</option>
                    <option value="placement">Placement (Ingress)</option>
                    <option value="layering">Layering (Transit)</option>
                    <option value="integration">Integration (Exits)</option>
                  </select>
                </div>

                <div style={{ fontSize: '12px', color: '#8A9DB5' }}>
                  Showing {filteredTxs.length} of {investigationData.transactions.length} transactions
                </div>
              </div>

              {/* Transactions Table */}
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(201,168,76,0.2)', color: '#8A9DB5', textAlign: 'left' }}>
                      <th style={{ padding: '10px 8px' }}>Tx Hash</th>
                      <th style={{ padding: '10px 8px' }}>Block</th>
                      <th style={{ padding: '10px 8px' }}>Direction</th>
                      <th style={{ padding: '10px 8px' }}>Counterparty</th>
                      <th style={{ padding: '10px 8px' }}>Amount</th>
                      <th style={{ padding: '10px 8px' }}>USD Value</th>
                      <th style={{ padding: '10px 8px' }}>AML Stage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTxs.map((tx, idx) => {
                      const isIncoming = (tx.to_address || '').toLowerCase() === investigationData.address.toLowerCase();
                      return (
                        <tr
                          key={idx}
                          style={{
                            borderBottom: '1px solid rgba(255,255,255,0.04)',
                            transition: 'background 0.15s',
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
                          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                        >
                          <td style={{ padding: '10px 8px', fontFamily: 'monospace', color: '#C8B98A' }}>
                            {truncateHash(tx.tx_hash, 8, 6)}
                          </td>
                          <td style={{ padding: '10px 8px', color: '#64748B' }}>
                            {tx.block_number || '-'}
                          </td>
                          <td style={{ padding: '10px 8px' }}>
                            <span style={{
                              padding: '2px 6px',
                              borderRadius: '4px',
                              fontSize: '10px',
                              fontWeight: '700',
                              background: isIncoming ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                              color: isIncoming ? '#4ADE80' : '#F87171',
                            }}>
                              {isIncoming ? 'IN' : 'OUT'}
                            </span>
                          </td>
                          <td style={{ padding: '10px 8px', fontFamily: 'monospace', color: '#E2D9C8' }}>
                            {truncateHash(isIncoming ? tx.from_address : tx.to_address, 8, 6)}
                          </td>
                          <td style={{ padding: '10px 8px', fontWeight: '600', color: '#E2D9C8' }}>
                            {formatCrypto(tx.value_eth, tx.native_asset || investigationData.native_asset)}
                          </td>
                          <td style={{ padding: '10px 8px', color: '#8A9DB5' }}>
                            {formatUSD(tx.usd_at_execution)}
                          </td>
                          <td style={{ padding: '10px 8px' }}>
                            <span style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '10px',
                              fontWeight: '600',
                              background: isIncoming ? 'rgba(245,158,11,0.15)' : 'rgba(167,139,250,0.15)',
                              color: isIncoming ? '#F59E0B' : '#A78BFA',
                            }}>
                              {isIncoming ? 'Placement' : 'Layering / Exit'}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 4: Formal AML Compliance Dossier */}
          {activeTab === 'dossier' && (
            <CourtReportDocument investigationData={investigationData} />
          )}

          {/* Hidden Print Container: Ensures printing works from any active tab */}
          {activeTab !== 'dossier' && (
            <div className="court-report-print-fallback" style={{ display: 'none' }}>
              <CourtReportDocument investigationData={investigationData} />
            </div>
          )}

        </div>
      )}

      {/* ── Recent Investigations Bar ── */}
      {recentList?.length > 0 && (
        <div className="no-print" style={{
          background: '#0D1628',
          border: '1px solid rgba(201,168,76,0.14)',
          borderRadius: '12px',
          padding: '16px 20px',
        }}>
          <div style={{ fontSize: '12px', fontWeight: '700', color: '#8A9DB5', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '10px' }}>
            Session Investigation History
          </div>
          <div style={{ display: 'flex', gap: '10px', overflowX: 'auto', paddingBottom: '4px' }}>
            {recentList.map((rec, i) => (
              <button
                key={i}
                onClick={() => {
                  setAddressInput(rec.address);
                  setSelectedChain(rec.chain || 'ethereum');
                  handleExecuteInvestigation(rec.address);
                }}
                style={{
                  background: '#070D19',
                  border: `1px solid ${rec.risk_color || '#C9A84C'}44`,
                  borderRadius: '8px',
                  padding: '8px 12px',
                  fontSize: '11px',
                  color: '#E2D9C8',
                  cursor: 'pointer',
                  textAlign: 'left',
                  flexShrink: 0,
                }}
              >
                <div style={{ fontFamily: 'monospace', color: '#C8B98A' }}>
                  {truncateHash(rec.address, 6, 4)}
                </div>
                <div style={{ fontSize: '10px', color: rec.risk_color, fontWeight: '700', marginTop: '2px' }}>
                  {rec.risk_level} ({rec.composite_score}) · {rec.chain?.toUpperCase()}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
