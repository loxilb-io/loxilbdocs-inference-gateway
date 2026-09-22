#!/usr/bin/env python3
"""Validate executable examples in the public Markdown documentation."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft4Validator, FormatChecker


MAIN_ONLY_MARKER = "CLI availability: main-only"
EXPECTED_SCHEMA_FAILURE_MARKER = "docs-example: expect-schema-error"
JWT_AUTH_MODES = {"jwt", "apikey-or-jwt"}
JWT_ALGORITHMS = {
    "RS256", "RS384", "RS512",
    "ES256", "ES384", "ES512",
    "PS256", "PS384", "PS512",
}
PLACEHOLDER_VALUES = {
    "id": "1",
    "ep-idx": "0",
    "port": "8080",
    "vip": "192.0.2.10",
    "host": "gateway.example.com",
    "loxilb": "192.0.2.10",
    "loxilb-host": "192.0.2.10",
    "node-ip": "198.51.100.10",
    "endpoint-ip": "198.51.100.11",
    "prefill-1-ip": "198.51.100.11",
    "prefill-2-ip": "198.51.100.12",
    "decode-1-ip": "198.51.100.21",
    "gpu": "example-gpu",
}
REFERENCED_BODY_FIXTURES = {
    "gateway-snapshot.json": {},
    "initial-gateway-user.json": {
        "username": "docs-admin",
        "password": "placeholder-passphrase",
        "role": "admin",
    },
}
PROMETHEUS_TARGET_LABELS = {"instance", "job"}
PROMQL_METRIC = re.compile(
    r"\b(?P<name>(?:loxilb|doca)_[A-Za-z0-9_:]+)"
    r"(?:\{(?P<selectors>[^{}]*)\})?"
)
PROMQL_SELECTOR = re.compile(
    r'(?P<label>[A-Za-z_][A-Za-z0-9_]*)\s*'
    r'(?P<operator>=~|!~|!=|=)\s*"(?P<value>(?:\\.|[^"\\])*)"'
)


@dataclass(frozen=True)
class Block:
    path: Path
    line: int
    language: str
    text: str

    @property
    def location(self) -> str:
        return f"{self.path.as_posix()}:{self.line}"


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def count(self, name: str, amount: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + amount

    def error(self, location: str, message: str) -> None:
        self.errors.append(f"{location}: {message}")


def substitute_placeholders(text: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return PLACEHOLDER_VALUES.get(key, "example")

    return re.sub(r"<([A-Za-z][A-Za-z0-9_.-]*)>", replacement, text)


def markdown_blocks(path: Path) -> Iterable[Block]:
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        opening = re.match(r"^(?P<indent>\s*)```\s*(?P<language>[A-Za-z0-9_+-]*)\s*$", lines[index])
        if not opening:
            index += 1
            continue
        indent = opening.group("indent")
        language = opening.group("language").lower()
        start_line = index + 2
        index += 1
        body: list[str] = []
        while index < len(lines) and not re.match(r"^\s*```\s*$", lines[index]):
            line = lines[index]
            body.append(line[len(indent) :] if line.startswith(indent) else line)
            index += 1
        yield Block(path, start_line, language, textwrap.dedent("\n".join(body)))
        index += 1


def extract_shell_commands(text: str, executable: str) -> list[str]:
    """Extract shell commands while retaining quoted multiline JSON bodies."""
    commands: list[str] = []
    pattern = re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(executable)}(?=\s)")
    cursor = 0
    while True:
        match = pattern.search(text, cursor)
        if not match:
            break
        line_prefix = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
        if line_prefix.lstrip().startswith("#"):
            cursor = match.end()
            continue
        index = match.start()
        quote: str | None = None
        escaped = False
        while index < len(text):
            char = text[index]
            if escaped:
                escaped = False
                index += 1
                continue
            if char == "\\":
                escaped = True
                index += 1
                continue
            if quote:
                if char == quote:
                    quote = None
                index += 1
                continue
            if char in {"'", '"'}:
                quote = char
                index += 1
                continue
            if index > match.start() and char in {"\n", ";", "|"}:
                break
            if index > match.start() and char == "&" and index + 1 < len(text) and text[index + 1] == "&":
                break
            index += 1
        commands.append(text[match.start() : index].strip())
        cursor = max(index + 1, match.end())
    return commands


def shell_tokens(command: str) -> list[str]:
    continued = re.sub(r"\\\n\s*", " ", command)
    if continued.rstrip().endswith("\\"):
        continued = continued.rstrip()[:-1]
    return shlex.split(substitute_placeholders(continued), comments=True, posix=True)


class ExampleValidator:
    def __init__(
        self,
        root: Path,
        require_external_tools: bool = True,
        contract_dir: Path | None = None,
    ) -> None:
        self.root = root
        contract_dir = contract_dir or root / "tests/contracts/docs_examples"
        self.cli_contract = json.loads((contract_dir / "cli.json").read_text())
        self.gateway_contract = json.loads((contract_dir / "gateway-api.json").read_text())
        self.metric_manifest = {
            family["name"]: family
            for family in self.gateway_contract.get("metric_manifest", {}).get(
                "families", []
            )
            if family.get("release_scope") == "release"
        }
        self.metric_label_enums = self.gateway_contract.get(
            "metric_manifest", {}
        ).get("label_enums", {})
        self.require_external_tools = require_external_tools

    def _metric_family(self, name: str) -> tuple[str, dict[str, Any] | None]:
        family = self.metric_manifest.get(name)
        if family is not None:
            return name, family
        for suffix in ("_bucket", "_sum", "_count", "_created"):
            if not name.endswith(suffix):
                continue
            base = name[: -len(suffix)]
            candidate = self.metric_manifest.get(base)
            if candidate and candidate.get("type") == "histogram":
                return base, candidate
        return name, None

    def validate_promql(self, expression: str) -> list[str]:
        """Validate documented metric names, selector labels, and closed enums."""
        errors: list[str] = []
        for match in PROMQL_METRIC.finditer(expression):
            rendered_name = match.group("name")
            family_name, family = self._metric_family(rendered_name)
            if family is None:
                errors.append(
                    f"metric is absent from the frozen release-scope manifest: {rendered_name}"
                )
                continue
            selectors = match.group("selectors") or ""
            allowed_labels = set(family.get("labels", [])) | PROMETHEUS_TARGET_LABELS
            if rendered_name.endswith("_bucket"):
                allowed_labels.add("le")
            for selector in PROMQL_SELECTOR.finditer(selectors):
                label = selector.group("label")
                operator = selector.group("operator")
                value = selector.group("value")
                if label not in allowed_labels:
                    errors.append(
                        f"label {label!r} is absent from metric {family_name}; "
                        f"expected one of {sorted(allowed_labels)}"
                    )
                    continue
                allowed_values = self.metric_label_enums.get(family_name, {}).get(label)
                if allowed_values and operator in {"=", "!="} and value not in allowed_values:
                    errors.append(
                        f"invalid {family_name} label {label}={value!r}; "
                        f"expected one of {sorted(allowed_values)}"
                    )
        return errors

    def validate_cli_command(self, command: str, context: str = "") -> list[str]:
        errors: list[str] = []
        try:
            tokens = shell_tokens(command)
        except ValueError as exc:
            return [f"cannot parse loxicmd command: {exc}"]
        if not tokens or tokens[0] != "loxicmd":
            return ["expected a loxicmd command"]

        args = tokens[1:]
        commands = self.cli_contract["commands"]
        command_name = next(
            (
                name
                for name in sorted(commands, key=lambda value: len(value.split()), reverse=True)
                if args[: len(name.split())] == name.split()
            ),
            None,
        )
        if command_name is None:
            return [f"unknown CLI command path: {' '.join(args[:2])}"]

        contract = commands[command_name]
        main = contract["main"]
        release = contract["release"]
        if not main["available"]:
            errors.append(f"CLI command is absent from frozen main: {command_name}")
            return errors
        if not release["available"] and MAIN_ONLY_MARKER not in context:
            errors.append(f"main-only CLI command lacks '{MAIN_ONLY_MARKER}' marker: {command_name}")

        known_main_flags = set(main["flags"])
        known_release_flags = set(release["flags"])
        enum_contracts = contract.get("enums", {})
        path_length = len(command_name.split())
        index = path_length
        while index < len(args):
            token = args[index]
            if not token.startswith("--"):
                index += 1
                continue
            flag, separator, value = token.partition("=")
            if flag not in known_main_flags:
                errors.append(f"flag is absent from frozen main for '{command_name}': {flag}")
                index += 1
                continue
            if flag not in known_release_flags and MAIN_ONLY_MARKER not in context:
                errors.append(f"main-only flag lacks '{MAIN_ONLY_MARKER}' marker: {flag}")
            if not separator and flag in enum_contracts and index + 1 < len(args):
                value = args[index + 1]
                index += 1
            if flag in enum_contracts and value:
                allowed = set(enum_contracts[flag])
                supplied = value.split(",") if "," in value else [value]
                invalid = [item for item in supplied if item not in allowed]
                if invalid:
                    errors.append(
                        f"invalid {flag} value {','.join(invalid)!r}; expected one of {sorted(allowed)}"
                    )
            index += 1
        return errors

    @staticmethod
    def _template_regex(path_template: str) -> re.Pattern[str]:
        parts = re.split(r"(\{[^}/]+\})", path_template)
        expression = "".join("[^/]+" if part.startswith("{") else re.escape(part) for part in parts)
        return re.compile(rf"^{expression}$")

    def matching_operations(self, method: str, route: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for spec in self.gateway_contract["specs"]:
            for template, operations in spec["paths"].items():
                if self._template_regex(template).match(route) and method.lower() in operations:
                    matches.append((spec, operations[method.lower()]))
        return matches

    def validate_route(self, method: str, route: str) -> list[str]:
        if self.matching_operations(method, route):
            return []
        return [f"{method.upper()} {route} is absent from the frozen Swagger union"]

    @staticmethod
    def _resolve_parameter(spec: dict[str, Any], parameter: dict[str, Any]) -> dict[str, Any]:
        reference = parameter.get("$ref")
        if reference and reference.startswith("#/parameters/"):
            return spec.get("parameters", {}).get(reference.rsplit("/", 1)[-1], parameter)
        return parameter

    def validate_json_body(self, method: str, route: str, body: Any) -> list[str]:
        errors: list[str] = []
        matches = self.matching_operations(method, route)
        if not matches:
            return self.validate_route(method, route)
        schemas: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for spec, operation in matches:
            for raw_parameter in operation.get("parameters", []):
                parameter = self._resolve_parameter(spec, raw_parameter)
                if parameter.get("in") == "body" and parameter.get("schema"):
                    schemas.append((spec, parameter["schema"]))
        if not schemas:
            return errors
        for spec, schema in schemas:
            validation_schema = {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "definitions": spec.get("definitions", {}),
                "allOf": [schema],
            }
            validator = Draft4Validator(validation_schema, format_checker=FormatChecker())
            for failure in sorted(validator.iter_errors(body), key=lambda item: list(item.path)):
                pointer = "/" + "/".join(str(value) for value in failure.path)
                errors.append(f"request body {pointer}: {failure.message}")
        errors.extend(self.validate_contract_semantics(method, route, body))
        return errors

    def validate_contract_semantics(self, method: str, route: str, body: Any) -> list[str]:
        """Validate implementation invariants that OpenAPI 2.0 does not encode."""
        if not isinstance(body, dict):
            return []

        def is_positive_number(value: Any) -> bool:
            return (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value > 0
            )

        errors: list[str] = []
        normalized_method = method.upper()
        if normalized_method == "PATCH" and re.fullmatch(
            r"/config/ai/apikey/[^/]+", route
        ):
            patchable = {
                "allowed_models", "enabled", "rate_limit_rps",
                "burst_size", "tokens_per_min",
            }
            if not any(field in body and body[field] is not None for field in patchable):
                errors.append("API-key PATCH must name at least one non-null patchable field")
            for field in ("rate_limit_rps", "burst_size", "tokens_per_min"):
                value = body.get(field)
                if (
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and value < 0
                ):
                    errors.append(f"{field} must not be negative")
            return errors

        if normalized_method != "POST":
            return errors

        if route == "/config/loadbalancer":
            args = body.get("serviceArguments")
            if not isinstance(args, dict):
                return errors
            policy = args.get("api_key_auth")
            profile = args.get("jwt_auth_profile")
            if policy in JWT_AUTH_MODES and not isinstance(profile, str):
                errors.append(f"api_key_auth {policy!r} requires jwt_auth_profile")
            elif policy in JWT_AUTH_MODES and not profile:
                errors.append(f"api_key_auth {policy!r} requires a non-empty jwt_auth_profile")
            elif policy not in JWT_AUTH_MODES and isinstance(profile, str) and profile:
                errors.append("jwt_auth_profile is valid only with api_key_auth 'jwt' or 'apikey-or-jwt'")

            exact_mode = args.get("kvExactMode", 0)
            pd_enabled = args.get("pd_disagg_mode") is True
            if exact_mode not in {0, 1, 3}:
                errors.append("kvExactMode must be one of 0, 1, or 3")
            elif exact_mode == 1 and not pd_enabled:
                errors.append("kvExactMode 1 requires pd_disagg_mode true")
            elif exact_mode == 3 and pd_enabled:
                errors.append("kvExactMode 3 is incompatible with pd_disagg_mode true")
            if exact_mode in {1, 3} and args.get("mode") != 4:
                errors.append("KV-exact routing requires fullproxy mode 4")
            if "kvExactApiMode" in args and exact_mode not in {1, 3}:
                errors.append("kvExactApiMode is meaningful only with KV-exact routing")
            if "kvModelProfile" in args and exact_mode not in {1, 3}:
                errors.append("kvModelProfile is meaningful only with KV-exact routing")
            if args.get("kvEngineType") == "llamacpp" and (
                exact_mode in {1, 3} or pd_enabled
            ):
                errors.append("llamacpp does not support KV-exact or P/D routing")

            sockmap_mode = args.get("sockMapMode", "off")
            if sockmap_mode != "off":
                if args.get("mode") != 4 or args.get("protocol") != "tcp":
                    errors.append("sockmap acceleration requires TCP fullproxy mode 4")
                if args.get("sse_mode") is True:
                    errors.append("sockmap acceleration is incompatible with sse_mode")
                if pd_enabled:
                    errors.append("sockmap acceleration is incompatible with pd_disagg_mode")
                if "api_key_auth" in args:
                    errors.append("sockmap acceleration is incompatible with any api_key_auth declaration")

        elif route == "/config/ai/jwtauthprofile":
            name = body.get("name")
            if isinstance(name, str) and len(name.encode("utf-8")) > 63:
                errors.append("JWT profile name exceeds the implementation's 63-byte limit")
            for field in ("leeway_sec", "refresh_sec"):
                value = body.get(field)
                if isinstance(value, int) and value < 0:
                    errors.append(f"{field} must not be negative")
            algs = body.get("algs")
            if isinstance(algs, list):
                invalid = [value for value in algs if value not in JWT_ALGORITHMS]
                if invalid:
                    errors.append(f"unsupported JWT algorithms: {invalid}")

        elif route == "/config/ai/user/ratelimit":
            models = body.get("model_limits", [])
            if isinstance(models, list):
                for index, entry in enumerate(models):
                    if not isinstance(entry, dict) or not entry.get("model"):
                        errors.append(f"model_limits/{index} requires a non-empty model")
            deciding = any(
                is_positive_number(body.get(field))
                for field in ("rps", "tokens_per_min")
            )
            if isinstance(models, list):
                deciding = deciding or any(
                    isinstance(entry, dict)
                    and is_positive_number(entry.get("tokens_per_min"))
                    for entry in models
                )
            if not deciding:
                errors.append("user rate-limit row must contain at least one non-zero limit")

        elif route == "/config/ai/tenant/ratelimit":
            models = body.get("model_limits", [])
            if isinstance(models, list):
                for index, entry in enumerate(models):
                    if not isinstance(entry, dict) or not entry.get("model"):
                        errors.append(f"model_limits/{index} requires a non-empty model")

        elif route == "/config/ai/ratelimit/defaults":
            scope = body.get("scope")
            rule_ident = body.get("rule_ident", "")
            if scope == "global" and rule_ident:
                errors.append("global defaults must not carry rule_ident")
            elif scope == "rule" and not rule_ident:
                errors.append("rule defaults require rule_ident")
            limit_fields = (
                "default_user_rps", "default_user_tpm",
                "default_tenant_rps", "default_tenant_tpm",
                "vip_shared_rps", "vip_shared_tpm",
            )
            if not any(is_positive_number(body.get(field)) for field in limit_fields):
                errors.append("rate-limit defaults row must contain at least one non-zero limit")
        return errors

    @staticmethod
    def validate_curl_credential_hygiene(command: str) -> list[str]:
        """Reject secret-bearing HTTP headers placed directly in curl argv."""
        try:
            tokens = shell_tokens(command)
        except ValueError as exc:
            return [f"cannot parse curl command: {exc}"]
        header_values: list[str] = []
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token in {"-H", "--header"} and index + 1 < len(tokens):
                header_values.append(tokens[index + 1])
                index += 2
                continue
            if token.startswith("--header="):
                header_values.append(token.split("=", 1)[1])
            elif token.startswith("-H") and len(token) > 2:
                header_values.append(token[2:])
            index += 1
        errors: list[str] = []
        for value in header_values:
            lowered = value.strip().lower()
            if lowered.startswith("authorization: bearer "):
                errors.append("management or JWT bearer credential is exposed in curl argv; use a protected header file")
            elif lowered.startswith("x-api-key:") and value.partition(":")[2].strip():
                errors.append("API key is exposed in curl argv; use a protected header file")
        return errors

    @staticmethod
    def _curl_details(command: str) -> tuple[str, str | None, str | None]:
        tokens = shell_tokens(command)
        method: str | None = None
        url: str | None = None
        body: str | None = None
        has_data = False
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token in {"-X", "--request"} and index + 1 < len(tokens):
                method = tokens[index + 1].upper()
                index += 2
                continue
            if token.startswith("--request="):
                method = token.split("=", 1)[1].upper()
            elif token.startswith("-X") and len(token) > 2:
                method = token[2:].upper()
            elif token in {"-I", "--head"}:
                method = "HEAD"
            elif token in {"-d", "--data", "--data-raw", "--data-binary"} and index + 1 < len(tokens):
                has_data = True
                body = tokens[index + 1]
                index += 2
                continue
            elif any(token.startswith(prefix) for prefix in ("--data=", "--data-raw=", "--data-binary=")):
                has_data = True
                body = token.split("=", 1)[1]
            elif token.startswith(("http://", "https://", "$CONTROL_API", "${CONTROL_API}", "$GATEWAY_API", "${GATEWAY_API}")):
                url = token.rstrip(");")
            index += 1
        return method or ("POST" if has_data else "GET"), url, body

    @staticmethod
    def _management_route(url: str | None) -> str | None:
        if not url:
            return None
        if url.startswith("${CONTROL_API}"):
            path = url[len("${CONTROL_API}") :]
        elif url.startswith("$CONTROL_API"):
            path = url[len("$CONTROL_API") :]
        elif url.startswith("${GATEWAY_API}"):
            path = url[len("${GATEWAY_API}") :]
        elif url.startswith("$GATEWAY_API"):
            path = url[len("$GATEWAY_API") :]
        else:
            path = urlsplit(url).path
        if "/netlox/v1" in path:
            path = path.split("/netlox/v1", 1)[1]
        elif not url.startswith(("$CONTROL_API", "${CONTROL_API}")):
            return None
        if not path:
            path = "/"
        return path.split("?", 1)[0]

    def _run_tool(self, report: ValidationReport, location: str, args: list[str], text: str) -> None:
        if shutil.which(args[0]) is None:
            if self.require_external_tools:
                report.error(location, f"required validator is not installed: {args[0]}")
            return
        process = subprocess.run(args, input=text, text=True, capture_output=True)
        if process.returncode:
            detail = (process.stderr or process.stdout).strip().splitlines()
            report.error(location, f"{' '.join(args)} failed: {detail[0] if detail else 'unknown error'}")

    def _validate_yaml_tool(self, report: ValidationReport, block: Block, text: str) -> None:
        if shutil.which("yq") is None:
            if self.require_external_tools:
                report.error(block.location, "required validator is not installed: yq")
            return
        version = subprocess.run(["yq", "--version"], text=True, capture_output=True)
        command = ["yq", "eval", ".", "-"] if "mikefarah" in (version.stdout + version.stderr).lower() else ["yq", "."]
        self._run_tool(report, block.location, command, text)

    def validate_repository(self) -> ValidationReport:
        report = ValidationReport()
        blocks: list[Block] = []
        for path in sorted((self.root / "docs").rglob("*.md")):
            for block in markdown_blocks(path):
                blocks.append(
                    Block(block.path.relative_to(self.root), block.line, block.language, block.text)
                )
        report.count("fenced_blocks", len(blocks))

        for block in blocks:
            safe_text = substitute_placeholders(block.text)
            if block.language in {"bash", "sh", "shell"}:
                report.count("bash_blocks")
                self._run_tool(report, block.location, ["bash", "-n", "-"], safe_text)
            elif block.language == "json":
                report.count("json_blocks")
                try:
                    json.loads(safe_text)
                except json.JSONDecodeError as exc:
                    report.error(block.location, f"invalid JSON: {exc.msg} at line {exc.lineno}")
                else:
                    self._run_tool(report, block.location, ["jq", "empty"], safe_text)
            elif block.language in {"yaml", "yml"}:
                report.count("yaml_blocks")
                try:
                    yaml.safe_load(safe_text)
                except yaml.YAMLError as exc:
                    report.error(block.location, f"invalid YAML: {str(exc).splitlines()[0]}")
                else:
                    self._validate_yaml_tool(report, block, safe_text)
            elif block.language == "promql":
                report.count("promql_blocks")
                for error in self.validate_promql(block.text):
                    report.error(block.location, error)

            for command in extract_shell_commands(block.text, "loxicmd"):
                report.count("loxicmd_commands")
                for error in self.validate_cli_command(command, block.text):
                    report.error(block.location, error)

            for command in extract_shell_commands(block.text, "curl"):
                report.count("curl_commands")
                for error in self.validate_curl_credential_hygiene(command):
                    report.error(block.location, error)
                try:
                    method, url, body_text = self._curl_details(command)
                except ValueError as exc:
                    report.error(block.location, f"cannot parse curl command: {exc}")
                    continue
                route = self._management_route(url)
                if route is None:
                    report.count("curl_external")
                    continue
                report.count("management_routes")
                for error in self.validate_route(method, route):
                    report.error(block.location, error)
                if body_text is None:
                    continue
                if body_text.startswith("@"):
                    fixture_name = Path(body_text[1:]).name
                    if fixture_name not in REFERENCED_BODY_FIXTURES:
                        report.error(block.location, f"referenced JSON body lacks a safe fixture: {fixture_name}")
                        continue
                    report.count("substituted_request_bodies")
                    body = REFERENCED_BODY_FIXTURES[fixture_name]
                elif body_text.startswith("$"):
                    report.error(block.location, "variable JSON body lacks a safe fixture")
                    continue
                else:
                    stripped = body_text.strip()
                    if not stripped.startswith(("{", "[")):
                        continue
                    report.count("inline_json_request_bodies")
                    try:
                        body = json.loads(substitute_placeholders(stripped))
                    except json.JSONDecodeError as exc:
                        report.error(block.location, f"invalid inline JSON request body: {exc.msg}")
                        continue
                self._run_tool(report, block.location, ["jq", "empty"], json.dumps(body))
                schema_errors = self.validate_json_body(method, route, body)
                expects_schema_error = EXPECTED_SCHEMA_FAILURE_MARKER in block.text
                if expects_schema_error:
                    if schema_errors:
                        report.count("expected_schema_rejections")
                    else:
                        report.error(block.location, "expected request-schema rejection was not detected")
                else:
                    for error in schema_errors:
                        report.error(block.location, error)
        return report


def print_report(report: ValidationReport) -> None:
    order = (
        "fenced_blocks",
        "bash_blocks",
        "json_blocks",
        "yaml_blocks",
        "promql_blocks",
        "loxicmd_commands",
        "curl_commands",
        "management_routes",
        "inline_json_request_bodies",
        "substituted_request_bodies",
        "expected_schema_rejections",
        "curl_external",
    )
    for name in order:
        print(f"{name}: {report.counts.get(name, 0)}")
    if report.errors:
        print("\nValidation failures:", file=sys.stderr)
        for error in report.errors:
            print(f"- {error}", file=sys.stderr)
        print(f"\nRESULT: FAIL ({len(report.errors)} errors)", file=sys.stderr)
    else:
        print("RESULT: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--contract-dir",
        type=Path,
        help="contract directory to validate against instead of the tracked snapshot",
    )
    parser.add_argument(
        "--allow-missing-tools",
        action="store_true",
        help="skip external bash/jq/yq checks when a command is unavailable",
    )
    args = parser.parse_args()
    validator = ExampleValidator(
        args.root.resolve(),
        not args.allow_missing_tools,
        args.contract_dir.resolve() if args.contract_dir else None,
    )
    report = validator.validate_repository()
    print_report(report)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
