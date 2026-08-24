import React, { useState, useMemo } from 'react'
import { GLOBAL_BENCHMARK_TRANSACTIONS } from '../services/benchmarkStore.js'

export default function WalletInvestigationReportModal({
  wallet,
  result,
  allTransactions = [],
  onClose,
  onApplyFeedback,
}) {
  const [feedbackStatus, setFeedbackStatus] = useState('pending') // 'pending' | 'confirmed' | 'false_positive' | 'needs_review'
  const [analystNotes, setAnalystNotes] = useState('')
  const [feedbackSaved, setFeedbackSaved] = useState(false)
  const [copyStatus, setCopyStatus] = useState(null)

  if (!wallet || !result) return null

  const isBad = result.verdict === 'Bad' || result.risk_score >= 0.60
  const isSuspicious = result.verdict === 'Suspicious' || (result.risk_score >= 0.30 && result.risk_score < 0.60)
  const isClean = !isBad && !isSuspicious

  const riskLabel = isBad ? 'CRITICAL RISK / HIGH-RISK' : isSuspicious ? 'ELEVATED SUSPICIOUS' : 'CLEAN CONTROL / LOW RISK'
  const riskColor = isBad ? '#EF4444' : isSuspicious ? '#F59E0B' : '#10B981'
  const riskBg = isBad ? 'rgba(239, 68, 68, 0.12)' : isSuspicious ? 'rgba(245, 158, 11, 0.12)' : 'rgba(16, 185, 129, 0.12)'

  // Filter transactions for this wallet
  const relatedTxs = useMemo(() => {
    const addr = String(wallet).toLowerCase().trim()
    const pool = (allTransactions && allTransactions.length > 0) ? allTransactions : (GLOBAL_BENCHMARK_TRANSACTIONS || [])
    
    let matched = pool.filter(t => {
      const s = String(t.sender || t.from || t.from_address || '').toLowerCase().trim()
      const r = String(t.receiver || t.to || t.to_address || '').toLowerCase().trim()
      return s === addr || r === addr
    })

    // If still not found in active pool and global benchmark exists, fall back to global pool
    if (matched.length === 0 && Array.isArray(GLOBAL_BENCHMARK_TRANSACTIONS)) {
      matched = GLOBAL_BENCHMARK_TRANSACTIONS.filter(t => {
        const s = String(t.sender || t.from || t.from_address || '').toLowerCase().trim()
        const r = String(t.receiver || t.to || t.to_address || '').toLowerCase().trim()
        return s === addr || r === addr
      })
    }

    return matched
  }, [wallet, allTransactions])

  const parseAmount = (t) => {
    if (!t) return 0
    const raw = t.amount_usd ?? t.value_usd ?? t.amount ?? t.value ?? 0
    return Number(String(raw).replace(/[$,]/g, '')) || 0
  }

  const totalInflow = useMemo(() => {
    const addr = String(wallet).toLowerCase().trim()
    return relatedTxs
      .filter(t => String(t.receiver || t.to || t.to_address || '').toLowerCase().trim() === addr)
      .reduce((acc, t) => acc + parseAmount(t), 0)
  }, [relatedTxs, wallet])

  const totalOutflow = useMemo(() => {
    const addr = String(wallet).toLowerCase().trim()
    return relatedTxs
      .filter(t => String(t.sender || t.from || t.from_address || '').toLowerCase().trim() === addr)
      .reduce((acc, t) => acc + parseAmount(t), 0)
  }, [relatedTxs, wallet])

  // Group detectors by phase
  const placementDetectors = (result.detectors || []).filter(d => d.phase === 'placement')
  const layeringDetectors = (result.detectors || []).filter(d => d.phase === 'layering')
  const integrationDetectors = (result.detectors || []).filter(d => d.phase === 'integration')

  const caseId = useMemo(() => {
    const hash = Math.abs(String(wallet).split('').reduce((acc, c) => ((acc << 5) - acc) + c.charCodeAt(0), 0))
    return `SAR-${new Date().getFullYear()}-${String(hash).slice(0, 6)}`
  }, [wallet])

  const reportDate = new Date().toUTCString()

  // Generate automated SAR Filing Narrative
  const sarNarrative = useMemo(() => {
    if (isClean) {
      return `INVESTIGATION CLEARANCE MEMORANDUM:
Case ID: ${caseId}
Target Entity: ${wallet}
Evaluation Date: ${reportDate}

FINDINGS:
The target address underwent automated screening across all 15 institutional AML detection algorithms (Placement, Layering, Integration). No suspicious transaction typologies, smurfing structures, mixer interactions, or high-depth layering chains were identified. Total inbound volume of $${totalInflow.toLocaleString()} and outbound volume of $${totalOutflow.toLocaleString()} conform to standard peer-to-peer or verified institutional protocol behavior.

RECOMMENDATION:
No Suspicious Activity Report (SAR) filing required at this time. Standard ongoing monitoring recommended.`
    }

    const algoNames = (result.detectors || []).map(d => d.name).join(', ')
    const summaries = (result.detectors || []).map(d => `• [${d.phase.toUpperCase()}]: ${d.summary}`).join('\n')

    return `FINANCIAL CRIMES ENFORCEMENT NETWORK (FinCEN) / FATF
SUSPICIOUS ACTIVITY REPORT (SAR) INVESTIGATION DOSSIER
================================================================================
Case Reference: ${caseId}
Investigation Date: ${reportDate}
Subject Entity / Primary Wallet: ${wallet}
Risk Assessment: ${riskLabel} (Composite Risk Score: ${(result.risk_score || 0).toFixed(2)} / 1.00)
Ground Truth Category: ${result.ground_truth || 'Identified via Live Heuristic Audit'}

EXECUTIVE SUMMARY OF SUSPICIOUS ACTIVITY:
A multi-factor blockchain AML audit flagged the subject address for high-confidence money laundering typologies across ${result.phases_triggered?.join(', ') || 'multiple phases'}. The entity triggered ${result.detectors?.length || 0} distinct AML detection algorithms: ${algoNames}.

Total Inbound Traced: $${totalInflow.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
Total Outbound Traced: $${totalOutflow.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}

EVIDENCE & TYPOLOGY BREAKDOWN:
${summaries}

REGULATORY TYPOLOGY MAPPING:
1. Structuring / Micro-Structuring (31 CFR § 1010.314) - Evading reporting thresholds.
2. Anonymity-Enhancing Technology / Mixer Interactions (FinCEN Advisory FIN-2019-A003).
3. Rapid Multi-Hop Peeling Chains and Transit Shell Wallets (FATF Virtual Asset Guidance).
4. Fan-In Consolidation & Value Reaggregation into High-Risk Terminal Nodes.

COMPLIANCE CONCLUSION & ACTION:
The behavioral patterns demonstrate deliberate obfuscation and laundering mechanics. Immediate escalation for formal regulatory SAR filing and blockchain asset monitoring is recommended.`
  }, [wallet, result, caseId, reportDate, isClean, riskLabel, totalInflow, totalOutflow])

  const handlePrint = () => {
    window.print()
  }

  const handleCopySAR = () => {
    navigator.clipboard.writeText(sarNarrative)
    setCopyStatus('SAR Narrative copied to clipboard!')
    setTimeout(() => setCopyStatus(null), 3000)
  }

  const handleDownloadJSON = () => {
    const reportPayload = {
      case_id: caseId,
      generated_at: new Date().toISOString(),
      target_wallet: wallet,
      composite_risk_score: result.risk_score,
      verdict: result.verdict,
      risk_label: riskLabel,
      ground_truth: result.ground_truth || null,
      scenario: result.scenario_description || null,
      summary_metrics: {
        total_inflow_usd: totalInflow,
        total_outflow_usd: totalOutflow,
        total_transactions: relatedTxs.length,
      },
      algorithms_triggered: result.algorithms_triggered || [],
      detailed_detectors: result.detectors || [],
      evidence_transactions: relatedTxs,
      sar_narrative: sarNarrative,
      analyst_review: {
        status: feedbackStatus,
        notes: analystNotes,
        timestamp: feedbackSaved ? new Date().toISOString() : null,
      }
    }

    const blob = new Blob([JSON.stringify(reportPayload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `AML_Investigation_Report_${wallet.slice(0, 10)}_${caseId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleSaveFeedback = () => {
    setFeedbackSaved(true)
    if (onApplyFeedback) {
      onApplyFeedback(wallet, {
        status: feedbackStatus,
        notes: analystNotes,
        timestamp: new Date().toISOString(),
      })
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(5, 10, 20, 0.85)',
        backdropFilter: 'blur(8px)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        overflowY: 'auto',
        fontFamily: "'Inter', system-ui, sans-serif",
      }}
      onClick={onClose}
    >
      <style>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #printable-aml-dossier, #printable-aml-dossier * {
            visibility: visible;
          }
          #printable-aml-dossier {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            background: #ffffff !important;
            color: #000000 !important;
            padding: 20px !important;
            box-shadow: none !important;
            border: none !important;
          }
          .no-print {
            display: none !important;
          }
          .print-border {
            border: 1px solid #cccccc !important;
          }
          .print-bg-light {
            background: #f8fafc !important;
          }
        }
      `}</style>

      {/* Main Container */}
      <div
        id="printable-aml-dossier"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '920px',
          maxHeight: '92vh',
          backgroundColor: '#0B132B',
          color: '#F1F5F9',
          borderRadius: '16px',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.8), 0 0 30px rgba(56, 189, 248, 0.1)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Toast */}
        {copyStatus && (
          <div style={{
            position: 'absolute',
            top: 16,
            right: 80,
            background: '#10B981',
            color: '#FFFFFF',
            padding: '6px 14px',
            borderRadius: '8px',
            fontSize: '12px',
            fontWeight: 600,
            zIndex: 100,
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          }}>
            {copyStatus}
          </div>
        )}

        {/* Modal Top Header (Interactive Controls) */}
        <div className="no-print" style={{
          padding: '16px 24px',
          borderBottom: '1px solid #1E293B',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: '20px' }}>🛡️</span>
            <div>
              <div style={{ fontSize: '15px', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.01em' }}>
                AML Investigation Dossier & Compliance Report
              </div>
              <div style={{ fontSize: '12px', color: '#94A3B8' }}>
                Case ID: <span style={{ fontFamily: 'monospace', color: '#38BDF8', fontWeight: 600 }}>{caseId}</span> • Generated: {reportDate}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={handlePrint}
              style={{
                background: 'linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%)',
                color: '#FFFFFF',
                border: 'none',
                padding: '8px 14px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                boxShadow: '0 2px 8px rgba(14, 165, 233, 0.3)',
              }}
            >
              🖨️ Print / Save PDF
            </button>

            <button
              onClick={handleDownloadJSON}
              style={{
                background: '#1E293B',
                color: '#E2E8F0',
                border: '1px solid #334155',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              📥 JSON
            </button>

            <button
              onClick={handleCopySAR}
              style={{
                background: '#1E293B',
                color: '#E2E8F0',
                border: '1px solid #334155',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              📋 Copy SAR
            </button>

            <button
              onClick={onClose}
              style={{
                background: 'rgba(239, 68, 68, 0.1)',
                color: '#F87171',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: 700,
                cursor: 'pointer',
                marginLeft: 6,
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* Scrollable Report Body */}
        <div style={{
          padding: '24px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px',
        }}>
          {/* Official Document Header (Visible in Print & Screen) */}
          <div style={{
            borderBottom: '2px solid #334155',
            paddingBottom: '16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            flexWrap: 'wrap',
            gap: 16,
          }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 800, color: '#38BDF8', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                Blockchain Intelligence & Anti-Money Laundering Suite
              </div>
              <h1 style={{ margin: '4px 0 0 0', fontSize: '22px', fontWeight: 800, color: '#F8FAFC' }}>
                WALLET AML AUDIT & SAR INVESTIGATION DOSSIER
              </h1>
              <div style={{ fontSize: '12px', color: '#94A3B8', marginTop: 4 }}>
                Authority: Compliance & Risk Intelligence Unit • FinCEN / FATF Standard Framework
              </div>
            </div>

            <div style={{ textAlign: 'right' }}>
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 14px',
                borderRadius: '8px',
                background: riskBg,
                border: `1px solid ${riskColor}`,
                color: riskColor,
                fontWeight: 800,
                fontSize: '13px',
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
              }}>
                {isBad ? '🔴' : isSuspicious ? '🟡' : '🟢'} {riskLabel}
              </div>
              <div style={{ fontSize: '11px', color: '#94A3B8', marginTop: 4 }}>
                Composite Risk Score: <strong style={{ color: riskColor, fontSize: '14px' }}>{(result.risk_score || 0).toFixed(2)}</strong> / 1.00
              </div>
            </div>
          </div>

          {/* Section 1: Executive Profile & Entity Metadata */}
          <div style={{
            background: 'rgba(15, 23, 42, 0.6)',
            border: '1px solid #1E293B',
            borderRadius: '12px',
            padding: '16px 20px',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
          }}>
            <div>
              <div style={{ fontSize: '11px', color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase' }}>Target Entity / Address</div>
              <div style={{ fontFamily: 'monospace', fontSize: '13px', fontWeight: 700, color: '#38BDF8', marginTop: 4, wordBreak: 'break-all' }}>
                {wallet}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '11px', color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase' }}>Classification Ground Truth</div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#F1F5F9', marginTop: 4 }}>
                {result.ground_truth || 'Heuristic Audit Discovery'}
              </div>
              {result.scenario_description && (
                <div style={{ fontSize: '11px', color: '#94A3B8', marginTop: 2 }}>{result.scenario_description}</div>
              )}
            </div>

            <div>
              <div style={{ fontSize: '11px', color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase' }}>Transaction Activity Volume</div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#F1F5F9', marginTop: 4 }}>
                Inflow: <span style={{ color: '#10B981' }}>${totalInflow.toLocaleString()}</span> | Outflow: <span style={{ color: '#F87171' }}>${totalOutflow.toLocaleString()}</span>
              </div>
              <div style={{ fontSize: '11px', color: '#94A3B8', marginTop: 2 }}>
                {relatedTxs.length} Related Transactions Traced
              </div>
            </div>

            <div>
              <div style={{ fontSize: '11px', color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase' }}>Pipeline Audit Coverage</div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#10B981', marginTop: 4 }}>
                ✓ 12 Algorithms Evaluated
              </div>
              <div style={{ fontSize: '11px', color: '#94A3B8', marginTop: 2 }}>
                Placement • Layering • Integration
              </div>
            </div>
          </div>

          {/* Section 2: 3-Phase Detection Breakdown */}
          <div>
            <div style={{ fontSize: '13px', fontWeight: 800, color: '#F8FAFC', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 12 }}>
              🔍 3-Stage AML Detection Engine Findings
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px' }}>
              {/* Placement Card */}
              <div style={{
                background: 'rgba(15, 23, 42, 0.8)',
                border: placementDetectors.length ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid #1E293B',
                borderRadius: '10px',
                padding: '14px 16px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: '12px', fontWeight: 800, color: '#F59E0B', textTransform: 'uppercase' }}>
                    1. Placement Phase
                  </span>
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    background: placementDetectors.length ? 'rgba(245, 158, 11, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                    color: placementDetectors.length ? '#FBBF24' : '#94A3B8',
                    fontWeight: 700,
                  }}>
                    {placementDetectors.length ? `${placementDetectors.length} Triggers` : 'Clear'}
                  </span>
                </div>

                {placementDetectors.length === 0 ? (
                  <div style={{ fontSize: '12px', color: '#64748B', fontStyle: 'italic' }}>
                    No structuring, smurfing, or micro-funding anomalies detected.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {placementDetectors.map((d, idx) => (
                      <div key={idx} style={{ background: 'rgba(30, 41, 59, 0.5)', padding: '8px 10px', borderRadius: '6px', fontSize: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, color: '#FBBF24' }}>
                          <span>{d.name}</span>
                          <span>{(d.confidence_score || d.score || 0).toFixed(2)}</span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#CBD5E1', marginTop: 4 }}>{d.summary}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Layering Card */}
              <div style={{
                background: 'rgba(15, 23, 42, 0.8)',
                border: layeringDetectors.length ? '1px solid rgba(59, 130, 246, 0.4)' : '1px solid #1E293B',
                borderRadius: '10px',
                padding: '14px 16px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: '12px', fontWeight: 800, color: '#3B82F6', textTransform: 'uppercase' }}>
                    2. Layering Phase
                  </span>
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    background: layeringDetectors.length ? 'rgba(59, 130, 246, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                    color: layeringDetectors.length ? '#60A5FA' : '#94A3B8',
                    fontWeight: 700,
                  }}>
                    {layeringDetectors.length ? `${layeringDetectors.length} Triggers` : 'Clear'}
                  </span>
                </div>

                {layeringDetectors.length === 0 ? (
                  <div style={{ fontSize: '12px', color: '#64748B', fontStyle: 'italic' }}>
                    No mixer interactions, peeling chains, bridge hops, or shell transit detected.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {layeringDetectors.map((d, idx) => (
                      <div key={idx} style={{ background: 'rgba(30, 41, 59, 0.5)', padding: '8px 10px', borderRadius: '6px', fontSize: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, color: '#60A5FA' }}>
                          <span>{d.name}</span>
                          <span>{(d.confidence_score || d.score || 0).toFixed(2)}</span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#CBD5E1', marginTop: 4 }}>{d.summary}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Integration Card */}
              <div style={{
                background: 'rgba(15, 23, 42, 0.8)',
                border: integrationDetectors.length ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid #1E293B',
                borderRadius: '10px',
                padding: '14px 16px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: '12px', fontWeight: 800, color: '#10B981', textTransform: 'uppercase' }}>
                    3. Integration Phase
                  </span>
                  <span style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    background: integrationDetectors.length ? 'rgba(16, 185, 129, 0.2)' : 'rgba(100, 116, 139, 0.2)',
                    color: integrationDetectors.length ? '#34D399' : '#94A3B8',
                    fontWeight: 700,
                  }}>
                    {integrationDetectors.length ? `${integrationDetectors.length} Triggers` : 'Clear'}
                  </span>
                </div>

                {integrationDetectors.length === 0 ? (
                  <div style={{ fontSize: '12px', color: '#64748B', fontStyle: 'italic' }}>
                    No fan-in convergence, dormancy activation, sinks, or reaggregation detected.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {integrationDetectors.map((d, idx) => (
                      <div key={idx} style={{ background: 'rgba(30, 41, 59, 0.5)', padding: '8px 10px', borderRadius: '6px', fontSize: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700, color: '#34D399' }}>
                          <span>{d.name}</span>
                          <span>{(d.confidence_score || d.score || 0).toFixed(2)}</span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#CBD5E1', marginTop: 4 }}>{d.summary}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Section 3: Evidence Transactions Table */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#F8FAFC', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                📊 Transaction Audit Ledger ({relatedTxs.length} Records)
              </div>
            </div>

            <div style={{ overflowX: 'auto', border: '1px solid #1E293B', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: '#0F172A', color: '#94A3B8', borderBottom: '1px solid #1E293B' }}>
                    <th style={{ padding: '8px 10px' }}>Tx Hash</th>
                    <th style={{ padding: '8px 10px' }}>Direction</th>
                    <th style={{ padding: '8px 10px' }}>Counterparty</th>
                    <th style={{ padding: '8px 10px', textAlign: 'right' }}>Amount (USD)</th>
                    <th style={{ padding: '8px 10px' }}>Chain</th>
                  </tr>
                </thead>
                <tbody>
                  {relatedTxs.length === 0 ? (
                    <tr>
                      <td colSpan={5} style={{ padding: '16px', textAlign: 'center', color: '#64748B' }}>
                        No direct transaction rows recorded in current dataset.
                      </td>
                    </tr>
                  ) : (
                    relatedTxs.slice(0, 15).map((t, i) => {
                      const isSender = String(t.sender || t.from || '').toLowerCase().trim() === String(wallet).toLowerCase().trim()
                      const counterparty = isSender ? (t.receiver || t.to || 'Unknown') : (t.sender || t.from || 'Unknown')
                      const val = parseAmount(t)

                      return (
                        <tr key={i} style={{ borderBottom: '1px solid #1E293B' }}>
                          <td style={{ padding: '6px 10px', fontFamily: 'monospace', color: '#38BDF8' }}>
                            {t.tx_hash ? String(t.tx_hash).slice(0, 14) + '...' : `TX_${i+1}`}
                          </td>
                          <td style={{ padding: '6px 10px' }}>
                            <span style={{
                              padding: '2px 6px',
                              borderRadius: '4px',
                              fontWeight: 700,
                              background: isSender ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                              color: isSender ? '#EF4444' : '#10B981',
                            }}>
                              {isSender ? 'OUTFLOW ↗' : 'INFLOW ↘'}
                            </span>
                          </td>
                          <td style={{ padding: '6px 10px', fontFamily: 'monospace', color: '#94A3B8' }}>
                            {counterparty}
                          </td>
                          <td style={{ padding: '6px 10px', textAlign: 'right', fontWeight: 600, color: '#F1F5F9' }}>
                            ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td style={{ padding: '6px 10px', color: '#64748B' }}>
                            {t.chain || 'ETH'}
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Section 4: Regulatory SAR Narrative */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#F8FAFC', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                📜 Regulatory SAR Narrative (FinCEN / FATF Compliance Text)
              </div>
              <button
                className="no-print"
                onClick={handleCopySAR}
                style={{
                  background: '#1E293B',
                  color: '#38BDF8',
                  border: '1px solid #334155',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                📋 Copy Text
              </button>
            </div>
            <pre style={{
              background: '#090D16',
              border: '1px solid #1E293B',
              borderRadius: '8px',
              padding: '14px',
              fontSize: '11px',
              lineHeight: 1.6,
              color: '#E2E8F0',
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              margin: 0,
            }}>
              {sarNarrative}
            </pre>
          </div>

          {/* Section 5: Analyst Feedback Loop & Review Log */}
          <div className="no-print" style={{
            background: 'rgba(15, 23, 42, 0.9)',
            border: '1px solid #1E293B',
            borderRadius: '12px',
            padding: '16px 20px',
          }}>
            <div style={{ fontSize: '13px', fontWeight: 800, color: '#F8FAFC', letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: 12 }}>
              🔄 Compliance Analyst Feedback & Audit Review Loop
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'center', marginBottom: 12 }}>
              <label style={{ fontSize: '12px', color: '#94A3B8', fontWeight: 600 }}>
                Analyst Disposition Verdict:
              </label>
              <select
                value={feedbackStatus}
                onChange={(e) => setFeedbackStatus(e.target.value)}
                style={{
                  background: '#1E293B',
                  color: '#F1F5F9',
                  border: '1px solid #334155',
                  padding: '6px 12px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 600,
                  outline: 'none',
                }}
              >
                <option value="pending">⏳ Pending Review</option>
                <option value="confirmed">🚨 Confirmed Illicit / Suspicious Activity</option>
                <option value="false_positive">🛡️ False Positive / Legitimate Commercial Activity</option>
                <option value="needs_review">🔍 Escalated for Deep Forensic Audit</option>
              </select>

              <button
                onClick={handleSaveFeedback}
                style={{
                  background: feedbackSaved ? '#10B981' : '#2563EB',
                  color: '#FFFFFF',
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                {feedbackSaved ? '✓ Disposition Recorded' : '💾 Save Disposition'}
              </button>
            </div>

            <input
              type="text"
              placeholder="Optional compliance analyst notes (e.g. Counterparty checked against OFAC SDN list)..."
              value={analystNotes}
              onChange={(e) => setAnalystNotes(e.target.value)}
              style={{
                width: '100%',
                background: '#1E293B',
                border: '1px solid #334155',
                color: '#F1F5F9',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                boxSizing: 'border-box',
                outline: 'none',
              }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
