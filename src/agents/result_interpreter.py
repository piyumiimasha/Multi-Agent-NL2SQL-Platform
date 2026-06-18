from __future__ import annotations

import json

from infastructure.llm.llm_client import GroqLLMClient
from messages.messages import InterpreterInput, InterpreterOutput, QueryIntent

INTERPRETER_SYSTEM_PROMPT = (
    "You are a hospital data analyst assistant for MediCore Hospital.\n\n"
    "The MediCore database contains ONLY these tables:\n"
    "patients, doctors, specialties, appointments, admissions, diagnoses, "
    "billing_invoices, lab_orders, prescriptions, departments, payments, staff.\n\n"
    "It does NOT contain: salary, insurance, inventory, pharmacy/medicine stock, "
    "patient satisfaction scores, room capacity/occupancy, shift schedules, "
    "overtime/attendance records, surgery logs, or any HR data.\n\n"
    "Rules:\n"
    "1. If `error` is present OR rows are empty AND the question references data "
    "NOT in the schema above: explain clearly that this data doesn't exist in the "
    "hospital database, name what's missing, and suggest 1-2 questions the user "
    "CAN ask instead.\n"
    "2. If rows are empty but the question is valid (e.g. doctor doesn't exist, "
    "future date, no matching records): say 'No matching records found' and explain why.\n"
    "3. If rows are present: write a 2-3 sentence summary citing specific numbers. "
    "Suggest a chart type.\n"
    "4. If the question is ambiguous ('best', 'worst', 'most important') AND the "
    "system made an assumption to answer it: state what assumption was made "
    "(e.g. 'I interpreted best as highest appointment count').\n\n"
    "Never mention SQL, column names, table names, psycopg, or technical errors.\n\n"
    "Respond with EXACTLY these lines:\n"
    "SUMMARY: <your response>\n"
    "CHART: <bar|line|pie|table|none>\n"
    "ANOMALIES: <comma-separated notes, or 'none'>"
)


class ResultInterpreterAgent:
    """Agent 3: interprets SQL results OR errors into a friendly plain-English response."""

    def __init__(self, llm_client: GroqLLMClient, *, max_rows_in_prompt: int = 25) -> None:
        self.llm_client = llm_client
        self.max_rows_in_prompt = max_rows_in_prompt

    def run(self, input_obj: InterpreterInput) -> InterpreterOutput:
        sample_rows = input_obj.rows[: self.max_rows_in_prompt]

        # Build a status block so the LLM knows exactly what happened
        if input_obj.error:
            status_block = f"STATUS: error\nERROR DETAILS: {input_obj.error}"
        elif not input_obj.rows:
            status_block = "STATUS: empty — query ran successfully but returned zero rows"
        else:
            status_block = f"STATUS: success — {len(input_obj.rows)} row(s) returned"

        user_prompt = (
            f"Question: {input_obj.question}\n"
            f"Intent: {input_obj.intent.value if input_obj.intent else 'unknown'}\n"
            f"SQL attempted:\n{input_obj.sql or '(no SQL generated)'}\n\n"
            f"{status_block}\n\n"
            f"Rows (showing {len(sample_rows)} of {len(input_obj.rows)}):\n"
            f"{json.dumps(sample_rows, default=str) if sample_rows else '[]'}"
        )

        try:
            response = self.llm_client.complete(
                system_prompt=INTERPRETER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return _parse_interpreter_response(response.text)
        except Exception as exc:
            return InterpreterOutput(
                summary="I wasn't able to interpret the results right now. Please try again.",
                chart_type="none",
                anomalies=[str(exc)],
            )


def _parse_interpreter_response(text: str) -> InterpreterOutput:
    summary = ""
    chart_type = "none"
    anomalies: list[str] = []

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CHART:"):
            value = line.split(":", 1)[1].strip().lower()
            if value in {"bar", "line", "pie", "table", "none"}:
                chart_type = value
        elif line.upper().startswith("ANOMALIES:"):
            value = line.split(":", 1)[1].strip()
            if value.lower() != "none":
                anomalies = [a.strip() for a in value.split(",") if a.strip()]

    if not summary:
        summary = "Query completed. Please review the results above."

    return InterpreterOutput(summary=summary, chart_type=chart_type, anomalies=anomalies)