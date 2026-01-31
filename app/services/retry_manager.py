"""
app/services/retry_manager.py -- Retry logic for Claude output validation.

When validation fails on Claude's output, the RetryManager:
  1. Formats validation errors as feedback
  2. Adds escalating constraints to the retry prompt
  3. Retries up to MAX_RETRIES times
  4. Falls back to manual entry if all retries fail

Integrates with ValidationPipeline and ClaudeClient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Generator

from app.services.claude_client import ClaudeClient, EventType, StreamEvent
from app.services.validation_pipeline import ValidationPipeline, ValidationResult

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

# Escalating constraint messages added to retry prompts
_ESCALATION = [
    (
        "Your previous response had validation errors. "
        "Please carefully review the errors below and provide a corrected response."
    ),
    (
        "IMPORTANT: This is your second retry. The previous responses failed validation. "
        "Please strictly follow the schema requirements. Do not add extra fields. "
        "Ensure all referenced entity IDs exist. Keep your response focused on "
        "the current step only."
    ),
    (
        "FINAL ATTEMPT: This is your last retry before falling back to manual entry. "
        "Produce a minimal, correct response that satisfies all validation rules. "
        "Use only the simplest valid values. Do not reference other entities unless "
        "you have verified they exist via the search_entities tool."
    ),
]


@dataclass
class RetryState:
    """Tracks retry state for a single request."""
    attempt: int = 0
    original_message: str = ""
    system_prompt: str = ""
    conversation_history: list[dict] = field(default_factory=list)
    last_validation: ValidationResult | None = None
    fell_back: bool = False

    @property
    def exhausted(self) -> bool:
        return self.attempt >= MAX_RETRIES

    @property
    def should_retry(self) -> bool:
        return (
            self.last_validation is not None
            and self.last_validation.needs_retry
            and not self.exhausted
        )


class RetryManager:
    """Manages retry logic with escalating constraints.

    Usage::

        rm = RetryManager(client, pipeline)

        # For streaming with retry
        for event in rm.send_with_retry(message, system_prompt, history):
            handle(event)  # StreamEvents + RetryEvents

        # Check if manual fallback needed
        if rm.state.fell_back:
            show_manual_entry_form()
    """

    def __init__(
        self,
        client: ClaudeClient,
        pipeline: ValidationPipeline,
    ):
        self._client = client
        self._pipeline = pipeline
        self._state = RetryState()

    @property
    def state(self) -> RetryState:
        return self._state

    def send_with_retry(
        self,
        user_message: str,
        system_prompt: str = "",
        conversation_history: list[dict] | None = None,
        validate_fn: Any = None,
    ) -> Generator[StreamEvent, None, None]:
        """Send a message with automatic retry on validation failure.

        Parameters
        ----------
        user_message : str
            The original user message.
        system_prompt : str
            Base system prompt.
        conversation_history : list[dict] | None
            Prior conversation messages.
        validate_fn : callable | None
            Optional custom validation function that takes the complete
            response text and returns a ValidationResult.
            If None, uses pipeline.validate_response().

        Yields
        ------
        StreamEvent
            All normal stream events plus:
            - EventType.ERROR with data="RETRY:N" before each retry
            - EventType.ERROR with data="FALLBACK" when retries exhausted
        """
        self._state = RetryState(
            original_message=user_message,
            system_prompt=system_prompt,
            conversation_history=list(conversation_history or []),
        )

        if validate_fn is None:
            validate_fn = self._pipeline.validate_response

        while True:
            # Build the message for this attempt
            message = self._build_retry_message()
            prompt = self._build_retry_prompt()

            # Stream the response
            accumulated = ""
            for event in self._client.send_message(
                message, prompt, self._state.conversation_history
            ):
                if event.type == EventType.TOKEN:
                    accumulated += event.data
                yield event

                if event.type == EventType.ERROR:
                    return  # Don't retry on hard errors

            # Validate the accumulated response
            if not accumulated.strip():
                # Empty response -- treat as error
                self._state.last_validation = ValidationResult(
                    passed=False,
                    needs_retry=True,
                    human_message="Empty response from Claude.",
                )
            else:
                self._state.last_validation = validate_fn(accumulated)

            self._state.attempt += 1

            if self._state.last_validation.passed:
                return  # Success

            if not self._state.should_retry:
                # Retries exhausted
                self._state.fell_back = True
                yield StreamEvent(
                    type=EventType.ERROR,
                    data="FALLBACK",
                )
                logger.warning(
                    "Retry exhausted after %d attempts, falling back to manual entry",
                    self._state.attempt,
                )
                return

            # Signal retry
            logger.info(
                "Validation failed (attempt %d/%d), retrying...",
                self._state.attempt, MAX_RETRIES,
            )
            yield StreamEvent(
                type=EventType.ERROR,
                data=f"RETRY:{self._state.attempt}",
            )

    def _build_retry_message(self) -> str:
        """Build the message for the current retry attempt."""
        if self._state.attempt == 0:
            return self._state.original_message

        # Include validation feedback in the retry message
        feedback = self._state.last_validation.format_for_retry()
        escalation = _ESCALATION[min(self._state.attempt - 1, len(_ESCALATION) - 1)]

        return (
            f"{escalation}\n\n"
            f"{feedback}\n\n"
            f"Original request: {self._state.original_message}"
        )

    def _build_retry_prompt(self) -> str:
        """Build the system prompt for the current retry attempt."""
        base = self._state.system_prompt

        if self._state.attempt == 0:
            return base

        # Add escalating constraint to system prompt
        constraint = (
            f"\n\nRETRY ATTEMPT {self._state.attempt}/{MAX_RETRIES}. "
            "Previous response had validation errors. "
            "Be extra careful with schema compliance and canon consistency."
        )

        return base + constraint
