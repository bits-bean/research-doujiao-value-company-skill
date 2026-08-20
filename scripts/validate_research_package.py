#!/usr/bin/env python3
"""Validate a Doujiao research package with fail-closed, stdlib-only gates."""

from __future__ import annotations

import argparse
import ast
from difflib import SequenceMatcher
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REQUIRED_FILES = (
    "research-report.md",
    "company.json",
    "research-completeness.md",
    "evidence-ledger.json",
    "calculation-ledger.json",
)
FROZEN_HASH_FILES = REQUIRED_FILES + ("validation-report.json",)
EXPECTED_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_ID = "https://doujiao-value-system/schemas/company.schema.json"
EXPECTED_SPEC_REPOSITORY = "bits-bean/doujiao-value-system"
EXPECTED_SCHEMA_PATH = "schemas/company.schema.json"
SKILL_ROOT = Path(__file__).resolve().parents[1]
TRUSTED_SPEC_LOCK_PATH = SKILL_ROOT / "references" / "trusted-spec-lock.json"
EXPECTED_PROTOCOL_AUTHORITY = "research-doujiao-value-company"
EXPECTED_PROTOCOL_REPOSITORY = "bits-bean/doujiao-value-research-skill"
PROTOCOL_DOCUMENT_PATHS = (
    "references/specs/automation-workflow.md",
    "references/specs/project-instructions.md",
    "references/specs/research-methodology.md",
)
BUNDLED_SCHEMA_PATH = "references/specs/company.schema.json"
TRUSTED_LOCK_KEYS = {"lock_version", "research_protocol", "company_schema"}
RESEARCH_PROTOCOL_KEYS = {
    "authority",
    "repository",
    "ref",
    "commit",
    "protocol_version",
    "digest_sha256",
    "documents",
}
COMPANY_SCHEMA_KEYS = {
    "repository",
    "ref",
    "commit",
    "path",
    "blob_sha1",
    "sha256",
    "size_bytes",
    "schema_version",
    "bundled_path",
}
CLASSIFICATIONS = {"fact", "management_claim", "third_party", "inference", "estimate"}
CONFIDENCE = {"high", "medium", "low"}
VERDICT_CONFIDENCE = CONFIDENCE | {"高", "中", "低"}
BUSINESS_QUALITY = {"优秀", "良好", "一般", "较差", "无法判断"}
VALUATION_STATUS = {"明显低估", "可能低估", "接近合理", "偏高", "无法判断"}
RESEARCH_STATUS = {"深入研究", "观察名单", "等待价格", "放弃", "Too Hard"}
PRIMARY_SOURCE_TYPES = {"annual_report", "quarterly_report", "earnings_release", "regulatory_filing"}
TOO_HARD_WARNING_CODES = {
    "insufficient-calculations",
    "insufficient-fy-history",
    "insubstantial-financial-history",
    "missing-latest-period",
    "missing-ttm",
    "empty-sankey",
    "moat-coverage",
    "unscored-moat",
    "management-score-coverage",
    "unscored-management",
    "management-commitments",
    "management-stop-doing",
    "capital-allocation-substance",
}
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "$comment",
    "title", "description", "default", "examples", "deprecated", "readOnly", "writeOnly",
    "type", "additionalProperties", "required", "properties", "items", "enum", "const",
    "pattern", "minLength", "minimum", "maximum", "uniqueItems", "minItems", "maxItems", "format",
}
REPORT_SECTIONS = (
    ("one-page-conclusion", ("一页式结论", "one-page conclusion", "executive summary")),
    ("identity-and-completeness", ("身份、日期与完整度", "数据截至日", "identity and completeness", "研究完整度")),
    ("business-model", ("商业模式", "business model")),
    ("ten-year-financials", ("十年财务", "10-year financial", "ten-year financial")),
    ("cash-flow", ("owner earnings", "所有者收益", "三种现金流", "自由现金流")),
    ("roic", ("roic", "投入资本回报")),
    ("moat", ("护城河", "moat")),
    ("durability", ("长期生存", "十年后", "durability")),
    ("culture-management", ("企业文化、管理层与资本配置", "文化与管理", "stop doing", "不做清单")),
    ("buyback-ledger", ("回购明细", "buyback ledger")),
    ("governance-debt", ("治理、债务与红旗", "治理与债务", "governance and debt")),
    ("valuation", ("reverse dcf", "反向 dcf", "估值")),
    ("pre-mortem", ("pre-mortem", "事前验尸", "失败路径")),
    ("open-questions", ("待调查", "open questions", "尚待调查")),
    ("monitoring", ("领先指标", "monitoring indicators")),
    ("final-conclusion", ("最终结论", "final conclusion")),
)


@dataclass
class Finding:
    severity: str
    code: str
    path: str
    message: str


class DuplicateKeyError(ValueError):
    pass


def add(findings: list[Finding], severity: str, code: str, path: str, message: str) -> None:
    findings.append(Finding(severity, code, path, message))


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_pairs_no_duplicates,
        parse_constant=reject_constant,
    )


def write_json(path: Path, payload: Any) -> None:
    """Atomically write JSON and never follow an existing destination symlink."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError(f"refusing to write through symlink: {path}")
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temp_path = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_sha256_candidates(path: Path) -> set[str]:
    """Return exact and one-final-LF transport variants for a trusted Schema."""
    data = path.read_bytes()
    variants = {data}
    if data.endswith(b"\n"):
        variants.add(data[:-1])
    else:
        variants.add(data + b"\n")
    return {hashlib.sha256(value).hexdigest() for value in variants}


def protocol_digest(documents: list[dict[str, Any]]) -> str:
    """Hash the path-sorted research protocol document inventory."""
    ordered = sorted(documents, key=lambda item: item["path"])
    encoded = json.dumps(
        ordered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def git_blob_sha1_candidates(path: Path) -> set[str]:
    """Return exact and connector-safe blob IDs (one transport-added final LF)."""
    data = path.read_bytes()
    candidates = {hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()}
    if data.endswith(b"\n"):
        stripped = data[:-1]
        candidates.add(hashlib.sha1(f"blob {len(stripped)}\0".encode() + stripped).hexdigest())
    return candidates


def numeric(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def substantive_text(value: Any, minimum: int = 10) -> bool:
    if not nonblank(value):
        return False
    compact = re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)
    return len(compact) >= minimum


def normalized_text(value: Any, replace_numbers: bool = False) -> str:
    if not isinstance(value, str):
        return ""
    text = value.lower()
    text = re.sub(r"https?://\S+", " url ", text)
    text = re.sub(r"\b(?:src|clm|calc)-[a-z0-9_-]+\b", " id ", text, flags=re.I)
    if replace_numbers:
        text = re.sub(r"[-+]?\d[\d,.]*(?:%|bp|bps|x|倍|亿元|万元|美元|元)?", " # ", text, flags=re.I)
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def looks_like_placeholder(value: Any) -> bool:
    compact = normalized_text(value)
    if not compact:
        return True
    exact = {
        "todo", "tbd", "na", "none", "unknown", "placeholder", "example",
        "待补充", "待完善", "待核实", "待填写", "暂无", "未知", "占位", "示例",
        "此处待补充", "这里填写", "同上", "略",
    }
    if compact in exact or re.fullmatch(r"(?:x|xx|xxx|todo|tbd|待补充|待完善|占位){1,6}", compact):
        return True
    if any(token in compact for token in ("placeholder", "loremipsum", "此处填写", "这里填写", "占位内容")):
        return True
    for size in range(1, min(16, len(compact) // 3) + 1):
        if len(compact) % size == 0 and compact == compact[:size] * (len(compact) // size):
            return True
    return False


def repeated_template_fingerprints(values: list[Any], minimum_count: int = 3) -> set[str]:
    counts: dict[str, int] = {}
    for value in values:
        fingerprint = normalized_text(value, replace_numbers=True)
        if len(fingerprint) < 12:
            continue
        counts[fingerprint] = counts.get(fingerprint, 0) + 1
    return {fingerprint for fingerprint, count in counts.items() if count >= minimum_count}


def has_near_duplicate_cluster(values: list[Any], minimum_count: int = 3, ratio: float = 0.94) -> bool:
    fingerprints = [normalized_text(value, replace_numbers=True) for value in values]
    fingerprints = [value for value in fingerprints if len(value) >= 12]
    for index, fingerprint in enumerate(fingerprints):
        similar = 1
        for candidate in fingerprints[index + 1:]:
            if SequenceMatcher(None, fingerprint, candidate, autojunk=False).ratio() >= ratio:
                similar += 1
        if similar >= minimum_count:
            return True
    return False


def flatten_leaves(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.extend(flatten_leaves(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(flatten_leaves(child, f"{prefix}[{index}]"))
    else:
        result.append((prefix.lower(), value))
    return result


class FormulaEvaluationError(ValueError):
    pass


def evaluate_custom_formula(formula: Any, inputs: Any) -> float:
    """Evaluate a small arithmetic expression without calls, attributes or code execution."""
    if not isinstance(formula, str) or not formula.strip():
        raise FormulaEvaluationError("formula must be a nonblank string")
    if not isinstance(inputs, dict) or not inputs:
        raise FormulaEvaluationError("inputs must be a nonempty object")
    environment: dict[str, float] = {}
    for name, value in inputs.items():
        if not isinstance(name, str) or not name.isidentifier() or name == "result":
            raise FormulaEvaluationError(f"input name {name!r} is not a safe expression variable")
        if not numeric(value):
            raise FormulaEvaluationError(f"input {name!r} must be a finite number")
        environment[name] = float(value)
    expression = formula.strip()
    assignment = re.fullmatch(r"result\s*=\s*(.+)", expression, flags=re.I | re.S)
    if assignment:
        expression = assignment.group(1).strip()
    elif "=" in expression:
        raise FormulaEvaluationError("only an optional 'result = expression' assignment is allowed")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise FormulaEvaluationError(f"invalid arithmetic expression: {exc.msg if isinstance(exc, SyntaxError) else exc}") from exc
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise FormulaEvaluationError("formula is too complex")
    operations = 0
    used_names: set[str] = set()

    def evaluate(node: ast.AST, depth: int = 0) -> float:
        nonlocal operations
        if depth > 24:
            raise FormulaEvaluationError("formula nesting is too deep")
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth + 1)
        if isinstance(node, ast.Constant):
            if not numeric(node.value):
                raise FormulaEvaluationError("only finite numeric constants are allowed")
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in environment:
                raise FormulaEvaluationError(f"unknown variable {node.id!r}")
            used_names.add(node.id)
            return environment[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            operations += 1
            value = evaluate(node.operand, depth + 1)
            result = value if isinstance(node.op, ast.UAdd) else -value
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)):
            operations += 1
            left = evaluate(node.left, depth + 1)
            right = evaluate(node.right, depth + 1)
            if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
                raise FormulaEvaluationError("division by zero")
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise FormulaEvaluationError("power exponent is outside the safe range")
            try:
                if isinstance(node.op, ast.Add):
                    result = left + right
                elif isinstance(node.op, ast.Sub):
                    result = left - right
                elif isinstance(node.op, ast.Mult):
                    result = left * right
                elif isinstance(node.op, ast.Div):
                    result = left / right
                elif isinstance(node.op, ast.Mod):
                    result = left % right
                else:
                    result = left ** right
            except (ArithmeticError, OverflowError, ValueError) as exc:
                raise FormulaEvaluationError(f"arithmetic failed: {exc}") from exc
        else:
            raise FormulaEvaluationError(f"unsupported expression node {type(node).__name__}")
        if not numeric(result):
            raise FormulaEvaluationError("formula produced a non-finite result")
        return float(result)

    result = evaluate(tree)
    if operations == 0:
        raise FormulaEvaluationError("formula must perform at least one arithmetic operation")
    if used_names != set(environment):
        unused = sorted(set(environment).difference(used_names))
        raise FormulaEvaluationError(f"all and only declared inputs must be used; unused inputs: {unused!r}")
    return result


def nonblank_list(value: Any, minimum: int = 1) -> bool:
    return isinstance(value, list) and len(value) >= minimum and all(nonblank(item) for item in value)


def close_enough(actual: float, expected: float, tolerance: float | None = None) -> bool:
    maximum = max(0.01, abs(expected) * 0.001)
    allowed = float(tolerance) if numeric(tolerance) and 0 <= float(tolerance) <= maximum else maximum
    return abs(actual - expected) <= allowed


def json_pointer(root: Any, ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"only local JSON pointers are supported: {ref}")
    current = root
    for raw in ref[2:].split("/"):
        current = current[raw.replace("~1", "/").replace("~0", "~")]
    return current


def validate_schema_keywords(schema: Any, path: str = "$") -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(schema, dict):
        return [Finding("error", "schema-node", path, "schema node must be an object")]
    for key in schema:
        if key not in SUPPORTED_SCHEMA_KEYWORDS:
            add(findings, "error", "unsupported-schema-keyword", f"{path}.{key}", "validator fails closed on unsupported Schema keywords")
    for container in ("$defs", "properties"):
        children = schema.get(container)
        if isinstance(children, dict):
            for name, child in children.items():
                findings.extend(validate_schema_keywords(child, f"{path}.{container}.{name}"))
    for container in ("items", "additionalProperties"):
        child = schema.get(container)
        if isinstance(child, dict):
            findings.extend(validate_schema_keywords(child, f"{path}.{container}"))
    return findings


def type_matches(value: Any, expected: str) -> bool:
    matchers = {
        "null": lambda item: item is None,
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: numeric(item),
        "string": lambda item: isinstance(item, str),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    matcher = matchers.get(expected)
    return bool(matcher and matcher(value))


def valid_format(value: str, format_name: str) -> bool:
    try:
        if format_name == "date":
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and date.fromisoformat(value) is not None
        if format_name == "date-time":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
                return False
            return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
        if format_name == "uri":
            if any(character.isspace() for character in value):
                return False
            parsed = urlparse(value)
            return bool(parsed.scheme and value.split(":", 1)[1])
    except (TypeError, ValueError):
        return False
    return False


def validate_schema(instance: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> list[Finding]:
    findings: list[Finding] = []
    if "$ref" in schema:
        try:
            target = json_pointer(root, schema["$ref"])
        except (KeyError, TypeError, ValueError) as exc:
            return [Finding("error", "schema-ref", path, str(exc))]
        findings.extend(validate_schema(instance, target, root, path))
        schema = {key: value for key, value in schema.items() if key != "$ref"}
    expected = schema.get("type")
    if expected is not None:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not expected_types or not all(isinstance(item, str) for item in expected_types):
            return [Finding("error", "schema-type-definition", path, "Schema type must be a string or nonempty string array")]
        if not any(type_matches(instance, item) for item in expected_types):
            return [Finding("error", "schema-type", path, f"expected {expected_types}, got {type(instance).__name__}")]
    if "const" in schema and instance != schema["const"]:
        add(findings, "error", "schema-const", path, f"must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        add(findings, "error", "schema-enum", path, f"not in {schema['enum']!r}")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            add(findings, "error", "schema-min-length", path, "string is too short")
        if schema.get("pattern") and re.search(schema["pattern"], instance) is None:
            add(findings, "error", "schema-pattern", path, f"does not match {schema['pattern']!r}")
        if schema.get("format") and not valid_format(instance, schema["format"]):
            add(findings, "error", "schema-format", path, f"invalid or unsupported {schema['format']}")
    if numeric(instance):
        if "minimum" in schema and instance < schema["minimum"]:
            add(findings, "error", "schema-minimum", path, f"below {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            add(findings, "error", "schema-maximum", path, f"above {schema['maximum']}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            add(findings, "error", "schema-min-items", path, "array is too short")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            add(findings, "error", "schema-max-items", path, "array is too long")
        if schema.get("uniqueItems"):
            canonical = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in instance]
            if len(canonical) != len(set(canonical)):
                add(findings, "error", "schema-unique-items", path, "array items are not unique")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(instance):
                findings.extend(validate_schema(item, schema["items"], root, f"{path}[{index}]"))
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                add(findings, "error", "schema-required", path, f"missing required key {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                findings.extend(validate_schema(value, properties[key], root, f"{path}.{key}"))
            elif schema.get("additionalProperties", True) is False:
                add(findings, "error", "schema-extra-key", f"{path}.{key}", "additional property is forbidden")
            elif isinstance(schema.get("additionalProperties"), dict):
                findings.extend(validate_schema(value, schema["additionalProperties"], root, f"{path}.{key}"))
    return findings


def extract_schema_version(schema: dict[str, Any]) -> Any:
    try:
        return schema["$defs"]["meta"]["properties"]["schema_version"].get("const")
    except (KeyError, TypeError):
        return None


def collect_source_ids(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "source_ids":
                result.append((child_path, child))
            result.extend(collect_source_ids(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(collect_source_ids(child, f"{path}[{index}]"))
    return result


def validate_ledger_sources(document: Any, name: str, known: set[str], findings: list[Finding]) -> None:
    for path, source_ids in collect_source_ids(document, f"$.{name}"):
        if not isinstance(source_ids, list):
            add(findings, "error", "source-ids-type", path, "source_ids must be an array")
            continue
        allow_empty = path.endswith("reporting.next_expected_report.source_ids")
        if not source_ids and not allow_empty:
            add(findings, "error", "empty-source-ids", path, "material structured records must cite at least one source")
        for source_id in source_ids:
            if source_id not in known:
                add(findings, "error", "unresolved-source-id", path, f"unknown source id {source_id!r}")


def period_year(period: Any) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", str(period))
    return int(match.group(0)) if match else None


def scenario_kind(name: Any) -> str | None:
    text = str(name).lower()
    if any(token in text for token in ("悲观", "bear", "pessim")):
        return "bear"
    if any(token in text for token in ("基准", "base")):
        return "base"
    if any(token in text for token in ("乐观", "bull", "optim")):
        return "bull"
    return None


def is_official_report_schedule_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    if source.get("source_type") in PRIMARY_SOURCE_TYPES:
        return True
    if source.get("source_type") != "official_website":
        return False
    url = source.get("url")
    if not nonblank(url) or not valid_format(url, "uri") or urlparse(url).scheme not in {"http", "https"}:
        return False
    context = " ".join(str(source.get(key, "")) for key in ("title", "publisher", "url", "notes")).lower()
    schedule_tokens = (
        "investor", "investors", "investor-relations", "ir.", "ir ", "calendar", "financial-calendar", "events-calendar",
        "earnings", "results", "reporting-calendar", "财报", "业绩", "投资者关系", "财务日历", "活动日历",
    )
    return any(token in context for token in schedule_tokens)


def is_unable(company: dict[str, Any]) -> bool:
    verdict = company.get("verdict") if isinstance(company.get("verdict"), dict) else {}
    return verdict.get("research_status") == "Too Hard" or verdict.get("valuation_status") == "无法判断"


def validate_evidence(evidence: Any, known: set[str], mode: str, findings: list[Finding]) -> None:
    if not isinstance(evidence, dict) or not isinstance(evidence.get("claims"), list):
        add(findings, "error", "evidence-ledger-shape", "evidence-ledger.json", "expected an object with claims[]")
        return
    claims = evidence["claims"]
    if len(claims) < (10 if mode == "full" else 1):
        add(findings, "error", "insufficient-evidence", "evidence-ledger.json.claims", "full research requires at least ten traceable claims")
    seen: set[str] = set()
    claim_texts: set[str] = set()
    classifications: set[str] = set()
    all_claim_texts: list[Any] = []
    falsifiability_texts: list[Any] = []
    for index, claim in enumerate(claims):
        path = f"evidence-ledger.json.claims[{index}]"
        if not isinstance(claim, dict):
            add(findings, "error", "claim-shape", path, "claim must be an object")
            continue
        claim_id = claim.get("id")
        if not nonblank(claim_id):
            add(findings, "error", "claim-id", path, "missing claim id")
        elif claim_id in seen:
            add(findings, "error", "duplicate-claim-id", path, f"duplicate id {claim_id!r}")
        else:
            seen.add(claim_id)
        claim_text = claim.get("claim")
        all_claim_texts.append(claim_text)
        normalized_claim = normalized_text(claim_text)
        if not substantive_text(claim_text, 12):
            add(findings, "error", "claim-text", path, "claim text must contain at least twelve substantive characters")
        elif looks_like_placeholder(claim_text):
            add(findings, "error", "claim-placeholder", path, "claim text is placeholder or repeated filler")
        elif normalized_claim in claim_texts:
            add(findings, "error", "duplicate-claim-text", path, "duplicate claim text does not add evidence coverage")
        else:
            claim_texts.add(normalized_claim)
        classification = claim.get("classification")
        if classification not in CLASSIFICATIONS:
            add(findings, "error", "claim-classification", path, "invalid classification")
        else:
            classifications.add(classification)
        if claim.get("confidence") not in CONFIDENCE:
            add(findings, "error", "claim-confidence", path, "invalid confidence")
        source_ids = claim.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            add(findings, "error", "claim-sources", path, "claim must cite at least one source")
        elif any(source_id not in known for source_id in source_ids):
            add(findings, "error", "claim-source", path, "claim has unresolved source_ids")
        if classification in {"fact", "management_claim", "third_party"}:
            if not substantive_text(claim.get("location"), 4) or looks_like_placeholder(claim.get("location")):
                add(findings, "error", "claim-location", path, "externally asserted claims require a real page, section, timestamp or filing location")
        if classification in {"inference", "estimate"}:
            falsifiability_texts.append(claim.get("would_falsify"))
            if not substantive_text(claim.get("would_falsify"), 10) or looks_like_placeholder(claim.get("would_falsify")):
                add(findings, "error", "claim-falsifiability", path, "inference or estimate requires a substantive, testable would_falsify condition")
        counter = claim.get("counterevidence")
        if counter is not None and (not isinstance(counter, list) or any(not substantive_text(item, 6) or looks_like_placeholder(item) for item in counter)):
            add(findings, "error", "claim-counterevidence", path, "counterevidence must be an array of nonblank strings")
    if repeated_template_fingerprints(all_claim_texts) or has_near_duplicate_cluster(all_claim_texts):
        add(findings, "error", "repeated-claim-template", "evidence-ledger.json.claims", "three or more claims repeat the same template with only numbers or identifiers changed")
    if repeated_template_fingerprints(falsifiability_texts) or has_near_duplicate_cluster(falsifiability_texts):
        add(findings, "error", "repeated-falsifiability-template", "evidence-ledger.json.claims", "falsifiability conditions repeat a numeric placeholder template")
    if mode == "full" and "fact" not in classifications:
        add(findings, "error", "evidence-classification-coverage", "evidence-ledger.json.claims", "full research requires directly verifiable facts")
    if mode == "full" and not classifications.intersection({"inference", "estimate"}):
        add(findings, "error", "evidence-classification-coverage", "evidence-ledger.json.claims", "full research must distinguish analytical inference or estimate from facts")


def unit_scale(company: dict[str, Any]) -> tuple[float, float]:
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    financial = {"unit": 1.0, "thousand": 1e3, "million": 1e6, "billion": 1e9}
    shares = {"share": 1.0, "thousand_shares": 1e3, "million_shares": 1e6, "billion_shares": 1e9}
    return financial.get(meta.get("financial_unit"), 1.0), shares.get(meta.get("share_unit"), 1.0)


def validate_calculations(calculations: Any, company: dict[str, Any], known: set[str], mode: str, findings: list[Finding]) -> None:
    if not isinstance(calculations, dict) or not isinstance(calculations.get("calculations"), list):
        add(findings, "error", "calculation-ledger-shape", "calculation-ledger.json", "expected an object with calculations[]")
        return
    items = calculations["calculations"]
    required_count = 2 if is_unable(company) else 4
    if mode == "full" and len(items) < required_count:
        add(findings, "warning" if is_unable(company) else "error", "insufficient-calculations", "calculation-ledger.json.calculations", f"requires at least {required_count} reviewed calculations, or an acknowledged Too Hard gap")
    seen: set[str] = set()
    financials = {item.get("period"): item for item in company.get("financials", []) if isinstance(item, dict)}
    valuation = company.get("valuation") if isinstance(company.get("valuation"), dict) else {}
    financial_scale, share_scale = unit_scale(company)
    formulas = {
        "free_cash_flow": (("operating_cash_flow", "capex_total"), lambda x: x["operating_cash_flow"] - x["capex_total"]),
        "net_debt": (("total_debt", "cash"), lambda x: x["total_debt"] - x["cash"]),
        "market_cap": (("market_price", "diluted_shares"), lambda x: x["market_price"] * x["diluted_shares"] * share_scale / financial_scale),
        "enterprise_value": (("market_cap", "net_debt"), lambda x: x["market_cap"] + x["net_debt"]),
    }
    mapped = {"free_cash_flow": "free_cash_flow", "net_debt": "net_debt", "market_cap": "market_cap", "enterprise_value": "enterprise_value"}
    for index, item in enumerate(items):
        path = f"calculation-ledger.json.calculations[{index}]"
        if not isinstance(item, dict):
            add(findings, "error", "calculation-shape", path, "calculation must be an object")
            continue
        item_id = item.get("id")
        if not nonblank(item_id):
            add(findings, "error", "calculation-id", path, "missing calculation id")
        elif item_id in seen:
            add(findings, "error", "duplicate-calculation-id", path, f"duplicate id {item_id!r}")
        else:
            seen.add(item_id)
        for field, minimum in (("period", 4), ("formula", 5), ("unit", 3)):
            if not substantive_text(item.get(field), minimum):
                add(findings, "error", "calculation-documentation", f"{path}.{field}", f"{field} is too short to be auditable")
        inputs, result = item.get("inputs"), item.get("result")
        if not isinstance(inputs, dict) or not inputs or any(value is None or (isinstance(value, str) and not value.strip()) for value in inputs.values()):
            add(findings, "error", "calculation-input", path, "inputs must be a nonempty object without blank values")
        if not numeric(result):
            add(findings, "error", "calculation-result", path, "result must be a finite number")
        source_ids = item.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids or any(source_id not in known for source_id in source_ids):
            add(findings, "error", "calculation-source", path, "calculation needs nonempty, resolved source_ids")
        metric = item.get("metric")
        if metric == "custom":
            formula = item.get("formula")
            if not substantive_text(item.get("review_method"), 16) or looks_like_placeholder(item.get("review_method")):
                add(findings, "error", "custom-calculation-review", path, "custom calculation requires a substantive independent review_method")
            if isinstance(inputs, dict) and any(not substantive_text(str(key), 2) for key in inputs):
                add(findings, "error", "custom-calculation-input-name", path, "custom input names must be descriptive")
            try:
                expected = evaluate_custom_formula(formula, inputs)
            except FormulaEvaluationError as exc:
                add(findings, "error", "custom-calculation-formula", path, str(exc))
                continue
            if not numeric(result):
                continue
            maximum_tolerance = max(0.01, abs(expected) * 0.001)
            tolerance = item.get("tolerance")
            if tolerance is not None and (not numeric(tolerance) or float(tolerance) < 0 or float(tolerance) > maximum_tolerance):
                add(findings, "error", "calculation-tolerance", path, f"tolerance cannot exceed {maximum_tolerance:g}")
            if not close_enough(float(result), expected, tolerance):
                add(findings, "error", "custom-calculation-mismatch", path, f"result {result} does not reconcile to {expected}")
            continue
        if metric not in formulas:
            add(findings, "error", "unknown-calculation-metric", path, f"unsupported metric {metric!r}; use custom with a review method")
            continue
        keys, compute = formulas[metric]
        if not isinstance(inputs, dict) or any(not numeric(inputs.get(key)) for key in keys) or not numeric(result):
            continue
        expected = float(compute(inputs))
        maximum_tolerance = max(0.01, abs(expected) * 0.001)
        tolerance = item.get("tolerance")
        if numeric(tolerance) and (float(tolerance) < 0 or float(tolerance) > maximum_tolerance):
            add(findings, "error", "calculation-tolerance", path, f"tolerance cannot exceed {maximum_tolerance:g}")
        if not close_enough(float(result), expected, tolerance):
            add(findings, "error", "calculation-mismatch", path, f"result {result} does not reconcile to {expected}")
        target = financials.get(item.get("period")) if metric in {"free_cash_flow", "net_debt"} else valuation
        target_value = target.get(mapped[metric]) if isinstance(target, dict) else None
        if not numeric(target_value):
            add(findings, "error", "calculation-target-missing", path, "no matching numeric company.json field for this period")
        elif not close_enough(float(result), float(target_value)):
            add(findings, "error", "calculation-target-mismatch", path, f"ledger result {result} differs from company.json value {target_value}")


def documented_material_gap(completeness: str) -> bool:
    lowered = completeness.lower()
    for phrase in ("无关键缺失", "未发现关键缺失", "没有关键缺失", "无关键缺口", "no material gap", "no key gap"):
        lowered = lowered.replace(phrase, "")
    return any(token in lowered for token in ("缺失", "缺口", "无法获取", "无法验证", "不足", "missing", "unavailable"))


def validate_completeness(text: str, findings: list[Finding]) -> None:
    if len(text.strip()) < 200:
        add(findings, "error", "completeness-too-short", "research-completeness.md", "must substantively explain coverage, gaps, confidence, impact and pending evidence")
    lowered = text.lower()
    signals = {
        "coverage": ("覆盖", "已取得", "coverage"),
        "gaps": ("缺口", "缺失", "无法", "无关键缺", "gap", "missing"),
        "confidence": ("置信", "可信度", "confidence"),
        "impact": ("影响", "impact"),
        "pending": ("待取得", "待补充", "下一步", "尚待", "pending"),
    }
    for code, alternatives in signals.items():
        if not any(token in lowered for token in alternatives):
            add(findings, "error", f"completeness-{code}", "research-completeness.md", f"missing {code} discussion")


def validate_too_hard_acknowledgements(company: dict[str, Any], text: str, findings: list[Finding]) -> None:
    if not is_unable(company):
        return
    warning_codes = sorted({
        item.code
        for item in findings
        if item.severity == "warning" and item.code in TOO_HARD_WARNING_CODES
    })
    lines = text.splitlines()
    for code in warning_codes:
        matching_lines = [
            line
            for line in lines
            if code in line and not any(other != code and other in line for other in warning_codes)
        ]
        def explains_gap(line: str) -> bool:
            explanation = line.replace(code, " ")
            lowered = explanation.lower()
            cause = any(token in lowered for token in ("原因", "由于", "因为", "未披露", "缺失", "无法获取", "cause", "because", "unavailable"))
            impact = any(token in lowered for token in ("影响", "限制", "导致", "降低", "impact", "limits", "reduces"))
            pending = any(token in lowered for token in ("待取得", "待补", "下一步", "补证", "获取后", "pending", "next", "obtain"))
            return substantive_text(explanation, 12) and not looks_like_placeholder(explanation) and cause and impact and pending
        if not matching_lines or not any(explains_gap(line) for line in matching_lines):
            add(
                findings,
                "error",
                "unacknowledged-too-hard-warning",
                "research-completeness.md",
                f"Too Hard warning {code!r} needs its own line naming the exact finding code and explaining cause, impact and pending evidence",
            )


def validate_financials(company: dict[str, Any], completeness: str, mode: str, findings: list[Finding]) -> None:
    financials = company.get("financials")
    if not isinstance(financials, list):
        return
    periods = [item.get("period") for item in financials if isinstance(item, dict)]
    if len(periods) != len(set(periods)):
        add(findings, "error", "duplicate-financial-period", "company.json.financials", "financial periods must be unique")
    fy_items = [item for item in financials if isinstance(item, dict) and item.get("period_type") == "FY"]
    years = [period_year(item.get("period")) for item in fy_items]
    known_years = [year for year in years if year is not None]
    if len(known_years) != len(set(known_years)):
        add(findings, "error", "duplicate-financial-year", "company.json.financials", "multiple FY labels resolve to the same year")
    if any(year is None for year in years):
        add(findings, "error", "financial-year-label", "company.json.financials", "each FY period must contain a four-digit year")
    if known_years != sorted(known_years):
        add(findings, "error", "financial-order", "company.json.financials", "FY periods must run earliest to latest")
    if mode == "full" and len(fy_items) < 10:
        severity = "warning" if documented_material_gap(completeness) else "error"
        add(findings, severity, "insufficient-fy-history", "company.json.financials", f"only {len(fy_items)} FY records; explain the actual availability gap and impact")
    core_fields = ("revenue", "operating_profit", "net_income", "operating_cash_flow", "cash", "total_debt", "diluted_shares")
    substantive = [item for item in fy_items if sum(numeric(item.get(field)) for field in core_fields) >= 3]
    required_substantive = min(8, len(fy_items)) if not is_unable(company) else min(3, len(fy_items))
    if len(substantive) < required_substantive or not substantive:
        severity = "warning" if is_unable(company) and documented_material_gap(completeness) else "error"
        add(findings, severity, "insubstantial-financial-history", "company.json.financials", f"only {len(substantive)} FY rows contain meaningful financial data")
    if not is_unable(company):
        for field in ("revenue", "net_income", "diluted_shares"):
            count = sum(numeric(item.get(field)) for item in fy_items)
            if count < min(8, len(fy_items)):
                add(findings, "error", "financial-core-coverage", f"company.json.financials.{field}", f"only {count} FY values are numeric")
    quarter_items = [item for item in financials if isinstance(item, dict) and item.get("period_type") in {"Q1", "Q2", "Q3", "Q4", "H1", "H2"}]
    ttm_items = [item for item in financials if isinstance(item, dict) and item.get("period_type") in {"TTM", "LTM"}]
    if mode == "full" and not quarter_items:
        add(findings, "warning" if documented_material_gap(completeness) else "error", "missing-latest-period", "company.json.financials", "latest quarter or half-year is missing")
    if mode == "full" and not ttm_items:
        add(findings, "warning" if documented_material_gap(completeness) else "error", "missing-ttm", "company.json.financials", "TTM or LTM record is missing")
    latest_fy = max(known_years) if known_years else None
    for label, items in (("latest-period", quarter_items), ("ttm", ttm_items)):
        for item in items:
            year = period_year(item.get("period"))
            if latest_fy is not None and (year is None or year < latest_fy):
                add(findings, "error", f"stale-{label}", "company.json.financials", f"{item.get('period')!r} predates latest FY{latest_fy}")
    for index, item in enumerate(financials):
        if not isinstance(item, dict):
            continue
        ocf, capex, fcf = item.get("operating_cash_flow"), item.get("capex_total"), item.get("free_cash_flow")
        if numeric(ocf) and numeric(capex) and numeric(fcf):
            expected = float(ocf) - float(capex)
            if not close_enough(float(fcf), expected):
                add(findings, "error", "fcf-mismatch", f"company.json.financials[{index}]", f"FCF {fcf} does not equal OCF - capex ({expected})")


def validate_sankey(company: dict[str, Any], findings: list[Finding]) -> None:
    sankey = company.get("income_statement_sankey")
    if not isinstance(sankey, dict):
        return
    nodes, links = sankey.get("nodes"), sankey.get("links")
    if not isinstance(nodes, list) or not nodes or not isinstance(links, list) or not links:
        add(findings, "warning" if is_unable(company) else "error", "empty-sankey", "company.json.income_statement_sankey", "formal research requires nonempty Sankey nodes and links, or an acknowledged Too Hard gap")
        return
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(ids) != len(set(ids)):
        add(findings, "error", "duplicate-sankey-node", "company.json.income_statement_sankey.nodes", "node IDs must be unique")
    node_ids = set(ids)
    incoming: dict[Any, float] = {}
    outgoing: dict[Any, float] = {}
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            continue
        source, target, value = link.get("source"), link.get("target"), link.get("value")
        if source not in node_ids or target not in node_ids:
            add(findings, "error", "sankey-node-reference", f"company.json.income_statement_sankey.links[{index}]", "link references an unknown node")
        if numeric(value):
            outgoing[source] = outgoing.get(source, 0.0) + float(value)
            incoming[target] = incoming.get(target, 0.0) + float(value)
    if sankey.get("reconciled") is True:
        for node_id in node_ids.intersection(incoming).intersection(outgoing):
            if not close_enough(incoming[node_id], outgoing[node_id]):
                add(findings, "error", "sankey-not-reconciled", "company.json.income_statement_sankey", f"node {node_id!r} has incoming {incoming[node_id]} and outgoing {outgoing[node_id]}")


def validate_research_modules(company: dict[str, Any], findings: list[Finding]) -> None:
    moat = company.get("moat")
    if not isinstance(moat, list) or len(moat) < 4:
        add(findings, "warning" if is_unable(company) else "error", "moat-coverage", "company.json.moat", "assess at least four moat dimensions, or acknowledge a Too Hard gap")
    else:
        dimensions: set[str] = set()
        for index, item in enumerate(moat):
            path = f"company.json.moat[{index}]"
            if not isinstance(item, dict):
                continue
            dimension = item.get("dimension")
            normalized = dimension.strip().lower() if nonblank(dimension) else ""
            if not normalized or normalized in dimensions:
                add(findings, "error", "moat-dimension", path, "dimension must be nonblank and unique")
            else:
                dimensions.add(normalized)
            if not substantive_text(item.get("assessment"), 10) or not isinstance(item.get("evidence"), list) or any(not substantive_text(value, 6) for value in item.get("evidence", [])) or not item.get("evidence"):
                add(findings, "error", "moat-substance", path, "requires an assessment and evidence")
            if not isinstance(item.get("risks"), list) or not item.get("risks") or any(not substantive_text(value, 6) for value in item.get("risks", [])):
                add(findings, "error", "moat-counterevidence", path, "requires at least one risk or counterexample")
            score = item.get("score")
            if score is None and is_unable(company):
                add(findings, "warning", "unscored-moat", f"{path}.score", "Too Hard assessment leaves this dimension unscored")
            elif not numeric(score) or not 0 <= float(score) <= 5:
                add(findings, "error", "methodology-score-range", f"{path}.score", "methodology score must be numeric within 0–5")
    management = company.get("management")
    if not isinstance(management, dict):
        return
    scores = management.get("scores")
    if not isinstance(scores, list) or len(scores) < 3:
        add(findings, "warning" if is_unable(company) else "error", "management-score-coverage", "company.json.management.scores", "requires at least three scored dimensions, or an acknowledged Too Hard gap")
    else:
        for index, item in enumerate(scores):
            path = f"company.json.management.scores[{index}]"
            if not isinstance(item, dict) or not substantive_text(item.get("dimension"), 2) or not substantive_text(item.get("assessment"), 10):
                add(findings, "error", "management-score-substance", path, "requires dimension and assessment")
            score = item.get("score") if isinstance(item, dict) else None
            if score is None and is_unable(company):
                add(findings, "warning", "unscored-management", f"{path}.score", "Too Hard assessment leaves this dimension unscored")
            elif not numeric(score) or not 0 <= float(score) <= 5:
                add(findings, "error", "methodology-score-range", f"{path}.score", "methodology score must be numeric within 0–5")
    commitments = management.get("commitment_timeline")
    if not isinstance(commitments, list) or not commitments:
        add(findings, "warning" if is_unable(company) else "error", "management-commitments", "company.json.management.commitment_timeline", "requires at least one commitment-versus-result event, or an acknowledged Too Hard gap")
    elif any(not isinstance(item, dict) or not substantive_text(item.get("date"), 4) or not substantive_text(item.get("commitment"), 8) or not substantive_text(item.get("status"), 2) for item in commitments):
        add(findings, "error", "management-commitment-substance", "company.json.management.commitment_timeline", "commitment events require date, commitment and status")
    stop_list = management.get("stop_doing_list")
    if not isinstance(stop_list, list) or len(stop_list) < 2 or any(not substantive_text(item, 6) for item in stop_list):
        add(findings, "warning" if is_unable(company) else "error", "management-stop-doing", "company.json.management.stop_doing_list", "requires at least two substantive stop-doing constraints, or an acknowledged Too Hard gap")
    allocation = company.get("capital_allocation")
    if not isinstance(allocation, list) or not allocation or not any(isinstance(item, dict) and numeric(item.get("amount")) for item in allocation):
        add(findings, "warning" if is_unable(company) else "error", "capital-allocation-substance", "company.json.capital_allocation", "requires at least one sourced numeric capital-allocation item or an acknowledged Too Hard gap")


def validate_valuation(company: dict[str, Any], findings: list[Finding]) -> None:
    valuation = company.get("valuation")
    if not isinstance(valuation, dict):
        return
    unable = is_unable(company)
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    financial_scale, share_scale = unit_scale(company)
    if not unable:
        for field in ("market_price", "diluted_shares", "market_cap"):
            if not numeric(valuation.get(field)):
                add(findings, "error", "valuation-snapshot", f"company.json.valuation.{field}", "complete valuation requires a finite number")
        if all(numeric(valuation.get(field)) for field in ("market_price", "diluted_shares", "market_cap")):
            expected = float(valuation["market_price"]) * float(valuation["diluted_shares"]) * share_scale / financial_scale
            if not close_enough(float(valuation["market_cap"]), expected):
                add(findings, "error", "market-cap-mismatch", "company.json.valuation.market_cap", f"market cap does not reconcile to price × diluted shares ({expected})")
    scenarios = valuation.get("dcf_scenarios")
    kinds: set[str] = set()
    values: dict[str, float] = {}
    if isinstance(scenarios, list):
        for index, scenario in enumerate(scenarios):
            if not isinstance(scenario, dict):
                continue
            kind = scenario_kind(scenario.get("name"))
            if kind:
                kinds.add(kind)
            discount, terminal, value = scenario.get("discount_rate"), scenario.get("terminal_growth"), scenario.get("fair_value_per_share")
            if not unable and not all(numeric(item) for item in (discount, terminal, value)):
                add(findings, "error", "dcf-scenario-inputs", f"company.json.valuation.dcf_scenarios[{index}]", "each scenario requires discount rate, terminal growth and fair value")
            if numeric(discount) and numeric(terminal) and float(terminal) >= float(discount):
                add(findings, "error", "dcf-terminal-rate", f"company.json.valuation.dcf_scenarios[{index}]", "terminal growth must be below discount rate")
            if kind and numeric(value):
                values[kind] = float(value)
    if not unable and kinds != {"bear", "base", "bull"}:
        add(findings, "error", "dcf-scenarios", "company.json.valuation.dcf_scenarios", "requires 悲观 / 基准 / 乐观 scenarios")
    if all(kind in values for kind in ("bear", "base", "bull")) and not values["bear"] <= values["base"] <= values["bull"]:
        add(findings, "error", "dcf-order", "company.json.valuation.dcf_scenarios", "scenario values must be 悲观 ≤ 基准 ≤ 乐观")
    sensitivity = valuation.get("dcf_sensitivity")
    if not unable and (not isinstance(sensitivity, list) or len(sensitivity) < 4):
        add(findings, "error", "dcf-sensitivity", "company.json.valuation.dcf_sensitivity", "requires at least four sensitivity cells")
    reverse = valuation.get("reverse_dcf")
    if not unable:
        leaves = flatten_leaves(reverse) if isinstance(reverse, dict) else []
        numeric_pairs = [(path, value) for path, value in leaves if numeric(value)]
        category_tokens = {
            "growth": ("growth", "cagr", "revenue", "sales", "earnings", "增长", "收入", "营收", "盈利"),
            "profitability": ("margin", "roe", "roa", "roic", "rotce", "profit", "利润率", "回报率", "回报", "净利率"),
            "capital_cash": ("capital", "reinvest", "cash", "capex", "turnover", "payout", "buyback", "资本", "再投资", "现金", "周转", "回购"),
        }
        categories = {
            category
            for category, tokens in category_tokens.items()
            if any(any(token in path for token in tokens) for path, _ in numeric_pairs)
        }
        blank_or_placeholder = any(
            isinstance(value, str) and (not value.strip() or looks_like_placeholder(value))
            for _, value in leaves
        )
        if not isinstance(reverse, dict) or len(numeric_pairs) < 2 or len(categories) < 2 or blank_or_placeholder:
            add(
                findings,
                "error",
                "missing-reverse-dcf",
                "company.json.valuation.reverse_dcf",
                "Reverse DCF requires at least two finite implied operating assumptions across two dimensions, without placeholders",
            )
        narrative = [f"{path} {value}".lower() for path, value in leaves if substantive_text(value, 16)]
        comparison_tokens = ("history", "historical", "industry", "management", "benchmark", "compare", "历史", "行业", "管理层", "同业", "对比", "合理")
        sensitivity_tokens = ("sensitive", "sensitivity", "trigger", "break", "threshold", "overvalu", "undervalu", "敏感", "阈值", "高估", "低估", "推翻", "临界")
        if not any(any(token in text for token in comparison_tokens) for text in narrative):
            add(findings, "error", "reverse-dcf-comparison", "company.json.valuation.reverse_dcf", "explain how implied assumptions compare with history, management targets or industry reality")
        if not any(any(token in text for token in sensitivity_tokens) for text in narrative):
            add(findings, "error", "reverse-dcf-sensitivity", "company.json.valuation.reverse_dcf", "identify sensitive variables and an operating threshold that would make price look high or low")
    multiples = valuation.get("multiples")
    if not unable and (not isinstance(multiples, dict) or not multiples or not any(numeric(value) or nonblank(value) for value in multiples.values())):
        add(findings, "error", "valuation-multiples", "company.json.valuation.multiples", "requires at least one substantive cross-check multiple")
    fair = valuation.get("fair_value_range")
    if not isinstance(fair, dict) or any(key not in fair for key in ("low", "base", "high", "currency")):
        add(findings, "error", "fair-value-range-shape", "company.json.valuation.fair_value_range", "requires low, base, high and currency")
    elif not unable:
        if not all(numeric(fair.get(key)) for key in ("low", "base", "high")):
            add(findings, "error", "fair-value-range-null", "company.json.valuation.fair_value_range", "complete valuation requires numeric low/base/high")
        elif not float(fair["low"]) <= float(fair["base"]) <= float(fair["high"]):
            add(findings, "error", "fair-value-order", "company.json.valuation.fair_value_range", "requires low ≤ base ≤ high")
        if fair.get("currency") != meta.get("report_currency"):
            add(findings, "error", "fair-value-currency", "company.json.valuation.fair_value_range.currency", "must match report_currency")
    returns = valuation.get("expected_returns")
    return_kinds = {scenario_kind(item.get("scenario")) for item in returns if isinstance(item, dict)} if isinstance(returns, list) else set()
    if not unable and (not isinstance(returns, list) or len(returns) < 3 or not {"bear", "base", "bull"}.issubset(return_kinds)):
        add(findings, "error", "expected-return-scenarios", "company.json.valuation.expected_returns", "requires 悲观 / 基准 / 乐观 annualized-return scenarios")
    if isinstance(returns, list):
        for index, item in enumerate(returns):
            if isinstance(item, dict) and (not numeric(item.get("annualized_return")) or not numeric(item.get("horizon_years"))):
                add(findings, "error", "expected-return-input", f"company.json.valuation.expected_returns[{index}]", "requires numeric horizon and annualized return")
    enterprise_value = valuation.get("enterprise_value")
    if numeric(enterprise_value) and numeric(valuation.get("market_cap")):
        financials = [item for item in company.get("financials", []) if isinstance(item, dict)]
        latest_net_debt = next((item.get("net_debt") for item in reversed(financials) if numeric(item.get("net_debt"))), None)
        if numeric(latest_net_debt):
            expected_ev = float(valuation["market_cap"]) + float(latest_net_debt)
            if not close_enough(float(enterprise_value), expected_ev):
                add(findings, "error", "enterprise-value-mismatch", "company.json.valuation.enterprise_value", f"EV does not reconcile to market cap + latest net debt ({expected_ev})")


def validate_verdict_and_risks(company: dict[str, Any], findings: list[Finding]) -> None:
    verdict = company.get("verdict")
    if not isinstance(verdict, dict):
        add(findings, "error", "verdict-shape", "company.json.verdict", "verdict must be a substantive object")
    else:
        for key, allowed in (("business_quality", BUSINESS_QUALITY), ("valuation_status", VALUATION_STATUS), ("research_status", RESEARCH_STATUS)):
            if verdict.get(key) not in allowed:
                add(findings, "error", "verdict-value", f"company.json.verdict.{key}", f"must be one of {sorted(allowed)!r}")
        confidence = verdict.get("confidence")
        if not nonblank(confidence) or confidence.strip().lower() not in {item.lower() for item in VERDICT_CONFIDENCE}:
            add(findings, "error", "verdict-confidence", "company.json.verdict.confidence", "use high/medium/low or 高/中/低")
        if not substantive_text(verdict.get("one_sentence"), 16) or looks_like_placeholder(verdict.get("one_sentence")):
            add(findings, "error", "verdict-summary", "company.json.verdict.one_sentence", "one-sentence verdict must state a company-specific conclusion")
        assumptions = verdict.get("key_assumptions")
        assumption_values = assumptions if isinstance(assumptions, list) else []
        assumption_keys = [normalized_text(item, replace_numbers=True) for item in assumption_values]
        if (
            not isinstance(assumptions, list)
            or not 2 <= len(assumptions) <= 4
            or any(not substantive_text(item, 8) or looks_like_placeholder(item) for item in assumptions)
            or len(set(assumption_keys)) != len(assumption_keys)
        ):
            add(findings, "error", "key-assumptions", "company.json.verdict.key_assumptions", "requires 2–4 distinct, company-specific assumptions")
        breakers = verdict.get("thesis_breakers")
        breaker_values = breakers if isinstance(breakers, list) else []
        breaker_keys = [normalized_text(item, replace_numbers=True) for item in breaker_values]
        if (
            not isinstance(breakers, list)
            or not breakers
            or any(not substantive_text(item, 8) or looks_like_placeholder(item) for item in breakers)
            or len(set(breaker_keys)) != len(breaker_keys)
        ):
            add(findings, "error", "thesis-breakers", "company.json.verdict.thesis_breakers", "requires distinct, observable thesis breakers")
        if set(assumption_keys).intersection(breaker_keys):
            add(findings, "error", "verdict-duplicate-logic", "company.json.verdict", "key assumptions and thesis breakers cannot be duplicated placeholders")
    risks = company.get("risks")
    if not isinstance(risks, dict):
        add(findings, "error", "risks-shape", "company.json.risks", "risks must be a substantive object")
        return
    for field, minimum in (("pre_mortem", 5), ("fragile_assumptions", 3)):
        values = risks.get(field)
        text_minimum = 10 if field == "pre_mortem" else 8
        normalized = [normalized_text(item, replace_numbers=True) for item in values] if isinstance(values, list) else []
        if (
            not isinstance(values, list)
            or len(values) < minimum
            or any(not substantive_text(item, text_minimum) or looks_like_placeholder(item) for item in values)
            or len(set(normalized)) != len(normalized)
            or bool(repeated_template_fingerprints(values, minimum_count=3))
            or has_near_duplicate_cluster(values, minimum_count=3)
        ):
            add(findings, "error", f"{field}-substance", f"company.json.risks.{field}", f"requires at least {minimum} distinct, company-specific entries")
    if not substantive_text(risks.get("bear_case"), 16) or looks_like_placeholder(risks.get("bear_case")):
        add(findings, "error", "bear-case", "company.json.risks.bear_case", "strongest bear case must be substantive")
    indicators = risks.get("monitoring_indicators")
    if not isinstance(indicators, list) or not 5 <= len(indicators) <= 10:
        add(findings, "error", "monitoring-count", "company.json.risks.monitoring_indicators", "requires 5–10 leading indicators")
    else:
        names: set[str] = set()
        triggers: set[str] = set()
        for index, item in enumerate(indicators):
            path = f"company.json.risks.monitoring_indicators[{index}]"
            if not isinstance(item, dict) or any(
                not substantive_text(item.get(key), minimum) or looks_like_placeholder(item.get(key))
                for key, minimum in (("name", 3), ("current_status", 5), ("trigger", 8))
            ):
                add(findings, "error", "monitoring-substance", path, "requires name, current status and thesis-breaking trigger")
            if not isinstance(item, dict) or not nonblank_list(item.get("source_ids")):
                add(findings, "error", "monitoring-sources", path, "leading indicators require source_ids")
            if isinstance(item, dict):
                name_key = normalized_text(item.get("name"), replace_numbers=True)
                trigger_key = normalized_text(item.get("trigger"), replace_numbers=True)
                if name_key in names or trigger_key in triggers:
                    add(findings, "error", "duplicate-monitoring-indicator", path, "indicator names and triggers must be distinct")
                names.add(name_key)
                triggers.add(trigger_key)
        trigger_values = [item.get("trigger") for item in indicators if isinstance(item, dict)]
        if repeated_template_fingerprints(trigger_values) or has_near_duplicate_cluster(trigger_values):
            add(findings, "error", "repeated-monitoring-template", "company.json.risks.monitoring_indicators", "monitoring triggers repeat a numeric placeholder template")


def parse_headings(report: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", report))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(report)
        result.append((match.group(1).strip(), report[match.end():end].strip()))
    return result


def validate_report(company: dict[str, Any], report: str, mode: str, findings: list[Finding]) -> None:
    lowered = report.lower()
    headings = parse_headings(report)
    if mode == "full":
        cursor = -1
        section_bodies: list[str] = []
        for code, alternatives in REPORT_SECTIONS:
            match_index = next((index for index in range(cursor + 1, len(headings)) if any(token in headings[index][0].lower() for token in alternatives)), None)
            if match_index is None:
                add(findings, "error", f"report-section-{code}", "research-report.md", f"missing ordered Markdown heading: {alternatives[0]}")
                continue
            cursor = match_index
            body = re.sub(r"[`*_>#|\-]", "", headings[match_index][1])
            section_bodies.append(body)
            if len(re.sub(r"\s+", "", body)) < 50 or looks_like_placeholder(body):
                add(findings, "error", "report-section-thin", f"research-report.md#{code}", "section body is too thin to support a formal conclusion")
        fingerprints: dict[str, int] = {}
        for body in section_bodies:
            fingerprint = normalized_text(body, replace_numbers=True)
            if len(fingerprint) >= 40:
                fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
        if any(count >= 2 for count in fingerprints.values()) or has_near_duplicate_cluster(section_bodies, minimum_count=2, ratio=0.94):
            add(findings, "error", "repeated-report-section", "research-report.md", "two or more required sections repeat the same body with only numbers or citations changed")
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    identities = [meta.get("company_name_cn"), meta.get("company_name_en"), meta.get("ticker")]
    if not any(nonblank(item) and item.lower() in lowered for item in identities):
        add(findings, "error", "report-company-identity", "research-report.md", "company name or ticker not found in report")
    source_ids = [item.get("id") for item in company.get("sources", []) if isinstance(item, dict)]
    has_source_id = any(nonblank(source_id) and source_id in report for source_id in source_ids)
    if source_ids and not has_source_id and re.search(r"https?://[^\s)>]+", report) is None:
        add(findings, "error", "report-citation", "research-report.md", "report needs source IDs or direct source links")


def load_trusted_spec_lock(findings: list[Finding]) -> dict[str, Any] | None:
    path = TRUSTED_SPEC_LOCK_PATH
    if path.is_symlink() or not path.is_file():
        add(findings, "error", "trusted-spec-lock-file", str(path), "bundled trust lock must be a regular file")
        return None
    try:
        lock = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        add(findings, "error", "trusted-spec-lock-load", str(path), str(exc))
        return None
    if (
        not isinstance(lock, dict)
        or set(lock) != TRUSTED_LOCK_KEYS
        or lock.get("lock_version") != "2.0"
    ):
        add(findings, "error", "trusted-spec-lock-shape", str(path), "bundled lock must use lock_version 2.0 and contain only lock_version, research_protocol, and company_schema")
        return None

    protocol = lock.get("research_protocol")
    documents = protocol.get("documents") if isinstance(protocol, dict) else None
    protocol_valid = (
        isinstance(protocol, dict)
        and set(protocol) == RESEARCH_PROTOCOL_KEYS
        and protocol.get("authority") == EXPECTED_PROTOCOL_AUTHORITY
        and protocol.get("repository") == EXPECTED_PROTOCOL_REPOSITORY
        and protocol.get("ref") == "main"
        and re.fullmatch(r"[0-9a-f]{40}", str(protocol.get("commit", ""))) is not None
        and substantive_text(protocol.get("protocol_version"), 3)
        and re.fullmatch(r"[0-9a-f]{64}", str(protocol.get("digest_sha256", ""))) is not None
        and isinstance(documents, list)
    )
    if not protocol_valid:
        add(findings, "error", "trusted-research-protocol-shape", str(path), "research_protocol has an invalid authority/repository/ref/commit/version/digest/documents binding")
        return None

    expected_paths = set(PROTOCOL_DOCUMENT_PATHS)
    seen_paths: list[str] = []
    for index, entry in enumerate(documents):
        item_path = f"{path}.research_protocol.documents[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size_bytes"}:
            add(findings, "error", "trusted-protocol-document-shape", item_path, "document entries require only path, sha256, and size_bytes")
            continue
        relative = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if (
            not isinstance(relative, str)
            or relative not in expected_paths
            or re.fullmatch(r"[0-9a-f]{64}", str(digest or "")) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            add(findings, "error", "trusted-protocol-document-shape", item_path, "document inventory contains an unsafe path, hash, or size")
            continue
        seen_paths.append(relative)
        local = SKILL_ROOT / relative
        if local.is_symlink() or not local.is_file():
            add(findings, "error", "trusted-protocol-document-file", relative, "authoritative protocol document must be a non-symlink regular file")
            continue
        if file_sha256(local) != digest or local.stat().st_size != size:
            add(findings, "error", "trusted-protocol-document-mismatch", relative, "authoritative protocol document differs from the bundled trust lock")
    if seen_paths != sorted(expected_paths):
        add(findings, "error", "trusted-protocol-document-set", str(path), f"documents must be unique and sorted as {sorted(expected_paths)!r}")
    if isinstance(documents, list) and all(isinstance(item, dict) and "path" in item for item in documents):
        try:
            actual_digest = protocol_digest(documents)
        except (KeyError, TypeError, ValueError):
            actual_digest = None
        if protocol.get("digest_sha256") != actual_digest:
            add(findings, "error", "trusted-protocol-digest", str(path), "research_protocol digest does not match its path-sorted documents inventory")

    company_schema = lock.get("company_schema")
    schema_valid = (
        isinstance(company_schema, dict)
        and set(company_schema) == COMPANY_SCHEMA_KEYS
        and company_schema.get("repository") == EXPECTED_SPEC_REPOSITORY
        and company_schema.get("ref") == "main"
        and re.fullmatch(r"[0-9a-f]{40}", str(company_schema.get("commit", ""))) is not None
        and company_schema.get("path") == EXPECTED_SCHEMA_PATH
        and re.fullmatch(r"[0-9a-f]{40}", str(company_schema.get("blob_sha1", ""))) is not None
        and re.fullmatch(r"[0-9a-f]{64}", str(company_schema.get("sha256", ""))) is not None
        and isinstance(company_schema.get("size_bytes"), int)
        and not isinstance(company_schema.get("size_bytes"), bool)
        and company_schema.get("size_bytes", -1) >= 0
        and substantive_text(company_schema.get("schema_version"), 3)
        and company_schema.get("bundled_path") == BUNDLED_SCHEMA_PATH
    )
    if not schema_valid:
        add(findings, "error", "trusted-company-schema-shape", str(path), "company_schema has an invalid repository/ref/commit/path/blob/hash/size/version binding")
        return None

    bundled = SKILL_ROOT / BUNDLED_SCHEMA_PATH
    if bundled.is_symlink() or not bundled.is_file():
        add(findings, "error", "trusted-company-schema-file", BUNDLED_SCHEMA_PATH, "bundled Schema must be a non-symlink regular file")
    else:
        data = bundled.read_bytes()
        size_candidates = {len(data)}
        if data.endswith(b"\n"):
            size_candidates.add(len(data) - 1)
        else:
            size_candidates.add(len(data) + 1)
        if company_schema["sha256"] not in schema_sha256_candidates(bundled):
            add(findings, "error", "trusted-company-schema-sha256", BUNDLED_SCHEMA_PATH, "bundled Schema differs beyond one transport-added final LF")
        if company_schema["blob_sha1"] not in git_blob_sha1_candidates(bundled):
            add(findings, "error", "trusted-company-schema-blob", BUNDLED_SCHEMA_PATH, "bundled Schema Git blob differs from the authoritative system lock")
        if company_schema["size_bytes"] not in size_candidates:
            add(findings, "error", "trusted-company-schema-size", BUNDLED_SCHEMA_PATH, "bundled Schema size differs beyond one transport-added final LF")

    if any(item.severity == "error" and item.code.startswith("trusted-") for item in findings):
        return None
    return lock


def validate_manifest(root: Path, schema_path: Path, company: dict[str, Any], mode: str, findings: list[Finding]) -> None:
    manifest_path = root / "research-manifest.json"
    if not manifest_path.exists():
        return
    if manifest_path.is_symlink() or not manifest_path.is_file():
        add(findings, "error", "manifest-file-type", "research-manifest.json", "manifest must be a regular file")
        return
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        add(findings, "error", "manifest-load", "research-manifest.json", str(exc))
        return
    if not isinstance(manifest, dict):
        add(findings, "error", "manifest-shape", "research-manifest.json", "manifest must be an object")
        return
    trusted = load_trusted_spec_lock(findings)
    manifest_version = manifest.get("manifest_version")
    if manifest_version not in {"1.0", "2.0"} or manifest.get("status") != "frozen":
        add(findings, "error", "manifest-status", "research-manifest.json", "requires manifest_version 1.0 or 2.0 and status frozen")
    if manifest_version == "1.0" and mode != "audit":
        add(findings, "error", "legacy-manifest-audit-only", "research-manifest.json", "manifest_version 1.0 is audit-only and cannot be used for new full/incremental/freeze/archive work")
    if manifest.get("human_review_status") not in {"pending", "accepted"}:
        add(findings, "error", "manifest-human-review", "research-manifest.json", "invalid human review status")
    if not isinstance(manifest.get("warning_acknowledged"), bool) or not valid_format(str(manifest.get("frozen_at", "")), "date-time"):
        add(findings, "error", "manifest-metadata", "research-manifest.json", "requires boolean warning acknowledgement and timezone-aware frozen_at")
    specification = manifest.get("specification")
    if not isinstance(specification, dict):
        add(findings, "error", "manifest-specification", "research-manifest.json", "specification block is missing")
    elif manifest_version == "1.0":
        expected_legacy = {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "schema_path": EXPECTED_SCHEMA_PATH,
            "schema_version": extract_schema_version(load_json(schema_path)),
        }
        for key, value in expected_legacy.items():
            if specification.get(key) != value:
                add(findings, "error", f"manifest-{key.replace('_', '-')}", "research-manifest.json.specification", f"legacy {key} does not match the supplied Schema")
        if specification.get("schema_sha256") not in schema_sha256_candidates(schema_path):
            add(findings, "error", "manifest-schema-sha256", "research-manifest.json.specification", "legacy schema_sha256 does not match the supplied Schema")
        if specification.get("schema_blob_sha1") not in git_blob_sha1_candidates(schema_path):
            add(findings, "error", "manifest-schema-blob-sha1", "research-manifest.json.specification", "legacy Schema blob does not match the supplied Schema")
        if re.fullmatch(r"[0-9a-f]{40}", str(specification.get("commit", ""))) is None or specification.get("ref") != "main":
            add(findings, "error", "manifest-legacy-anchor", "research-manifest.json.specification", "legacy manifest needs an exact commit and main ref for audit")
    elif manifest_version == "2.0" and trusted is not None:
        company_schema = trusted["company_schema"]
        expected = {
            "repository": company_schema["repository"],
            "ref": company_schema["ref"],
            "commit": company_schema["commit"],
            "schema_path": company_schema["path"],
            "schema_blob_sha1": company_schema["blob_sha1"],
            "schema_version": company_schema["schema_version"],
        }
        for key, value in expected.items():
            if specification.get(key) != value:
                add(findings, "error", f"manifest-{key.replace('_', '-')}", "research-manifest.json.specification", f"{key} must exactly match trusted company_schema and the local Schema")
        if specification.get("schema_sha256") not in schema_sha256_candidates(schema_path):
            add(findings, "error", "manifest-schema-sha256", "research-manifest.json.specification", "schema_sha256 must match the trusted Schema bytes, allowing only one transport-added final LF")
        if company_schema["blob_sha1"] not in git_blob_sha1_candidates(schema_path):
            add(findings, "error", "trusted-schema-local-mismatch", str(schema_path), "local Schema bytes do not match the trusted locked blob")
        meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
        if meta.get("schema_version") != company_schema["schema_version"]:
            add(findings, "error", "manifest-company-schema-version", "company.json.meta.schema_version", "company schema_version must exactly match trusted company_schema")
        research_protocol = manifest.get("research_protocol")
        if research_protocol != trusted["research_protocol"]:
            add(findings, "error", "manifest-research-protocol", "research-manifest.json.research_protocol", "research_protocol must exactly match the bundled v2 trust lock")
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    research = manifest.get("research")
    if not isinstance(research, dict):
        add(findings, "error", "manifest-research", "research-manifest.json", "research identity block is missing")
    else:
        for key in ("company_name_cn", "company_name_en", "ticker", "exchange", "report_currency", "data_as_of", "valuation_date", "source_version"):
            if research.get(key) != meta.get(key):
                add(findings, "error", "manifest-research-mismatch", f"research-manifest.json.research.{key}", "does not match company.json")
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or validation.get("mode") != "full" or validation.get("errors") != 0:
        add(findings, "error", "manifest-validation", "research-manifest.json.validation", "frozen package must record full validation with zero errors")
    try:
        validation_report = load_json(root / "validation-report.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        add(findings, "error", "validation-report-load", "validation-report.json", str(exc))
    else:
        if not isinstance(validation_report, dict) or validation_report.get("mode") != "full" or validation_report.get("errors") != 0:
            add(findings, "error", "validation-report-status", "validation-report.json", "must record full validation with zero errors")
        elif isinstance(validation, dict):
            for key in ("validator", "mode", "errors", "warnings"):
                if validation.get(key) != validation_report.get(key):
                    add(findings, "error", "manifest-validation-mismatch", f"research-manifest.json.validation.{key}", "does not match validation-report.json")
    expected_paths = set(FROZEN_HASH_FILES)
    gap_path = root / "schema-gap-report.md"
    if gap_path.exists():
        if gap_path.is_symlink() or not gap_path.is_file() or not gap_path.read_text(encoding="utf-8").strip():
            add(findings, "error", "schema-gap-file", "schema-gap-report.md", "optional Schema Gap Report must be a nonempty regular file")
        expected_paths.add("schema-gap-report.md")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        add(findings, "error", "manifest-files", "research-manifest.json", "files must be an array")
        return
    paths = [item.get("path") for item in entries if isinstance(item, dict)]
    if len(paths) != len(set(paths)):
        add(findings, "error", "manifest-duplicate-file", "research-manifest.json.files", "file paths must be unique")
    if set(paths) != expected_paths:
        add(findings, "error", "manifest-file-set", "research-manifest.json.files", f"expected exactly {sorted(expected_paths)!r}")
    root_resolved = root.resolve()
    for index, item in enumerate(entries):
        path = f"research-manifest.json.files[{index}]"
        if not isinstance(item, dict) or not nonblank(item.get("path")):
            add(findings, "error", "manifest-file-shape", path, "file entry must contain a relative path")
            continue
        candidate = root / item["path"]
        if candidate.is_symlink():
            add(findings, "error", "manifest-file-symlink", path, "frozen inputs cannot be symlinks")
            continue
        try:
            candidate.resolve().relative_to(root_resolved)
        except ValueError:
            add(findings, "error", "manifest-path-escape", path, "file path escapes the package")
            continue
        if not candidate.is_file():
            add(findings, "error", "manifest-file-missing", path, f"missing {item['path']!r}")
            continue
        if item.get("sha256") != file_sha256(candidate) or item.get("size_bytes") != candidate.stat().st_size:
            add(findings, "error", "manifest-hash-mismatch", path, f"hash or size mismatch for {item['path']!r}")


def validate_research_package(root: Path, schema_path: Path, mode: str) -> list[Finding]:
    findings: list[Finding] = []
    for name in REQUIRED_FILES:
        path = root / name
        if path.is_symlink():
            add(findings, "error", "symlink-input", name, "research inputs must be regular files")
        elif not path.is_file():
            add(findings, "error", "missing-file", name, "required research package file is missing")
    if findings:
        return findings
    try:
        schema = load_json(schema_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [Finding("error", "schema-load", str(schema_path), str(exc))]
    if not isinstance(schema, dict):
        return [Finding("error", "schema-root", str(schema_path), "Schema must be an object")]
    if schema.get("$schema") != EXPECTED_SCHEMA_DRAFT or schema.get("$id") != EXPECTED_SCHEMA_ID:
        add(findings, "error", "schema-identity", str(schema_path), "must be the Doujiao Draft 2020-12 company Schema")
    findings.extend(validate_schema_keywords(schema))
    load_trusted_spec_lock(findings)
    if any(item.severity == "error" for item in findings):
        return findings
    documents: dict[str, Any] = {}
    for name in ("company.json", "evidence-ledger.json", "calculation-ledger.json"):
        try:
            documents[name] = load_json(root / name)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            add(findings, "error", "json-load", name, str(exc))
    if any(item.code == "json-load" for item in findings):
        return findings
    company, evidence, calculations = documents["company.json"], documents["evidence-ledger.json"], documents["calculation-ledger.json"]
    if not isinstance(company, dict):
        return [Finding("error", "json-root", "company.json", "company must be a JSON object")]
    findings.extend(validate_schema(company, schema, schema))
    expected_version = extract_schema_version(schema)
    actual_version = company.get("meta", {}).get("schema_version") if isinstance(company.get("meta"), dict) else None
    if expected_version is None or actual_version != expected_version:
        add(findings, "error", "schema-version", "company.json.meta.schema_version", f"expected {expected_version!r}")
    sources = company.get("sources")
    known: set[str] = set()
    source_types: dict[str, Any] = {}
    source_records: dict[str, dict[str, Any]] = {}
    official_urls = 0
    if not isinstance(sources, list) or not sources:
        add(findings, "error", "empty-sources", "company.json.sources", "sources cannot be empty")
    else:
        for index, source in enumerate(sources):
            path = f"company.json.sources[{index}]"
            source_id = source.get("id") if isinstance(source, dict) else None
            if not nonblank(source_id):
                add(findings, "error", "source-id", path, "source id is missing")
            elif source_id in known:
                add(findings, "error", "duplicate-source-id", path, f"duplicate source id {source_id!r}")
            else:
                known.add(source_id)
                if isinstance(source, dict):
                    source_types[source_id] = source.get("source_type")
                    source_records[source_id] = source
            if not isinstance(source, dict) or not substantive_text(source.get("title"), 4):
                add(findings, "error", "source-title", path, "source title must be descriptive")
            if isinstance(source, dict) and source.get("source_type") in PRIMARY_SOURCE_TYPES:
                if nonblank(source.get("url")) and valid_format(source["url"], "uri"):
                    official_urls += 1
                else:
                    add(findings, "warning", "primary-source-url", path, "primary source has no directly verifiable URL")
    if mode == "full" and official_urls == 0:
        add(findings, "error", "missing-primary-source", "company.json.sources", "full research requires at least one primary official source URL")
    validate_ledger_sources(company, "company", known, findings)
    validate_ledger_sources(evidence, "evidence", known, findings)
    validate_ledger_sources(calculations, "calculations", known, findings)
    validate_evidence(evidence, known, mode, findings)
    validate_calculations(calculations, company, known, mode, findings)
    try:
        report = (root / "research-report.md").read_text(encoding="utf-8")
        completeness = (root / "research-completeness.md").read_text(encoding="utf-8")
    except UnicodeDecodeError:
        add(findings, "error", "text-encoding", str(root), "text files must be UTF-8")
        return findings
    validate_completeness(completeness, findings)
    validate_financials(company, completeness, mode, findings)
    validate_sankey(company, findings)
    validate_research_modules(company, findings)
    validate_valuation(company, findings)
    validate_verdict_and_risks(company, findings)
    validate_report(company, report, mode, findings)
    validate_too_hard_acknowledgements(company, completeness, findings)
    meta = company.get("meta")
    if isinstance(meta, dict):
        if meta.get("ratio_convention") != "decimal":
            add(findings, "error", "ratio-convention", "company.json.meta.ratio_convention", "must be decimal")
        try:
            if date.fromisoformat(meta.get("valuation_date", "")) < date.fromisoformat(meta.get("data_as_of", "")):
                add(findings, "error", "valuation-before-data", "company.json.meta", "valuation_date cannot predate data_as_of")
        except (TypeError, ValueError):
            pass
    reporting = company.get("reporting") if isinstance(company.get("reporting"), dict) else {}
    latest = reporting.get("latest_report") if isinstance(reporting.get("latest_report"), dict) else {}
    latest_ids = latest.get("source_ids") if isinstance(latest.get("source_ids"), list) else []
    if latest.get("date_status") != "official" or not latest_ids or not any(source_types.get(source_id) in PRIMARY_SOURCE_TYPES for source_id in latest_ids):
        add(findings, "error", "latest-report-provenance", "company.json.reporting.latest_report", "latest report must cite a primary official source")
    next_report = reporting.get("next_expected_report") if isinstance(reporting.get("next_expected_report"), dict) else {}
    next_ids = next_report.get("source_ids") if isinstance(next_report.get("source_ids"), list) else []
    if next_report.get("date_status") == "official" and (not next_ids or not any(is_official_report_schedule_source(source_records.get(source_id)) for source_id in next_ids)):
        add(findings, "error", "next-report-provenance", "company.json.reporting.next_expected_report", "an official next-report date must cite a filing/release or a verifiable official IR calendar page")
    brand = company.get("brand_identity")
    logo = brand.get("company_logo") if isinstance(brand, dict) and isinstance(brand.get("company_logo"), dict) else {}
    if logo.get("is_official") is True and not nonblank(logo.get("source_url")):
        add(findings, "error", "official-logo-source", "company.json.brand_identity.company_logo", "official logo requires a source URL")
    elif logo.get("is_official") is not True:
        add(findings, "warning", "unofficial-logo", "company.json.brand_identity.company_logo", "official logo unavailable; document the limitation and do not synthesize one")
    validate_manifest(root, schema_path, company, mode, findings)
    return findings


def report_payload(root: Path, schema_path: Path, mode: str, findings: list[Finding]) -> dict[str, Any]:
    return {
        "validator": "research-doujiao-value-company/2.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "schema": str(schema_path),
        "mode": mode,
        "errors": sum(item.severity == "error" for item in findings),
        "warnings": sum(item.severity == "warning" for item in findings),
        "findings": [asdict(item) for item in findings],
    }


def self_test() -> int:
    failures: list[str] = []
    if valid_format("2026-08-19", "date-time"):
        failures.append("date-time accepted a bare date")
    if not valid_format("2026-08-19T12:00:00Z", "date-time"):
        failures.append("valid date-time rejected")
    if not valid_format("urn:isbn:9780141036144", "uri") or not valid_format("mailto:test@example.com", "uri"):
        failures.append("valid non-HTTP URI rejected")
    unsupported = validate_schema_keywords({"type": "object", "anyOf": []})
    if not any(item.code == "unsupported-schema-keyword" for item in unsupported):
        failures.append("unsupported Schema keyword did not fail closed")
    schema = {"$defs": {"x": {"type": "string"}}, "$ref": "#/$defs/x", "minLength": 2}
    if not validate_schema("a", schema, schema):
        failures.append("$ref sibling was ignored")
    findings: list[Finding] = []
    validate_evidence({"claims": []}, set(), "full", findings)
    if not any(item.code == "insufficient-evidence" for item in findings):
        failures.append("empty evidence passed")
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print("self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, help="Research package root")
    parser.add_argument("--schema", type=Path, help="Locked company.schema.json path")
    parser.add_argument("--mode", choices=("full", "incremental", "audit"), default="full")
    parser.add_argument("--output", type=Path, help="Write JSON validation report")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.root is None or args.schema is None:
        parser.error("root and --schema are required unless --self-test is used")
    root, schema_path = args.root.resolve(), args.schema.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if not schema_path.is_file():
        parser.error(f"schema does not exist: {schema_path}")
    findings = validate_research_package(root, schema_path, args.mode)
    payload = report_payload(root, schema_path, args.mode, findings)
    if args.output:
        output = args.output.resolve()
        try:
            output.relative_to(root)
            inside = True
        except ValueError:
            inside = False
        if (root / "research-manifest.json").exists() and inside:
            print("Refusing to write inside a frozen research package; choose an external --output path.", file=sys.stderr)
            return 1
        try:
            write_json(output, payload)
        except OSError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
