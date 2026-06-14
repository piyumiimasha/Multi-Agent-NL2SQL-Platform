from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .engine import NL2SQLPromptComposer
from infastructure.llm.llm_client import GroqLLMClient
from .validation import SQLValidationGatekeeper, ValidationResult, ValidationStatus


class EngineStatus(str, Enum):
    SUCCESS = "success"
    CLARIFICATION_NEEDED = "clarification_needed"
    FAILED = "failed"


@dataclass
class AttemptTrace:
    attempt: int
    raw_llm_output: str
    validation: ValidationResult
    input_tokens: int
    output_tokens: int


@dataclass
class EngineResult:
    status: EngineStatus
    question: str
    sql: str | None
    message: str
    attempts: list[AttemptTrace] = field(default_factory=list)


CLARIFICATION_SYSTEM_PROMPT = (
    "You are a helpful assistant for MediCore Hospital's analytics platform. "
    "The user's question could not be turned into a safe, valid SQL query after "
    "multiple attempts. Ask ONE short, specific clarifying question that would "
    "help generate the correct query next time. Return only the question — no "
    "SQL, no preamble."
)


class NL2SQLEngine:
    """Part 1c: schema-aware generation with retry and clarification."""

    def __init__(
        self,
        composer: NL2SQLPromptComposer,
        llm_client: GroqLLMClient,
        validator: SQLValidationGatekeeper,
        *,
        max_retries: int = 3,
    ) -> None:
        self.composer = composer
        self.llm_client = llm_client
        self.validator = validator
        self.max_retries = max_retries

    def generate_sql(self, question: str) -> EngineResult:
        bundle = self.composer.compose(question)
        system_prompt = bundle.system_prompt
        user_prompt = bundle.user_prompt
        attempts: list[AttemptTrace] = []

        for attempt_number in range(1, self.max_retries + 1):
            response = self.llm_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            validation = self.validator.validate(response.text)
            attempts.append(
                AttemptTrace(
                    attempt=attempt_number,
                    raw_llm_output=response.text,
                    validation=validation,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
            )

            if validation.status == ValidationStatus.OK:
                return EngineResult(
                    status=EngineStatus.SUCCESS,
                    question=question,
                    sql=validation.sql,
                    message="Query generated and validated successfully.",
                    attempts=attempts,
                )

            if validation.status == ValidationStatus.BLOCKED:
                # Don't retry destructive/unsafe SQL — fail immediately.
                return EngineResult(
                    status=EngineStatus.FAILED,
                    question=question,
                    sql=None,
                    message=validation.user_message,
                    attempts=attempts,
                )

            # status == INVALID -> feed the error back and retry
            user_prompt = self._build_retry_prompt(
                original_prompt=bundle.user_prompt,
                failed_sql=response.text,
                validation=validation,
            )

        # All retries exhausted -> ask the user a clarifying question
        clarification = self._ask_clarification(question, attempts)
        return EngineResult(
            status=EngineStatus.CLARIFICATION_NEEDED,
            question=question,
            sql=None,
            message=clarification,
            attempts=attempts,
        )

    def _build_retry_prompt(
        self, *, original_prompt: str, failed_sql: str, validation: ValidationResult
    ) -> str:
        return (
            f"{original_prompt}\n\n"
            "Your previous SQL failed validation:\n"
            f"{failed_sql}\n\n"
            f"Validation error: {validation.reason or validation.user_message}\n\n"
            "Fix the query so it is valid and uses only the schema context above. "
            "Return SQL only, no markdown, no prose."
        )

    def _ask_clarification(self, question: str, attempts: list[AttemptTrace]) -> str:
        last = attempts[-1]
        user_prompt = (
            f"Original question: {question}\n\n"
            f"Last failed SQL:\n{last.raw_llm_output}\n\n"
            f"Last error: {last.validation.reason or last.validation.user_message}\n\n"
            "Write one short clarifying question to ask the user."
        )
        response = self.llm_client.complete(
            system_prompt=CLARIFICATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return response.text