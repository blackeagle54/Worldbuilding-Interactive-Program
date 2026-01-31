"""
app/services/enforcement.py -- Enforcement service tying validation,
retry, option generation, entity save, and bookkeeping together.

Central orchestrator for Sprint 5 tasks 5.4-5.6.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.services.event_bus import EventBus
from app.services.validation_pipeline import (
    DriftDetector,
    Severity,
    ValidationPipeline,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class EnforcementService:
    """Orchestrates validation, retry, and bookkeeping for all Claude output.

    Responsibilities:
        - Validate option generation output before display
        - Validate entity data before save
        - Log events to bookkeeper
        - Emit signals for UI feedback
    """

    def __init__(self, engine_manager: Any, current_step: int = 1):
        self._engine = engine_manager
        self._pipeline = ValidationPipeline(engine_manager, current_step)
        self._drift = DriftDetector(engine_manager, current_step)
        self._bus = EventBus.instance()
        self._current_step = current_step

    def set_current_step(self, step: int) -> None:
        self._current_step = step
        self._pipeline.set_current_step(step)
        self._drift.set_current_step(step)

    @property
    def pipeline(self) -> ValidationPipeline:
        return self._pipeline

    # ------------------------------------------------------------------
    # 5.4: Option generation validation
    # ------------------------------------------------------------------

    def validate_and_filter_options(
        self, options_data: dict
    ) -> tuple[ValidationResult, list[dict]]:
        """Validate option generation output, return valid options only.

        Parameters
        ----------
        options_data : dict
            Raw output from option_generator.generate_options().

        Returns
        -------
        tuple[ValidationResult, list[dict]]
            The validation result and list of valid options.
            If all options fail, returns empty list (caller should retry).
        """
        self._log_event("llm_call_made", {
            "call_type": "option_generation",
            "step": self._current_step,
        })

        result = self._pipeline.validate_options(options_data)

        if result.passed:
            self._log_event("validation_passed", {
                "validation_type": "options",
                "step": self._current_step,
                "option_count": len(options_data.get("options", [])),
            })
            return result, options_data.get("options", [])

        # Filter to only valid options
        valid_options = []
        options = options_data.get("options", [])
        for i, opt in enumerate(options):
            if not isinstance(opt, dict):
                continue
            # An option is valid if it has at minimum a title/name
            if opt.get("title") or opt.get("name"):
                # Check if this specific option had errors
                opt_has_error = any(
                    issue.field.startswith(f"options[{i}]")
                    and issue.severity == Severity.ERROR
                    for issue in result.issues
                )
                if not opt_has_error:
                    valid_options.append(opt)

        self._log_event("validation_failed", {
            "validation_type": "options",
            "step": self._current_step,
            "total_options": len(options),
            "valid_options": len(valid_options),
            "errors": [i.message for i in result.errors],
        })

        if result.drift_detected:
            self._log_event("drift_detected", {
                "drift_types": result.drift_types,
                "step": self._current_step,
            })

        return result, valid_options

    # ------------------------------------------------------------------
    # 5.5: Entity save validation
    # ------------------------------------------------------------------

    def validate_and_save_entity(
        self,
        entity_data: dict,
        template_id: str,
        entity_id: str | None = None,
    ) -> tuple[ValidationResult, str | None]:
        """Validate entity data and save if valid.

        Parameters
        ----------
        entity_data : dict
            The entity data to validate and save.
        template_id : str
            The template ID for schema validation.
        entity_id : str | None
            If updating an existing entity, the entity ID.

        Returns
        -------
        tuple[ValidationResult, str | None]
            The validation result and entity ID (or None if save failed).
        """
        result = self._pipeline.validate_entity(entity_data, template_id)

        if not result.passed:
            self._log_event("validation_failed", {
                "validation_type": "entity_save",
                "template_id": template_id,
                "entity_id": entity_id or "(new)",
                "errors": [i.message for i in result.errors],
            })
            self._bus.error_occurred.emit(
                f"Entity validation failed: {len(result.errors)} error(s)"
            )
            return result, None

        # Validation passed -- save the entity
        try:
            if entity_id:
                # Update existing
                self._engine.with_lock(
                    "data_manager",
                    lambda d: d.update_entity(entity_id, entity_data),
                )
                saved_id = entity_id
                self._bus.entity_updated.emit(entity_id)
            else:
                # Create new
                saved_id = self._engine.with_lock(
                    "data_manager",
                    lambda d: d.create_entity(template_id, entity_data),
                )
                self._bus.entity_created.emit(saved_id)

            self._log_event("validation_passed", {
                "validation_type": "entity_save",
                "entity_id": saved_id,
                "template_id": template_id,
                "warnings": len(result.warnings),
            })

            self._bus.status_message.emit(
                f"Entity saved: {entity_data.get('name', saved_id)}"
            )

            return result, saved_id

        except Exception as e:
            logger.exception("Entity save failed after validation")
            self._bus.error_occurred.emit(f"Save failed: {e}")
            return result, None

    # ------------------------------------------------------------------
    # Response validation (for chat messages)
    # ------------------------------------------------------------------

    def validate_response(self, text: str) -> ValidationResult:
        """Validate a Claude response for drift.

        Called after each complete message from Claude.
        """
        self._log_event("llm_call_made", {
            "call_type": "chat_response",
            "step": self._current_step,
            "response_length": len(text),
        })

        result = self._pipeline.validate_response(text)

        if result.drift_detected:
            self._log_event("drift_detected", {
                "drift_types": result.drift_types,
                "step": self._current_step,
            })

        if result.passed:
            self._log_event("validation_passed", {
                "validation_type": "response",
                "step": self._current_step,
            })
        else:
            self._log_event("validation_failed", {
                "validation_type": "response",
                "step": self._current_step,
                "issues": [i.message for i in result.issues],
            })

        return result

    # ------------------------------------------------------------------
    # User decision logging
    # ------------------------------------------------------------------

    def log_user_decision(
        self,
        decision_type: str,
        details: dict,
    ) -> None:
        """Log a user decision to the bookkeeper.

        Parameters
        ----------
        decision_type : str
            Type of decision (e.g. "option_chosen", "entity_approved",
            "manual_entry", "step_advanced").
        details : dict
            Details about the decision.
        """
        self._log_event("user_decision", {
            "decision_type": decision_type,
            "step": self._current_step,
            **details,
        })

    def log_retry_attempted(self, attempt: int, errors: list[str]) -> None:
        """Log a retry attempt."""
        self._log_event("retry_attempted", {
            "attempt": attempt,
            "step": self._current_step,
            "error_count": len(errors),
            "errors": errors[:5],  # Cap at 5 for brevity
        })

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------

    def _log_event(self, event_type: str, data: dict) -> None:
        """Log an event to the bookkeeper (best-effort)."""
        try:
            self._engine.with_lock(
                "bookkeeper",
                lambda b: b.log_event(event_type, data),
            )
        except Exception:
            logger.debug("Failed to log event: %s", event_type, exc_info=True)
