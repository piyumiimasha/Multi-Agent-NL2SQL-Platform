from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objects import Figure


def revenue_trend_chart(rows: list[dict]) -> Figure:
    df = pd.DataFrame(rows)
    df["month"] = pd.to_datetime(df["month"])
    df["total_revenue"] = df["total_revenue"].astype(float)

    fig = px.line(
        df,
        x="month",
        y="total_revenue",
        title="Monthly Revenue Trend",
        labels={"month": "Month", "total_revenue": "Total Revenue (LKR)"},
        markers=True,
    )
    fig.update_traces(line_color="#0077b6", line_width=2.5)
    fig.update_layout(hovermode="x unified", yaxis_tickprefix="LKR ")
    return fig


def top_diagnoses_chart(rows: list[dict], top_n: int = 15) -> Figure:
    df = pd.DataFrame(rows).head(top_n)

    fig = px.bar(
        df,
        x="total_cases",
        y="diagnosis_name",
        color="diagnosis_category",
        orientation="h",
        title=f"Top {top_n} Diagnoses",
        labels={
            "total_cases": "Number of Cases",
            "diagnosis_name": "Diagnosis",
            "diagnosis_category": "Category",
        },
        text="total_cases",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=True)
    return fig


def doctor_load_chart(rows: list[dict]) -> Figure:
    df = pd.DataFrame(rows)
    df["total_appointments"] = df["total_appointments"].astype(int)

    mean_load = df["total_appointments"].mean()

    fig = px.bar(
        df,
        x="doctor_name",
        y="total_appointments",
        color="no_show_rate_pct",
        color_continuous_scale="RdYlGn_r",
        title="Doctor Workload & No-Show Rate",
        labels={
            "doctor_name": "Doctor",
            "total_appointments": "Total Appointments",
            "no_show_rate_pct": "No-Show Rate (%)",
        },
        hover_data=["specialization", "no_shows", "no_show_rate_pct"],
    )
    # Dashed line for average
    fig.add_hline(
        y=mean_load,
        line_dash="dash",
        line_color="gray",
        annotation_text=f"Avg: {mean_load:.0f}",
        annotation_position="top right",
    )
    fig.update_layout(xaxis_tickangle=-35)
    return fig


def payment_methods_chart(rows: list[dict]) -> Figure:
    df = pd.DataFrame(rows)
    df["total_revenue"] = df["total_revenue"].astype(float)

    fig = px.pie(
        df,
        names="payment_method",
        values="total_revenue",
        title="Revenue by Payment Method",
        hole=0.4,  # donut style — easier to read labels
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


def department_revenue_chart(rows: list[dict]) -> Figure:
    df = pd.DataFrame(rows)
    df["total_revenue"] = df["total_revenue"].astype(float)

    fig = px.bar(
        df,
        x="department_name",
        y="total_revenue",
        color="avg_bill",
        color_continuous_scale="Blues",
        title="Revenue by Department",
        labels={
            "department_name": "Department",
            "total_revenue": "Total Revenue (LKR)",
            "avg_bill": "Avg Bill (LKR)",
        },
        text="invoice_count",
    )
    fig.update_traces(texttemplate="%{text} invoices", textposition="outside")
    fig.update_layout(xaxis_tickangle=-30)
    return fig


def adhoc_chart(rows: list[dict], chart_type: str, title: str = "Query Result") -> Figure | None:
    """Render a chart for ad-hoc NL query results based on the interpreter's suggestion."""
    if not rows:
        return None

    df = pd.DataFrame(rows)
    cols = df.columns.tolist()

    # Heuristic: first column = category/x axis, second = numeric y axis
    x_col = cols[0]
    y_cols = [c for c in cols[1:] if pd.api.types.is_numeric_dtype(df[c])]
    if not y_cols:
        # Try to coerce
        for c in cols[1:]:
            try:
                df[c] = pd.to_numeric(df[c])
                y_cols.append(c)
            except (ValueError, TypeError):
                pass
    if not y_cols:
        return None

    y_col = y_cols[0]

    if chart_type == "line":
        fig = px.line(df, x=x_col, y=y_col, title=title, markers=True)
    elif chart_type == "pie":
        fig = px.pie(df, names=x_col, values=y_col, title=title)
    elif chart_type == "bar":
        fig = px.bar(df, x=x_col, y=y_col, title=title, text=y_col)
        fig.update_traces(textposition="outside")
    else:
        return None

    fig.update_layout(
        xaxis_title=x_col.replace("_", " ").title(),
        yaxis_title=y_col.replace("_", " ").title(),
    )
    return fig