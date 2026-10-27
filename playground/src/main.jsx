import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Playground, createHttpAdapter, readSolutionSpec, deriveNextSteps } from '@specificity/playground'
import '@specificity/playground/styles.css'
import precord from './precord.json'
import { kpiActual } from './kpiEntry.js'
const spec = readSolutionSpec(precord.files, precord.build)
const http = createHttpAdapter({baseUrl:'/playground'})
// Two sources, each read once. The SDK reads the Precord open items in this bundle (a dismissed item is hidden,
// blocks_rung decides blocking). The served Solution answers /next-steps with the builder gaps and builder
// deviations it wrote, each with a severity. The two sources do not overlap.
const SEVERITY_ORDER = ['BLOCKS RELEASE', 'BLOCKS PRODUCTION', 'BELOW THRESHOLD', 'ENVIRONMENT']
async function nextSteps() {
  const derived = deriveNextSteps({spec})
  const served = await http.nextSteps.list()
  const items = [...served.items, ...derived.items]
  items.sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
  return {items, recommendations: [...served.recommendations, ...derived.recommendations]}
}
const adapter = {...http, solution: async () => spec, nextSteps: {...http.nextSteps, list: nextSteps}}

// A small CSV reader for the KPI board file. Quoted fields may hold commas.
function readCsv(text) {
  const rows = []
  let row = [], cell = '', quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i]
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i += 1 } else if (c === '"') quoted = false; else cell += c
    } else if (c === '"') quoted = true
    else if (c === ',') { row.push(cell); cell = '' }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = '' }
    else if (c !== '\r') cell += c
  }
  if (cell || row.length) { row.push(cell); rows.push(row) }
  const [header, ...body] = rows.filter((r) => r.some(Boolean))
  return body.map((r) => Object.fromEntries(header.map((h, i) => [h.replace(/^﻿/, ''), r[i] ?? ''])))
}

function useJson(url) {
  const [state, setState] = useState({ loading: true, data: null, error: '' })
  useEffect(() => {
    let live = true
    fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${url} answered ${r.status}`))))
      .then((data) => live && setState({ loading: false, data, error: '' }))
      .catch((error) => live && setState({ loading: false, data: null, error: String(error.message || error) }))
    return () => { live = false }
  }, [url])
  return state
}

// C6-1: age of a case in whole hours and minutes, from its creation time.
function age(created, now) {
  const minutes = Math.max(0, Math.floor((now - Date.parse(created)) / 60000))
  return minutes >= 60 ? `${Math.floor(minutes / 60)} h ${minutes % 60} min` : `${minutes} min`
}

// The case list (C6-1). It reads the case table of the Solution database (C1-3).
// Columns: status, step, assignee, age, last action, open checkpoint. The reader can filter, sort and open the history.
const SORTS = {
  case: (c) => c.case_id, status: (c) => c.status || '', step: (c) => c.step || '', assignee: (c) => c.assignee || '',
  created: (c) => c.created_at, changed: (c) => c.updated_at || '',
}
function CaseList() {
  const { loading, data, error } = useJson('/cases')
  const pending = useJson('/playground/reviews/pending')
  const [filter, setFilter] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('created')
  const [open, setOpen] = useState('')
  if (loading) return <p>Reading the cases…</p>
  if (error) return <p role="alert">The case list is not available: {error}</p>
  const cases = data.cases || []
  if (!cases.length) return <p>No case exists yet. A case appears here when it is created.</p>
  const waiting = Object.fromEntries(((pending.data) || []).map((r) => [r.caseId, r.checkpointId]))
  const statuses = [...new Set(cases.map((c) => c.status).filter(Boolean))]
  const shown = cases
    .filter((c) => (!status || c.status === status) && (!filter || JSON.stringify(c).toLowerCase().includes(filter.toLowerCase())))
    .sort((a, b) => String(SORTS[sort](a)).localeCompare(String(SORTS[sort](b))))
  const now = Date.now()
  return (
    <div>
      <p>
        <label>Filter <input aria-label="Filter cases" value={filter} onChange={(e) => setFilter(e.target.value)} /></label>{' '}
        <label>Status <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All</option>{statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>{' '}
        <label>Sort by <select aria-label="Sort cases" value={sort} onChange={(e) => setSort(e.target.value)}>
          {Object.keys(SORTS).map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
      </p>
      <table aria-label="Cases">
        <thead><tr><th>Case</th><th>Status</th><th>Step</th><th>Assignee</th><th>Age</th><th>Last action</th>
          <th>Open checkpoint</th><th>Fields</th><th>Created</th><th>Last change</th><th>History</th></tr></thead>
        <tbody>{shown.map((c) => (
          <tr key={c.case_id}><td>{c.case_id}</td><td>{c.status || 'not set'}</td><td>{c.step || 'not set'}</td>
            <td>{c.assignee || 'unassigned'}</td><td>{age(c.created_at, now)}</td>
            <td>{c.last_action ? `${c.last_action.field} by ${c.last_action.author} (${c.last_action.source})` : 'no action yet'}</td>
            <td>{waiting[c.case_id] || 'none'}</td><td>{c.fields}</td><td>{c.created_at}</td>
            <td>{c.updated_at || 'no change yet'}</td>
            <td><button onClick={() => setOpen(open === c.case_id ? '' : c.case_id)}>{open === c.case_id ? 'Hide' : 'Show'}</button></td></tr>
        ))}</tbody>
      </table>
      {open && <CaseHistory caseId={open} />}
    </div>
  )
}

// The version history of one case: every write of every field, oldest first.
function CaseHistory({ caseId }) {
  const { loading, data, error } = useJson(`/cases/${encodeURIComponent(caseId)}/history`)
  if (loading) return <p>Reading the history…</p>
  if (error) return <p role="alert">The history is not available: {error}</p>
  return (
    <table aria-label={`History of ${caseId}`}>
      <thead><tr><th>Field</th><th>Version</th><th>Value</th><th>Author</th><th>Source</th><th>Written</th></tr></thead>
      <tbody>{(data.history || []).map((h) => (
        <tr key={`${h.field}-${h.version}`}><td>{h.field}</td><td>{h.version}</td><td>{JSON.stringify(h.value)}</td>
          <td>{h.author}</td><td>{h.source}</td><td>{h.written_at}</td></tr>
      ))}</tbody>
    </table>
  )
}

// C6-2: one block for each KPI row, with its declared visualization, actual, benchmark and projected value.
// A v2 Precord gives spec/kpis.csv (with current_value and projected_value) and spec/kpi_views.csv (form and cadence).
// A v1 Precord gives context/kpi_board_definition.csv. A value shows only when the Solution reports one.
// A column the Precord lacks reads "not declared".
function KpiBoard() {
  const v2 = precord.files['spec/kpis.csv'] !== undefined
  const rows = readCsv(precord.files['spec/kpis.csv'] || precord.files['context/kpi_board_definition.csv'] || '')
  const views = {}
  for (const view of readCsv(precord.files['spec/kpi_views.csv'] || '')) {
    for (const id of (view.headline_metrics || '').split(';').map((part) => part.trim()).filter(Boolean)) {
      if (!views[id]) views[id] = view
    }
  }
  const { data } = useJson('/playground/kpis')
  const values = (data && (data.values || data.kpis || data.snapshot)) || {}
  const fidelity = ((data && data.fidelity) || []).join(' · ')
  // BUG-105: the SDK marks a KPI that is owed above the build rung. The board shows that mark and does not hide the KPI.
  const owed = Object.fromEntries(spec.kpiBoard.map((k) => [k.id, k]))
  const later = rows.filter((row) => (owed[row.kpi_id] || {}).aboveRung).length
  const declared = (row, key) => (row[key] === undefined ? 'not declared' : row[key] || 'none')
  return (
    <div>
      {fidelity && <p>Data: {fidelity}</p>}
      {later > 0 && <p>{rows.length - later} of {rows.length} KPIs are owed at {precord.build.rung}. {later} {later === 1 ? 'is' : 'are'} owed at a later rung.</p>}
      {rows.map((row) => {
        const actual = kpiActual(values[row.kpi_id])
        const view = views[row.kpi_id] || {}
        return (
          <section key={row.kpi_id} aria-label={row.name} data-visualization={row.visualization || ''}>
            <h3>{row.name}</h3>
            {row.owed_at && <p>Owed at {row.owed_at}{(owed[row.kpi_id] || {}).aboveRung ? `: not owed at ${precord.build.rung}` : ''}</p>}
            <p>{row.measures}</p>
            {v2 ? <p>Form: {view.form || 'not declared'}, Cadence: {view.cadence || 'not declared'}</p>
              : <p>Visualization: {declared(row, 'visualization')}</p>}
            <p>Actual: <strong>{actual.text}</strong> {actual.unit || row.unit}{actual.status ? ` (${actual.status})` : ''} · {row.grain}</p>
            {v2 ? <p>Current value: {declared(row, 'current_value')}, Projected: {declared(row, 'projected_value')}</p>
              : <p>Benchmark: {declared(row, 'benchmark_value')} · Projected: {declared(row, 'projected_value')}</p>}
            <p>Alert: {v2 ? declared(row, 'alerting') : declared(row, 'alert_condition')}</p>
            <p>Formula: {row.formula}. Source: {v2 ? 'kpis' : 'kpi_board_definition'} row {row.kpi_id}.</p>
          </section>
        )
      })}
    </div>
  )
}

// BUG-105: the sample rows of context/sample_data.csv, each with its origin. A Precord with none says so.
function SampleData() {
  const rows = spec.sampleData || []
  if (!rows.length) return <p>The Precord gives no sample data.</p>
  const columns = [...new Set(rows.flatMap((r) => Object.keys(r.fields)))]
  return (
    <table aria-label="Sample data">
      <thead><tr><th>Sample</th><th>Origin</th><th>Scenario</th><th>Expected outcome</th>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id}><td>{r.id}</td><td>{r.origin || 'not recorded'}</td><td>{r.scenarioId || 'none'}</td>
          <td>{r.expectedOutcome || 'none'}</td>{columns.map((c) => <td key={c}>{r.fields[c] || ''}</td>)}</tr>
      ))}</tbody>
    </table>
  )
}

const TABS = [['', 'Playground'], ['cases', 'Cases'], ['kpis', 'KPIs'], ['sample-data', 'Sample data']]

function App() {
  const [view, setView] = useState(() => (window.location.hash.match(/^#\/(cases|kpis|sample-data)\b/) || [])[1] || '')
  useEffect(() => {
    const on = () => setView((window.location.hash.match(/^#\/(cases|kpis|sample-data)\b/) || [])[1] || '')
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return (
    <div>
      <nav aria-label="Solution screens" style={{ display: 'flex', gap: 12, padding: 8 }}>
        {TABS.map(([key, label]) => (
          <a key={label} href={key ? `#/${key}` : '#/'} aria-current={view === key ? 'page' : undefined}>{label}</a>
        ))}
      </nav>
      {view === 'cases' ? <main><h2>Cases</h2><CaseList /></main>
        : view === 'sample-data' ? <main><h2>Sample data</h2><SampleData /></main>
        : view === 'kpis' ? <main><h2>KPIs</h2><KpiBoard /></main>
        : <Playground adapter={adapter} routing="hash" />}
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App />)
