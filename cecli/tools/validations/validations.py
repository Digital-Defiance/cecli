"""
Tool parameter validation module for BaseTool subclasses.

Provides a framework for declarative parameter validation via VALIDATIONS dicts
on tool classes, along with built-in validation methods.

The VALIDATIONS dict maps parameter paths (dot-separated, optionally with []
for list iteration) to lists of validation method names that are executed
sequentially on the parameter value.

Example::

    VALIDATIONS = {
        "delegations": ["coerce_list"],
        "delegations[]": ["coerce_dict"],
        "edits": ["coerce_list"],
        "edits[].file_path": ["coerce_str"],
    }
"""

from __future__ import annotations

import json

from cecli.helpers import responses
from cecli.tools.utils.helpers import ToolError


class ToolValidations:
    """
    Registry of validation methods for tool parameters.

    Each classmethod in this class can be referenced by name in a tool's
    VALIDATIONS dict. The ``validate_params`` classmethod orchestrates
    the application of validations based on the dict.
    """

    @classmethod
    def validate_params(cls, params: dict, validations: dict, schema: dict | None = None) -> dict:
        """
        Apply validations to *params* according to the *validations* dict.

        Parameters are modified in place and also returned for convenience.

        Args:
            params: The raw tool parameters dict.
            validations: A VALIDATIONS dict mapping parameter paths to
                lists of validation method names.
            schema: The tool's SCHEMA dict (used for context, currently
                reserved for future use).

        Returns:
            The (possibly mutated) *params* dict.
        """
        # Apply basic structural corrections before declarative validations
        params = cls._basic_validations(params, schema)

        if not validations:
            return params

        for raw_key, method_names in validations.items():
            # Determine whether the key targets list items (trailing "[]")
            iterate_over_list = raw_key.endswith("[]")
            clean_key = raw_key.rstrip("[]")

            # Split on dots to get the navigation path into params
            path = clean_key.split(".") if clean_key else []

            if not path:
                continue

            if iterate_over_list:
                cls._apply_validations_to_list_items(params, path, method_names)
            else:
                cls._apply_validations_to_value(params, path, method_names)

        return params

    @classmethod
    def _basic_validations(cls, params: object, schema: dict | None = None) -> dict:
        """
        Apply basic structural corrections to *params* based on *schema*.

        If the schema declares exactly one property of type ``array`` and
        *params* is itself a list (i.e. the LLM emitted the array directly
        instead of wrapping it as ``{param_name: [...]}``), wrap the list
        into the expected dict form.

        Returns the (possibly corrected) *params* dict.
        """
        # Only apply when params is a bare list (LLM forgot the wrapping dict)
        if not isinstance(params, list):
            return params

        if not schema or "function" not in schema:
            return params

        function_schema = schema["function"]
        if "parameters" not in function_schema:
            return params

        parameters = function_schema["parameters"]
        properties = parameters.get("properties", {})

        # Only auto-correct when there is exactly one property and it is an array
        if len(properties) == 1:
            single_param_name = next(iter(properties.keys()))
            param_schema = properties[single_param_name]
            if param_schema.get("type") == "array":
                return {single_param_name: params}

        return params

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_nested(params: dict, path: list[str]) -> tuple[dict | list, str] | None:
        """
        Navigate *params* along *path* and return ``(container, last_key)``.

        Returns ``None`` if any intermediate key is missing or isn't a dict.
        """
        current: dict | list = params
        for key in path[:-1]:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        if isinstance(current, dict):
            return current, path[-1]
        return None

    @staticmethod
    def _set_nested(params: dict, path: list[str], value: object) -> None:
        """Set *value* at the nested location described by *path* in *params*."""
        current = params
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    @classmethod
    def _apply_validations_to_value(
        cls, params: dict, path: list[str], method_names: list[str]
    ) -> None:
        """Apply the named validations sequentially to the value at *path*."""
        result = cls._get_nested(params, path)
        if result is None:
            return
        container, last_key = result
        if last_key not in container:
            return
        value = container[last_key]

        for method_name in method_names:
            method = getattr(cls, method_name, None)
            if method is None:
                raise ToolError(f"Unknown validation method: {method_name}")
            value = method(value)
            if value is None:
                # Validation chose to drop the value entirely
                container[last_key] = value
                return

        container[last_key] = value

    @classmethod
    def _apply_validations_to_list_items(
        cls, params: dict, path: list[str], method_names: list[str]
    ) -> None:
        """Apply validations to each item of the list found at *path*."""
        result = cls._get_nested(params, path)
        if result is None:
            return
        container, last_key = result
        if last_key not in container:
            return
        items = container[last_key]

        if not isinstance(items, list):
            return

        new_items: list = []
        for item in items:
            for method_name in method_names:
                method = getattr(cls, method_name, None)
                if method is None:
                    raise ToolError(f"Unknown validation method: {method_name}")
                item = method(item)
                if item is None:
                    break
            if item is not None:
                new_items.append(item)

        container[last_key] = new_items

    # ------------------------------------------------------------------
    # Built-in validation methods
    # ------------------------------------------------------------------

    @classmethod
    def coerce_list(cls, item: object) -> list:
        """
        Coerce *item* into a list.

        * If *item* is already a list it is returned as-is (after checking
          for char-split JSON arrays).
        * If *item* is a string it is parsed as JSON.  A JSON array is
          returned directly; a JSON object is wrapped in a list.
        * If *item* is a dict it is wrapped in a list.
        * Otherwise an empty list is returned.
        """
        if isinstance(item, list):
            # Check for per-character-split JSON arrays first
            coerced = responses.try_join_char_split_json_array(item)
            if coerced is not None:
                return coerced
            # Single-element wrapping a JSON string of an array/object
            if len(item) == 1 and isinstance(item[0], str):
                if item[0].strip().startswith(("[", "{", '"')):
                    item = item[0]
                else:
                    return item
            else:
                return item

        if isinstance(item, str):
            text = item.strip()
            if not text:
                return []
            parsed = responses.try_parse_json_value(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
            return []

        if isinstance(item, dict):
            return [item]

        return []

    @classmethod
    def coerce_dict(cls, item: object) -> dict | None:
        """
        Coerce *item* into a dict.

        * If *item* is already a dict it is returned as-is.
        * If *item* is a string it is parsed as JSON; returns the dict if
          successful, otherwise ``None``.
        * All other types return ``None``.
        """
        if isinstance(item, dict):
            return item
        if isinstance(item, str):
            text = item.strip()
            if not text:
                return None
            parsed = responses.try_parse_json_value(text)
            if isinstance(parsed, dict):
                return parsed
            # Fallback: try standard json.loads
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                return None
            if isinstance(parsed, dict):
                return parsed
        return None

    @classmethod
    def coerce_str(cls, item: object) -> str | None:
        """Coerce *item* to a string, returning ``None`` if not possible."""
        if isinstance(item, str):
            return item
        if item is None:
            return None
        try:
            return str(item)
        except (ValueError, TypeError):
            return None

    @classmethod
    def coerce_int(cls, item: object) -> int | None:
        """Coerce *item* to an int, returning ``None`` if not possible."""
        if isinstance(item, int) and not isinstance(item, bool):
            return item
        if isinstance(item, (float, str)):
            try:
                return int(item)
            except (ValueError, TypeError):
                return None
        return None

    @classmethod
    def coerce_bool(cls, item: object) -> bool | None:
        """Coerce *item* to a bool, returning ``None`` if not possible."""
        if isinstance(item, bool):
            return item
        if isinstance(item, str):
            low = item.strip().lower()
            if low in ("true", "1", "yes"):
                return True
            if low in ("false", "0", "no"):
                return False
            return None
        if isinstance(item, int):
            return bool(item)
        return None
