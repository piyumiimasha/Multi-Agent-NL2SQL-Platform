from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1]
_ROOT_DIR = Path(__file__).resolve().parents[2]

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

ENV_PATH = _ROOT_DIR / ".env"

import datetime

import plotly.express as px
import pandas as pd
import streamlit as st

from nl2sql.engine import NL2SQLPromptComposer
from nl2sql.executor import SQLQueryExecutor
from infastructure.llm.llm_client import GroqLLMClient
from nl2sql.retry_engine import NL2SQLEngine, EngineStatus
from nl2sql.validation import SQLValidationGatekeeper

from agents.intent_router import IntentRouterAgent
from agents.result_interpreter import ResultInterpreterAgent
from agents.sql_generator import SQLGeneratorAgent
from orchestrator.orchestrator import Orchestrator
from tracing.tracing import AgentTracer

from dashboard.charts import (
    adhoc_chart,
    department_revenue_chart,
    doctor_load_chart,
    payment_methods_chart,
    revenue_trend_chart,
    top_diagnoses_chart,
)
from dashboard.insights import InsightGenerator
from dashboard.queries import DashboardQueryRunner


# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MediCore Analytics",
    page_icon="🏥",
    layout="wide",
)


# ── Cached resource init ───────────────────────────────────────────────────────
@st.cache_resource
def get_resources():
    try:
        llm = GroqLLMClient(env_path=ENV_PATH)
        composer = NL2SQLPromptComposer.from_env(ENV_PATH)
        validator = SQLValidationGatekeeper.from_env(ENV_PATH)
        executor = SQLQueryExecutor.from_env(ENV_PATH)
        engine = NL2SQLEngine(composer, llm, validator, max_retries=3)

        router = IntentRouterAgent(llm)
        sql_agent = SQLGeneratorAgent(engine, executor)
        interpreter = ResultInterpreterAgent(llm)
        orchestrator = Orchestrator(
            router, sql_agent, interpreter, tracer=AgentTracer("traces")
        )

        db = DashboardQueryRunner.from_env(ENV_PATH)
        insight_gen = InsightGenerator(llm)

        return orchestrator, db, insight_gen, None

    except Exception as exc:
        return None, None, None, str(exc)


orchestrator, db, insight_gen, init_error = get_resources()

if init_error:
    st.error(f"⚠️ Could not connect to the database: {init_error}")
    st.info("Check your `.env` file and database connection, then refresh the page.")
    st.stop()


# ── Sidebar navigation ─────────────────────────────────────────────────────────
st.sidebar.title("🏥 MediCore Analytics")
page = st.sidebar.radio(
    "Navigate",
    [
        "💬 Ask a Question",
        "📈 Revenue Trend",
        "🩺 Top Diagnoses",
        "👨‍⚕️ Doctor Load",
        "💳 Payment Methods",
        "🏢 Department Revenue",
    ],
)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Ad-hoc NL Query
# ══════════════════════════════════════════════════════════════════════════════
if page == "💬 Ask a Question":
    st.title("💬 Ask the Hospital Database")
    st.caption(
        "Type a plain-English question — the system generates SQL, runs it, and charts the result."
    )

    if "history" not in st.session_state:
        st.session_state.history = []
    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    question = st.text_input(
        "Your question",
        placeholder="e.g. Which departments had the highest revenue last quarter?",
    )

    if st.button("Run", type="primary") and question.strip():
        with st.spinner("Thinking..."):
            result = orchestrator.run(
                question, conversation_history=st.session_state.history
            )

        st.session_state.history.append(question)
        st.session_state.last_result = result

        if result.status == "success" and result.rows:
            # ── Happy path: data returned ──────────────────────────────
            st.success(
                f"✅ Intent: **{result.intent.value if result.intent else 'unknown'}**"
            )

            with st.expander("🔍 Generated SQL"):
                st.code(result.sql, language="sql")

            fig = adhoc_chart(result.rows, result.chart_type, title=question)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(result.rows, use_container_width=True)

            st.markdown("### 💡 Insight")
            with st.spinner("Generating insight..."):
                insight = insight_gen.generate(
                    panel_name=question,
                    rows=result.rows,
                    context=f"Intent: {result.intent.value if result.intent else ''}",
                )
            st.info(insight)

            with st.expander(f"📋 Raw data ({len(result.rows)} rows)"):
                st.dataframe(result.rows, use_container_width=True)

        elif result.status == "success" and not result.rows:
            # ── Valid SQL, zero rows returned ──────────────────────────
            with st.expander("🔍 Generated SQL"):
                st.code(result.sql, language="sql")

            # Interpreter's summary explains WHY no rows came back
            st.warning(f"🔍 {result.summary}")
            st.caption("Try adjusting your filters or rephrasing the question.")

        else:
            # ── Error / schema missing / clarification needed ──────────
            # result.summary is the LLM-generated friendly message
            st.warning(f"💬 {result.summary}")

            if result.sql:
                with st.expander("🔍 SQL that was attempted"):
                    st.code(result.sql, language="sql")

            st.caption(
                "Try rephrasing, or ask about appointments, revenue, diagnoses, or doctor workload."
            )

    if st.session_state.history:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Recent questions**")
        for q in reversed(st.session_state.history[-5:]):
            st.sidebar.caption(f"• {q}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Revenue Trend
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Revenue Trend":
    st.title("📈 Revenue Trend")

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start date", value=None)
    with col2:
        end = st.date_input("End date", value=None)

    start_str = str(start) if start else "2020-01-01"
    end_str = str(end) if end else str(datetime.date.today())

    with st.spinner("Loading..."):
        data = db.revenue_trend(start_str, end_str)

    if data.error:
        st.error(f"⚠️ {data.error}")
    elif not data.rows:
        st.warning("No revenue data found for the selected period.")
    else:
        m1, m2, m3 = st.columns(3)
        total = sum(float(r["total_revenue"]) for r in data.rows)
        invoices = sum(int(r["invoice_count"]) for r in data.rows)
        avg_month = total / len(data.rows) if data.rows else 0
        m1.metric("Total Revenue", f"LKR {total:,.0f}")
        m2.metric("Total Invoices", f"{invoices:,}")
        m3.metric("Avg Monthly Revenue", f"LKR {avg_month:,.0f}")

        st.plotly_chart(revenue_trend_chart(data.rows), use_container_width=True)

        st.markdown("### 💡 Insight")
        with st.spinner("Generating insight..."):
            insight = insight_gen.generate(
                "Revenue Trend",
                data.rows,
                context=f"Date range: {start_str} to {end_str}",
            )
        st.info(insight)

        with st.expander("📋 Monthly breakdown"):
            st.dataframe(data.rows, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Top Diagnoses
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🩺 Top Diagnoses":
    st.title("🩺 Top Diagnoses")

    top_n = st.slider("Number of diagnoses to show", 5, 30, 15)

    with st.spinner("Loading..."):
        data = db.top_diagnoses(limit=top_n)

    if data.error:
        st.error(f"⚠️ {data.error}")
    elif not data.rows:
        st.warning("No diagnosis data found.")
    else:
        m1, m2 = st.columns(2)
        m1.metric("Diagnoses Shown", top_n)
        m2.metric("Total Cases (shown)", sum(int(r["total_cases"]) for r in data.rows))

        st.plotly_chart(top_diagnoses_chart(data.rows, top_n), use_container_width=True)

        st.markdown("### 🔎 Drill-down by Category")
        categories = sorted(
            {r["diagnosis_category"] for r in data.rows if r.get("diagnosis_category")}
        )
        selected = st.selectbox("Filter by category", ["All"] + categories)
        filtered = (
            data.rows
            if selected == "All"
            else [r for r in data.rows if r["diagnosis_category"] == selected]
        )
        st.dataframe(filtered, use_container_width=True)

        st.markdown("### 💡 Insight")
        with st.spinner("Generating insight..."):
            insight = insight_gen.generate("Top Diagnoses", data.rows)
        st.info(insight)


# ══════════════════════════════════════════════════════════════════════════════