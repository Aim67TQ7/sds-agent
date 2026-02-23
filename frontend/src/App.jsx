import React, { useState, useEffect, useRef } from 'react'

const API = ''
const getHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem('sds_token')}` })
const jsonHeaders = () => ({ ...getHeaders(), 'Content-Type': 'application/json' })

// ============================================================
// LOGIN
// ============================================================
function LoginPage({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Login failed')
      localStorage.setItem('sds_token', data.token)
      onLogin(data)
    } catch (err) { setError(err.message) }
    setLoading(false)
  }

  return (
    <div className="login-container">
      <form className="login-box" onSubmit={handleLogin}>
        <h1>SDS Agent</h1>
        <p>Safety Data Sheet Management</p>
        {error && <div className="error-msg">{error}</div>}
        <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required />
        <button className="btn btn-primary" style={{ width: '100%' }} disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}

// ============================================================
// DASHBOARD
// ============================================================
function Dashboard() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch(`${API}/sds/dashboard`, { headers: getHeaders() })
      .then(r => r.json()).then(setData).catch(console.error)
  }, [])

  if (!data) return <div>Loading dashboard...</div>

  const ss = data.status_summary || {}
  const total = data.chemical_count || 0
  const current = ss.current || 0
  const rate = total > 0 ? ((current / total) * 100).toFixed(1) : 'N/A'

  return (
    <div>
      <h1>Dashboard</h1>
      <div className="stats-grid">
        <div className="stat-card"><div className="value">{total}</div><div className="label">Total Chemicals</div></div>
        <div className="stat-card"><div className="value">{rate}%</div><div className="label">SDS Compliance</div></div>
        <div className="stat-card"><div className="value">{ss.expired || 0}</div><div className="label">Expired SDS</div></div>
        <div className="stat-card"><div className="value">{ss.missing_sds || 0}</div><div className="label">Missing SDS</div></div>
        <div className="stat-card"><div className="value">{data.labels_generated || 0}</div><div className="label">Labels Generated</div></div>
        <div className="stat-card"><div className="value">{data.labels_printed || 0}</div><div className="label">Labels Printed</div></div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 12 }}>Storage Class Breakdown</h3>
        {Object.entries(data.hazard_summary || {}).map(([cls, count]) => (
          <div key={cls} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
            <span>{cls.replace(/_/g, ' ')}</span><span style={{ color: 'var(--accent)' }}>{count}</span>
          </div>
        ))}
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 12 }}>Recent Activity</h3>
        {(data.recent_events || []).map((ev, i) => (
          <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
            <span className={`badge ${ev.type === 'sds_uploaded' ? 'badge-current' : ev.type === 'label_printed' ? 'badge-warning' : 'badge-current'}`}>
              {ev.type.replace(/_/g, ' ')}
            </span>
            <span style={{ marginLeft: 8 }}>{ev.chemical || ''}</span>
            <span style={{ float: 'right', color: 'var(--text-secondary)', fontSize: 11 }}>
              {new Date(ev.timestamp).toLocaleString()}
            </span>
          </div>
        ))}
        {(data.recent_events || []).length === 0 && <p style={{ color: 'var(--text-secondary)' }}>No activity yet.</p>}
      </div>
    </div>
  )
}

// ============================================================
// UPLOAD SDS
// ============================================================
function UploadPage() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [dragging, setDragging] = useState(false)

  const handleUpload = async () => {
    if (!file) return
    setLoading(true); setResult(null)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch(`${API}/sds/upload`, { method: 'POST', headers: getHeaders(), body: form })
      setResult(await res.json())
    } catch (err) { setResult({ status: 'error', message: err.message }) }
    setLoading(false)
  }

  const handleDrop = (e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]) }

  return (
    <div>
      <h1>Upload SDS</h1>
      <div className={`upload-zone ${dragging ? 'dragging' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById('sds-file').click()}>
        <input id="sds-file" type="file" accept=".pdf,.jpg,.png" style={{ display: 'none' }} onChange={e => setFile(e.target.files[0])} />
        {file ? <p>{file.name} ({(file.size / 1024).toFixed(0)} KB)</p> : <p>Drop SDS PDF here or click to browse</p>}
      </div>
      <button className="btn btn-primary" onClick={handleUpload} disabled={!file || loading}>
        {loading ? 'Processing with AI...' : 'Upload & Extract'}
      </button>

      {result && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ color: result.status === 'success' ? 'var(--success)' : 'var(--danger)', marginBottom: 8 }}>
            {result.status === 'success' ? 'Extraction Complete' : 'Error'}
          </h3>
          <p>{result.message}</p>
          {result.data && (
            <div style={{ marginTop: 12 }}>
              <table>
                <tbody>
                  <tr><td style={{ color: 'var(--text-secondary)' }}>Product</td><td>{result.data.product_name}</td></tr>
                  <tr><td style={{ color: 'var(--text-secondary)' }}>CAS#</td><td>{result.data.cas_number || 'N/A'}</td></tr>
                  <tr><td style={{ color: 'var(--text-secondary)' }}>Signal Word</td><td>
                    <span className={`badge ${result.data.signal_word === 'Danger' ? 'badge-danger' : 'badge-warning'}`}>
                      {result.data.signal_word || 'None'}
                    </span>
                  </td></tr>
                  <tr><td style={{ color: 'var(--text-secondary)' }}>Manufacturer</td><td>{result.data.manufacturer}</td></tr>
                  <tr><td style={{ color: 'var(--text-secondary)' }}>Revision Date</td><td>{result.data.revision_date || 'N/A'}</td></tr>
                  <tr><td style={{ color: 'var(--text-secondary)' }}>Pictograms</td><td>{(result.data.pictogram_codes || []).join(', ') || 'None'}</td></tr>
                  <tr><td style={{ color: 'var(--text-secondary)' }}>Sections Extracted</td><td>{Object.keys(result.data.sections || {}).length}/16</td></tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// Q&A
// ============================================================
function QuestionPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEnd = useRef(null)

  useEffect(() => { messagesEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const ask = async (e) => {
    e.preventDefault()
    if (!input.trim() || loading) return
    const q = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: q }])
    setLoading(true)
    try {
      const res = await fetch(`${API}/sds/question`, {
        method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ question: q }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'agent', text: data.answer || data.message }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'agent', text: `Error: ${err.message}` }])
    }
    setLoading(false)
  }

  return (
    <div>
      <h1>Safety Q&A</h1>
      <div className="chat-container">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--text-secondary)', marginTop: 40 }}>
              <p>Ask about chemicals, PPE, storage, compliance, emergency procedures...</p>
              <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
                {['What PPE for acetone?', "What's our SDS compliance rate?", 'Which chemicals expire this quarter?', 'Spill procedure for sulfuric acid'].map(q => (
                  <button key={q} className="btn btn-secondary" style={{ fontSize: 12 }}
                    onClick={() => { setInput(q) }}>{q}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`chat-message ${m.role}`}>
              <div style={{ whiteSpace: 'pre-wrap' }}>{m.text}</div>
            </div>
          ))}
          {loading && <div className="chat-message agent" style={{ opacity: 0.6 }}>Thinking...</div>}
          <div ref={messagesEnd} />
        </div>
        <form className="chat-input" onSubmit={ask}>
          <input value={input} onChange={e => setInput(e.target.value)} placeholder="Ask a safety question..." disabled={loading} />
          <button className="btn btn-primary" disabled={loading}>Send</button>
        </form>
      </div>
    </div>
  )
}

// ============================================================
// CHEMICALS
// ============================================================
function ChemicalsPage() {
  const [chemicals, setChemicals] = useState([])
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ chemical_name: '', cas_number: '', manufacturer: '', storage_class: 'general_storage', location: '', critical: false })

  const load = () => fetch(`${API}/sds/chemicals`, { headers: getHeaders() })
    .then(r => r.json()).then(d => setChemicals(d.chemicals || [])).catch(console.error)

  useEffect(() => { load() }, [])

  const addChemical = async (e) => {
    e.preventDefault()
    await fetch(`${API}/sds/chemicals`, { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(form) })
    setShowAdd(false)
    setForm({ chemical_name: '', cas_number: '', manufacturer: '', storage_class: 'general_storage', location: '', critical: false })
    load()
  }

  const statusBadge = (s) => {
    const cls = s === 'current' ? 'badge-current' : s === 'expired' ? 'badge-expired' : s === 'expiring_soon' ? 'badge-expiring' : 'badge-missing'
    return <span className={`badge ${cls}`}>{(s || 'unknown').replace(/_/g, ' ')}</span>
  }

  return (
    <div>
      <h1>Chemical Registry</h1>
      <div style={{ marginBottom: 16 }}>
        <button className="btn btn-primary" onClick={() => setShowAdd(!showAdd)}>
          {showAdd ? 'Cancel' : '+ Add Chemical'}
        </button>
      </div>

      {showAdd && (
        <form className="card" onSubmit={addChemical}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
            <input placeholder="Chemical Name *" value={form.chemical_name} onChange={e => setForm({ ...form, chemical_name: e.target.value })} required />
            <input placeholder="CAS Number" value={form.cas_number} onChange={e => setForm({ ...form, cas_number: e.target.value })} />
            <input placeholder="Manufacturer" value={form.manufacturer} onChange={e => setForm({ ...form, manufacturer: e.target.value })} />
            <select value={form.storage_class} onChange={e => setForm({ ...form, storage_class: e.target.value })}>
              <option value="general_storage">General Storage</option>
              <option value="flammable_cabinet">Flammable Cabinet</option>
              <option value="corrosive_cabinet">Corrosive Cabinet</option>
              <option value="oxidizer_cabinet">Oxidizer Cabinet</option>
              <option value="refrigerated">Refrigerated</option>
              <option value="ventilated">Ventilated</option>
            </select>
            <input placeholder="Location" value={form.location} onChange={e => setForm({ ...form, location: e.target.value })} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 0' }}>
              <input type="checkbox" checked={form.critical} onChange={e => setForm({ ...form, critical: e.target.checked })} /> High Hazard
            </label>
          </div>
          <button className="btn btn-primary" type="submit">Add Chemical</button>
        </form>
      )}

      <div className="card" style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr><th>Chemical</th><th>CAS#</th><th>Signal</th><th>Storage</th><th>Location</th><th>SDS Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {chemicals.map(c => (
              <tr key={c.id}>
                <td><strong>{c.chemical_name}</strong>{c.critical && <span className="badge badge-danger" style={{ marginLeft: 6 }}>HIGH</span>}</td>
                <td>{c.cas_number || '—'}</td>
                <td>{c.signal_word ? <span className={`badge ${c.signal_word === 'Danger' ? 'badge-danger' : 'badge-warning'}`}>{c.signal_word}</span> : '—'}</td>
                <td style={{ fontSize: 12 }}>{(c.storage_class || '').replace(/_/g, ' ')}</td>
                <td>{c.location || '—'}</td>
                <td>{statusBadge(c.status)}</td>
                <td>
                  <button className="btn btn-secondary" style={{ fontSize: 11, padding: '4px 8px' }}
                    onClick={() => window.open(`${API}/sds/emergency/${c.id}`)}>Emergency</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {chemicals.length === 0 && <p style={{ padding: 20, textAlign: 'center', color: 'var(--text-secondary)' }}>No chemicals registered. Upload an SDS or add manually.</p>}
      </div>
    </div>
  )
}

// ============================================================
// LABELS
// ============================================================
function LabelsPage() {
  const [chemicals, setChemicals] = useState([])
  const [selected, setSelected] = useState('')
  const [labelType, setLabelType] = useState('ghs_primary')
  const [quantity, setQuantity] = useState(2)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [printing, setPrinting] = useState(false)

  useEffect(() => {
    fetch(`${API}/sds/chemicals`, { headers: getHeaders() })
      .then(r => r.json()).then(d => setChemicals((d.chemicals || []).filter(c => c.has_sds)))
  }, [])

  const generate = async () => {
    if (!selected) return
    setLoading(true); setResult(null)
    try {
      const res = await fetch(`${API}/sds/label`, {
        method: 'POST', headers: jsonHeaders(),
        body: JSON.stringify({ chemical_id: selected, label_type: labelType, label_size: labelType === 'ghs_primary' ? '4x6' : '2x1', quantity }),
      })
      setResult(await res.json())
    } catch (err) { setResult({ status: 'error', message: err.message }) }
    setLoading(false)
  }

  const printLabel = async () => {
    if (!selected) return
    setPrinting(true)
    try {
      const res = await fetch(`${API}/sds/print`, {
        method: 'POST', headers: jsonHeaders(),
        body: JSON.stringify({ chemical_id: selected, label_type: labelType, quantity }),
      })
      const data = await res.json()
      alert(data.message || 'Print sent')
    } catch (err) { alert(err.message) }
    setPrinting(false)
  }

  return (
    <div>
      <h1>GHS Labels</h1>
      <div className="card">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Chemical</label>
            <select value={selected} onChange={e => setSelected(e.target.value)}>
              <option value="">Select chemical...</option>
              {chemicals.map(c => <option key={c.id} value={c.id}>{c.chemical_name} ({c.cas_number || 'no CAS'})</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Label Type</label>
            <select value={labelType} onChange={e => setLabelType(e.target.value)}>
              <option value="ghs_primary">GHS Primary (4×6)</option>
              <option value="secondary">Secondary Container (2×1)</option>
              <option value="pipe_marker">Pipe Marker</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Quantity</label>
            <input type="number" min="1" max="100" value={quantity} onChange={e => setQuantity(parseInt(e.target.value) || 1)} />
          </div>
        </div>
        <button className="btn btn-primary" onClick={generate} disabled={!selected || loading}>
          {loading ? 'Generating...' : 'Generate Label'}
        </button>
        {result && result.zpl && (
          <button className="btn btn-secondary" onClick={printLabel} disabled={printing} style={{ marginLeft: 8 }}>
            {printing ? 'Sending...' : 'Print to Zebra'}
          </button>
        )}
      </div>

      {result && result.label_data && (
        <div className="card">
          <h3 style={{ marginBottom: 12 }}>Label Preview</h3>
          <div className="label-preview">
            <div style={{ fontSize: 24, fontWeight: 'bold' }}>{result.label_data.product_name}</div>
            {result.label_data.signal_word && (
              <div className={result.label_data.signal_word === 'Danger' ? 'signal-danger' : 'signal-warning'}>
                {result.label_data.signal_word}
              </div>
            )}
            <div className="pictogram-row">
              {(result.label_data.pictogram_codes || []).map(p => (
                <div key={p} className="pictogram"><span style={{ transform: 'rotate(-45deg)', fontSize: 9 }}>{p}</span></div>
              ))}
            </div>
            <div style={{ marginTop: 8 }}>
              <strong>Hazard Statements:</strong>
              <ul style={{ marginLeft: 20, fontSize: 12 }}>
                {(result.label_data.hazard_statements || []).map((h, i) => <li key={i}>{h}</li>)}
              </ul>
            </div>
            <div style={{ marginTop: 8 }}>
              <strong>Precautionary Statements:</strong>
              <ul style={{ marginLeft: 20, fontSize: 12 }}>
                {(result.label_data.precautionary_statements || []).map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
            <div style={{ marginTop: 12, fontSize: 11, color: '#666' }}>
              CAS: {result.label_data.cas_number || 'N/A'} | {result.label_data.manufacturer} | Generated: {result.label_data.generated_at?.split('T')[0]}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================
// COMPATIBILITY
// ============================================================
function CompatibilityPage() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch(`${API}/sds/compatibility`, { headers: getHeaders() })
      .then(r => r.json()).then(setData).catch(console.error)
  }, [])

  if (!data) return <div>Loading compatibility check...</div>

  return (
    <div>
      <h1>Storage Compatibility</h1>

      {(data.warnings || []).length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ color: 'var(--danger)', marginBottom: 8 }}>Warnings</h3>
          {data.warnings.map((w, i) => (
            <div key={i} className="compat-warning">
              <strong>{w.location}:</strong> {w.warning}
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                Chemicals: {w.chemicals.join(', ')}
              </div>
            </div>
          ))}
        </div>
      )}

      {Object.entries(data.locations || {}).map(([loc, chems]) => (
        <div key={loc} className="card">
          <h3 style={{ marginBottom: 8 }}>{loc} <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>({chems.length} chemicals)</span></h3>
          <table>
            <thead><tr><th>Chemical</th><th>Storage Class</th><th>Signal Word</th></tr></thead>
            <tbody>
              {chems.map(c => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{(c.storage_class || '').replace(/_/g, ' ')}</td>
                  <td>{c.signal_word ? <span className={`badge ${c.signal_word === 'Danger' ? 'badge-danger' : 'badge-warning'}`}>{c.signal_word}</span> : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {Object.keys(data.locations || {}).length === 0 && (
        <div className="card"><p style={{ color: 'var(--text-secondary)' }}>No chemicals with assigned locations yet.</p></div>
      )}
    </div>
  )
}

// ============================================================
// EVIDENCE DOWNLOAD
// ============================================================
function DownloadPage() {
  const [evidenceType, setEvidenceType] = useState('all')
  const [loading, setLoading] = useState(false)
  const [textResult, setTextResult] = useState(null)

  const download = async (format) => {
    setLoading(true); setTextResult(null)
    try {
      const res = await fetch(`${API}/sds/download`, {
        method: 'POST', headers: jsonHeaders(),
        body: JSON.stringify({ evidence_type: evidenceType, format }),
      })
      if (format === 'pdf') {
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url
        a.download = `sds_evidence_${evidenceType}_${new Date().toISOString().split('T')[0]}.pdf`
        a.click(); URL.revokeObjectURL(url)
      } else {
        setTextResult(await res.json())
      }
    } catch (err) { setTextResult({ status: 'error', message: err.message }) }
    setLoading(false)
  }

  return (
    <div>
      <h1>Audit Evidence</h1>
      <div className="card">
        <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Evidence Type</label>
        <select value={evidenceType} onChange={e => setEvidenceType(e.target.value)}>
          <option value="all">All Chemicals</option>
          <option value="current">Current SDS Only</option>
          <option value="expired">Expired SDS</option>
          <option value="missing">Missing SDS</option>
        </select>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={() => download('pdf')} disabled={loading}>
            {loading ? 'Generating...' : 'Download PDF'}
          </button>
          <button className="btn btn-secondary" onClick={() => download('text')} disabled={loading}>
            View Summary
          </button>
        </div>
      </div>

      {textResult && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={{ marginBottom: 8 }}>AI Summary</h3>
          <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6 }}>{textResult.package_description || textResult.message}</div>
          {textResult.record_count !== undefined && (
            <p style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: 12 }}>
              {textResult.record_count} records | Generated {textResult.generated_at}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// APP
// ============================================================
export default function App() {
  const [user, setUser] = useState(null)
  const [page, setPage] = useState('dashboard')

  useEffect(() => {
    const token = localStorage.getItem('sds_token')
    if (token) setUser({ token })
  }, [])

  if (!user) return <LoginPage onLogin={(data) => setUser(data)} />

  const logout = () => { localStorage.removeItem('sds_token'); setUser(null) }

  const pages = {
    dashboard: Dashboard,
    upload: UploadPage,
    question: QuestionPage,
    chemicals: ChemicalsPage,
    labels: LabelsPage,
    compatibility: CompatibilityPage,
    download: DownloadPage,
  }

  const Page = pages[page] || Dashboard

  return (
    <div className="app-layout">
      <nav className="sidebar">
        <h2>SDS Agent</h2>
        {[
          ['dashboard', 'Dashboard'],
          ['upload', 'Upload SDS'],
          ['question', 'Safety Q&A'],
          ['chemicals', 'Chemicals'],
          ['labels', 'GHS Labels'],
          ['compatibility', 'Compatibility'],
          ['download', 'Audit Evidence'],
        ].map(([key, label]) => (
          <button key={key} className={page === key ? 'active' : ''} onClick={() => setPage(key)}>
            {label}
          </button>
        ))}
        <button className="logout" onClick={logout}>Sign Out</button>
      </nav>
      <main className="main-content">
        <Page />
      </main>
    </div>
  )
}
