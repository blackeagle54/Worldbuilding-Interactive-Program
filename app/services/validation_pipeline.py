"""
app/services/validation_pipeline.py -- 7-layer validation pipeline.

Orchestrates all validation checks between Claude output and world data:

    Layer 1: Pydantic schema validation
    Layer 2: Canon cross-reference checks
    Layer 3: Range and numeric checks
    Layer 4: Enum and allowed-value checks
    Layer 5: Drift detection (format, topic, canon, scope)
    Layer 6: Semantic similarity checks
    Layer 7: Structured ValidationResult with field-level errors

All layers are run by the engine's ConsistencyChecker (layers 1-3 + 6)
plus this module's DriftDetector (layer 5).  This pipeline class
orchestrates them into a single pass and produces a structured result.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class Severity(Enum):
    ERROR = auto()
    WARNING = auto()
    INFO = auto()


@dataclass
class ValidationIssue:
    """A single validation issue."""
    layer: str
    severity: Severity
    message: str
    field: str = ""  # For field-level highlighting


@dataclass
class ValidationResult:
    """Structured result from the full validation pipeline."""
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    drift_detected: bool = False
    drift_types: list[str] = field(default_factory=list)
    needs_retry: bool = False
    retry_hint: str = ""
    human_message: str = ""

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def error_fields(self) -> set[str]:
        """Fields that have errors (for UI highlighting)."""
        return {i.field for i in self.errors if i.field}

    def format_for_retry(self) -> str:
        """Format issues as feedback for retry prompt."""
        lines = ["VALIDATION ERRORS (please fix these):"]
        for issue in self.errors:
            prefix = f"[{issue.field}] " if issue.field else ""
            lines.append(f"  - {prefix}{issue.message}")
        for issue in self.warnings:
            prefix = f"[{issue.field}] " if issue.field else ""
            lines.append(f"  - WARNING: {prefix}{issue.message}")
        if self.drift_types:
            lines.append(f"  - DRIFT DETECTED: {', '.join(self.drift_types)}")
        return "\n".join(lines)

    def format_human(self) -> str:
        """Format for display to the user."""
        if self.passed and not self.warnings:
            return "Validation passed."
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s):")
            for e in self.errors:
                prefix = f"  [{e.field}] " if e.field else "  "
                parts.append(f"{prefix}{e.message}")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s):")
            for w in self.warnings:
                prefix = f"  [{w.field}] " if w.field else "  "
                parts.append(f"{prefix}{w.message}")
        if self.drift_types:
            parts.append(f"Drift: {', '.join(self.drift_types)}")
        return "\n".join(parts)


class DriftDetector:
    """Detects various forms of drift in Claude's output.

    Drift types:
        format_drift   - Response lacks expected structure (no JSON, no tool use)
        topic_drift    - References steps beyond current + 1
        canon_drift    - References entity IDs that don't exist
        scope_drift    - Response is excessively long or off-topic
    """

    def __init__(self, engine_manager: Any = None, current_step: int = 1):
        self._engine = engine_manager
        self._current_step = current_step

    def set_current_step(self, step: int) -> None:
        self._current_step = step

    def detect(self, text: str) -> list[ValidationIssue]:
        """Run all drift checks on a text response.

        Returns a list of issues (may be empty if no drift).
        """
        issues: list[ValidationIssue] = []
        issues.extend(self._check_topic_drift(text))
        issues.extend(self._check_canon_drift(text))
        issues.extend(self._check_scope_drift(text))
        return issues

    def detect_format_drift(self, response_data: dict) -> list[ValidationIssue]:
        """Check if a structured response has format issues.

        Called on parsed option/entity data rather than raw text.
        """
        issues: list[ValidationIssue] = []

        # Check for empty or stub responses
        if not response_data:
            issues.append(ValidationIssue(
                layer="drift",
                severity=Severity.ERROR,
                message="Empty response data -- possible format drift.",
            ))
            return issues

        # Check if required option fields are present
        if "options" in response_data:
            for i, opt in enumerate(response_data["options"]):
                if not isinstance(opt, dict):
                    issues.append(ValidationIssue(
                        layer="drift",
                        severity=Severity.ERROR,
                        field=f"options[{i}]",
                        message=f"Option {i} is not a valid object.",
                    ))
                    continue
                if not opt.get("title") and not opt.get("name"):
                    issues.append(ValidationIssue(
                        layer="drift",
                        severity=Severity.WARNING,
                        field=f"options[{i}].title",
                        message=f"Option {i} is missing a title/name.",
                    ))

        return issues

    def _check_topic_drift(self, text: str) -> list[ValidationIssue]:
        """Detect references to future steps."""
        issues = []
        # Look for "step N" references where N > current + 1
        step_refs = re.findall(r"[Ss]tep\s+(\d+)", text)
        for ref in step_refs:
            step_num = int(ref)
            if step_num > self._current_step + 1:
                issues.append(ValidationIssue(
                    layer="drift",
                    severity=Severity.WARNING,
                    message=(
                        f"References Step {step_num} but current step is "
                        f"{self._current_step}. Stay focused on the current step."
                    ),
                ))
                break  # One warning is enough
        return issues

    def _check_canon_drift(self, text: str) -> list[ValidationIssue]:
        """Detect references to non-existent entity IDs."""
        if self._engine is None:
            return []

        issues = []
        # Look for entity ID patterns (slug-hexsuffix)
        potential_ids = re.findall(r"\b([a-z][\w-]+-[a-f0-9]{4})\b", text)
        if not potential_ids:
            return []

        try:
            dm = self._engine.data_manager
            existing = {
                e["id"]
                for e in self._engine.with_lock("data_manager", lambda d: d.list_entities())
            }
        except Exception:
            return []

        for pid in potential_ids[:10]:  # Cap checks
            if pid not in existing:
                issues.append(ValidationIssue(
                    layer="drift",
                    severity=Severity.WARNING,
                    message=f"References non-existent entity '{pid}'.",
                ))

        return issues

    def _check_scope_drift(self, text: str) -> list[ValidationIssue]:
        """Detect overly long or off-topic responses."""
        issues = []

        # Excessive length check (> 5000 chars suggests scope creep)
        if len(text) > 5000:
            issues.append(ValidationIssue(
                layer="drift",
                severity=Severity.INFO,
                message=(
                    f"Response is {len(text)} characters. Consider breaking "
                    "into smaller, focused pieces."
                ),
            ))

        return issues


class ValidationPipeline:
    """Orchestrates the full validation pipeline.

    Usage::

        pipeline = ValidationPipeline(engine_manager, current_step=7)
        result = pipeline.validate_entity(entity_data, template_id)
        result = pipeline.validate_response(claude_text)
        result = pipeline.validate_options(options_data)
    """

    # Simple LRU-style validation cache to avoid re-running identical
    # validations within the same session.  Keyed by (template_id, data_hash).
    _CACHE_MAX_SIZE = 64

    def __init__(self, engine_manager: Any, current_step: int = 1):
        self._engine = engine_manager
        self._current_step = current_step
        self._drift = DriftDetector(engine_manager, current_step)
        self._cache: dict[tuple[str, int], ValidationResult] = {}

    def set_current_step(self, step: int) -> None:
        self._current_step = step
        self._drift.set_current_step(step)

    # ------------------------------------------------------------------
    # Entity validation (Layers 1-6)
    # ------------------------------------------------------------------

    def _data_hash(self, data: dict) -> int:
        """Produce a stable hash of entity data for cache lookup."""
        try:
            raw = _json.dumps(data, sort_keys=True, default=str)
            return int(hashlib.md5(raw.encode()).hexdigest(), 16)
        except Exception:
            return id(data)

    def validate_entity(
        self, entity_data: dict, template_id: str = ""
    ) -> ValidationResult:
        """Run the full pipeline on entity data.

        Layers:
            1. Pydantic schema
            2. Canon cross-references
            3. Range / numeric checks
            4. Enum / allowed values
            5. Drift detection
            6. Semantic similarity
        """
        # Check cache for identical data + template combination
        cache_key = (template_id, self._data_hash(entity_data))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        issues: list[ValidationIssue] = []
        drift_types: list[str] = []

        # Layers 1-4 + 6 via ConsistencyChecker
        try:
            cc = self._engine.consistency_checker
            check_result = self._engine.with_lock(
                "consistency_checker",
                lambda c: c.check_entity(entity_data, template_id),
            )

            if isinstance(check_result, dict):
                # Schema errors (Layer 1)
                schema_result = check_result.get("schema", {})
                if not schema_result.get("passed", True):
                    for err in schema_result.get("errors", []):
                        # Try to extract field name from error
                        fld = _extract_field(err)
                        issues.append(ValidationIssue(
                            layer="schema",
                            severity=Severity.ERROR,
                            message=err,
                            field=fld,
                        ))

                # Rule-based errors (Layers 2-4)
                rules_result = check_result.get("rules", {})
                if not rules_result.get("passed", True):
                    for err in rules_result.get("errors", []):
                        fld = _extract_field(err)
                        issues.append(ValidationIssue(
                            layer="rules",
                            severity=Severity.ERROR,
                            message=err,
                            field=fld,
                        ))

                # Semantic warnings (Layer 6)
                semantic_result = check_result.get("semantic", {})
                for conflict in semantic_result.get("conflicts", []):
                    issues.append(ValidationIssue(
                        layer="semantic",
                        severity=Severity.WARNING,
                        message=conflict if isinstance(conflict, str) else str(conflict),
                    ))
                for warning in semantic_result.get("warnings", []):
                    issues.append(ValidationIssue(
                        layer="semantic",
                        severity=Severity.WARNING,
                        message=warning if isinstance(warning, str) else str(warning),
                    ))

        except Exception as e:
            logger.exception("ConsistencyChecker failed")
            issues.append(ValidationIssue(
                layer="internal",
                severity=Severity.WARNING,
                message=f"Validation engine error: {e}",
            ))

        # Layer 5: Drift detection on entity data
        # Check for entity-level format drift
        if not entity_data.get("name") and not entity_data.get("title"):
            issues.append(ValidationIssue(
                layer="drift",
                severity=Severity.ERROR,
                field="name",
                message="Entity is missing a name or title.",
            ))
            drift_types.append("format_drift")

        has_errors = any(i.severity == Severity.ERROR for i in issues)

        result = ValidationResult(
            passed=not has_errors,
            issues=issues,
            drift_detected=len(drift_types) > 0,
            drift_types=drift_types,
            needs_retry=has_errors,
            retry_hint="Fix validation errors and try again." if has_errors else "",
        )
        result.human_message = result.format_human()

        # Store in cache (evict oldest entries if over limit)
        if len(self._cache) >= self._CACHE_MAX_SIZE:
            # Remove the oldest entry (first key)
            try:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            except StopIteration:
                pass
        self._cache[cache_key] = result

        return result

    # ------------------------------------------------------------------
    # Response validation (text from Claude)
    # ------------------------------------------------------------------

    def validate_response(self, text: str) -> ValidationResult:
        """Validate a raw text response from Claude for drift."""
        drift_issues = self._drift.detect(text)
        drift_types = list({i.layer for i in drift_issues if i.severity != Severity.INFO})

        has_errors = any(i.severity == Severity.ERROR for i in drift_issues)

        result = ValidationResult(
            passed=not has_errors,
            issues=drift_issues,
            drift_detected=len(drift_types) > 0,
            drift_types=drift_types,
            needs_retry=has_errors,
        )
        result.human_message = result.format_human()
        return result

    # ------------------------------------------------------------------
    # Options validation
    # ------------------------------------------------------------------

    def validate_options(self, options_data: dict) -> ValidationResult:
        """Validate option generation output."""
        issues: list[ValidationIssue] = []
        drift_types: list[str] = []

        # Format drift on structure
        format_issues = self._drift.detect_format_drift(options_data)
        issues.extend(format_issues)
        if format_issues:
            drift_types.append("format_drift")

        # Validate individual options if they contain entity-like data
        options = options_data.get("options", [])
        if not options:
            issues.append(ValidationIssue(
                layer="format",
                severity=Severity.ERROR,
                message="No options were generated.",
            ))
            drift_types.append("format_drift")

        valid_count = 0
        for i, opt in enumerate(options):
            if not isinstance(opt, dict):
                continue

            # Check for required option fields
            if opt.get("title") or opt.get("name"):
                valid_count += 1

            # If option includes template_data, validate it
            template_data = opt.get("template_data", {})
            if template_data and isinstance(template_data, dict):
                template_id = template_data.get("$id", "")
                if template_id:
                    sub_result = self.validate_entity(template_data, template_id)
                    for issue in sub_result.issues:
                        issue.field = f"options[{i}].{issue.field}" if issue.field else f"options[{i}]"
                        issues.append(issue)

        has_errors = any(i.severity == Severity.ERROR for i in issues)

        result = ValidationResult(
            passed=not has_errors,
            issues=issues,
            drift_detected=len(drift_types) > 0,
            drift_types=drift_types,
            needs_retry=has_errors and valid_count == 0,
            retry_hint=(
                f"Only {valid_count} of {len(options)} options are valid."
                if valid_count < len(options) else ""
            ),
        )
        result.human_message = result.format_human()
        return result


def _extract_field(error_msg: str) -> str:
    """Try to extract a field name from an error message.

    Looks for patterns like:
        'name' is a required property
        $.name: ...
        Field 'name' ...
    """
    # Pattern: 'fieldname' is required
    m = re.search(r"'(\w+)'\s+is\s+(a\s+)?required", error_msg)
    if m:
        return m.group(1)

    # Pattern: $.fieldname
    m = re.search(r"\$\.(\w+)", error_msg)
    if m:
        return m.group(1)

    # Pattern: Field 'fieldname'
    m = re.search(r"[Ff]ield\s+'(\w+)'", error_msg)
    if m:
        return m.group(1)

    return ""
