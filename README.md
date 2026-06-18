# 🏥 MediCore Analytics — Multi-Agent NL2SQL Platform

A production-grade, multi-agent Natural Language to SQL (NL2SQL) analytics platform for MediCore Hospital. Hospital staff can ask plain-English questions and receive validated SQL results rendered as dynamic charts — no SQL expertise required.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Agent Pipeline](#agent-pipeline)
- [Technologies & Tools](#technologies--tools)
- [Folder Structure](#folder-structure)
- [Setup Guide](#setup-guide)
- [Usage](#usage)
- [Dashboard Pages](#dashboard-pages)
- [Error Handling](#error-handling)
- [Observability & Tracing](#observability--tracing)
- [Database Schema](#database-schema)
- [Environment Variables](#environment-variables)
---

## Overview

MediCore Analytics transforms natural language questions into validated PostgreSQL queries using a three-agent pipeline. Instead of requiring SQL expertise, hospital staff type questions like:

> *"Which doctors have the highest no-show rates?"*
> *"Show monthly revenue trend for the last year."*
> *"What are the top 10 diagnoses by case count?"*

The system generates SQL, validates it for safety and correctness, executes it against the live hospital database, and renders the results as an appropriate chart with a plain-English insight summary.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard                       │
│         (Ad-hoc NL queries + 5 pre-built panels)            │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                            │
│         (retry logic · tracing · fallback · routing)        │
└──────────┬──────────────────┬──────────────────┬────────────┘
           │                  │                  │
           ▼                  ▼                  ▼
   ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐
   │ Intent Router │  │ SQL Generator │  │ Result Interpreter│
   │   (Agent 1)   │→ │   (Agent 2)   │→ │    (Agent 3)      │
   └───────────────┘  └───────┬───────┘  └───────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
   ┌─────────────────┐ ┌──────────┐ ┌────────────────┐
   │ Schema-Aware    │ │  Safety  │ │ Query Executor │
   │ Prompt Builder  │ │Validator │ │  (psycopg3)    │
   └─────────────────┘ └──────────┘ └────────┬───────┘
                                             │
                                             ▼
                                   ┌──────────────────┐
                                   │  PostgreSQL DB   │
                                   │ (Supabase hosted)│
                                   └──────────────────┘
```

### Key Design Principles

- **Schema injection over fine-tuning** — the database schema is dynamically injected into every LLM prompt at runtime, so no model training is required and the system stays current as the schema evolves.
- **Deterministic safety, probabilistic generation** — SQL validation (safety + syntax) uses deterministic code (regex + `EXPLAIN`), never LLM calls. Only generation and interpretation use the LLM.
- **Agents communicate via typed contracts** — every agent receives a typed `*Input` dataclass and returns a typed `*Output` dataclass. No shared mutable state between agents.
- **Graceful degradation** — every failure path produces a friendly user-facing message. Raw errors never reach the UI.

---

## Agent Pipeline

### Agent 1 — Intent Router
Classifies the user's question into one of five intents: `aggregation`, `comparison`, `trend`, `lookup`, or `unknown`. This classification is passed to Agent 2 as a routing hint that improves SQL generation (e.g. trend questions prompt the LLM to use `DATE_TRUNC`).

### Agent 2 — SQL Generator
The core NL2SQL agent. Built on three sub-layers:

| Sub-layer | Role | Uses LLM? |
|---|---|---|
| Schema-Aware Prompt Builder | Selects relevant tables, injects schema + FK + sample rows | No |
| Safety Validator | Blocks DROP/DELETE/INSERT/ALTER etc. | No |
| Syntax Validator | Runs `EXPLAIN <sql>` against the live DB | No |
| Retry Engine | Re-prompts with error feedback (up to 3 attempts) | Yes |
| Clarification Engine | Asks user a clarifying question after 3 failed retries | Yes |

### Agent 3 — Result Interpreter
Receives the SQL, result rows, and any error context. Uses the LLM to generate a 2–3 sentence plain-English summary citing specific numbers, suggests an appropriate chart type (`bar`, `line`, `pie`, `table`, `none`), and flags anomalies. Also handles error cases — missing schema, empty results, and ambiguous questions — by explaining what went wrong in plain English.

### Fallback Agent
Triggered when Agent 1 or Agent 2 crash after all retries. Returns a friendly, informative `PipelineResult` without ever raising an exception to the UI.

---

## Technologies & Tools

| Category | Technology | Purpose |
|---|---|---|
| **LLM** | [Groq](https://console.groq.com) + `llama-3.3-70b-versatile` | SQL generation, intent routing, result interpretation |
| **Database** | PostgreSQL via [Supabase](https://supabase.com) | Hospital data storage |
| **DB Driver** | `psycopg` (v3) | Database connectivity |
| **SQL Parsing** | `sqlparse` | Statement splitting and keyword extraction |
| **Dashboard** | [Streamlit](https://streamlit.io) | User interface |
| **Charts** | [Plotly Express](https://plotly.com/python/plotly-express/) | Interactive visualisations |
| **Data Processing** | `pandas` | DataFrame manipulation for charts |
| **Language** | Python 3.11+ | Core implementation |
| **Environment** | `python-dotenv` pattern | Secret management |
| **Tracing** | Custom JSON tracer | Observability (see `traces/`) |

---

## Folder Structure

```
Multi-Agent-NL2SQL-Platform/
│
├── .env                          # secrets (never committed)
├── README.md
├── requirements.txt
│
├── traces/                       # auto-created — one JSON trace per query
│   └── <query_id>.json
│
├── notebooks/                    # exploration and testing notebooks
│
└── src/
    │
    ├── dashboard/                # Part 3 — Streamlit UI
    │   ├── app.py                # main Streamlit application
    │   ├── charts.py             # Plotly chart renderers (3a)
    │   ├── insights.py           # LLM insight generator (3c)
    │   └── queries.py            # pre-built SQL panel queries (3b)
    │
    ├── nl2sql/                   # Part 1 — NL2SQL Engine
    │   ├── schema.py             # PostgreSQL schema introspection
    │   ├── prompt.py             # schema-aware prompt builder
    │   ├── engine.py             # NL2SQLPromptComposer (1a)
    │   ├── validation.py         # safety + syntax validators (1b)
    │   ├── retry_engine.py       # retry + clarification loop (1c)
    │   └── executor.py           # SQL query executor
    │
    ├── agents/                   # Part 2a — specialist agents
    │   ├── intent_router.py      # Agent 1: intent classification
    │   ├── sql_generator.py      # Agent 2: NL→SQL (wraps nl2sql/)
    │   ├── result_interpreter.py # Agent 3: rows → insight + chart type
    │   └── fallback.py           # fallback agent for pipeline failures
    │
    ├── orchestrator/             # Part 2a + 2c
    │   └── orchestrator.py       # agent pipeline, retry, error propagation
    │
    ├── messages/                 # typed agent contracts
    │   └── messages.py           # all Input/Output dataclasses
    │
    ├── tracing/                  # Part 2b — observability
    │   └── tracing.py            # AgentTracer, QueryTrace, StepRecorder
    │
    └── infastructure/
        └── llm/
            └── llm_client.py     # GroqLLMClient wrapper
```

---

## Setup Guide

### Prerequisites

- Python 3.11 or higher
- A [Supabase](https://supabase.com) project with the MediCore database loaded
- A [Groq](https://console.groq.com) API key (free tier is sufficient)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/Multi-Agent-NL2SQL-Platform.git
cd Multi-Agent-NL2SQL-Platform
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt`:
```
groq
psycopg[binary]
sqlparse
streamlit
plotly
pandas
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
# Groq LLM
GROQ_API_KEY=gsk_...

# Supabase — use the Direct Connection string (not the Transaction Pooler)
# Found at: Supabase Dashboard → Project → Settings → Database → Connection String
SUPABASE_DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
```

> ⚠️ Use the **Direct Connection** or **Session Pooler (port 5432)** string, not the Transaction Pooler (port 6543). The Transaction Pooler causes `DuplicatePreparedStatement` errors with psycopg3.

### 5. Load the database

Load the MediCore schema dump into your Supabase project via the SQL editor or `psql`:

```bash
psql "postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres" \
  -f medicare.sql
```

### 6. Test the database connection

```bash
python -c "
import psycopg, os
from pathlib import Path

# Quick connection test
url = None
for line in Path('.env').read_text().splitlines():
    if line.startswith('SUPABASE_DATABASE_URL='):
        url = line.split('=', 1)[1].strip()

with psycopg.connect(url, prepare_threshold=None) as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM patients')
        print('✅ Connected! Patients:', cur.fetchone()[0])
"
```

### 7. Run the dashboard

```bash
# Always run from the project root
streamlit run src/dashboard/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Usage

### Ad-hoc Natural Language Queries

Navigate to **💬 Ask a Question** and type any question about the hospital data:

```
Which doctors have the highest no-show rates?
Show monthly revenue for 2024.
What are the top diagnoses in the Cardiology department?
How many appointments were completed vs cancelled last month?
Compare revenue across departments.
```

The system will:
1. Classify the intent (aggregation / comparison / trend / lookup)
2. Generate and validate SQL
3. Execute the query
4. Render an appropriate chart
5. Generate a plain-English insight with specific numbers

### Pre-built Dashboard Panels

| Page | What it shows |
|---|---|
| 📈 Revenue Trend | Monthly revenue with date-range filter |
| 🩺 Top Diagnoses | Most common diagnoses with category drill-down |
| 👨‍⚕️ Doctor Load | Workload distribution with overload/underload flags |
| 💳 Payment Methods | Revenue breakdown by payment type (pie + bar) |
| 🏢 Department Revenue | Revenue and invoice counts by department |

---

## Dashboard Pages

### Ask a Question (Ad-hoc)
- Free-form NL input
- Shows detected intent, generated SQL, chart, LLM insight, and raw data
- Maintains last 5 questions in sidebar for multi-turn context

### Revenue Trend
- Date range selector
- Line chart with markers
- KPI metrics: total revenue, invoice count, monthly average

### Top Diagnoses
- Adjustable slider (5–30 diagnoses)
- Horizontal bar chart coloured by diagnosis category
- Category drill-down filter below the chart

### Doctor Load
- Bar chart with no-show rate as colour scale
- Average workload reference line
- Automatic overload/underload detection (±30% of average)

### Payment Methods
- Donut pie chart + transaction count bar chart side by side
- Top payment method highlighted in KPI

### Department Revenue
- Bar chart with average bill as colour scale
- Invoice count as bar labels

---

## Error Handling

The system handles four classes of errors gracefully — no raw SQL errors or stack traces ever reach the user.

| Scenario | System response |
|---|---|
| Missing schema (salary, insurance, surgery) | "MediCore's database doesn't contain [X]. You can ask about [alternatives] instead." |
| Ambiguous question ("best doctor") | Answers based on a stated assumption, e.g. "I interpreted 'best' as highest appointment count." |
| Valid query, empty result | "No matching records found." with explanation (e.g. future date, non-existent name) |
| SQL injection attempt | Input sanitised before reaching the LLM; destructive patterns stripped |
| LLM API unavailable | Fallback agent returns a friendly retry message |
| Database connection failure | Streamlit shows connection error with instructions; app does not crash |

### SQL Safety Layers

1. **Input sanitisation** — regex strips `OR 1=1`, `; DROP TABLE`, `UNION SELECT`, and SQL comment patterns from user input before the LLM sees it.
2. **Statement type check** — only `SELECT` and `WITH` statements are allowed through; all others are blocked immediately.
3. **Keyword blocklist** — `DELETE`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `ALTER`, `GRANT`, `REVOKE` and others are rejected even if embedded inside a SELECT.
4. **EXPLAIN validation** — the generated SQL is run through `EXPLAIN` on the live database before execution, catching schema mismatches (wrong column/table names) without touching real data.
5. **Read-only DB user** — recommended at the infrastructure level as a final defence.

---

## Observability & Tracing

Every query generates a JSON trace file in `traces/`. Each file contains:

```json
{
  "query_id": "a3f9c12b8e4d",
  "question": "Which doctors have the highest no-show rates?",
  "started_at": 1718123456.789,
  "total_latency_ms": 3241.5,
  "steps": [
    {
      "agent": "intent_router_attempt_1",
      "latency_ms": 412.3,
      "input": { "question": "..." },
      "output": { "intent": "comparison", "reasoning": "..." },
      "tokens": { "input_tokens": 180, "output_tokens": 22 },
      "error": null
    },
    {
      "agent": "sql_generator_attempt_1",
      "latency_ms": 1823.1,
      "input": { "question": "...", "intent": "comparison" },
      "output": { "success": true, "sql": "SELECT ...", "row_count": 12 },
      "tokens": null,
      "error": null
    },
    {
      "agent": "result_interpreter_attempt_1",
      "latency_ms": 987.6,
      "input": { "question": "...", "sql": "...", "rows": [...] },
      "output": { "summary": "...", "chart_type": "bar" },
      "tokens": { "input_tokens": 620, "output_tokens": 95 },
      "error": null
    }
  ]
}
```

Use traces to:
- Debug why a query failed at a specific agent step
- Identify latency bottlenecks across the pipeline
- Monitor token usage and API cost per query
- Provide concrete examples for the engineering report

---

## Database Schema

MediCore Hospital CRM — 12 tables covering the full patient lifecycle:

| Table | Category | Description |
|---|---|---|
| `patients` | Clinical | Patient demographics and records |
| `doctors` | Clinical | Doctor profiles and specialties |
| `specialties` | Reference | Medical specialisation lookup |
| `appointments` | Operations | Scheduled appointments and status |
| `admissions` | Clinical | Hospital admission records |
| `diagnoses` | Clinical | Diagnosis codes and categories |
| `lab_orders` | Clinical | Laboratory test orders |
| `prescriptions` | Clinical | Medication prescriptions |
| `billing_invoices` | Finance | Invoice and payment records |
| `payments` | Finance | Payment transactions |
| `departments` | Admin | Hospital department structure |
| `staff` | Admin | Non-doctor staff records |

**Not in the schema** (common hallucination targets): salary, insurance, pharmacy inventory, patient satisfaction scores, room capacity/occupancy, shift schedules, overtime records, surgery logs.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ | Groq API key from console.groq.com |
| `SUPABASE_DATABASE_URL` | ✅ | Full PostgreSQL connection string |
| `SUPABASE_DB_HOST` | Optional | Alternative: host component only |
| `SUPABASE_DB_PASSWORD` | Optional | Alternative: password component only |
| `SUPABASE_DB_USER` | Optional | Default: `postgres` |
| `SUPABASE_DB_NAME` | Optional | Default: `postgres` |
| `SUPABASE_DB_PORT` | Optional | Default: `5432` |

---

