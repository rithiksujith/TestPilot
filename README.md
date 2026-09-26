# TestPilot

> **Your tests are green. But are they actually good?**

TestPilot is a mutation-testing pipeline that automatically finds behavioural gaps in Python test suites and explains exactly what tests are missing — and why.

---

## The Problem

A green test suite is not the same as a good test suite. Tests can pass while completely missing critical boundary conditions. Coverage tools tell you *which lines* were executed — not whether those lines are actually *verified*. A function whose condition quietly changes from `>=` to `>` may never be caught, yet every test still passes.

---

## How TestPilot Works

TestPilot applies **mutation testing** to expose these gaps:

1. **Mutate** — the engine rewrites a small piece of production code (e.g. changes `>=` to `>`)
2. **Run** — pytest is executed against the mutated code in an isolated temporary copy
3. **Classify** — if all tests still pass, the mutation **survived** (a gap exists); if any test fails, the mutation is **killed** (the suite caught it)
4. **Analyse** — every surviving mutation is passed to the AI advisor, which identifies the missing boundary condition, explains the risk, and generates a ready-to-run pytest test

### Concrete Example

`demo_projects/calculator/calculator.py` contains:

```python
def calculate_discount(total: float) -> float:
    if total >= 100:          # <-- boundary condition
        return total * 0.9
    return total
```

The test suite covers values clearly below 100 (50, 99) and clearly above 100 (150, 200) — but never the exact boundary value `100`.

TestPilot mutates `>=` → `>`. The mutated code compiles and all tests still pass. The mutation **survives**. TestPilot then reports:

- **Explanation:** the operator change means an order of exactly 100 no longer qualifies for the discount
- **Missing behaviour:** `calculate_discount(100)` is never asserted
- **Suggested test:** a concrete `test_discount_applied_at_exact_threshold` function, ready to copy-paste

---

## Supported Mutation Operators

| Operator | Meaning |
|---|---|
| `>=` → `>` | GreaterThanOrEqual → GreaterThan |
| `>` → `>=` | GreaterThan → GreaterThanOrEqual |
| `==` → `!=` | Equal → NotEqual |
| `!=` → `==` | NotEqual → Equal |
| `+` → `-` | Add → Subtract |

Operators are detected using Python's `tokenize` module so strings and comments are **never** mutated.

---

## Mutation Score

```
mutation score = (killed mutations / total mutations) × 100
```

A score of **100 %** means the test suite caught every injected fault. A lower score reveals exactly how many — and which — behavioural gaps exist. TestPilot surfaces each surviving mutation individually so you know precisely what to fix.

---

## AI Behavioural-Gap Analysis

For every mutation that **survives**, TestPilot's advisor component (`backend/ai/advisor.py`) produces a structured `AnalysisResult`:

| Field | Content |
|---|---|
| `explanation` | Plain-English description of what the operator change means |
| `risk` | Why the missing coverage matters (HIGH / MEDIUM / LOW) |
| `missing_behavior` | The specific scenario no test exercises |
| `suggested_test_name` | A descriptive pytest function name |
| `suggested_test` | Complete, ready-to-run pytest source code |

The advisor is deterministic and pattern-based — it uses the mutation operator, the mutated line, and the surrounding source context (class name, method name, literal values) to produce context-aware output without any external AI service or network calls.

---

## Architecture

```
TestPilot
├── backend/
│   ├── main.py              FastAPI application entry point; serves ui.html at /
│   ├── pipeline.py          Integration layer — chains mutation, runner, and advisor
│   ├── discovery.py         Locates Python source files in a project directory
│   ├── mutations/
│   │   └── engine.py        Tokenize-based mutation engine; generates Mutation objects
│   ├── runner/
│   │   ├── runner.py        Runs pytest in a temp copy; classifies KILLED / SURVIVED
│   │   └── workflow.py      Ties engine + runner together; exposes single & bulk APIs
│   ├── ai/
│   │   └── advisor.py       Rule-based behavioral-gap analyser; emits AnalysisResult
│   └── api/
│       └── routes.py        REST endpoints: GET /api/health, POST /api/analyze
├── frontend/
│   ├── ui.html              Self-contained dashboard (served directly by FastAPI)
│   └── src/                 React + Vite source (App.jsx, main.jsx, index.css)
├── tests/                   pytest suite for all backend components
├── demo_projects/
│   ├── calculator/          Calculator demo — intentional boundary gap in calculate_discount
│   ├── bank_account/        BankAccount demo — withdrawal boundary condition
│   └── score_checker/       Score-checker demo
└── bob_sessions/            Screenshots of IBM Bob sessions used during development
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3, FastAPI, Pydantic |
| Test runner | pytest (invoked as a subprocess) |
| Mutation engine | Python `tokenize` stdlib module |
| Frontend | React 18, Vite 6, vanilla HTML/CSS (no UI framework) |
| API transport | JSON over HTTP (REST) |

---

## Setup & Running

### Prerequisites

- Python 3.10+ with `pip`
- Node.js 18+ with `npm` (needed for running the Vite dev server)

### Backend

```bash
# Install Python dependencies
pip install fastapi uvicorn pydantic pytest

# Start the API server (serves the UI at http://localhost:8000)
uvicorn backend.main:app --reload
```

The UI is served as a static file by FastAPI at `http://localhost:8000/`. The API is available at `http://localhost:8000/api/`.

### Frontend (development server — optional)

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server starts at `http://localhost:5173` and hot-reloads `src/App.jsx` during development.

### Python Test Suite

```bash
# Run all backend tests from the project root
pytest
```

`pytest.ini` sets `testpaths = tests`, so only the `tests/` directory is exercised (not the demo projects).

---

## Demo Workflow

1. Start the backend: `uvicorn backend.main:app --reload`
2. Open `http://localhost:8000` in a browser
3. In the UI, set **Project directory** to `demo_projects/calculator`
4. Click **Analyse**
5. TestPilot generates all mutations for `calculator.py`, runs pytest for each, and displays the results
6. The `>=` → `>` mutation on the `calculate_discount` boundary **survives**
7. Expand that row to see the AI explanation and the suggested test

---

## Project Structure (at a glance)

```
TestPilot/
├── backend/          Python backend (FastAPI + mutation engine + advisor)
├── frontend/         React/Vite UI + standalone ui.html
├── tests/            pytest suite (test_mutation_engine, test_pipeline, test_api, …)
├── demo_projects/    Sample Python projects used to demonstrate the tool
├── bob_sessions/     Evidence screenshots from IBM Bob IDE development sessions
├── pytest.ini        Points pytest at the tests/ directory
└── README.md
```

---

## Built with IBM Bob

IBM Bob IDE was used as a **core development tool** throughout this project — not just for editing, but as an active engineering partner at every phase:

- **Planning** — repository architecture, module boundaries, and data-flow design were mapped out in Bob sessions before any code was written (`bob_sessions/repo_architecture_session.png`)
- **Implementation** — the mutation engine, pipeline, runner, AI advisor, FastAPI routes, and frontend were all implemented with Bob's assistance (`mutation_engine_creation.png`, `initial_pipeline_creation.png`, `fast_api_creation.png`, `front_end_implementation.jpeg`)
- **Debugging & fixing** — regressions in the AI advisor and pipeline were diagnosed and resolved in Bob (`fix_ai_regression.png`, `fix_pipepline.png`, `fix_to_ai_analysis.png`, `fix_tests.png`)
- **Testing** — test coverage strategy and the pytest suite were authored with Bob (`fix_tests.png`)
- **Demo creation** — the calculator demo project and its intentional boundary gap were designed in Bob (`calculator_demo_creation.png`)
- **Extensibility** — generic Python project discovery was added in a Bob session (`add_generic_py_project_discovery.png`)

Evidence of every major session is preserved as screenshots in [`bob_sessions/`](bob_sessions/).

---

## Team

| # | Name |
|---|---|
| 1 | Rithik Sujith |
| 2 | Mohammed Najad |
| 3 | Ann Maria Tony |
| 4 | Ananya Premchand |

---

*IBM Bob 2.0 Hackathon submission.*
