// BUG-131: one entry of the /playground/kpis payload. The C8 service gives {value, unit, status, source_ref, ...}.
// A KPI with no value, or with status "unmeasured", shows "No data yet". The text is never JSON of the entry.
export function kpiActual(entry) {
  if (entry === undefined || entry === null) return { text: 'No data yet', unit: '', status: '' }
  if (typeof entry !== 'object') return { text: String(entry), unit: '', status: '' }
  const unit = entry.unit || ''
  const status = entry.status || ''
  const none = entry.value === undefined || entry.value === null || status === 'unmeasured'
  return { text: none ? 'No data yet' : String(entry.value), unit, status }
}
