import { useState, useCallback, useMemo } from 'react'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function scoreClass(s) {
  if (s >= 80) return 'high'
  if (s >= 50) return 'mid'
  return 'low'
}

function basename(path) {
  return path ? path.split('/').pop() : '—'
}

function riskyClass(r) {
  if (!r) return ''
  const u = r.toUpperCase()
  if (u === 'HIGH') return 'risk-HIGH'
  if (u === 'MEDIUM') return 'risk-MEDIUM'
  return 'risk-LOW'
}

/** Minimal Python syntax highlighting via regex → HTML string. */
function highlightPython(code) {
  if (!code) return ''
  const kwds = [
    'def', 'return', 'assert', 'import', 'from', 'if', 'else', 'elif',
    'for', 'while', 'with', 'class', 'in', 'not', 'and', 'or',
    'True', 'False', 'None', 'pass', 'raise', 'try', 'except',
  ]
  let s = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  s = s.replace(/(#[^\n]*)/g, '<span class="cm">$1</span>')
  s = s.replace(
    /("""[\s\S]*?"""|'''[\s\S]*?'''|"[^"]*"|'[^']*')/g,
    '<span class="st">$1</span>',
  )
  kwds.forEach(k => {
    s = s.replace(new RegExp(`\\b(${k})\\b`, 'g'), '<span class="kw">$1</span>')
  })
  s = s.replace(/\b(\d+\.?\d*)\b/g, '<span class="nu">$1</span>')
  s = s.replace(
    /(<span class="kw">def<\/span>)\s+(\w+)/g,
    '$1 <span class="fn">$2</span>',
  )
  return s
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LogoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="#fff"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" />
      <line x1="12" y1="9" x2="12" y2="15" />
      <line x1="9" y1="12" x2="15" y2="12" />
    </svg>
  )
}

function ConceptStrip() {
  return (
    <div className="concept-strip">
      <div className="concept-step">
        <span className="cs-label">Normal testing</span>
        <span className="cs-value green">✓ All tests pass</span>
      </div>
      <span className="concept-arrow">→</span>
      <div className="concept-step">
        <span className="cs-label">TestPilot introduces</span>
        <span className="cs-value red">⚠ One mutation survived</span>
      </div>
      <span className="concept-arrow">→</span>
      <div className="concept-step">
        <span className="cs-label">Gap identified</span>
        <span className="cs-value blue">⊙ Missing behavior found</span>
      </div>
      <span className="concept-arrow">→</span>
      <div className="concept-step">
        <span className="cs-label">Fix suggested</span>
        <span className="cs-value purple">✎ Here&apos;s the test to write</span>
      </div>
    </div>
  )
}

function MetricsGrid({ data }) {
  const sc = scoreClass(data.mutation_score)
  const pct = data.mutation_score.toFixed(1)
  return (
    <div className="metrics-grid">
      <div className="metric-card">
        <div className="mc-label">Mutation Score</div>
        <div className={`mc-value score-${sc}`}>{pct}%</div>
        <div className="score-bar-wrap">
          <div
            className={`score-bar-fill ${sc}`}
            style={{ width: `${Math.min(data.mutation_score, 100)}%` }}
          />
        </div>
        <div className="mc-sub">
          {sc === 'high'
            ? 'Strong test coverage'
            : sc === 'mid'
            ? 'Coverage needs improvement'
            : 'Significant gaps detected'}
        </div>
      </div>
      <div className="metric-card">
        <div className="mc-label">Total Mutations</div>
        <div className="mc-value count-total">{data.total}</div>
        <div className="mc-sub">Code mutations generated</div>
      </div>
      <div className="metric-card">
        <div className="mc-label">Killed</div>
        <div className="mc-value count-killed">{data.killed}</div>
        <div className="mc-sub">Caught by your tests</div>
      </div>
      <div className="metric-card">
        <div className="mc-label">Survived</div>
        <div className="mc-value count-survived">{data.survived}</div>
        <div className="mc-sub">
          {data.survived === 0 ? 'No gaps found' : 'Behavioral gaps detected'}
        </div>
      </div>
    </div>
  )
}

function MutationTable({ mutations, selectedId, onSelect }) {
  if (mutations.length === 0) {
    return (
      <div className="empty-state">
        <div className="es-icon">🔬</div>
        <h3>No mutations generated</h3>
        <p>TestPilot found no mutable operators in the source file.</p>
      </div>
    )
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Operator</th>
            <th>File</th>
            <th>Line</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {mutations.map(m => (
            <tr
              key={m.id}
              className={selectedId === m.id ? 'selected-row' : ''}
              onClick={() => onSelect(m.id === selectedId ? null : m.id)}
            >
              <td>{m.id}</td>
              <td><span className="op-tag">{m.operator}</span></td>
              <td>
                <span className="file-cell" title={m.source_file}>
                  {basename(m.source_file)}
                </span>
              </td>
              <td><span className="line-cell">{m.line_number}</span></td>
              <td>
                <span className={`badge ${m.status === 'KILLED' ? 'badge-killed' : 'badge-survived'}`}>
                  {m.status === 'KILLED' ? '✓ Killed' : '⚠ Survived'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function InsightPanel({ mutation }) {
  if (!mutation) {
    return (
      <div className="empty-state">
        <div className="es-icon">↑</div>
        <h3>Select a mutation above</h3>
        <p>Click a survived mutation row to see the AI analysis and suggested fix.</p>
      </div>
    )
  }

  if (mutation.status === 'KILLED') {
    return (
      <div className="empty-state">
        <div className="es-icon">✓</div>
        <h3>Mutation killed</h3>
        <p>Your existing tests caught this mutation. No action needed.</p>
      </div>
    )
  }

  const ai = mutation.ai_insight

  if (!ai) {
    return (
      <div className="empty-state">
        <div className="es-icon">⏳</div>
        <h3>No AI insight available</h3>
        <p>This mutation survived but no AI analysis was returned.</p>
      </div>
    )
  }

  return (
    <div className="insight-panel">
      <div className="insight-header">
        <span className="ih-icon">🤖</span>
        <div className="ih-meta">
          <div className="ih-title">AI Insight — Behavioral Gap Detected</div>
          <div className="ih-sub">
            Mutation #{mutation.id} survived all tests · Line {mutation.line_number}
          </div>
        </div>
        <span className={`risk-pill ${riskyClass(ai.risk)}`}>
          {ai.risk || 'UNKNOWN'}
        </span>
      </div>
      <div className="insight-body">
        <div className="insight-section">
          <div className="is-label">Code change</div>
          <div className="diff-pair">
            <div className="diff-line diff-original">
              <span className="diff-prefix">−</span>
              {mutation.original_line.trim()}
            </div>
            <div className="diff-line diff-mutated">
              <span className="diff-prefix">+</span>
              {mutation.mutated_line.trim()}
            </div>
          </div>
        </div>

        <div className="insight-section">
          <div className="is-label">Why it survived</div>
          <div className="is-text">{ai.explanation}</div>
        </div>

        <div className="insight-section">
          <div className="is-label">Missing behavior</div>
          <div className="is-text">{ai.missing_behavior}</div>
        </div>

        <div className="insight-section">
          <div className="is-label">Suggested test</div>
          <div style={{ marginBottom: '10px' }}>
            <span className="test-name-tag">
              <span>⚑</span>
              {ai.suggested_test_name}
            </span>
          </div>
          <div
            className="code-block"
            dangerouslySetInnerHTML={{ __html: highlightPython(ai.suggested_test) }}
          />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Demo project options
// ---------------------------------------------------------------------------
const DEMO_PROJECTS = [
  { label: 'Calculator',    value: 'demo_projects/calculator' },
  { label: 'Bank Account',  value: 'demo_projects/bank_account' },
  { label: 'Score Checker', value: 'demo_projects/score_checker' },
]

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
export default function App() {
  const [selectedProject, setSelectedProject] = useState('demo_projects/calculator')
  const [status, setStatus]     = useState('idle')   // idle | loading | success | error
  const [result, setResult]     = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  const selectedMutation = useMemo(() => {
    if (!result || selectedId === null) return null
    return result.mutations.find(m => m.id === selectedId) || null
  }, [result, selectedId])

  const handleAnalyze = useCallback(async () => {
    setStatus('loading')
    setResult(null)
    setErrorMsg('')
    setSelectedId(null)
    try {
      const resp = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_dir: selectedProject }),
      })
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`
        try { const j = await resp.json(); detail = j.detail || detail } catch {}
        setErrorMsg(detail)
        setStatus('error')
        return
      }
      const data = await resp.json()
      setResult(data)
      setStatus('success')
      const first = data.mutations.find(m => m.status === 'SURVIVED' && m.ai_insight)
      if (first) setSelectedId(first.id)
    } catch (err) {
      setErrorMsg('Could not reach the server. Make sure the TestPilot backend is running on port 8000.')
      setStatus('error')
    }
  }, [selectedProject])

  return (
    <div className="shell">
      {/* ── Header */}
      <header className="header">
        <div className="logo-mark"><LogoIcon /></div>
        <div className="header-text">
          <h1>TestPilot</h1>
          <p>Your tests are green. But are they actually good?</p>
        </div>
        <span className="header-badge">Mutation Testing · AI Insights</span>
      </header>

      {/* ── Concept strip */}
      <ConceptStrip />

      {/* ── Project selector */}
      <div className="card">
        <div className="card-title">Project</div>
        <div className="project-row">
          <div className="field">
            <label htmlFor="proj-select">Demo project</label>
            <select
              id="proj-select"
              value={selectedProject}
              onChange={e => setSelectedProject(e.target.value)}
            >
              {DEMO_PROJECTS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="proj-path">Path</label>
            <input
              id="proj-path"
              value={selectedProject}
              onChange={e => setSelectedProject(e.target.value)}
              placeholder="demo_projects/..."
              spellCheck={false}
            />
          </div>
          <button
            className="btn btn-primary"
            onClick={handleAnalyze}
            disabled={status === 'loading'}
          >
            {status === 'loading'
              ? <><span className="spinner" /> Analyzing…</>
              : <>▶ Run Analysis</>}
          </button>
        </div>
      </div>

      {/* ── Loading */}
      {status === 'loading' && (
        <div className="card">
          <div className="loading-block">
            <div className="big-spinner" />
            <p>Running mutation pipeline…</p>
            <small>Generating mutations · Running pytest · Consulting AI advisor</small>
          </div>
        </div>
      )}

      {/* ── Error */}
      {status === 'error' && (
        <div className="card">
          <div className="error-block">
            <span className="err-icon">✕</span>
            <div>
              <strong>Analysis failed</strong>
              <br />
              {errorMsg}
            </div>
          </div>
        </div>
      )}

      {/* ── Results */}
      {status === 'success' && result && (
        <>
          <div className="card">
            <div className="card-title">Summary</div>
            <MetricsGrid data={result} />
          </div>

          <div className="card">
            <div className="card-title">
              Mutations ({result.total}) — click a row to inspect
            </div>
            <MutationTable
              mutations={result.mutations}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>

          <div className="card">
            <div className="card-title">AI Analysis</div>
            <InsightPanel mutation={selectedMutation} />
          </div>
        </>
      )}

      {/* ── Idle state */}
      {status === 'idle' && (
        <div className="empty-state" style={{ padding: '64px 0' }}>
          <div className="es-icon">🧬</div>
          <h3>Ready to analyze</h3>
          <p>Select a project and click Run Analysis to start mutation testing.</p>
        </div>
      )}

      {/* ── Footer */}
      <div className="page-footer">TestPilot · AI-powered mutation testing</div>
    </div>
  )
}
