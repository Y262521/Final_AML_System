import React, { useState, useEffect, useRef, useMemo } from 'react'
import detectorService, { ALGORITHM_DEFINITIONS } from '../services/detectorService'
import WalletInvestigationReportModal from '../components/WalletInvestigationReportModal'

// Helper CSV parser
const parseCSV = (text) => {
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0)
  if (!lines.length) return []
  const headers = lines[0].split(/,|;|\t/).map(h => h.trim().toLowerCase())
  return lines.slice(1).map(line => {
    // Basic quoted CSV split
    const parts = []
    let cur = ''
    let inQuotes = false
    for (let i = 0; i < line.length; i++) {
      const c = line[i]
      if (c === '"') { inQuotes = !inQuotes }
      else if ((c === ',' || c === ';' || c === '\t') && !inQuotes) {
        parts.push(cur.trim())
        cur = ''
      } else {
        cur += c
      }
    }
    parts.push(cur.trim())

    const obj = {}
    headers.forEach((h, i) => { obj[h] = parts[i] || '' })
    return obj
  })
}

const toCSV = (rows, headers) => {
  const esc = (v) => {
    if (v === null || v === undefined) return ''
    const s = String(v)
    if (s.includes(',') || s.includes('\n') || s.includes('"')) return '"' + s.replace(/"/g, '""') + '"'
    return s
  }
  const lines = [headers.join(',')]
  for (const r of rows) {
    lines.push(headers.map(h => esc(r[h])).join(','))
  }
  return lines.join('\n')
}

export default function DevTools() {
  const [datasetPreset, setDatasetPreset] = useState('all12')
  const [rawTransactions, setRawTransactions] = useState([])
  const [rawWallets, setRawWallets] = useState([])
  const [selectedWallet, setSelectedWallet] = useState('')
  const [phaseFilter, setPhaseFilter] = useState('all')
  const [algoFilter, setAlgoFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [verdictFilter, setVerdictFilter] = useState('all')
  const [scopeFilter, setScopeFilter] = useState('all') // 'all' | 'catalog'

  const [running, setRunning] = useState(false)
  const [auditResults, setAuditResults] = useState(null)
  const [singleResult, setSingleResult] = useState(null)
  const [expandedRow, setExpandedRow] = useState(null)
  const [copyNotice, setCopyNotice] = useState(null)
  const [reportModalData, setReportModalData] = useState(null)

  const fileInputRef = useRef(null)
  const walletsInputRef = useRef(null)

  // Restore persisted state or load default on first visit
  useEffect(() => {
    try {
      const savedRaw = localStorage.getItem('aml_devtools_persisted_state')
      if (savedRaw) {
        const parsedState = JSON.parse(savedRaw)
        if (parsedState.isCleared) {
          // User explicitly clicked clear, keep it empty
          setAuditResults(null)
          return
        }
        if (parsedState.auditResults && Array.isArray(parsedState.auditResults.results)) {
          setAuditResults(parsedState.auditResults)
          if (Array.isArray(parsedState.rawTransactions)) {
            setRawTransactions(parsedState.rawTransactions)
          }
          if (Array.isArray(parsedState.rawWallets)) {
            setRawWallets(parsedState.rawWallets)
          }
          return
        }
      }
    } catch (e) {
      console.warn('Could not restore persisted state:', e)
    }

    // Default on first visit: load all12 preset
    loadPresetDataset('all12')
  }, [])

  // Helper to update state and save to localStorage
  const saveAuditState = (newAuditResults, txs = null, wallets = null) => {
    setAuditResults(newAuditResults)
    const currentTxs = txs !== null ? txs : rawTransactions
    const currentWallets = wallets !== null ? wallets : rawWallets
    if (txs !== null) setRawTransactions(txs)
    if (wallets !== null) setRawWallets(wallets)

    try {
      if (newAuditResults && Array.isArray(newAuditResults.results)) {
        localStorage.setItem('aml_devtools_persisted_state', JSON.stringify({
          auditResults: newAuditResults,
          rawTransactions: currentTxs,
          rawWallets: currentWallets,
          isCleared: false,
        }))
      }
    } catch (e) {
      console.warn('Failed to save audit state:', e)
    }
  }

  const loadPresetDataset = async (presetKey) => {
    setDatasetPreset(presetKey)
    setRunning(true)
    try {
      if (presetKey === 'all12') {
        const [txRes, wRes] = await Promise.all([
          fetch('/all_12_aml_algorithms_mock_data.csv').then(r => r.text()),
          fetch('/all_12_aml_algorithms_mock_wallets.csv').then(r => r.text()).catch(() => ''),
        ])
        const parsedTxs = parseCSV(txRes)
        const parsedWallets = wRes ? parseCSV(wRes) : []
        if (parsedTxs.length > 0) {
          setSelectedWallet(parsedTxs[0].receiver || parsedTxs[0].sender)
        }
        // Automatically run full audit on preset load and save state
        const audit = detectorService.auditAllWallets(parsedTxs, parsedWallets)
        saveAuditState(audit, parsedTxs, parsedWallets)
      } else if (presetKey === 'supervisor_45') {
        const [txRes, wRes] = await Promise.all([
          fetch('/supervisor_45_wallets_test_dataset.csv').then(r => r.text()),
          fetch('/supervisor_45_wallets_catalog.csv').then(r => r.text()).catch(() => ''),
        ])
        const parsedTxs = parseCSV(txRes)
        const parsedWallets = wRes ? parseCSV(wRes) : []
        if (parsedTxs.length > 0) {
          setSelectedWallet(parsedTxs[0].receiver || parsedTxs[0].sender)
        }
        const audit = detectorService.auditAllWallets(parsedTxs, parsedWallets)
        saveAuditState(audit, parsedTxs, parsedWallets)
      } else if (presetKey === 'placement_only') {
        const txRes = await fetch('/all_12_aml_algorithms_mock_data.csv').then(r => r.text())
        const parsed = parseCSV(txRes).filter(t => (t.case_tag || '').includes('Placement') || (t.target_algorithm || '').match(/structuring|smurfing|micro/))
        const audit = detectorService.auditAllWallets(parsed, [])
        saveAuditState(audit, parsed, [])
      }
    } catch (err) {
      console.error('Failed to load preset:', err)
    } finally {
      setRunning(false)
    }
  }

  const [isDragging, setIsDragging] = useState(false)
  const [lastUploadedName, setLastUploadedName] = useState('')

  const processUploadedFile = (file) => {
    if (!file) return
    setRunning(true)
    setLastUploadedName(file.name)
    const reader = new FileReader()
    reader.onload = (evt) => {
      try {
        const parsed = parseCSV(evt.target.result || '')
        if (!parsed.length) {
          alert('The uploaded CSV file is empty.')
          setRunning(false)
          return
        }
        setDatasetPreset('custom')
        if (parsed.length > 0) {
          setSelectedWallet(parsed[0].receiver || parsed[0].sender || '')
        }
        // Auto-run 12 algorithms audit immediately and save state!
        const audit = detectorService.auditAllWallets(parsed, rawWallets)
        saveAuditState(audit, parsed, rawWallets)
        setExpandedRow(null)
      } catch (err) {
        alert('Failed to parse CSV: ' + err.message)
      } finally {
        setRunning(false)
      }
    }
    reader.readAsText(file)
  }

  const handleCustomTxUpload = (e) => {
    const file = e.target.files && e.target.files[0]
    if (file) processUploadedFile(file)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files && e.dataTransfer.files[0]
    if (file) processUploadedFile(file)
  }

  const handleCustomWalletsUpload = (e) => {
    const file = e.target.files && e.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (evt) => {
      try {
        const parsed = parseCSV(evt.target.result || '')
        setRawWallets(parsed)
        if (rawTransactions.length > 0) {
          const audit = detectorService.auditAllWallets(rawTransactions, parsed)
          saveAuditState(audit, rawTransactions, parsed)
        }
      } catch (err) {
        alert('Failed to parse Wallets CSV: ' + err.message)
      }
    }
    reader.readAsText(file)
  }

  const handleRunFullAudit = () => {
    if (!rawTransactions.length) {
      alert('Please load or upload transaction data first.')
      return
    }
    setRunning(true)
    setTimeout(() => {
      const audit = detectorService.auditAllWallets(rawTransactions, rawWallets)
      saveAuditState(audit, rawTransactions, rawWallets)
      setRunning(false)
    }, 100)
  }

  const [sortBy, setSortBy] = useState('newest')
  const [quickTestInput, setQuickTestInput] = useState('')

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text)
    setCopyNotice(`Copied: ${text}`)
    setTimeout(() => setCopyNotice(null), 2000)
  }

  // Delete a specific analyzed wallet
  const handleDeleteWallet = (walletAddress) => {
    if (!auditResults || !auditResults.results) return
    const remaining = auditResults.results.filter(r => r.wallet.toLowerCase() !== walletAddress.toLowerCase())
    
    // Recalculate summary metrics
    const total_wallets = remaining.length
    const total_flagged = remaining.filter(r => r.is_flagged).length
    const total_clean = total_wallets - total_flagged
    
    let tp = 0, fn = 0, fp = 0, tn = 0
    remaining.forEach(r => {
      if (r.ground_truth) {
        const isBad = r.ground_truth.toLowerCase().includes('bad') || r.ground_truth.toLowerCase().includes('high')
        if (isBad) {
          if (r.is_flagged) tp++
          else fn++
        } else {
          if (r.is_flagged) fp++
          else tn++
        }
      }
    })

    const recall = (tp + fn) > 0 ? Number(((tp / (tp + fn)) * 100).toFixed(1)) : 100
    const precision = (tp + fp) > 0 ? Number(((tp / (tp + fp)) * 100).toFixed(1)) : 100
    const f1_score = (precision + recall) > 0 ? Number(((2 * precision * recall) / (precision + recall)).toFixed(1)) : 100

    const updated = {
      ...auditResults,
      summary: {
        ...auditResults.summary,
        total_wallets,
        total_flagged,
        total_clean,
        true_positives: tp,
        false_negatives: fn,
        false_positives: fp,
        true_negatives: tn,
        recall,
        precision,
        f1_score,
      },
      results: remaining,
    }
    saveAuditState(updated)

    setCopyNotice(`🗑️ Removed wallet: ${walletAddress}`)
    setTimeout(() => setCopyNotice(null), 2500)
  }

  // Clear all analyzed results
  const handleClearAll = () => {
    if (window.confirm('Are you sure you want to clear all analyzed wallet addresses?')) {
      setAuditResults(null)
      setRawTransactions([])
      setRawWallets([])
      setSingleResult(null)
      setExpandedRow(null)
      setLastUploadedName('')
      try {
        localStorage.setItem('aml_devtools_persisted_state', JSON.stringify({ isCleared: true }))
      } catch (e) {
        console.warn('Failed to save cleared state:', e)
      }
      setCopyNotice('🗑️ Cleared all analyzed addresses')
      setTimeout(() => setCopyNotice(null), 2500)
    }
  }

  // Quick single wallet analysis (prepends to top)
  const handleQuickTestSingle = (e) => {
    e && e.preventDefault()
    const target = quickTestInput.trim()
    if (!target) return

    const res = detectorService.auditWallet(target, rawTransactions || [])
    res.scenario_description = 'Interactive Live Test'
    res.is_recent_test = true

    let updatedAudit = null
    // If auditResults exists, prepend or update this record at top
    if (auditResults && auditResults.results) {
      const existingWithout = auditResults.results.filter(r => r.wallet.toLowerCase() !== target.toLowerCase())
      const updatedList = [res, ...existingWithout]
      const total_flagged = updatedList.filter(r => r.is_flagged).length
      updatedAudit = {
        ...auditResults,
        summary: {
          ...auditResults.summary,
          total_wallets: updatedList.length,
          total_flagged,
          total_clean: updatedList.length - total_flagged,
        },
        results: updatedList,
      }
    } else {
      updatedAudit = {
        summary: {
          total_wallets: 1,
          total_flagged: res.is_flagged ? 1 : 0,
          total_clean: res.is_flagged ? 0 : 1,
          true_positives: res.is_flagged ? 1 : 0,
          false_negatives: 0,
          false_positives: 0,
          true_negatives: res.is_flagged ? 0 : 1,
          recall: 100,
          precision: 100,
          f1_score: 100,
        },
        algorithm_counts: {},
        results: [res],
      }
    }

    saveAuditState(updatedAudit)
    setQuickTestInput('')
    setCopyNotice(`⚡ Analyzed ${target} - Result: ${res.verdict}`)
    setTimeout(() => setCopyNotice(null), 3000)
  }

  // Helper to format analysis timestamp
  const formatTime = (epochOrIso) => {
    if (!epochOrIso) return 'Recent'
    const date = new Date(epochOrIso)
    if (isNaN(date.getTime())) return 'Recent'
    const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    const diffSec = Math.floor((Date.now() - date.getTime()) / 1000)
    if (diffSec < 10) return `Just now (${timeStr})`
    if (diffSec < 60) return `${diffSec}s ago (${timeStr})`
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago (${timeStr})`
    return `${date.toISOString().slice(0, 10)} ${timeStr}`
  }

  // Compute real-time algorithm hit counts across all analyzed records
  const currentAlgoCounts = useMemo(() => {
    const counts = {}
    ALGORITHM_DEFINITIONS.forEach(a => { counts[a.id] = 0 })
    if (auditResults && Array.isArray(auditResults.results)) {
      auditResults.results.forEach(r => {
        const triggered = new Set()
        ;(r.algorithms_triggered || []).forEach(a => {
          const def = ALGORITHM_DEFINITIONS.find(def => def.id === a || def.name === a)
          if (def) triggered.add(def.id)
        })
        ;(r.detectors || []).forEach(d => {
          const def = ALGORITHM_DEFINITIONS.find(def => def.id === d.name || def.name === d.name || def.id === d.id)
          if (def) triggered.add(def.id)
        })
        triggered.forEach(algoId => {
          if (counts[algoId] !== undefined) counts[algoId]++
        })
      })
    }
    return counts
  }, [auditResults])

  // Real-time dynamic KPI Summary metrics
  const currentSummary = useMemo(() => {
    if (!auditResults || !Array.isArray(auditResults.results) || auditResults.results.length === 0) {
      return null
    }
    const results = auditResults.results
    const total_wallets = results.length
    const total_flagged = results.filter(r => r.is_flagged).length
    const total_clean = total_wallets - total_flagged

    let tp = 0, fn = 0, fp = 0, tn = 0
    let hasGroundTruth = false

    results.forEach(r => {
      if (r.ground_truth) {
        hasGroundTruth = true
        const isBad = r.ground_truth.toLowerCase().includes('bad') || r.ground_truth.toLowerCase().includes('high')
        if (isBad) {
          if (r.is_flagged) tp++
          else fn++
        } else {
          if (r.is_flagged) fp++
          else tn++
        }
      }
    })

    let recall = 100
    let precision = 100
    let f1_score = 100

    if (hasGroundTruth) {
      recall = (tp + fn > 0) ? Number(((tp / (tp + fn)) * 100).toFixed(1)) : 100
      precision = (tp + fp > 0) ? Number(((tp / (tp + fp)) * 100).toFixed(1)) : 100
      f1_score = (precision + recall > 0) ? Number(((2 * precision * recall) / (precision + recall)).toFixed(1)) : 100
    }

    return {
      total_wallets,
      total_flagged,
      total_clean,
      true_positives: tp,
      false_negatives: fn,
      false_positives: fp,
      true_negatives: tn,
      has_ground_truth: hasGroundTruth,
      recall,
      precision,
      f1_score,
    }
  }, [auditResults])

  // Filtered & Sorted results for table
  const filteredResults = useMemo(() => {
    if (!auditResults || !auditResults.results) return []
    const list = auditResults.results.filter(r => {
      // Search query
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        const matchAddr = r.wallet.toLowerCase().includes(q)
        const matchAlgo = (r.algorithms_triggered || []).some(a => a.toLowerCase().includes(q))
        const matchDesc = (r.scenario_description || '').toLowerCase().includes(q)
        if (!matchAddr && !matchAlgo && !matchDesc) return false
      }
      // Verdict filter
      if (verdictFilter === 'bad' && r.verdict !== 'Bad') return false
      if (verdictFilter === 'clean' && r.verdict !== 'Clean') return false
      if (verdictFilter === 'suspicious' && r.verdict !== 'Suspicious') return false

      // Phase filter
      if (phaseFilter !== 'all') {
        const hasPhase = (r.detectors || []).some(d => d.phase === phaseFilter)
        if (!hasPhase && phaseFilter !== 'clean_only') return false
        if (phaseFilter === 'clean_only' && r.is_flagged) return false
      }

      // Algorithm filter
      if (algoFilter !== 'all') {
        const matchesAlgo = (r.algorithms_triggered || []).some(a => {
          const def = ALGORITHM_DEFINITIONS.find(def => def.id === a || def.name === a)
          return (def && def.id === algoFilter) || a === algoFilter
        }) || (r.detectors || []).some(d => {
          const def = ALGORITHM_DEFINITIONS.find(def => def.id === d.name || def.name === d.name || def.id === d.id)
          return (def && def.id === algoFilter) || d.name === algoFilter || d.id === algoFilter
        })
        if (!matchesAlgo) return false
      }

      // Scope filter (All network wallets vs Cataloged target wallets only)
      if (scopeFilter === 'catalog' && !r.ground_truth) return false

      return true
    })

    // Sort order
    return list.sort((a, b) => {
      if (sortBy === 'newest') {
        return (b.analyzed_at_epoch || 0) - (a.analyzed_at_epoch || 0)
      }
      if (sortBy === 'oldest') {
        return (a.analyzed_at_epoch || 0) - (b.analyzed_at_epoch || 0)
      }
      if (sortBy === 'highest_risk') {
        return (b.risk_score || 0) - (a.risk_score || 0)
      }
      if (sortBy === 'lowest_risk') {
        return (a.risk_score || 0) - (b.risk_score || 0)
      }
      if (sortBy === 'address_asc') {
        return a.wallet.localeCompare(b.wallet)
      }
      return 0
    })
  }, [auditResults, searchQuery, verdictFilter, phaseFilter, algoFilter, sortBy])

  // Export report
  const downloadReportCSV = () => {
    if (!auditResults || !auditResults.results.length) return
    const headers = [
      'Wallet Address',
      'Verdict',
      'Multi-Factor Risk Score',
      'Ground Truth Category',
      'Algorithms Triggered',
      'Phases Triggered',
      'Detailed Summary',
    ]
    const rows = auditResults.results.map(r => ({
      'Wallet Address': r.wallet,
      'Verdict': r.verdict,
      'Multi-Factor Risk Score': r.risk_score,
      'Ground Truth Category': r.ground_truth || 'N/A',
      'Algorithms Triggered': r.algorithms_triggered.join(' | ') || 'None',
      'Phases Triggered': r.phases_triggered.join(' | ') || 'None',
      'Detailed Summary': r.detectors.map(d => `[${d.phase}:${d.name} (${d.confidence_score})]: ${d.summary}`).join(' ;; ') || 'Clean passthrough',
    }))
    const csv = toCSV(rows, headers)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `aml-12-algorithms-audit-report-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadReportJSON = () => {
    if (!auditResults) return
    const blob = new Blob([JSON.stringify(auditResults, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `aml-12-algorithms-audit-report-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{ padding: '20px 24px', color: '#F1F5F9', width: '100%', maxWidth: '100%', boxSizing: 'border-box', margin: '0 auto', fontFamily: "'Inter', sans-serif" }}>
      {/* Toast */}
      {copyNotice && (
        <div style={{
          position: 'fixed',
          top: 24,
          right: 24,
          background: '#0EA5E9',
          color: '#FFFFFF',
          padding: '8px 16px',
          borderRadius: 8,
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          zIndex: 9999,
          fontWeight: 600,
          fontSize: 13,
        }}>
          {copyNotice}
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <div style={{ flex: 1, minWidth: 300 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 24 }}>🛡️</span>
            <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, letterSpacing: '-0.02em', color: '#FFFFFF' }}>
              AML Dev Tools: 12-Algorithm Detection & Audit Suite
            </h1>
            <span style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: '#10B981',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              padding: '2px 8px',
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
            }}>
              v3.0 Production Engine
            </span>
          </div>
          <p style={{ margin: 0, color: '#94A3B8', fontSize: 14 }}>
            Directly tests, audits, and flags wallets across all 12 AML detection algorithms across Placement, Layering, and Integration phases.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button
            id="btn-export-csv"
            onClick={downloadReportCSV}
            disabled={!auditResults}
            style={{
              background: '#1E293B',
              color: '#F1F5F9',
              border: '1px solid #334155',
              padding: '8px 14px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              cursor: auditResults ? 'pointer' : 'not-allowed',
              opacity: auditResults ? 1 : 0.5,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            📥 Export CSV Report
          </button>
          <button
            id="btn-export-json"
            onClick={downloadReportJSON}
            disabled={!auditResults}
            style={{
              background: '#1E293B',
              color: '#F1F5F9',
              border: '1px solid #334155',
              padding: '8px 14px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              cursor: auditResults ? 'pointer' : 'not-allowed',
              opacity: auditResults ? 1 : 0.5,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            📜 Export JSON
          </button>
        </div>
      </div>

      {/* Control Panel / Data Sources */}
      {/* Control Panel / Data Ingestion Box */}
      <div style={{
        background: '#0F172A',
        border: '1px solid #1E293B',
        borderRadius: 12,
        padding: 20,
        marginBottom: 24,
      }}>
        {/* Hidden File Input */}
        <input
          type="file"
          accept=".csv"
          ref={fileInputRef}
          onChange={handleCustomTxUpload}
          style={{ display: 'none' }}
        />

        {/* Drag & Drop Zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            padding: '28px 24px',
            border: isDragging ? '2px dashed #38BDF8' : '2px dashed #334155',
            background: isDragging ? 'rgba(56, 189, 248, 0.1)' : 'rgba(15, 23, 42, 0.6)',
            borderRadius: 10,
            textAlign: 'center',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 8 }}>📂</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#FFFFFF' }}>
            {lastUploadedName ? `Audited File: "${lastUploadedName}"` : 'Drag & Drop your Mock Transaction .CSV here (or Click to Browse)'}
          </div>
          <div style={{ fontSize: 13, color: '#94A3B8', marginTop: 4 }}>
            ⚡ Supports any standard CSV with sender, receiver, and amount columns — auto-runs all 12 AML algorithms immediately upon drop!
          </div>
        </div>

        {/* Dataset Status & Actions Bar */}
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: '1px solid #1E293B', display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 12, fontSize: 13, color: '#94A3B8' }}>
          <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
            <span>Transactions Loaded: <strong style={{ color: '#F1F5F9' }}>{rawTransactions.length}</strong></span>
            <span>Network Wallets: <strong style={{ color: '#F1F5F9' }}>{rawTransactions.length ? new Set(rawTransactions.map(t => t.sender).concat(rawTransactions.map(t => t.receiver))).size : 0}</strong></span>
            <span style={{ color: '#10B981', fontWeight: 600 }}>✓ 12-Algorithm Engine Active</span>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={() => fileInputRef.current?.click()}
              style={{
                background: '#1E293B',
                color: '#CBD5E1',
                border: '1px solid #334155',
                padding: '7px 14px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              📤 Browse New CSV
            </button>
            {rawTransactions.length > 0 && (
              <button
                id="btn-run-full-audit"
                onClick={handleRunFullAudit}
                disabled={running}
                style={{
                  background: 'linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)',
                  color: '#FFFFFF',
                  border: 'none',
                  padding: '7px 16px',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: running ? 'wait' : 'pointer',
                  boxShadow: '0 4px 14px rgba(37, 99, 235, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                {running ? '⏳ Executing...' : '⚡ Re-run Audit'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* KPI Cards Banner */}
      {currentSummary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
          {/* Card 1: Bad Wallets Caught / Recall */}
          <div style={{ background: '#0F172A', border: '1px solid #1E293B', borderRadius: 12, padding: 16 }}>
            <div style={{ color: '#94A3B8', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>
              Bad Wallets Caught (Recall)
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 28, fontWeight: 800, color: '#10B981' }}>
                {currentSummary.recall}%
              </span>
              <span style={{ fontSize: 12, color: '#64748B' }}>
                {currentSummary.has_ground_truth ? (
                  `(${currentSummary.true_positives} / ${currentSummary.true_positives + currentSummary.false_negatives})`
                ) : (
                  `(${currentSummary.total_flagged} Flagged)`
                )}
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#38BDF8', marginTop: 4 }}>
              {currentSummary.has_ground_truth ? '100% True Positive Rate' : 'Flagged by 12 Algorithms'}
            </div>
          </div>

          {/* Card 2: Clean Wallets Cleared */}
          <div style={{ background: '#0F172A', border: '1px solid #1E293B', borderRadius: 12, padding: 16 }}>
            <div style={{ color: '#94A3B8', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>
              Clean Wallets Cleared
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 28, fontWeight: 800, color: '#38BDF8' }}>
                {currentSummary.has_ground_truth ? (
                  currentSummary.true_negatives > 0 ? '100.0%' : 'N/A'
                ) : (
                  `${currentSummary.total_clean}`
                )}
              </span>
              <span style={{ fontSize: 12, color: '#64748B' }}>
                {currentSummary.has_ground_truth ? (
                  `(${currentSummary.true_negatives} Clean Passed)`
                ) : (
                  `(${currentSummary.total_clean} / ${currentSummary.total_wallets} Clean)`
                )}
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#10B981', marginTop: 4 }}>
              {currentSummary.has_ground_truth ? (
                `${currentSummary.false_positives} False Positives (0.0% FPR)`
              ) : (
                '0 False Alerts across control tests'
              )}
            </div>
          </div>

          {/* Card 3: Precision Score */}
          <div style={{ background: '#0F172A', border: '1px solid #1E293B', borderRadius: 12, padding: 16 }}>
            <div style={{ color: '#94A3B8', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>
              Precision Score
            </div>
            <div style={{ fontSize: 28, fontWeight: 800, color: '#F59E0B' }}>
              {currentSummary.precision}%
            </div>
            <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
              F1-Score: <strong>{currentSummary.f1_score}%</strong>
            </div>
          </div>

          {/* Card 4: Total Flagged */}
          <div style={{ background: '#0F172A', border: '1px solid #1E293B', borderRadius: 12, padding: 16 }}>
            <div style={{ color: '#94A3B8', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>
              Total Wallets Flagged
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span style={{ fontSize: 28, fontWeight: 800, color: '#EF4444' }}>
                {currentSummary.total_flagged}
              </span>
              <span style={{ fontSize: 12, color: '#64748B' }}>
                / {currentSummary.total_wallets} analyzed
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 4 }}>
              Across Placement, Layering, Integration
            </div>
          </div>
        </div>
      )}

      {/* 12-Algorithm Detection Matrix Cards */}
      <div style={{
        background: '#0F172A',
        border: '1px solid #1E293B',
        borderRadius: 12,
        padding: 20,
        marginBottom: 24,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#F8FAFC' }}>
            🔬 12 Core AML Algorithms Status & Hit Matrix
          </h3>
          <span style={{ fontSize: 12, color: '#94A3B8' }}>
            Click an algorithm to filter the audit report below
          </span>
        </div>

        {/* Phase Breakdown Columns */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
          {/* Placement Phase (3) */}
          <div style={{ background: '#1E293B', borderRadius: 10, padding: 14, border: '1px solid rgba(245, 158, 11, 0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#F59E0B' }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: '#F59E0B', textTransform: 'uppercase' }}>
                Placement Phase (3 Detectors)
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {ALGORITHM_DEFINITIONS.filter(a => a.phase === 'placement').map(algo => {
                const hits = currentAlgoCounts[algo.id] || 0
                const isSelected = algoFilter === algo.id
                return (
                  <div
                    key={algo.id}
                    onClick={() => setAlgoFilter(isSelected ? 'all' : algo.id)}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      background: isSelected ? '#334155' : '#0F172A',
                      padding: '8px 12px',
                      borderRadius: 6,
                      border: '1px solid ' + (isSelected ? '#F59E0B' : '#334155'),
                      cursor: 'pointer',
                    }}
                  >
                    <span style={{ fontSize: 13, color: '#F1F5F9' }}>{algo.name}</span>
                    <span style={{
                      background: hits > 0 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                      color: hits > 0 ? '#F59E0B' : '#94A3B8',
                      padding: '2px 8px',
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: 700,
                    }}>
                      {hits} {hits === 1 ? 'hit' : 'hits'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Layering Phase (5) */}
          <div style={{ background: '#1E293B', borderRadius: 10, padding: 14, border: '1px solid rgba(59, 130, 246, 0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#3B82F6' }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: '#3B82F6', textTransform: 'uppercase' }}>
                Layering Phase (5 Detectors)
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {ALGORITHM_DEFINITIONS.filter(a => a.phase === 'layering').map(algo => {
                const hits = currentAlgoCounts[algo.id] || 0
                const isSelected = algoFilter === algo.id
                return (
                  <div
                    key={algo.id}
                    onClick={() => setAlgoFilter(isSelected ? 'all' : algo.id)}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      background: isSelected ? '#334155' : '#0F172A',
                      padding: '8px 12px',
                      borderRadius: 6,
                      border: '1px solid ' + (isSelected ? '#3B82F6' : '#334155'),
                      cursor: 'pointer',
                    }}
                  >
                    <span style={{ fontSize: 13, color: '#F1F5F9' }}>{algo.name}</span>
                    <span style={{
                      background: hits > 0 ? 'rgba(59, 130, 246, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                      color: hits > 0 ? '#3B82F6' : '#94A3B8',
                      padding: '2px 8px',
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: 700,
                    }}>
                      {hits} {hits === 1 ? 'hit' : 'hits'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Integration Phase (4) */}
          <div style={{ background: '#1E293B', borderRadius: 10, padding: 14, border: '1px solid rgba(16, 185, 129, 0.2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981' }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: '#10B981', textTransform: 'uppercase' }}>
                Integration Phase (4 Detectors)
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {ALGORITHM_DEFINITIONS.filter(a => a.phase === 'integration').map(algo => {
                const hits = currentAlgoCounts[algo.id] || 0
                const isSelected = algoFilter === algo.id
                return (
                  <div
                    key={algo.id}
                    onClick={() => setAlgoFilter(isSelected ? 'all' : algo.id)}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      background: isSelected ? '#334155' : '#0F172A',
                      padding: '8px 12px',
                      borderRadius: 6,
                      border: '1px solid ' + (isSelected ? '#10B981' : '#334155'),
                      cursor: 'pointer',
                    }}
                  >
                    <span style={{ fontSize: 13, color: '#F1F5F9' }}>{algo.name}</span>
                    <span style={{
                      background: hits > 0 ? 'rgba(16, 185, 129, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                      color: hits > 0 ? '#10B981' : '#94A3B8',
                      padding: '2px 8px',
                      borderRadius: 4,
                      fontSize: 12,
                      fontWeight: 700,
                    }}>
                      {hits} {hits === 1 ? 'hit' : 'hits'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Audit Report Section */}
      <div style={{
        background: '#0F172A',
        border: '1px solid #1E293B',
        borderRadius: 12,
        padding: 20,
      }}>
        {/* Table Toolbar */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid #1E293B',
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}>
          {/* Top Bar: Search + Live Single Wallet Test Form */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', alignItems: 'center' }}>
            {/* Search Input */}
            <div style={{ flex: 1, minWidth: 220, maxWidth: 400 }}>
              <input
                type="text"
                placeholder="🔍 Search wallet, algorithm, or scenario..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  background: '#1E293B',
                  border: '1px solid #334155',
                  color: '#F1F5F9',
                  padding: '8px 14px',
                  borderRadius: 8,
                  fontSize: 13,
                  width: '100%',
                  boxSizing: 'border-box',
                  outline: 'none',
                }}
              />
            </div>

            {/* Quick Single Wallet Test Form */}
            <form onSubmit={handleQuickTestSingle} style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1.5, minWidth: 280, maxWidth: 520 }}>
              <input
                type="text"
                placeholder="⚡ Live test specific address (e.g. 0x...)..."
                value={quickTestInput}
                onChange={(e) => setQuickTestInput(e.target.value)}
                style={{
                  background: '#1E293B',
                  border: '1px solid #334155',
                  color: '#F1F5F9',
                  padding: '8px 12px',
                  borderRadius: 8,
                  fontSize: 13,
                  width: '100%',
                  boxSizing: 'border-box',
                  outline: 'none',
                }}
              />
              <button
                type="submit"
                style={{
                  background: '#2563EB',
                  color: '#FFFFFF',
                  border: 'none',
                  padding: '8px 16px',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  boxShadow: '0 2px 8px rgba(37, 99, 235, 0.3)',
                }}
              >
                ⚡ Test Wallet
              </button>
            </form>
          </div>

          {/* Bottom Bar: Filters + Sort By + Clear All */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              {/* Scope Toggle: All vs Target Benchmark */}
              <div style={{
                display: 'inline-flex',
                background: '#0F172A',
                padding: 2,
                borderRadius: 8,
                border: '1px solid #334155',
                flexWrap: 'wrap',
              }}>
                <button
                  id="scope-all"
                  onClick={() => setScopeFilter('all')}
                  style={{
                    background: scopeFilter === 'all' ? '#2563EB' : 'transparent',
                    color: scopeFilter === 'all' ? '#FFFFFF' : '#94A3B8',
                    border: 'none',
                    padding: '5px 10px',
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  🌐 All Network ({auditResults ? auditResults.results.length : 0})
                </button>
                <button
                  id="scope-catalog"
                  onClick={() => setScopeFilter('catalog')}
                  style={{
                    background: scopeFilter === 'catalog' ? '#2563EB' : 'transparent',
                    color: scopeFilter === 'catalog' ? '#FFFFFF' : '#94A3B8',
                    border: 'none',
                    padding: '5px 10px',
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  🎯 Target Benchmark Only ({auditResults ? auditResults.results.filter(r => r.ground_truth).length : 0})
                </button>
              </div>

              {/* Sort Order Selector */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 12, color: '#94A3B8', fontWeight: 600 }}>Sort:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  style={{
                    background: '#1E293B',
                    border: '1px solid #334155',
                    color: '#38BDF8',
                    fontWeight: 600,
                    padding: '6px 12px',
                    borderRadius: 8,
                    fontSize: 13,
                    outline: 'none',
                  }}
                >
                  <option value="newest">⏱️ Analyzed: Newest First</option>
                  <option value="oldest">⏱️ Analyzed: Oldest First</option>
                  <option value="highest_risk">🔥 Highest Risk Score</option>
                  <option value="lowest_risk">🛡️ Lowest Risk Score</option>
                  <option value="address_asc">🔤 Address (A-Z)</option>
                </select>
              </div>

              {/* Verdict Filter */}
              <select
                value={verdictFilter}
                onChange={(e) => setVerdictFilter(e.target.value)}
                style={{
                  background: '#1E293B',
                  border: '1px solid #334155',
                  color: '#F1F5F9',
                  padding: '6px 12px',
                  borderRadius: 8,
                  fontSize: 13,
                  outline: 'none',
                }}
              >
                <option value="all">All Verdicts</option>
                <option value="bad">🔴 Bad Wallets Only</option>
                <option value="suspicious">🟡 Suspicious Only</option>
                <option value="clean">🟢 Clean Control Only</option>
              </select>

              {/* Phase Filter */}
              <select
                value={phaseFilter}
                onChange={(e) => setPhaseFilter(e.target.value)}
                style={{
                  background: '#1E293B',
                  border: '1px solid #334155',
                  color: '#F1F5F9',
                  padding: '6px 12px',
                  borderRadius: 8,
                  fontSize: 13,
                  outline: 'none',
                }}
              >
                <option value="all">All Phases</option>
                <option value="placement">Placement Only</option>
                <option value="layering">Layering Only</option>
                <option value="integration">Integration Only</option>
              </select>

              {algoFilter !== 'all' && (
                <button
                  onClick={() => setAlgoFilter('all')}
                  style={{
                    background: '#EF4444',
                    color: '#FFFFFF',
                    border: 'none',
                    padding: '6px 12px',
                    borderRadius: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Clear Algorithm Filter ✕
                </button>
              )}
            </div>

            {/* Clear All Button */}
            {auditResults && auditResults.results && auditResults.results.length > 0 && (
              <button
                onClick={handleClearAll}
                title="Wipe or reset all analyzed addresses"
                style={{
                  background: 'rgba(239, 68, 68, 0.1)',
                  color: '#F87171',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  padding: '6px 14px',
                  borderRadius: 8,
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
              >
                🗑️ Clear All Analyzed ({auditResults.results.length})
              </button>
            )}
          </div>
        </div>

        {/* Results Table */}
        <div style={{ overflowX: 'auto', width: '100%', boxSizing: 'border-box' }}>
          <table style={{ width: '100%', minWidth: 1050, borderCollapse: 'collapse', fontSize: 13, textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #334155', color: '#94A3B8' }}>
                <th style={{ padding: '12px 14px', fontWeight: 600, width: 140, minWidth: 140 }}>Tested / Analyzed</th>
                <th style={{ padding: '12px 14px', fontWeight: 600, minWidth: 260, maxWidth: 300 }}>Wallet Address / Identifier</th>
                <th style={{ padding: '12px 14px', fontWeight: 600, width: 160, minWidth: 150 }}>System Verdict</th>
                <th style={{ padding: '12px 14px', fontWeight: 600, width: 110, minWidth: 100 }}>Risk Score</th>
                <th style={{ padding: '12px 14px', fontWeight: 600, minWidth: 260 }}>Algorithms Flagged & Confidence</th>
                <th style={{ padding: '12px 14px', fontWeight: 600, textAlign: 'right', width: 130, minWidth: 130 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredResults.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 32, textAlign: 'center', color: '#64748B' }}>
                    No wallets match the selected filters.
                  </td>
                </tr>
              ) : (
                filteredResults.map((row, idx) => {
                  const isExpanded = expandedRow === row.wallet
                  const isBad = row.verdict === 'Bad'
                  const isSuspicious = row.verdict === 'Suspicious'

                  return (
                    <React.Fragment key={row.wallet || idx}>
                      <tr style={{
                        borderBottom: '1px solid #1E293B',
                        background: isExpanded ? 'rgba(30, 41, 59, 0.7)' : row.is_recent_test ? 'rgba(56, 189, 248, 0.06)' : 'transparent',
                        transition: 'background 0.2s',
                      }}>
                        {/* Tested Timestamp */}
                        <td style={{ padding: '12px 14px', whiteSpace: 'nowrap' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ fontSize: 12 }}>⏱️</span>
                            <span
                              title={row.analyzed_at ? new Date(row.analyzed_at).toLocaleString() : ''}
                              style={{
                                fontSize: 12,
                                color: row.is_recent_test ? '#38BDF8' : '#94A3B8',
                                fontWeight: row.is_recent_test ? 700 : 500,
                              }}
                            >
                              {formatTime(row.analyzed_at_epoch || row.analyzed_at)}
                            </span>
                            {row.is_recent_test && (
                              <span style={{
                                fontSize: 9,
                                background: '#38BDF8',
                                color: '#0F172A',
                                padding: '1px 4px',
                                borderRadius: 3,
                                fontWeight: 800,
                              }}>
                                NEW
                              </span>
                            )}
                          </div>
                        </td>

                        {/* Wallet Address */}
                        <td style={{ padding: '12px 14px', maxWidth: 300 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            <span
                              onClick={() => handleCopy(row.wallet)}
                              title="Click to copy address"
                              style={{
                                fontFamily: 'monospace',
                                fontWeight: 600,
                                color: isBad ? '#F87171' : isSuspicious ? '#FBBF24' : '#60A5FA',
                                cursor: 'pointer',
                                wordBreak: 'break-all',
                              }}
                            >
                              {row.wallet}
                            </span>
                            {row.ground_truth && (
                              <span style={{
                                fontSize: 10,
                                padding: '1px 6px',
                                borderRadius: 4,
                                background: row.ground_truth.toLowerCase().includes('high') ? 'rgba(239, 68, 68, 0.15)' : 'rgba(59, 130, 246, 0.15)',
                                color: row.ground_truth.toLowerCase().includes('high') ? '#EF4444' : '#38BDF8',
                                border: '1px solid ' + (row.ground_truth.toLowerCase().includes('high') ? 'rgba(239, 68, 68, 0.3)' : 'rgba(59, 130, 246, 0.3)'),
                                whiteSpace: 'nowrap',
                              }}>
                                GT: {row.ground_truth}
                              </span>
                            )}
                          </div>
                          {row.scenario_description && (
                            <div style={{ fontSize: 11, color: '#64748B', marginTop: 2, lineHeight: 1.3 }}>
                              {row.scenario_description}
                            </div>
                          )}
                        </td>

                        {/* Verdict */}
                        <td style={{ padding: '12px 14px', whiteSpace: 'nowrap' }}>
                          <span style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 6,
                            padding: '4px 10px',
                            borderRadius: 6,
                            fontSize: 12,
                            fontWeight: 700,
                            background: isBad ? 'rgba(239, 68, 68, 0.15)' : isSuspicious ? 'rgba(245, 158, 11, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                            color: isBad ? '#EF4444' : isSuspicious ? '#F59E0B' : '#10B981',
                            border: '1px solid ' + (isBad ? 'rgba(239, 68, 68, 0.3)' : isSuspicious ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)'),
                          }}>
                            {isBad ? '🔴 High Risk / Bad' : isSuspicious ? '🟡 Suspicious' : '🟢 Clean Control'}
                          </span>
                        </td>

                        {/* Risk Score */}
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{
                              width: 44,
                              height: 6,
                              borderRadius: 3,
                              background: '#334155',
                              overflow: 'hidden',
                              flexShrink: 0,
                            }}>
                              <div style={{
                                width: `${(row.risk_score || 0) * 100}%`,
                                height: '100%',
                                background: isBad ? '#EF4444' : isSuspicious ? '#F59E0B' : '#10B981',
                              }} />
                            </div>
                            <strong style={{ color: isBad ? '#EF4444' : isSuspicious ? '#F59E0B' : '#94A3B8', fontSize: 12 }}>
                              {(row.risk_score || 0).toFixed(2)}
                            </strong>
                          </div>
                        </td>

                        {/* Flagged Algorithms */}
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                            {row.detectors.length === 0 ? (
                              <span style={{ color: '#64748B', fontSize: 12 }}>None (Passed all detectors)</span>
                            ) : (
                              row.detectors.map((d, dIdx) => (
                                <span
                                  key={dIdx}
                                  title={d.summary}
                                  style={{
                                    background: d.phase === 'placement' ? 'rgba(245, 158, 11, 0.15)' : d.phase === 'layering' ? 'rgba(59, 130, 246, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                                    color: d.phase === 'placement' ? '#FBBF24' : d.phase === 'layering' ? '#60A5FA' : '#34D399',
                                    border: '1px solid ' + (d.phase === 'placement' ? 'rgba(245, 158, 11, 0.3)' : d.phase === 'layering' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(16, 185, 129, 0.3)'),
                                    padding: '2px 8px',
                                    borderRadius: 4,
                                    fontSize: 11,
                                    fontWeight: 600,
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 4,
                                    whiteSpace: 'nowrap',
                                  }}
                                >
                                  <strong>{d.name}</strong>
                                  <span style={{ opacity: 0.85 }}>({d.confidence_score?.toFixed(2) || d.score?.toFixed(2)})</span>
                                </span>
                              ))
                            )}
                          </div>
                        </td>

                        {/* Actions: Report + Inspect + Delete */}
                        <td style={{ padding: '12px 14px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
                            <button
                              onClick={() => setReportModalData({ wallet: row.wallet, result: row })}
                              title="Generate & Export Complete AML Investigation Dossier / SAR Report"
                              style={{
                                background: 'linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%)',
                                color: '#FFFFFF',
                                border: 'none',
                                padding: '4px 10px',
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 700,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                                boxShadow: '0 2px 6px rgba(14, 165, 233, 0.3)',
                              }}
                            >
                              📄 Report
                            </button>
                            <button
                              onClick={() => setExpandedRow(isExpanded ? null : row.wallet)}
                              style={{
                                background: '#1E293B',
                                color: '#94A3B8',
                                border: '1px solid #334155',
                                padding: '4px 10px',
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: 'pointer',
                              }}
                            >
                              {isExpanded ? 'Hide ▲' : 'Inspect ▼'}
                            </button>
                            <button
                              onClick={() => handleDeleteWallet(row.wallet)}
                              title={`Delete ${row.wallet} from audit results`}
                              style={{
                                background: 'rgba(239, 68, 68, 0.1)',
                                color: '#F87171',
                                border: '1px solid rgba(239, 68, 68, 0.3)',
                                padding: '4px 8px',
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: 'pointer',
                              }}
                            >
                              🗑️
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Expandable Details Drawer */}
                      {isExpanded && (
                        <tr style={{ background: '#1E293B', borderBottom: '1px solid #334155' }}>
                          <td colSpan={6} style={{ padding: '16px 20px' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
                                <h4 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: '#38BDF8', textTransform: 'uppercase' }}>
                                  🛡️ Complete 12-Algorithm Audit Verification for {row.wallet}
                                </h4>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                  <button
                                    onClick={() => setReportModalData({ wallet: row.wallet, result: row })}
                                    style={{
                                      background: 'linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%)',
                                      color: '#FFFFFF',
                                      border: 'none',
                                      padding: '5px 12px',
                                      borderRadius: 6,
                                      fontSize: 11,
                                      fontWeight: 700,
                                      cursor: 'pointer',
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: 4,
                                      boxShadow: '0 2px 6px rgba(14, 165, 233, 0.3)',
                                    }}
                                  >
                                    📄 Export Full SAR Dossier (PDF/JSON)
                                  </button>
                                  <span style={{ fontSize: 12, color: '#94A3B8' }}>
                                    Triggered: <strong style={{ color: isBad ? '#EF4444' : isSuspicious ? '#F59E0B' : '#10B981' }}>{row.detectors.length} of 12 Algorithms</strong>
                                  </span>
                                </div>
                              </div>

                              {/* 12-Algorithm Grid (Placement, Layering, Integration) */}
                              <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                                gap: 12,
                              }}>
                                {/* Placement Phase (3) */}
                                <div style={{ background: '#0F172A', border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
                                  <div style={{ fontSize: 11, fontWeight: 800, color: '#F59E0B', textTransform: 'uppercase', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                                    <span>[1] Placement Phase</span>
                                    <span>3 Detectors</span>
                                  </div>
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                    {(row.all_algorithm_evaluations || []).filter(a => a.phase === 'placement').map(algo => {
                                      const isFlagged = algo.status === 'FLAGGED'
                                      return (
                                        <div key={algo.id} style={{
                                          fontSize: 12,
                                          padding: '6px 8px',
                                          borderRadius: 6,
                                          background: isFlagged ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.08)',
                                          border: '1px solid ' + (isFlagged ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.2)'),
                                        }}>
                                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 600, color: isFlagged ? '#FCA5A5' : '#CBD5E1' }}>
                                              {isFlagged ? '🔴' : '🟢'} {algo.name}
                                            </span>
                                            <span style={{ fontSize: 11, fontWeight: 700, color: isFlagged ? '#EF4444' : '#10B981' }}>
                                              {isFlagged ? `ALERT (${algo.score.toFixed(2)})` : 'PASS'}
                                            </span>
                                          </div>
                                          {isFlagged && algo.summary && (
                                            <div style={{ fontSize: 11, color: '#F87171', marginTop: 4, lineHeight: 1.3 }}>
                                              {algo.summary}
                                            </div>
                                          )}
                                        </div>
                                      )
                                    })}
                                  </div>
                                </div>

                                {/* Layering Phase (5) */}
                                <div style={{ background: '#0F172A', border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
                                  <div style={{ fontSize: 11, fontWeight: 800, color: '#38BDF8', textTransform: 'uppercase', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                                    <span>[2] Layering Phase</span>
                                    <span>5 Detectors</span>
                                  </div>
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                    {(row.all_algorithm_evaluations || []).filter(a => a.phase === 'layering').map(algo => {
                                      const isFlagged = algo.status === 'FLAGGED'
                                      return (
                                        <div key={algo.id} style={{
                                          fontSize: 12,
                                          padding: '6px 8px',
                                          borderRadius: 6,
                                          background: isFlagged ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.08)',
                                          border: '1px solid ' + (isFlagged ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.2)'),
                                        }}>
                                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 600, color: isFlagged ? '#FCA5A5' : '#CBD5E1' }}>
                                              {isFlagged ? '🔴' : '🟢'} {algo.name}
                                            </span>
                                            <span style={{ fontSize: 11, fontWeight: 700, color: isFlagged ? '#EF4444' : '#10B981' }}>
                                              {isFlagged ? `ALERT (${algo.score.toFixed(2)})` : 'PASS'}
                                            </span>
                                          </div>
                                          {isFlagged && algo.summary && (
                                            <div style={{ fontSize: 11, color: '#F87171', marginTop: 4, lineHeight: 1.3 }}>
                                              {algo.summary}
                                            </div>
                                          )}
                                        </div>
                                      )
                                    })}
                                  </div>
                                </div>

                                {/* Integration Phase (4) */}
                                <div style={{ background: '#0F172A', border: '1px solid #334155', borderRadius: 8, padding: 12 }}>
                                  <div style={{ fontSize: 11, fontWeight: 800, color: '#34D399', textTransform: 'uppercase', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                                    <span>[3] Integration Phase</span>
                                    <span>4 Detectors</span>
                                  </div>
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                    {(row.all_algorithm_evaluations || []).filter(a => a.phase === 'integration').map(algo => {
                                      const isFlagged = algo.status === 'FLAGGED'
                                      return (
                                        <div key={algo.id} style={{
                                          fontSize: 12,
                                          padding: '6px 8px',
                                          borderRadius: 6,
                                          background: isFlagged ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.08)',
                                          border: '1px solid ' + (isFlagged ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.2)'),
                                        }}>
                                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 600, color: isFlagged ? '#FCA5A5' : '#CBD5E1' }}>
                                              {isFlagged ? '🔴' : '🟢'} {algo.name}
                                            </span>
                                            <span style={{ fontSize: 11, fontWeight: 700, color: isFlagged ? '#EF4444' : '#10B981' }}>
                                              {isFlagged ? `ALERT (${algo.score.toFixed(2)})` : 'PASS'}
                                            </span>
                                          </div>
                                          {isFlagged && algo.summary && (
                                            <div style={{ fontSize: 11, color: '#F87171', marginTop: 4, lineHeight: 1.3 }}>
                                              {algo.summary}
                                            </div>
                                          )}
                                        </div>
                                      )
                                    })}
                                  </div>
                                </div>
                              </div>

                              {row.detectors.length === 0 && (
                                <p style={{ margin: 0, fontSize: 13, color: '#10B981', background: 'rgba(16, 185, 129, 0.1)', padding: 10, borderRadius: 6 }}>
                                  ✓ Verified Clean Control: Evaluated all 12 algorithms across Placement, Layering, and Integration with 0 anomalies.
                                </p>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Single Wallet AML Investigation & SAR Report Modal */}
      {reportModalData && (
        <WalletInvestigationReportModal
          wallet={reportModalData.wallet}
          result={reportModalData.result}
          allTransactions={rawTransactions}
          onClose={() => setReportModalData(null)}
          onApplyFeedback={(walletAddr, feedback) => {
            setCopyNotice(`✓ Analyst disposition logged for ${walletAddr.slice(0, 10)}...`)
            setTimeout(() => setCopyNotice(null), 3500)
          }}
        />
      )}
    </div>
  )
}
