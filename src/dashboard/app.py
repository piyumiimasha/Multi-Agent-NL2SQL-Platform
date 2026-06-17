from __future__ import annotations

import sys
from pathlib import Path

# Make sure src/ is on the path when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import streamlit as st

from nl2sql.engine import NL2SQLPromptComposer
from nl2sql.executor import SQLQueryExecutor
from infastructure.llm.llm_client import GroqLLMClient
from nl2sql.retry_engine import NL2SQLEngine, EngineStatus
from nl2sql.validation import SQLValidationGatekeeper

from agents.intent_router import IntentRouterAgent
from agents.result_interpreter import ResultInterpreterAgent
from agents.sql_generator import SQLGeneratorAgent
from orchestrator import Orchestrator
from tracing import AgentTracer

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

ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


# ── Cached resource init (runs once per session) ───────────────────────────────
@st.cache_resource
def get_resources():
    llm = GroqLLMClient(env_path=ENV_PATH)
    composer = NL2SQLPromptComposer.from_env(ENV_PATH)
    validator = SQLValidationGatekeeper.from_env(ENV_PATH)
    executor = SQLQueryExecutor.from_env(ENV_PATH)
    engine = NL2SQLEngine(composer, llm, validator, max_retries=3)

    router = IntentRouterAgent(llm)
    sql_agent = SQLGeneratorAgent(engine, executor)
    interpreter = ResultInterpreterAgent(llm)
    orchestrator = Orchestrator(router, sql_agent, interpreter, tracer=AgentTracer("traces"))

    db = DashboardQueryRunner.from_env(ENV_PATH)
    insight_gen = InsightGenerator(llm)

    return orchestrator, db, insight_gen


orchestrator, db, insight_gen = get_resources()


# ── Sidebar navigation ─────────────────────────────────────────────────────────
st.sidebar.title("🏥 MediCore Analytics")
page = st.sidebar.radio(
    "Navigate",
    ["💬 Ask a Question", "📈 Revenue Trend", "🩺 Top Diagnoses",
     "👨‍⚕️ Doctor Load", "💳 Payment Methods", "🏢 Department Revenue"],
)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Ad-hoc NL Query (3a + 3c)
# ══════════════════════════════════════════════════════════════════════════════
if page == "💬 Ask a Question":
    st.title("💬 Ask the Hospital Database")
    st.caption("Type a plain-English question — the system generates SQL, runs it, and charts the result.")

    # Maintain conversation history for multi-turn
    if "history" not in st.session_state:
        st.session_state.history = []
    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    question = st.text_input("Your question", placeholder="e.g. Which departments had the highest revenue last quarter?")

    if st.button("Run", type="primary") and question.strip():
        with st.spinner("Thinking..."):
            result = orchestrator.run(question, conversation_history=st.session_state.history)

        st.session_state.history.append(question)
        st.session_state.last_result = result

        if result.status == "success":
            # Intent badge
            st.success(f"✅ Intent: **{result.intent.value if result.intent else 'unknown'}**")

            # SQL expander
            with st.expander("🔍 Generated SQL"):
                st.code(result.sql, language="sql")

            # Chart
            fig = adhoc_chart(result.rows, result.chart_type, title=question)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.dataframe(result.rows, use_container_width=True)

            # NL Insight (3c)
            st.markdown("### 💡 Insight")
            with st.spinner("Generating insight..."):
                insight = insight_gen.generate(
                    panel_name=question,
                    rows=result.rows,
                    context=f"Intent: {result.intent.value if result.intent else ''}",
                )
            st.info(insight)

            # Raw data toggle
            with st.expander(f"📋 Raw data ({result.rows.__len__()} rows)"):
                st.dataframe(result.rows, use_container_width=True)

        elif result.status == "error":
            st.warning(f"⚠️ {result.summary}")
        else:
            st.error(f"❌ {result.summary}")

    # Conversation history sidebar
    if st.session_state.history:
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Recent questions**")
        for q in reversed(st.session_state.history[-5:]):
            st.sidebar.caption(f"• {q}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Revenue Trend (3b panel 1)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Revenue Trend":
    st.title("📈 Revenue Trend")

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start date", value=None)
    with col2:
        end = st.date_input("End date", value=None)

    import datetime
    start_str = str(start) if start else "2020-01-01"
    end_str = str(end) if end else str(datetime.date.today())

    with st.spinner("Loading..."):
        data = db.revenue_trend(start_str, end_str)

    if data.error:
        st.error(data.error)
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
# PAGE 3 — Top Diagnoses (3b panel 2)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🩺 Top Diagnoses":
    st.title("🩺 Top Diagnoses")

    top_n = st.slider("Number of diagnoses to show", 5, 30, 15)

    with st.spinner("Loading..."):
        data = db.top_diagnoses(limit=top_n)

    if data.error:
        st.error(data.error)
    elif not data.rows:
        st.warning("No diagnosis data found.")
    else:
        m1, m2 = st.columns(2)
        m1.metric("Diagnoses Shown", top_n)
        m2.metric("Total Cases (shown)", sum(int(r["total_cases"]) for r in data.rows))

        st.plotly_chart(top_diagnoses_chart(data.rows, top_n), use_container_width=True)

        # Drill-down: click a category to filter
        st.markdown("### 🔎 Drill-down by Category")
        categories = sorted({r["diagnosis_category"] for r in data.rows if r.get("diagnosis_category")})
        selected = st.selectbox("Filter by category", ["All"] + categories)
        filtered = data.rows if selected == "All" else [r for r in data.rows if r["diagnosis_category"] == selected]

        st.dataframe(filtered, use_container_width=True)

        st.markdown("### 💡 Insight")
        with st.spinner("Generating insight..."):
            insight = insight_gen.generate("Top Diagnoses", data.rows)
        st.info(insight)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — Doctor Load (3b panel 3)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👨‍⚕️ Doctor Load":
    st.title("👨‍⚕️ Doctor Workload")

    with st.spinner("Loading..."):
        data = db.doctor_load()

    if data.error:
        st.error(data.error)
    elif not data.rows:
        st.warning("No appointment data found.")
    else:
        appts = [int(r["total_appointments"]) for r in data.rows]
        avg = sum(appts) / len(appts)
        overloaded = [r for r in data.rows if int(r["total_appointments"]) > avg * 1.3]
        underloaded = [r for r in data.rows if int(r["total_appointments"]) < avg * 0.7]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Doctors", len(data.rows))
        m2.metric("Avg Appointments", f"{avg:.0f}")
        m3.metric("Overloaded (>130% avg)", len(overloaded))
        m4.metric("Underloaded (<70% avg)", len(underloaded))

        st.plotly_chart(doctor_load_chart(data.rows), use_container_width=True)

        if overloaded:
            st.warning(f"⚠️ **{len(overloaded)} overloaded doctors:** " +
                       ", ".join(r["doctor_name"] for r in overloaded))

        st.markdown("### 💡 Insight")
        with st.spinner("Generating insight..."):
            insight = insight_gen.generate("Doctor Workload", data.rows)
        st.info(insight)

        with st.expander("📋 Full doctor table"):
            st.dataframe(data.rows, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — Payment Methods (3b panel 4)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💳 Payment Methods":
    st.title("💳 Payment Methods")

    with st.spinner("Loading..."):
        data = db.payment_methods()

    if data.error:
        st.error(data.error)
    elif not data.rows:
        st.warning("No payment data found.")
    else:
        total_rev = sum(float(r["total_revenue"]) for r in data.rows)
        top_method = data.rows[0]

        m1, m2, m3 = st.columns(3)
        m1.metric("Payment Methods", len(data.rows))
        m2.metric("Total Revenue", f"LKR {total_rev:,.0f}")
        m3.metric("Top Method", top_method["payment_method"])

        col1, col2 = st.columns([1, 1])
        with col1:
            st.plotly_chart(payment_methods_chart(data.rows), use_container_width=True)
        with col2:
            import plotly.express as px
            import pandas as pd
            df = pd.DataFrame(data.rows)
            df["total_revenue"] = df["total_revenue"].astype(float)
            fig2 = px.bar(
                df,
                x="payment_method",
                y="transaction_count",
                title="Transactions by Payment Method",
                labels={"payment_method": "Method", "transaction_count": "Transactions"},
                color="payment_method",
                text="transaction_count",
            )
            fig2.update_traces(textposition="outside")
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("### 💡 Insight")
        with st.spinner("Generating insight..."):
            insight = insight_gen.generate("Payment Methods", data.rows)
        st.info(insight)

        with st.expander("📋 Raw data"):
            st.dataframe(data.rows, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 6 — Department Revenue (3a panel 5 — 5th panel requirement)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏢 Department Revenue":
    st.title("🏢 Department Revenue Breakdown")

    with st.spinner("Loading..."):
        data = db.department_revenue()

    if data.error:
        st.error(data.error)
    elif not data.rows:
        st.warning("No department data found.")
    else:
        total = sum(float(r["total_revenue"]) for r in data.rows)
        top_dept = data.rows[0]

        m1, m2, m3 = st.columns(3)
        m1.metric("Departments", len(data.rows))
        m2.metric("Total Revenue", f"LKR {total:,.0f}")
        m3.metric("Top Department", top_dept["department_name"])

        st.plotly_chart(department_revenue_chart(data.rows), use_container_width=True)

        st.markdown("### 💡 Insight")
        with st.spinner("Generating insight..."):
            insight = insight_gen.generate("Department Revenue", data.rows)
        st.info(insight)

        with st.expander("📋 Full breakdown"):
            st.dataframe(data.rows, use_container_width=True)