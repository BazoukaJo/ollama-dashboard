"""Input validation and sanitization for Ollama Dashboard.

Provides validators for:
- Model names (alphanumeric + valid Ollama characters)
- Numeric inputs (with min/max bounds)
- JSON payloads (schema validation)
- Output sanitization (XSS prevention)
"""

import re
import html
import logging
from typing import Any, Tuple, Optional

logger = logging.getLogger(__name__)


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


class InputValidator:
    """Validates and sanitizes user inputs."""

    # Ollama model names: alphanumeric, hyphens, underscores, colons
    # Example: llama3.1:8b, llava-phi, custom-model
    MODEL_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9:._-]+$')

    @staticmethod
    def validate_model_name(model_name: str) -> Tuple[bool, str]:
        """Validate model name format.

        Args:
            model_name: Model name to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not model_name or not isinstance(model_name, str):
            return False, "Model name must be a non-empty string"

        if len(model_name) > 255:
            return False, "Model name too long (max 255 characters)"

        if not InputValidator.MODEL_NAME_PATTERN.match(model_name):
            return False, f"Invalid model name: {model_name}. Use alphanumeric, hyphens, underscores, colons, and periods."

        return True, ""

    @staticmethod
    def validate_integer(value: Any, min_val: Optional[int] = None, max_val: Optional[int] = None) -> Tuple[bool, str]:
        """Validate integer input with bounds.

        Args:
            value: Value to validate
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            int_val = int(value)
        except (ValueError, TypeError):
            return False, f"Expected integer, got {type(value).__name__}"

        if min_val is not None and int_val < min_val:
            return False, f"Value must be >= {min_val}"

        if max_val is not None and int_val > max_val:
            return False, f"Value must be <= {max_val}"

        return True, ""

    @staticmethod
    def validate_float(value: Any, min_val: Optional[float] = None, max_val: Optional[float] = None) -> Tuple[bool, str]:
        """Validate float input with bounds.

        Args:
            value: Value to validate
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            float_val = float(value)
        except (ValueError, TypeError):
            return False, f"Expected number, got {type(value).__name__}"

        if min_val is not None and float_val < min_val:
            return False, f"Value must be >= {min_val}"

        if max_val is not None and float_val > max_val:
            return False, f"Value must be <= {max_val}"

        return True, ""

    @staticmethod
    def validate_json_object(data: Any, required_fields: Optional[list] = None) -> Tuple[bool, str]:
        """Validate JSON object structure.

        Args:
            data: Object to validate
            required_fields: List of required field names

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(data, dict):
            return False, "Expected JSON object"

        if required_fields:
            missing = [f for f in required_fields if f not in data]
            if missing:
                return False, f"Missing required fields: {', '.join(missing)}"

        return True, ""

    @staticmethod
    def validate_json_array(data: Any, item_type: type = None) -> Tuple[bool, str]:
        """Validate JSON array structure.

        Args:
            data: Array to validate
            item_type: Expected type of array items (if uniform)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(data, list):
            return False, "Expected JSON array"

        if item_type and data:
            non_matching = [i for i, item in enumerate(data) if not isinstance(item, item_type)]
            if non_matching:
                return False, f"Array items must be {item_type.__name__}"

        return True, ""


class OutputSanitizer:
    """Sanitizes output to prevent XSS attacks."""

    @staticmethod
    def escape_html(text: str) -> str:
        """Escape HTML special characters.

        Converts:
        - < to &lt;
        - > to &gt;
        - & to &amp;
        - " to &quot;
        - ' to &#x27;

        Args:
            text: Text to escape

        Returns:
            HTML-safe text
        """
        if not isinstance(text, str):
            return str(text)
        return html.escape(text, quote=True)

    @staticmethod
    def escape_json_string(text: str) -> str:
        """Escape text for safe inclusion in JSON.

        Args:
            text: Text to escape

        Returns:
            JSON-safe text
        """
        import json
        return json.dumps(text)[1:-1]  # Remove outer quotes

    @staticmethod
    def sanitize_model_name_for_display(model_name: str) -> str:
        """Sanitize model name for HTML display.

        Args:
            model_name: Model name to sanitize

        Returns:
            HTML-safe model name
        """
        # Model names shouldn't contain HTML, but be defensive
        return OutputSanitizer.escape_html(model_name)

    @staticmethod
    def sanitize_dict(data: dict) -> dict:
        """Recursively sanitize dictionary values for HTML.

        Args:
            data: Dictionary to sanitize

        Returns:
            Dictionary with HTML-escaped string values
        """
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = OutputSanitizer.escape_html(value)
            elif isinstance(value, dict):
                sanitized[key] = OutputSanitizer.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    OutputSanitizer.escape_html(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                sanitized[key] = value
        return sanitized
