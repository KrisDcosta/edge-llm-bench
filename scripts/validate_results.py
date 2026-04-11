#!/usr/bin/env python3
"""Validate JSONL run records against the repo schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class SchemaValidationError(Exception):
    """Raised when a value does not match the schema."""


class SchemaCompatibilityError(Exception):
    """Raised when the schema uses unsupported JSON Schema features."""


class MiniSchemaValidator:
    """Minimal JSON Schema validator for the subset used in run.schema.json."""

    SUPPORTED_TYPES = {"object", "string", "number", "integer", "boolean", "null"}
    SUPPORTED_SCHEMA_KEYS = {
        "$schema",
        "$defs",
        "$ref",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "else",
        "enum",
        "if",
        "maximum",
        "minLength",
        "minimum",
        "properties",
        "required",
        "then",
        "title",
        "type",
    }

    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self._ensure_schema_supported(self.schema, "$")

    def validate(self, value: Any) -> None:
        self._validate(value, self.schema, "$")

    def _validate(self, value: Any, schema: dict[str, Any], path: str) -> None:
        if "$ref" in schema:
            self._validate(value, self._resolve_ref(schema["$ref"]), path)
            return

        if "anyOf" in schema:
            if self._matches_any(value, schema["anyOf"], path):
                return
            raise SchemaValidationError(f"{path}: does not match any allowed schema")

        if "allOf" in schema:
            for subschema in schema["allOf"]:
                self._validate(value, subschema, path)

        if "if" in schema:
            if self._matches(value, schema["if"], path):
                if "then" in schema:
                    self._validate(value, schema["then"], path)
            elif "else" in schema:
                self._validate(value, schema["else"], path)

        expected_type = schema.get("type")
        if expected_type is not None:
            self._validate_type(value, expected_type, path)

        if "const" in schema and value != schema["const"]:
            raise SchemaValidationError(f"{path}: expected constant {schema['const']!r}")

        if "enum" in schema and value not in schema["enum"]:
            raise SchemaValidationError(
                f"{path}: expected one of {schema['enum']!r}, got {value!r}"
            )

        if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
            raise SchemaValidationError(
                f"{path}: expected string length >= {schema['minLength']}, got {len(value)}"
            )

        if self._is_number(value):
            if "minimum" in schema and value < schema["minimum"]:
                raise SchemaValidationError(
                    f"{path}: expected value >= {schema['minimum']}, got {value}"
                )
            if "maximum" in schema and value > schema["maximum"]:
                raise SchemaValidationError(
                    f"{path}: expected value <= {schema['maximum']}, got {value}"
                )

        if isinstance(value, dict):
            self._validate_object(value, schema, path)

    def _validate_object(self, value: dict[str, Any], schema: dict[str, Any], path: str) -> None:
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}: missing required property {key!r}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise SchemaValidationError(
                    f"{path}: unexpected properties {', '.join(repr(item) for item in extras)}"
                )

        for key, subschema in properties.items():
            if key in value:
                self._validate(value[key], subschema, f"{path}.{key}")

    def _matches_any(
        self, value: Any, schemas: list[dict[str, Any]], path: str
    ) -> bool:
        for subschema in schemas:
            if self._matches(value, subschema, path):
                return True
        return False

    def _matches(self, value: Any, schema: dict[str, Any], path: str) -> bool:
        try:
            self._validate(value, schema, path)
        except SchemaValidationError:
            return False
        return True

    def _resolve_ref(self, ref: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            raise SchemaValidationError(f"Unsupported schema reference: {ref}")

        target: Any = self.schema
        for part in ref[2:].split("/"):
            if not isinstance(target, dict) or part not in target:
                raise SchemaValidationError(f"Unresolvable schema reference: {ref}")
            target = target[part]

        if not isinstance(target, dict):
            raise SchemaValidationError(f"Schema reference does not resolve to an object: {ref}")
        return target

    def _validate_type(self, value: Any, expected_type: str, path: str) -> None:
        type_checks = {
            "object": isinstance(value, dict),
            "string": isinstance(value, str),
            "number": self._is_number(value),
            "integer": self._is_integer(value),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }
        if expected_type not in type_checks:
            raise SchemaValidationError(f"Unsupported schema type {expected_type!r}")
        if not type_checks[expected_type]:
            actual = type(value).__name__
            raise SchemaValidationError(
                f"{path}: expected {expected_type}, got {actual}"
            )

    @staticmethod
    def _is_integer(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    @classmethod
    def _is_number(cls, value: Any) -> bool:
        return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(
            value, float
        )

    def _ensure_schema_supported(self, schema: Any, path: str) -> None:
        if not isinstance(schema, dict):
            raise SchemaCompatibilityError(f"{path}: schema node must be an object")

        unknown_keys = sorted(set(schema) - self.SUPPORTED_SCHEMA_KEYS)
        if unknown_keys:
            raise SchemaCompatibilityError(
                f"{path}: unsupported schema keyword(s): {', '.join(repr(key) for key in unknown_keys)}"
            )

        if "$ref" in schema:
            ref = schema["$ref"]
            if not isinstance(ref, str) or not ref:
                raise SchemaCompatibilityError(f"{path}.$ref: expected non-empty string")
            sibling_keys = sorted(set(schema) - {"$ref"})
            if sibling_keys:
                raise SchemaCompatibilityError(
                    f"{path}: $ref cannot appear with sibling keyword(s): {', '.join(repr(key) for key in sibling_keys)}"
                )

        schema_uri = schema.get("$schema")
        if schema_uri is not None and not isinstance(schema_uri, str):
            raise SchemaCompatibilityError(f"{path}.$schema: expected string")

        title = schema.get("title")
        if title is not None and not isinstance(title, str):
            raise SchemaCompatibilityError(f"{path}.title: expected string")

        expected_type = schema.get("type")
        if expected_type is not None:
            if not isinstance(expected_type, str):
                raise SchemaCompatibilityError(f"{path}.type: expected supported string type")
            if expected_type not in self.SUPPORTED_TYPES:
                raise SchemaCompatibilityError(
                    f"{path}.type: unsupported type {expected_type!r}"
                )

        required = schema.get("required")
        if required is not None:
            if not isinstance(required, list):
                raise SchemaCompatibilityError(f"{path}.required: expected array of non-empty strings")
            for index, item in enumerate(required):
                if not isinstance(item, str) or not item:
                    raise SchemaCompatibilityError(
                        f"{path}.required[{index}]: expected non-empty string"
                    )

        enum_values = schema.get("enum")
        if enum_values is not None and not isinstance(enum_values, list):
            raise SchemaCompatibilityError(f"{path}.enum: expected array")

        additional_properties = schema.get("additionalProperties")
        if additional_properties is not None and not isinstance(additional_properties, bool):
            raise SchemaCompatibilityError(f"{path}.additionalProperties: expected boolean")

        min_length = schema.get("minLength")
        if min_length is not None:
            if not self._is_integer(min_length) or min_length < 0:
                raise SchemaCompatibilityError(
                    f"{path}.minLength: expected non-negative integer"
                )

        for keyword in ("minimum", "maximum"):
            bound = schema.get(keyword)
            if bound is not None and not self._is_number(bound):
                raise SchemaCompatibilityError(f"{path}.{keyword}: expected number")

        defs = schema.get("$defs")
        if defs is not None:
            if not isinstance(defs, dict):
                raise SchemaCompatibilityError(f"{path}.$defs: expected object")
            for key, subschema in defs.items():
                self._ensure_schema_supported(subschema, f"{path}.$defs.{key}")

        properties = schema.get("properties")
        if properties is not None:
            if not isinstance(properties, dict):
                raise SchemaCompatibilityError(f"{path}.properties: expected object")
            for key, subschema in properties.items():
                self._ensure_schema_supported(subschema, f"{path}.properties.{key}")

        for keyword in ("anyOf", "allOf"):
            subschemas = schema.get(keyword)
            if subschemas is None:
                continue
            if not isinstance(subschemas, list):
                raise SchemaCompatibilityError(f"{path}.{keyword}: expected array")
            for index, subschema in enumerate(subschemas):
                self._ensure_schema_supported(subschema, f"{path}.{keyword}[{index}]")

        for keyword in ("if", "then", "else"):
            subschema = schema.get(keyword)
            if subschema is not None:
                self._ensure_schema_supported(subschema, f"{path}.{keyword}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one or more JSONL files against schemas/run.schema.json."
    )
    parser.add_argument(
        "--schema",
        default=str(Path(__file__).resolve().parents[1] / "schemas" / "run.schema.json"),
        help="Schema file to use (defaults to schemas/run.schema.json).",
    )
    parser.add_argument("paths", nargs="+", help="One or more JSONL files to validate.")
    return parser.parse_args()


def load_schema(schema_path_str: str) -> dict[str, Any]:
    schema_path = Path(schema_path_str)
    try:
        with schema_path.open("r", encoding="utf-8") as handle:
            schema = json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"Schema file not found: {schema_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Schema file is not valid JSON: {schema_path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(schema, dict):
        raise SystemExit(f"Schema root must be a JSON object: {schema_path}")
    return schema


def validate_file(path_str: str, validator: MiniSchemaValidator) -> int:
    path = Path(path_str)
    errors = 0

    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.rstrip("\n")
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"{path}:{line_number}: malformed JSON: {exc.msg}",
                        file=sys.stderr,
                    )
                    errors += 1
                    continue

                if not isinstance(record, dict):
                    print(
                        f"{path}:{line_number}: schema validation failed: $: expected object, got {type(record).__name__}",
                        file=sys.stderr,
                    )
                    errors += 1
                    continue

                try:
                    validator.validate(record)
                except SchemaValidationError as exc:
                    print(
                        f"{path}:{line_number}: schema validation failed: {exc}",
                        file=sys.stderr,
                    )
                    errors += 1
    except FileNotFoundError:
        print(f"{path}: file not found", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{path}: could not read file: {exc}", file=sys.stderr)
        return 1

    return errors


def main() -> int:
    args = parse_args()
    try:
        validator = MiniSchemaValidator(load_schema(args.schema))
    except SchemaCompatibilityError as exc:
        print(f"Unsupported schema: {exc}", file=sys.stderr)
        return 1
    total_errors = 0

    for path_str in args.paths:
        total_errors += validate_file(path_str, validator)

    if total_errors:
        print(f"Validation failed with {total_errors} error(s).", file=sys.stderr)
        return 1

    print(f"Validated {len(args.paths)} file(s) successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
