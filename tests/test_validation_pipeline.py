"""
Tests for app/services/validation_pipeline.py -- DriftDetector, ValidationPipeline,
ValidationResult.
"""

from unittest.mock import MagicMock

import pytest

from app.services.validation_pipeline import (
    DriftDetector,
    Severity,
    ValidationIssue,
    ValidationPipeline,
    ValidationResult,
    _extract_field,
)


# ==================================================================
# DriftDetector tests
# ==================================================================


class TestDriftDetector:
    def test_topic_drift_detects_future_step(self):
        dd = DriftDetector(current_step=5)
        issues = dd.detect("We will handle this in Step 20.")
        assert len(issues) == 1
        assert issues[0].severity == Severity.WARNING
        assert "Step 20" in issues[0].message

    def test_topic_drift_allows_current_and_next(self):
        dd = DriftDetector(current_step=5)
        issues = dd.detect("Step 5 is great and Step 6 follows.")
        assert len(issues) == 0

    def test_canon_drift_no_engine_returns_empty(self):
        dd = DriftDetector(engine_manager=None, current_step=1)
        issues = dd.detect("References thor-abcd-1234 which does not exist.")
        assert len(issues) == 0  # No engine means no canon checking

    def test_canon_drift_with_mock_engine(self):
        engine = MagicMock()
        engine.with_lock.return_value = [
            {"id": "known-entity-a1b2"}
        ]
        dd = DriftDetector(engine_manager=engine, current_step=1)
        issues = dd.detect("Mentions unknown-entity-c3d4 which is not real.")
        assert any("unknown-entity-c3d4" in i.message for i in issues)

    def test_scope_drift_long_text(self):
        dd = DriftDetector(current_step=1)
        long_text = "x" * 6000
        issues = dd.detect(long_text)
        assert any(i.severity == Severity.INFO for i in issues)
        assert any("6000 characters" in i.message for i in issues)

    def test_scope_drift_short_text_no_issue(self):
        dd = DriftDetector(current_step=1)
        issues = dd.detect("Short text")
        assert len(issues) == 0

    def test_detect_format_drift_empty_data(self):
        dd = DriftDetector(current_step=1)
        issues = dd.detect_format_drift({})
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR

    def test_detect_format_drift_missing_title(self):
        dd = DriftDetector(current_step=1)
        issues = dd.detect_format_drift({"options": [{"description": "no title"}]})
        assert any("missing a title" in i.message for i in issues)


# ==================================================================
# ValidationResult tests
# ==================================================================


class TestValidationResult:
    def test_errors_property(self):
        result = ValidationResult(
            passed=False,
            issues=[
                ValidationIssue("schema", Severity.ERROR, "Missing name", field="name"),
                ValidationIssue("rules", Severity.WARNING, "Unusual value"),
            ],
        )
        assert len(result.errors) == 1
        assert len(result.warnings) == 1

    def test_error_fields_property(self):
        result = ValidationResult(
            passed=False,
            issues=[
                ValidationIssue("schema", Severity.ERROR, "Missing", field="name"),
                ValidationIssue("schema", Severity.ERROR, "Invalid", field="domain"),
                ValidationIssue("rules", Severity.WARNING, "Check this", field=""),
            ],
        )
        assert result.error_fields == {"name", "domain"}

    def test_format_for_retry(self):
        result = ValidationResult(
            passed=False,
            issues=[
                ValidationIssue("schema", Severity.ERROR, "Missing name", field="name"),
            ],
            drift_types=["format_drift"],
        )
        text = result.format_for_retry()
        assert "VALIDATION ERRORS" in text
        assert "[name]" in text
        assert "format_drift" in text

    def test_format_human_passed(self):
        result = ValidationResult(passed=True)
        assert result.format_human() == "Validation passed."

    def test_format_human_with_errors(self):
        result = ValidationResult(
            passed=False,
            issues=[
                ValidationIssue("schema", Severity.ERROR, "Bad field", field="name"),
            ],
        )
        text = result.format_human()
        assert "1 error" in text
        assert "Bad field" in text


# ==================================================================
# ValidationPipeline tests
# ==================================================================


class TestValidationPipeline:
    def test_validate_entity_missing_name(self):
        engine = MagicMock()
        engine.consistency_checker = MagicMock()
        engine.with_lock.return_value = {"schema": {"passed": True}, "rules": {"passed": True}, "semantic": {}}

        pipeline = ValidationPipeline(engine, current_step=7)
        result = pipeline.validate_entity({"domain": "storms"})
        assert not result.passed
        assert "name" in result.error_fields or "format_drift" in result.drift_types

    def test_validate_entity_with_name_passes(self):
        engine = MagicMock()
        engine.with_lock.return_value = {"schema": {"passed": True}, "rules": {"passed": True}, "semantic": {}}

        pipeline = ValidationPipeline(engine, current_step=7)
        result = pipeline.validate_entity({"name": "Thorin", "domain": "storms"})
        assert result.passed

    def test_validate_response_clean(self):
        engine = MagicMock()
        pipeline = ValidationPipeline(engine, current_step=5)
        result = pipeline.validate_response("Here is the answer for step 5.")
        assert result.passed

    def test_validate_response_with_drift(self):
        engine = MagicMock()
        pipeline = ValidationPipeline(engine, current_step=3)
        result = pipeline.validate_response("Let me skip ahead to Step 50.")
        assert len(result.issues) > 0

    def test_validate_options_empty(self):
        engine = MagicMock()
        engine.with_lock.return_value = {"schema": {"passed": True}, "rules": {"passed": True}, "semantic": {}}
        pipeline = ValidationPipeline(engine, current_step=7)
        result = pipeline.validate_options({"options": []})
        assert not result.passed
        assert any("No options" in i.message for i in result.issues)


# ==================================================================
# Helper tests
# ==================================================================


class TestExtractField:
    def test_required_property_pattern(self):
        assert _extract_field("'name' is a required property") == "name"

    def test_dollar_dot_pattern(self):
        assert _extract_field("$.alignment: invalid value") == "alignment"

    def test_field_pattern(self):
        assert _extract_field("Field 'domain' must be a string") == "domain"

    def test_no_match(self):
        assert _extract_field("Some generic error") == ""
