from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from nl2sql.validation import _load_database_url


@dataclass
class PanelData:
    rows: list[dict]
    columns: list[str]
    error: str | None = None


class DashboardQueryRunner:
    """Runs the pre-built panel queries directly — no LLM needed for these."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @classmethod
    def from_env(cls, env_path: str | Path = ".env") -> "DashboardQueryRunner":
        url = _load_database_url(Path(env_path))
        if not url:
            raise RuntimeError("Missing database URL in .env")
        return cls(url)

    def _run(self, sql: str) -> PanelData:
        try:
            with psycopg.connect(
                self.database_url,
                row_factory=dict_row,
                prepare_threshold=None,
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = [dict(r) for r in cur.fetchall()]
                    columns = list(rows[0].keys()) if rows else []
                    return PanelData(rows=rows, columns=columns)
        except Exception as exc:
            return PanelData(rows=[], columns=[], error=str(exc))

    # ---- Panel 1: Revenue Trend ----
    def revenue_trend(self, start_date: str, end_date: str) -> PanelData:
        sql = f"""
        SELECT
            DATE_TRUNC('month', b.invoice_date) AS month,
            SUM(b.total_amount)                 AS total_revenue,
            COUNT(b.billing_id)                 AS invoice_count
        FROM billing_invoices b
        WHERE b.invoice_date BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY DATE_TRUNC('month', b.invoice_date)
        ORDER BY month ASC;
        """
        return self._run(sql)

    # ---- Panel 2: Top Diagnoses ----
    def top_diagnoses(self, limit: int = 15) -> PanelData:
        sql = f"""
        SELECT
            d.diagnosis_name,
            d.diagnosis_category,
            COUNT(a.admission_id) AS total_cases
        FROM diagnoses d
        JOIN admissions a ON d.diagnosis_id = a.diagnosis_id
        GROUP BY d.diagnosis_name, d.diagnosis_category
        ORDER BY total_cases DESC
        LIMIT {limit};
        """
        return self._run(sql)

    # ---- Panel 3: Doctor Load ----
    def doctor_load(self) -> PanelData:
        sql = """
        SELECT
            CONCAT(d.first_name, ' ', d.last_name) AS doctor_name,
            s.specialization_name                  AS specialization,
            COUNT(a.appointment_id)                AS total_appointments,
            COUNT(CASE WHEN a.status = 'No-Show'
                       THEN a.appointment_id END)  AS no_shows,
            ROUND(
                COUNT(CASE WHEN a.status = 'No-Show'
                           THEN a.appointment_id END) * 100.0
                / NULLIF(COUNT(a.appointment_id), 0), 1
            )                                      AS no_show_rate_pct
        FROM doctors d
        JOIN appointments a       ON d.doctor_id = a.doctor_id
        JOIN specialties s        ON d.specialty_id = s.specialty_id
        GROUP BY d.doctor_id, d.first_name, d.last_name, s.specialization_name
        ORDER BY total_appointments DESC;
        """
        return self._run(sql)

    # ---- Panel 4: Payment Methods ----
    def payment_methods(self) -> PanelData:
        sql = """
        SELECT
            b.payment_method,
            COUNT(b.billing_id)   AS transaction_count,
            SUM(b.total_amount)   AS total_revenue,
            ROUND(AVG(b.total_amount), 2) AS avg_invoice
        FROM billing_invoices b
        WHERE b.payment_method IS NOT NULL
        GROUP BY b.payment_method
        ORDER BY total_revenue DESC;
        """
        return self._run(sql)

    # ---- Panel 5: Department Revenue breakdown (bonus panel) ----
    def department_revenue(self) -> PanelData:
        sql = """
        SELECT
            dep.department_name,
            COUNT(b.billing_id)          AS invoice_count,
            SUM(b.total_amount)          AS total_revenue,
            ROUND(AVG(b.total_amount),2) AS avg_bill
        FROM billing_invoices b
        JOIN admissions a   ON b.patient_id = a.patient_id
        JOIN doctors d      ON a.doctor_id  = d.doctor_id
        JOIN departments dep ON d.department_id = dep.department_id
        GROUP BY dep.department_name
        ORDER BY total_revenue DESC;
        """
        return self._run(sql)