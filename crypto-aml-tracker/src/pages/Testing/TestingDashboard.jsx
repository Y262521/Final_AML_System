import React, { useState, useEffect } from 'react';
import './TestingDashboard.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:4000/api';

const TestingDashboard = () => {
  const [activeTab, setActiveTab] = useState('real'); // Default to Real Data / DB labels
  const [summary, setSummary] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

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

  useEffect(() => {
    fetchData();
    fetchDatabaseLabels();
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
      alert('Test suite started. Refresh in a moment.');
      setTimeout(fetchData, 2000);
    } catch (err) {
      alert('Failed to start tests');
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

  // Filter dbLabels by search
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

  // Extract unique categories
  const categories = Array.from(new Set(dbLabels.map(l => l.category).filter(Boolean))).sort();

  if (loading && dbLoading) return <div className="testing-loading">Loading Test & Label Data...</div>;

  return (
    <div className="testing-dashboard">
      <header className="testing-header">
        <div>
          <h1>Testing & Label Evaluation Center</h1>
          <p className="subtitle">Evaluate AML models against ground-truth labels pulled directly from the database or manual test cases.</p>
        </div>
        <div className="testing-tabs">
          <button className={activeTab === 'real' ? 'active' : ''} onClick={() => setActiveTab('real')}>
            Database Labels & Evaluation
          </button>
          <button className={activeTab === 'synthetic' ? 'active' : ''} onClick={() => setActiveTab('synthetic')}>
            Synthetic Test Suites
          </button>
        </div>
      </header>

      {activeTab === 'real' && (
        <div className="real-eval-view">
          {/* Mode Selector */}
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
            </div>
          </div>

          {syncStatus && <div className="sync-banner">{syncStatus}</div>}

          {/* Database Driven Mode */}
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
                    {evalLoading ? '⚡ Evaluating DB...' : '🚀 Evaluate from Database'}
                  </button>
                  <button className="sync-btn" onClick={handleSyncDatabaseLabels} title="Sync / seed labels into database">
                    🔄 Sync DB Labels
                  </button>
                  <button className="load-btn" onClick={handleLoadDbLabelsIntoEditor} title="Export to manual editor">
                    📋 Load into Editor
                  </button>
                </div>
              </div>

              {/* Live Database Labels Preview Table */}
              <div className="db-table-container">
                <div className="db-table-header">
                  <h3>Labels Stored in Database ({filteredDbLabels.length} records)</h3>
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
                      {filteredDbLabels.length === 0 && (
                        <tr>
                          <td colSpan="7" style={{ textAlign: 'center', padding: '30px' }}>
                            No database labels match current filters.{' '}
                            <button onClick={handleSyncDatabaseLabels} style={{ marginLeft: '10px' }}>Sync Labels Now</button>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Manual Entry Mode */}
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
                <h3>Evaluation Metrics & Confusion Matrix</h3>
                <span className="eval-source-badge">
                  Source: {evalResult.metrics.source_mode === 'database' ? 'Database Labels' : 'Manual Input'} ({evalResult.metrics.total_evaluated || evalResult.details.length} addresses)
                </span>
              </div>

              <div className="metrics-cards">
                <div className="card"><h4>Accuracy</h4><div className="value">{(evalResult.metrics.accuracy * 100).toFixed(1)}%</div></div>
                <div className="card"><h4>Precision</h4><div className="value">{(evalResult.metrics.precision * 100).toFixed(1)}%</div></div>
                <div className="card"><h4>Recall</h4><div className="value">{(evalResult.metrics.recall * 100).toFixed(1)}%</div></div>
                <div className="card"><h4>F1 Score</h4><div className="value">{(evalResult.metrics.f1_score * 100).toFixed(1)}%</div></div>
                {evalResult.metrics.stage_breakdown && (
                  <>
                    <div className="card stage-stat"><h4>Placement Hits</h4><div className="value" style={{ color: '#f87171' }}>{evalResult.metrics.stage_breakdown.placement_hits}</div></div>
                    <div className="card stage-stat"><h4>Layering Hits</h4><div className="value" style={{ color: '#fbbf24' }}>{evalResult.metrics.stage_breakdown.layering_hits}</div></div>
                    <div className="card stage-stat"><h4>Integration Hits</h4><div className="value" style={{ color: '#c084fc' }}>{evalResult.metrics.stage_breakdown.integration_hits}</div></div>
                    <div className="card stage-stat"><h4>All 3 Stages Flagged</h4><div className="value" style={{ color: '#4ade80' }}>{evalResult.metrics.stage_breakdown.all_3_stages_detected}</div></div>
                  </>
                )}
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
              
              <h4>Detailed Evaluation Breakdown & 3-Stage AML Verification</h4>
              <div className="table-scroll">
                <table className="runs-table eval-details-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Address</th>
                      <th>Entity / Category</th>
                      <th>Risk Score</th>
                      <th>3-Stage AML Status</th>
                      <th>POI Flag</th>
                      <th>Actual Label</th>
                      <th>Predicted</th>
                      <th>Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalResult.details.map((d, i) => {
                      const p = d.stages?.placement || {};
                      const l = d.stages?.layering || {};
                      const ing = d.stages?.integration || {};
                      return (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <td><code>{d.address}</code></td>
                          <td><strong>{d.name || d.category || '-'}</strong></td>
                          <td>{d.risk_score !== undefined ? d.risk_score.toFixed(4) : '-'}</td>
                          <td>
                            <div className="stage-badges" title={`Placement: ${p.detected ? `YES (Score: ${p.score})` : 'NO'}\nLayering: ${l.detected ? `YES (Score: ${l.score})` : 'NO'}\nIntegration: ${ing.detected ? `YES (Score: ${ing.score})` : 'NO'}`}>
                              <span className={`stage-badge placement ${p.detected ? 'active' : 'inactive'}`} title={p.detected ? `Placement Flagged (${(p.behaviors || []).join(', ') || 'Score ' + p.score})` : 'Placement Clean'}>P</span>
                              <span className={`stage-badge layering ${l.detected ? 'active' : 'inactive'}`} title={l.detected ? `Layering Flagged (${(l.methods || []).join(', ') || 'Score ' + l.score})` : 'Layering Clean'}>L</span>
                              <span className={`stage-badge integration ${ing.detected ? 'active' : 'inactive'}`} title={ing.detected ? `Integration Flagged (${(ing.signals || []).join(', ') || 'Score ' + ing.score})` : 'Integration Clean'}>I</span>
                            </div>
                          </td>
                          <td>{d.is_poi ? '🚩 YES' : 'NO'}</td>
                          <td><span className={`badge ${d.label.toLowerCase()}`}>{d.label}</span></td>
                          <td><span className={`badge ${d.predicted.toLowerCase()}`}>{d.predicted}</span></td>
                          <td><span className={`outcome-badge ${d.outcome.toLowerCase()}`}>{d.outcome}</span></td>
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

      {activeTab === 'synthetic' && (
        <div className="synthetic-view">
          <div className="testing-actions">
            <button className="run-btn" onClick={handleRunAll}>Run All Synthetic Tests</button>
            <button className="refresh-btn" onClick={fetchData}>Refresh</button>
          </div>

          {summary && (
            <div className="summary-cards">
              <div className="card">
                <h3>Total Runs</h3>
                <div className="value">{summary.total_runs}</div>
              </div>
              <div className="card">
                <h3>Passed</h3>
                <div className="value success">{summary.passed_runs}</div>
              </div>
              <div className="card">
                <h3>Failed</h3>
                <div className="value danger">{summary.failed_runs}</div>
              </div>
              <div className="card">
                <h3>Pass Rate</h3>
                <div className="value info">{summary.pass_rate.toFixed(1)}%</div>
              </div>
            </div>
          )}

          <div className="runs-section">
            <h2>Recent Synthetic Test Runs</h2>
            <table className="runs-table">
              <thead>
                <tr>
                  <th>Test Name</th>
                  <th>Stage</th>
                  <th>Status</th>
                  <th>Duration (ms)</th>
                  <th>Started</th>
                  <th>Passed</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run.test_run_id}>
                    <td>{run.test_name}</td>
                    <td>{run.stage.toUpperCase()}</td>
                    <td>
                      <span className={`status-badge ${run.status}`}>
                        {run.status}
                      </span>
                    </td>
                    <td>{run.duration_ms}</td>
                    <td>{new Date(run.started_at).toLocaleString()}</td>
                    <td>
                      {run.status === 'completed' ? (
                        run.passed ? <span className="pass">✅ PASS</span> : <span className="fail">❌ FAIL</span>
                      ) : '-'}
                    </td>
                    <td>
                      <button onClick={() => handleDeleteRun(run.test_run_id)}>Delete</button>
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr><td colSpan="7">No test runs found.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default TestingDashboard;

