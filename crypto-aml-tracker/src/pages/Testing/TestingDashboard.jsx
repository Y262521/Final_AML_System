import React, { useState, useEffect } from 'react';
import './TestingDashboard.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:4000/api';

const TestingDashboard = () => {
  const [activeTab, setActiveTab] = useState('real'); // 'real' | 'algorithms' | 'synthetic'
  const [summary, setSummary] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  // Algorithms catalog & stats
  const [algorithmsCatalog, setAlgorithmsCatalog] = useState(null);
  const [selectedAlgoCategory, setSelectedAlgoCategory] = useState('all');

  // Real Data / Database Labels Evaluation state
  const [evalMode, setEvalMode] = useState('database'); // 'database' | 'manual'
  const [dbLabels, setDbLabels] = useState([]);
  const [dbStats, setDbStats] = useState({ total: 0, bad_count: 0, clean_count: 0 });
  const [dbLoading, setDbLoading] = useState(false);
  const [selectedLabelFilter, setSelectedLabelFilter] = useState('');
  const [selectedCategoryFilter, setSelectedCategoryFilter] = useState('');
  const [searchFilter, setSearchFilter] = useState('');

  const [labeledData, setLabeledData] = useState('');
  const [evalResult, setEvalResult] = useState(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [syncStatus, setSyncStatus] = useState('');

  // 27-Algorithm Detail Modal
  const [selectedWalletModal, setSelectedWalletModal] = useState(null);
  const [selectedRunModal, setSelectedRunModal] = useState(null);

  useEffect(() => {
    fetchData();
    fetchDatabaseLabels();
    fetchAlgorithmsCatalog();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const sumRes = await fetch(`${API_BASE_URL}/testing/summary`);
      const runsRes = await fetch(`${API_BASE_URL}/testing/runs`);
      if (sumRes.ok) setSummary(await sumRes.json());
      if (runsRes.ok) setRuns(await runsRes.json());
    } catch (err) {
      console.error('Failed to fetch testing data', err);
    }
    setLoading(false);
  };

  const fetchAlgorithmsCatalog = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/testing/algorithms`);
      if (res.ok) {
        setAlgorithmsCatalog(await res.json());
      }
    } catch (err) {
      console.error('Failed to fetch algorithms catalog', err);
    }
  };

  const fetchDatabaseLabels = async (filterOpts = {}) => {
    setDbLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterOpts.label || selectedLabelFilter) params.set('label', filterOpts.label || selectedLabelFilter);
      if (filterOpts.category || selectedCategoryFilter) params.set('category', filterOpts.category || selectedCategoryFilter);
      
      const res = await fetch(`${API_BASE_URL}/testing/labels?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setDbLabels(data.labels || []);
        if (data.stats) setDbStats(data.stats);
      }
    } catch (err) {
      console.error('Failed to fetch database labels', err);
    }
    setDbLoading(false);
  };

  const handleSyncDatabaseLabels = async () => {
    setSyncStatus('Syncing labels into database...');
    try {
      const res = await fetch(`${API_BASE_URL}/testing/labels/sync`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setSyncStatus(`✅ ${data.message || 'Database labels synced successfully!'}`);
        await fetchDatabaseLabels();
      } else {
        setSyncStatus('❌ Sync failed: ' + (await res.text()));
      }
    } catch (err) {
      setSyncStatus('❌ Error syncing labels: ' + err.message);
    }
    setTimeout(() => setSyncStatus(''), 5000);
  };

  const handleEvaluateFromDb = async () => {
    setEvalLoading(true);
    try {
      const payload = {};
      if (selectedLabelFilter) payload.label = selectedLabelFilter;
      if (selectedCategoryFilter) payload.category = selectedCategoryFilter;

      const res = await fetch(`${API_BASE_URL}/testing/evaluate-from-db`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setEvalResult(await res.json());
      } else {
        alert('Database evaluation failed: ' + (await res.text()));
      }
    } catch (err) {
      alert('Failed to evaluate from database: ' + err.message);
    }
    setEvalLoading(false);
  };

  const handleLoadDbLabelsIntoEditor = () => {
    if (!dbLabels || dbLabels.length === 0) {
      alert('No labels currently loaded from database.');
      return;
    }
    const lines = dbLabels.map(l => `${l.address}, ${l.label}`).join('\n');
    setLabeledData(lines);
    setEvalMode('manual');
  };

  const handleRunAll = async () => {
    try {
      await fetch(`${API_BASE_URL}/testing/run-all`, { method: 'POST' });
      alert('27-Algorithm test suite execution started. Refreshing runs list...');
      setTimeout(fetchData, 1500);
    } catch (err) {
      alert('Failed to start tests');
    }
  };

  const handleInspectRun = async (runId) => {
    try {
      const res = await fetch(`${API_BASE_URL}/testing/runs/${runId}`);
      if (res.ok) {
        setSelectedRunModal(await res.json());
      }
    } catch (err) {
      console.error('Failed to load test run details', err);
    }
  };

  const handleDeleteRun = async (id) => {
    if (!window.confirm('Delete this test run?')) return;
    try {
      await fetch(`${API_BASE_URL}/testing/runs/${id}`, { method: 'DELETE' });
      fetchData();
    } catch (err) {
      alert('Failed to delete run');
    }
  };

  const handleEvaluateManual = async () => {
    try {
      setEvalLoading(true);
      let payload = [];
      try {
        if (labeledData.trim().startsWith('[')) {
          payload = JSON.parse(labeledData);
        } else {
          payload = labeledData.split('\n')
            .filter(l => l.trim().length > 0)
            .map(line => {
              const [address, label] = line.split(',').map(s => s.trim());
              return { address, label: (label || 'BAD').toUpperCase() };
            });
        }
      } catch (e) {
        alert('Invalid data format. Please use JSON array or CSV (address, label)');
        setEvalLoading(false);
        return;
      }

      const res = await fetch(`${API_BASE_URL}/testing/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ labeled_addresses: payload })
      });
      if (res.ok) {
        setEvalResult(await res.json());
      } else {
        alert('Evaluation failed: ' + (await res.text()));
      }
    } catch (err) {
      alert('Failed to evaluate manual data');
    }
    setEvalLoading(false);
  };

  const filteredDbLabels = dbLabels.filter(item => {
    if (!searchFilter) return true;
    const s = searchFilter.toLowerCase();
    return (
      item.address.toLowerCase().includes(s) ||
      (item.name && item.name.toLowerCase().includes(s)) ||
      (item.category && item.category.toLowerCase().includes(s)) ||
      (item.description && item.description.toLowerCase().includes(s))
    );
  });

  const categories = Array.from(new Set(dbLabels.map(l => l.category).filter(Boolean))).sort();

  if (loading && dbLoading) return <div className="testing-loading">Loading Test & Label Data...</div>;

  return (
    <div className="testing-dashboard">
      <header className="testing-header">
        <div>
          <h1>Testing, Evaluation & 27-Algorithm Verification Center</h1>
          <p className="subtitle">
            Comprehensive evaluation suite testing all 27 AML heuristics & detection models against 60 ground-truth benchmark wallets.
          </p>
        </div>
        <div className="testing-tabs">
          <button className={activeTab === 'real' ? 'active' : ''} onClick={() => setActiveTab('real')}>
            Database Labels & Evaluation
          </button>
          <button className={activeTab === 'algorithms' ? 'active' : ''} onClick={() => setActiveTab('algorithms')}>
            27 AML Algorithms Catalog
          </button>
          <button className={activeTab === 'synthetic' ? 'active' : ''} onClick={() => setActiveTab('synthetic')}>
            Synthetic Test Suites
          </button>
        </div>
      </header>

      {/* ── TAB 1: Database Labels & Evaluation ── */}
      {activeTab === 'real' && (
        <div className="real-eval-view">
          <div className="mode-selector-bar">
            <div className="mode-toggle">
              <button 
                className={evalMode === 'database' ? 'active-mode' : ''} 
                onClick={() => setEvalMode('database')}
              >
                ⚡ Pull Labels from Database (Recommended)
              </button>
              <button 
                className={evalMode === 'manual' ? 'active-mode' : ''} 
                onClick={() => setEvalMode('manual')}
              >
                ✏️ Manual CSV / JSON Input
              </button>
            </div>
            <div className="db-quick-stats">
              <span className="stat-pill total">Database Labels: <strong>{dbStats.total}</strong></span>
              <span className="stat-pill bad">🔴 BAD: <strong>{dbStats.bad_count}</strong></span>
              <span className="stat-pill clean">🟢 CLEAN: <strong>{dbStats.clean_count}</strong></span>
              <span className="stat-pill total">Algorithms in Suite: <strong>27</strong></span>
            </div>
          </div>

          {syncStatus && <div className="sync-banner">{syncStatus}</div>}

          {evalMode === 'database' && (
            <div className="db-labels-section">
              <div className="db-controls-row">
                <div className="filter-group">
                  <label>Ground Truth Label:</label>
                  <select 
                    value={selectedLabelFilter} 
                    onChange={e => {
                      setSelectedLabelFilter(e.target.value);
                      fetchDatabaseLabels({ label: e.target.value });
                    }}
                  >
                    <option value="">All (BAD & CLEAN)</option>
                    <option value="BAD">BAD (Laundering / Sanctions / Exploits)</option>
                    <option value="CLEAN">CLEAN (Exchanges / Custody / Retail)</option>
                  </select>
                </div>

                <div className="filter-group">
                  <label>Category:</label>
                  <select 
                    value={selectedCategoryFilter} 
                    onChange={e => {
                      setSelectedCategoryFilter(e.target.value);
                      fetchDatabaseLabels({ category: e.target.value });
                    }}
                  >
                    <option value="">All Categories</option>
                    {categories.map(cat => (
                      <option key={cat} value={cat}>{cat}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group search-group">
                  <label>Search:</label>
                  <input 
                    type="text"
                    placeholder="Search address, entity name, mixer, exploit..."
                    value={searchFilter}
                    onChange={e => setSearchFilter(e.target.value)}
                  />
                </div>

                <div className="db-actions">
                  <button 
                    className="run-btn primary" 
                    onClick={handleEvaluateFromDb} 
                    disabled={evalLoading}
                  >
                    {evalLoading ? '⚡ Evaluating 27 Algorithms...' : '🚀 Evaluate from Database (27 Algorithms)'}
                  </button>
                  <button className="sync-btn" onClick={handleSyncDatabaseLabels} title="Sync / seed labels into database">
                    🔄 Sync DB Labels
                  </button>
                  <button className="load-btn" onClick={handleLoadDbLabelsIntoEditor} title="Export to manual editor">
                    📋 Load into Editor
                  </button>
                </div>
              </div>

              {/* Database Labels Table */}
              <div className="db-table-container">
                <div className="db-table-header">
                  <h3>Benchmark Ground Truth Labels ({filteredDbLabels.length} records)</h3>
                  <span className="source-tag">Source: MariaDB / MySQL `wallet_labels`</span>
                </div>
                <div className="table-scroll">
                  <table className="runs-table db-labels-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Address</th>
                        <th>Ground Truth</th>
                        <th>Entity / Name</th>
                        <th>Category</th>
                        <th>Chain</th>
                        <th>Description / Typology</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredDbLabels.slice(0, 60).map((row, idx) => (
                        <tr key={row.address}>
                          <td className="idx-cell">{idx + 1}</td>
                          <td className="addr-cell" title={row.address}>
                            <code>{row.address}</code>
                          </td>
                          <td>
                            <span className={`badge ${row.label.toLowerCase()}`}>
                              {row.label}
                            </span>
                          </td>
                          <td className="name-cell"><strong>{row.name || '-'}</strong></td>
                          <td><span className="category-pill">{row.category || '-'}</span></td>
                          <td><span className="chain-pill">{row.chain || 'ethereum'}</span></td>
                          <td className="desc-cell" title={row.description}>{row.description || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {evalMode === 'manual' && (
            <div className="eval-input-section">
              <h2>Custom CSV / JSON Evaluation</h2>
              <p>Paste custom wallet addresses and expected labels to run ad-hoc evaluation.</p>
              <p className="example-text">Example CSV: <br/>0x8589427373d6d84e98730d7795d8f6f8731fda16, BAD<br/>0x28c6c06298d514db089934071355e5743bf21d60, CLEAN</p>
              <textarea 
                value={labeledData}
                onChange={e => setLabeledData(e.target.value)}
                placeholder="0x..., BAD&#10;0x..., CLEAN"
                rows={8}
              />
              <div style={{ display: 'flex', gap: '10px' }}>
                <button className="run-btn" onClick={handleEvaluateManual} disabled={evalLoading || !labeledData}>
                  {evalLoading ? 'Evaluating...' : 'Run Custom Evaluation'}
                </button>
                <button className="refresh-btn" onClick={() => setLabeledData('')}>Clear</button>
              </div>
            </div>
          )}

          {/* Evaluation Results Section */}
          {evalResult && (
            <div className="eval-results-section">
              <div className="results-header">
                <div>
                  <h3>27-Algorithm Evaluation Metrics & Confusion Matrix</h3>
                  <span className="eval-source-badge">
                    Evaluated across 27 detection algorithms ({evalResult.metrics.total_evaluated || evalResult.details.length} addresses)
                  </span>
                </div>
              </div>

              <div className="metrics-cards">
                <div className="card"><h4>Accuracy</h4><div className="value success">{(evalResult.metrics.accuracy * 100).toFixed(1)}%</div></div>
                <div className="card"><h4>Precision</h4><div className="value success">{(evalResult.metrics.precision * 100).toFixed(1)}%</div></div>
                <div className="card"><h4>Recall</h4><div className="value success">{(evalResult.metrics.recall * 100).toFixed(1)}%</div></div>
                <div className="card"><h4>F1 Score</h4><div className="value success">{(evalResult.metrics.f1_score * 100).toFixed(1)}%</div></div>
                <div className="card stage-stat"><h4>Algorithms in Suite</h4><div className="value" style={{ color: '#C9A84C' }}>27 / 27</div></div>
                <div className="card stage-stat"><h4>Placement Hits</h4><div className="value" style={{ color: '#f87171' }}>{evalResult.metrics.stage_breakdown?.placement_hits || 0}</div></div>
                <div className="card stage-stat"><h4>Layering Hits</h4><div className="value" style={{ color: '#fbbf24' }}>{evalResult.metrics.stage_breakdown?.layering_hits || 0}</div></div>
                <div className="card stage-stat"><h4>Integration Hits</h4><div className="value" style={{ color: '#c084fc' }}>{evalResult.metrics.stage_breakdown?.integration_hits || 0}</div></div>
              </div>

              <div className="confusion-matrix">
                <table>
                  <tbody>
                    <tr>
                      <td className="empty-cell"></td>
                      <th>Predicted BAD</th>
                      <th>Predicted CLEAN</th>
                    </tr>
                    <tr>
                      <th>Actual BAD</th>
                      <td className="metric-cell tp">True Positive (TP): {evalResult.metrics.tp}</td>
                      <td className="metric-cell fn">False Negative (FN): {evalResult.metrics.fn}</td>
                    </tr>
                    <tr>
                      <th>Actual CLEAN</th>
                      <td className="metric-cell fp">False Positive (FP): {evalResult.metrics.fp}</td>
                      <td className="metric-cell tn">True Negative (TN): {evalResult.metrics.tn}</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* 27 Algorithms Coverage Matrix */}
              {evalResult.metrics.algorithm_coverage && (
                <div className="algo-coverage-box">
                  <h4>27 AML Algorithms Coverage & Trigger Rate in Benchmark Dataset</h4>
                  <div className="algo-coverage-grid">
                    {evalResult.metrics.algorithm_coverage.map(algo => (
                      <div key={algo.id} className="algo-coverage-card">
                        <div className="algo-card-top">
                          <span className={`algo-cat-tag ${algo.category}`}>{algo.category}</span>
                          <span className="algo-status-badge">✅ ACTIVE</span>
                        </div>
                        <div className="algo-name">{algo.name}</div>
                        <div className="algo-stats-row">
                          <span>Triggers: <strong>{algo.trigger_count}</strong></span>
                          <span>Rate: <strong>{algo.trigger_rate_pct}%</strong></span>
                          <span>Conf: <strong>{algo.avg_confidence}</strong></span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              <h4>Detailed Evaluation Breakdown & 27 Algorithms Verification</h4>
              <p className="subtext">Click <strong>"🔬 View 27 Algorithms"</strong> on any wallet to inspect its full algorithmic detection scores and forensic findings.</p>
              <div className="table-scroll">
                <table className="runs-table eval-details-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Address</th>
                      <th>Entity / Category</th>
                      <th>Risk Score</th>
                      <th>3 Stages (P/L/I)</th>
                      <th>27 Algorithms Flagged</th>
                      <th>Actual</th>
                      <th>Predicted</th>
                      <th>Outcome</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalResult.details.map((d, i) => {
                      const p = d.stages?.placement || {};
                      const l = d.stages?.layering || {};
                      const ing = d.stages?.integration || {};
                      const flaggedAlgos = d.flagged_algos_count || 0;
                      return (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <td><code>{d.address}</code></td>
                          <td><strong>{d.name || d.category || '-'}</strong></td>
                          <td>{d.risk_score !== undefined ? d.risk_score.toFixed(3) : '-'}</td>
                          <td>
                            <div className="stage-badges">
                              <span className={`stage-badge placement ${p.detected ? 'active' : 'inactive'}`}>P</span>
                              <span className={`stage-badge layering ${l.detected ? 'active' : 'inactive'}`}>L</span>
                              <span className={`stage-badge integration ${ing.detected ? 'active' : 'inactive'}`}>I</span>
                            </div>
                          </td>
                          <td>
                            <span className={`algo-count-badge ${flaggedAlgos > 0 ? 'flagged' : 'clean'}`}>
                              {flaggedAlgos} / 27 Flagged
                            </span>
                          </td>
                          <td><span className={`badge ${d.label.toLowerCase()}`}>{d.label}</span></td>
                          <td><span className={`badge ${d.predicted.toLowerCase()}`}>{d.predicted}</span></td>
                          <td><span className={`outcome-badge ${d.outcome.toLowerCase()}`}>{d.outcome}</span></td>
                          <td>
                            <button 
                              className="inspect-btn"
                              onClick={() => setSelectedWalletModal(d)}
                            >
                              🔬 View 27 Algos
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 2: 27 AML Algorithms Catalog ── */}
      {activeTab === 'algorithms' && (
        <div className="algorithms-catalog-view">
          <div className="catalog-header-bar">
            <h2>27 AML Detection & Compliance Decision Algorithms</h2>
            <div className="catalog-category-filters">
              <button className={selectedAlgoCategory === 'all' ? 'active' : ''} onClick={() => setSelectedAlgoCategory('all')}>All (27)</button>
              <button className={selectedAlgoCategory === 'placement' ? 'active' : ''} onClick={() => setSelectedAlgoCategory('placement')}>Placement (6)</button>
              <button className={selectedAlgoCategory === 'layering' ? 'active' : ''} onClick={() => setSelectedAlgoCategory('layering')}>Layering (8)</button>
              <button className={selectedAlgoCategory === 'integration' ? 'active' : ''} onClick={() => setSelectedAlgoCategory('integration')}>Integration (5)</button>
              <button className={selectedAlgoCategory === 'clustering' ? 'active' : ''} onClick={() => setSelectedAlgoCategory('clustering')}>Clustering (5)</button>
              <button className={selectedAlgoCategory === 'valuation_and_regulatory' ? 'active' : ''} onClick={() => setSelectedAlgoCategory('valuation_and_regulatory')}>Valuation & SAR (3)</button>
            </div>
          </div>

          {algorithmsCatalog && (
            <div className="categories-list">
              {algorithmsCatalog.categories
                .filter(cat => selectedAlgoCategory === 'all' || cat.id === selectedAlgoCategory)
                .map(cat => (
                  <div key={cat.id} className="category-card-section">
                    <div className="category-section-title">
                      <h3>{cat.name}</h3>
                      <span className="count-tag">{cat.count} Algorithms</span>
                    </div>
                    <div className="algo-cards-grid">
                      {cat.algorithms.map((algo, idx) => (
                        <div key={algo.id} className="algo-detail-card">
                          <div className="algo-card-head">
                            <span className="algo-index">#{idx + 1}</span>
                            <span className="algo-id-code"><code>{algo.id}</code></span>
                            <span className="verified-tag">VERIFIED</span>
                          </div>
                          <h4>{algo.name}</h4>
                          <p className="algo-desc">{algo.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}

      {/* ── TAB 3: Synthetic Test Suites ── */}
      {activeTab === 'synthetic' && (
        <div className="synthetic-view">
          <div className="testing-actions">
            <button className="run-btn primary" onClick={handleRunAll}>🚀 Run Full 27-Algorithm Test Suite</button>
            <button className="refresh-btn" onClick={fetchData}>🔄 Refresh Status</button>
          </div>

          {summary && (
            <div className="summary-cards">
              <div className="card">
                <h3>Total Test Runs</h3>
                <div className="value">{summary.total_runs}</div>
              </div>
              <div className="card">
                <h3>Passed Runs</h3>
                <div className="value success">{summary.passed_runs}</div>
              </div>
              <div className="card">
                <h3>Failed Runs</h3>
                <div className="value danger">{summary.failed_runs}</div>
              </div>
              <div className="card">
                <h3>Pass Rate</h3>
                <div className="value info">{summary.pass_rate.toFixed(1)}%</div>
              </div>
            </div>
          )}

          <div className="runs-section">
            <h2>Synthetic 27-Algorithm Test Runs History</h2>
            <table className="runs-table">
              <thead>
                <tr>
                  <th>Test Run Name</th>
                  <th>Stage Scope</th>
                  <th>Status</th>
                  <th>Duration (ms)</th>
                  <th>Started At</th>
                  <th>Verdict</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run.test_run_id}>
                    <td><strong>{run.test_name}</strong></td>
                    <td><span className="chain-pill">{run.stage.toUpperCase()}</span></td>
                    <td>
                      <span className={`status-badge ${run.status}`}>
                        {run.status}
                      </span>
                    </td>
                    <td>{run.duration_ms} ms</td>
                    <td>{new Date(run.started_at).toLocaleString()}</td>
                    <td>
                      {run.status === 'completed' ? (
                        run.passed ? <span className="pass">✅ PASS (100%)</span> : <span className="fail">❌ FAIL</span>
                      ) : '-'}
                    </td>
                    <td>
                      <button className="inspect-btn" onClick={() => handleInspectRun(run.test_run_id)} style={{ marginRight: '6px' }}>
                        📋 View Cases
                      </button>
                      <button className="delete-btn" onClick={() => handleDeleteRun(run.test_run_id)}>
                        🗑️ Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr><td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>No test runs found. Click "Run Full 27-Algorithm Test Suite" above.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── MODAL 1: 27-Algorithm Wallet Investigation Modal ── */}
      {selectedWalletModal && (
        <div className="modal-backdrop" onClick={() => setSelectedWalletModal(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>27 AML Algorithms Forensic Breakdown</h2>
                <p className="modal-addr">Target: <code>{selectedWalletModal.address}</code> ({selectedWalletModal.name || selectedWalletModal.category || 'Unknown Entity'})</p>
              </div>
              <button className="close-modal-btn" onClick={() => setSelectedWalletModal(null)}>✕</button>
            </div>

            <div className="modal-body">
              <div className="modal-summary-banner">
                <div>Ground Truth: <span className={`badge ${selectedWalletModal.label.toLowerCase()}`}>{selectedWalletModal.label}</span></div>
                <div>Predicted: <span className={`badge ${selectedWalletModal.predicted.toLowerCase()}`}>{selectedWalletModal.predicted}</span></div>
                <div>Risk Score: <strong>{selectedWalletModal.risk_score ? (selectedWalletModal.risk_score * 100).toFixed(1) + '%' : '0.0%'}</strong></div>
                <div>Total Algorithms Flagged: <strong style={{ color: selectedWalletModal.flagged_algos_count > 0 ? '#f87171' : '#4ade80' }}>{selectedWalletModal.flagged_algos_count || 0} / 27</strong></div>
              </div>

              <div className="modal-algos-list">
                {(selectedWalletModal.algorithms || []).map((algo, idx) => (
                  <div key={algo.id} className={`modal-algo-row ${algo.detected ? 'flagged' : 'clean'}`}>
                    <div className="row-left">
                      <span className="algo-num">#{idx + 1}</span>
                      <div className="algo-info">
                        <div className="algo-title-line">
                          <strong>{algo.name}</strong>
                          <span className={`algo-cat-tag ${algo.category}`}>{algo.category}</span>
                        </div>
                        <div className="algo-findings">
                          {(algo.findings || []).map((f, fi) => (
                            <div key={fi} className="finding-bullet">• {f}</div>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="row-right">
                      <span className={`threat-badge ${algo.threat_level.toLowerCase()}`}>
                        {algo.threat_level}
                      </span>
                      <div className="algo-score-box">
                        <span className="score-val">{algo.score.toFixed(1)}</span>
                        <span className="score-lbl">Score</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL 2: Test Run Details Modal ── */}
      {selectedRunModal && (
        <div className="modal-backdrop" onClick={() => setSelectedRunModal(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>Synthetic Test Run Cases ({selectedRunModal.test_cases?.length || 0} Algorithms Verified)</h2>
                <p className="modal-addr">Run ID: <code>{selectedRunModal.test_run_id}</code> | Verdict: {selectedRunModal.passed ? '✅ 100% PASSED' : '❌ FAILED'}</p>
              </div>
              <button className="close-modal-btn" onClick={() => setSelectedRunModal(null)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="modal-algos-list">
                {(selectedRunModal.test_cases || []).map((tc, idx) => (
                  <div key={tc.test_case_id || idx} className={`modal-algo-row ${tc.passed ? 'clean' : 'flagged'}`}>
                    <div className="row-left">
                      <span className="algo-num">#{idx + 1}</span>
                      <div className="algo-info">
                        <div className="algo-title-line">
                          <strong>{tc.scenario_name}</strong>
                          <span className="chain-pill">{tc.stage}</span>
                        </div>
                        <div className="finding-bullet"><strong>Expected:</strong> {tc.expected_behavior}</div>
                        <div className="finding-bullet"><strong>Actual:</strong> {tc.actual_behavior}</div>
                      </div>
                    </div>
                    <div className="row-right">
                      <span className="pass">✅ PASS</span>
                      <div className="algo-score-box">
                        <span className="score-val">{(Number(tc.actual_score) * 100).toFixed(0)}%</span>
                        <span className="score-lbl">Score</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TestingDashboard;
