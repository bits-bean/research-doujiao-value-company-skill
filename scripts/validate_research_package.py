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
VALUATION_CASH_FLOW_BASES = {"fcff", "fcfe", "owner_earnings", "distributable_common_cash"}
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
    ("identity-and-completeness", ("身份、数据截至日、完整度和缺失项", "身份、日期与完整度", "数据截至日", "identity and completeness", "研究完整度")),
    ("business-model", ("商业模式与行业结构", "商业模式", "business model")),
    ("ten-year-financials", ("十年财务表和关键趋势", "十年财务", "10-year financial", "ten-year financial")),
    ("cash-flow", ("fcf、股东调整后 fcf 与 owner earnings", "owner earnings", "所有者收益", "三种现金流", "自由现金流")),
    ("roic", ("roic 与再投资跑道", "roic", "投入资本回报")),
    ("moat", ("逐维护城河", "护城河", "moat")),
    ("durability", ("十年后需求与长期生存", "长期生存", "十年后", "durability")),
    ("culture-management", ("文化、不做清单、管理层和资本配置", "企业文化、管理层与资本配置", "文化与管理", "stop doing", "不做清单")),
    ("buyback-ledger", ("回购明细账", "回购明细", "buyback ledger")),
    ("governance-debt", ("会计、治理、负债和红旗", "治理、债务与红旗", "治理与债务", "governance and debt")),
    ("valuation", ("估值、reverse dcf、敏感性和情景回报", "reverse dcf", "反向 dcf", "估值")),
    ("pre-mortem", ("完整 pre-mortem", "pre-mortem", "事前验尸", "失败路径")),
    ("open-questions", ("尚待调查问题", "待调查", "open questions", "尚待调查")),
    ("monitoring", ("未来跟踪的 5—10 个领先指标", "领先指标", "monitoring indicators")),
    ("final-conclusion", ("最终结论", "final conclusion")),
)
REPORT_SOURCE_HEADINGS = ("来源定位索引", "主要来源索引", "主要来源", "来源索引", "source index", "sources", "references")
REPORT_EVIDENCE_SECTIONS = {
    "business-model", "ten-year-financials", "cash-flow", "roic", "moat", "durability",
    "culture-management", "buyback-ledger", "governance-debt", "valuation", "pre-mortem", "monitoring",
}
MOAT_CORE_DIMENSIONS = (
    ("pricing-power", ("定价权", "pricing power")),
    ("hard-to-replicate", ("难复制", "不可复制", "hard to replicate", "hard to copy")),
    ("switching-costs", ("转换成本", "切换成本", "switching costs", "switching cost")),
    ("network-effects", ("网络效应", "network effects", "network effect")),
)
CONFIDENCE_ALIASES = {
    "high": ("high", "high confidence", "高", "高置信度"),
    "medium": ("medium", "medium confidence", "中", "中等", "中置信度"),
    "low": ("low", "low confidence", "低", "低置信度"),
}
DEFAULT_SOURCE_PAGE_LIMIT = 5000
FINAL_SCORE_DIMENSIONS = (
    ("business-understanding", ("生意可理解", "商业模式", "business understanding", "business model")),
    ("financial-cash-flow", ("财务与现金流", "财务和现金流", "financial and cash flow", "financials and cash flow")),
    ("returns-reinvestment", ("roic与再投资", "roe与再投资", "资本回报与再投资", "returns and reinvestment")),
    ("moat", ("护城河", "moat")),
    ("durability", ("长期生存", "需求持久", "durability", "long-term survival")),
    ("management-capital-allocation", ("文化、管理层和资本配置", "文化管理层与资本配置", "management and capital allocation")),
    ("governance-balance-sheet", ("会计、治理和资产负债表", "会计治理与资产负债表", "governance and balance sheet")),
    ("valuation-margin-of-safety", ("估值与安全边际", "估值和安全边际", "valuation and margin of safety")),
)
SOURCE_TYPE_ALIASES = {
    "annual_report": ("annual report", "年报"),
    "quarterly_report": ("quarterly report", "10-q", "季报"),
    "earnings_release": ("earnings release", "results release", "业绩公告"),
    "earnings_call": ("earnings call", "conference call", "业绩会"),
    "investor_presentation": ("investor presentation", "earnings presentation", "投资者演示"),
    "regulatory_filing": ("regulatory filing", "filing", "监管申报"),
    "official_website": ("official website", "investor relations", "官方网站", "投资者关系"),
    "management_interview": ("management interview", "管理层访谈"),
    "news": ("news", "新闻"),
    "research": ("research", "研究"),
    "other": ("other", "其他"),
}

NONLOCALIZED_CHINESE_UNIT_PATTERNS = (
    re.compile(
        r"\b(?:USD|CNY|RMB|HKD|EUR|GBP|JPY|US\$)\s*"
        r"(?:thousand|million|billion|trillion)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:thousand|million|billion|trillion)\s*"
        r"(?:USD|CNY|RMB|HKD|EUR|GBP|JPY|US dollars?|shares?)\b",
        re.I,
    ),
    re.compile(r"百万\s*(?:美元|港元|人民币|欧元|英镑|日元|元|股)"),
    re.compile(
        r"(?:单位|口径)\s*[:：]?\s*(?:USD|CNY|RMB|HKD|EUR|GBP|JPY|US\$)?\s*"
        r"(?:thousand|million|billion|trillion)\b",
        re.I,
    ),
    re.compile(r"(?:单位|口径)\s*[:：]?\s*百万(?:美元|港元|人民币|欧元|英镑|日元|元|股)?"),
)


@dataclass
class Finding:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class HeadingBlock:
    level: int
    title: str
    body: str
    start: int
    end: int


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


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
    if calculations.get("numeric_convention") != "base_units":
        add(
            findings,
            "error",
            "calculation-numeric-convention",
            "calculation-ledger.json.numeric_convention",
            "must equal 'base_units'; monetary amounts and share counts must be actual unscaled values",
        )
    items = calculations["calculations"]
    required_count = 2 if is_unable(company) else 4
    if mode == "full" and len(items) < required_count:
        add(findings, "warning" if is_unable(company) else "error", "insufficient-calculations", "calculation-ledger.json.calculations", f"requires at least {required_count} reviewed calculations, or an acknowledged Too Hard gap")
    seen: set[str] = set()
    financials = {item.get("period"): item for item in company.get("financials", []) if isinstance(item, dict)}
    valuation = company.get("valuation") if isinstance(company.get("valuation"), dict) else {}
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    if meta.get("financial_unit") != "unit" or meta.get("share_unit") != "share":
        add(
            findings,
            "error",
            "company-base-unit-convention",
            "company.json.meta",
            "financial_unit must be 'unit' and share_unit must be 'share' for current research packages",
        )
    formulas = {
        "free_cash_flow": (("operating_cash_flow", "capex_total"), lambda x: x["operating_cash_flow"] - x["capex_total"]),
        "net_debt": (("total_debt", "cash"), lambda x: x["total_debt"] - x["cash"]),
        "market_cap": (("market_price", "diluted_shares"), lambda x: x["market_price"] * x["diluted_shares"]),
        "enterprise_value": (("market_cap", "net_debt"), lambda x: x["market_cap"] + x["net_debt"]),
    }
    mapped = {"free_cash_flow": "free_cash_flow", "net_debt": "net_debt", "market_cap": "market_cap", "enterprise_value": "enterprise_value"}
    starting_cash_records: list[tuple[int, dict[str, Any]]] = []
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
        for field, minimum in (("period", 4), ("formula", 5)):
            if not substantive_text(item.get(field), minimum):
                add(findings, "error", "calculation-documentation", f"{path}.{field}", f"{field} is too short to be auditable")
        if "unit" in item:
            add(
                findings,
                "error",
                "calculation-unit-field",
                f"{path}.unit",
                "per-calculation unit fields are forbidden; use base numeric values and root numeric_convention='base_units'",
            )
        inputs, result = item.get("inputs"), item.get("result")
        if not isinstance(inputs, dict) or not inputs or any(value is None or (isinstance(value, str) and not value.strip()) for value in inputs.values()):
            add(findings, "error", "calculation-input", path, "inputs must be a nonempty object without blank values")
        if not numeric(result):
            add(findings, "error", "calculation-result", path, "result must be a finite number")
        source_ids = item.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids or any(source_id not in known for source_id in source_ids):
            add(findings, "error", "calculation-source", path, "calculation needs nonempty, resolved source_ids")
        metric = item.get("metric")
        if item.get("valuation_role") == "starting_cash_flow":
            starting_cash_records.append((index, item))
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

    if mode == "full" and not is_unable(company):
        if len(starting_cash_records) != 1:
            add(
                findings,
                "error",
                "missing-valuation-starting-cash-flow",
                "calculation-ledger.json.calculations",
                "full research requires exactly one reviewed valuation_role=starting_cash_flow record",
            )
        else:
            index, record = starting_cash_records[0]
            path = f"calculation-ledger.json.calculations[{index}]"
            basis = record.get("cash_flow_basis")
            formula = record.get("formula")
            inputs = record.get("inputs")
            forbidden_text = " ".join(
                [str(basis or ""), str(formula or "")]
                + ([str(key) for key in inputs] if isinstance(inputs, dict) else [])
            ).lower()
            if record.get("metric") != "custom" or basis not in VALUATION_CASH_FLOW_BASES:
                add(findings, "error", "valuation-starting-cash-flow-basis", path, f"cash_flow_basis must be one of {sorted(VALUATION_CASH_FLOW_BASES)!r} on a custom calculation")
            if re.search(r"(?:^|[^a-z])eps(?:$|[^a-z])|earnings\s*per\s*share|每股收益", forbidden_text, re.I):
                add(findings, "error", "valuation-starting-cash-flow-eps", path, "EPS cannot be the starting cash flow for DCF or Reverse DCF")
            result = record.get("result")
            shares = record.get("diluted_shares")
            per_share = record.get("per_share")
            years = record.get("forecast_years")
            if not numeric(shares) or float(shares) <= 0 or not numeric(per_share) or not isinstance(years, int) or isinstance(years, bool) or years <= 0:
                add(findings, "error", "valuation-starting-cash-flow-fields", path, "requires positive diluted_shares, finite per_share and positive integer forecast_years")
            elif numeric(result):
                expected_per_share = float(result) / float(shares)
                if not close_enough(float(per_share), expected_per_share, max(0.0001, abs(expected_per_share) * 0.001)):
                    add(findings, "error", "valuation-starting-cash-flow-per-share", path, f"per_share {per_share} does not reconcile to total cash flow and diluted shares ({expected_per_share})")


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
            "growth": ("growth", "cagr", "revenue", "sales", "cash_flow", "fcf", "fcfe", "增长", "收入", "营收", "现金流"),
            "profitability": ("margin", "roe", "roa", "roic", "rotce", "profit", "利润率", "回报率", "回报", "净利率"),
            "capital_cash": ("capital", "reinvest", "cash", "capex", "turnover", "payout", "retention", "buyback", "资本", "再投资", "现金", "周转", "留存", "分配", "回购"),
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
        if any(re.search(r"(?:^|[^a-z])eps(?:$|[^a-z])|earnings_per_share|每股收益", path, re.I) for path, _ in numeric_pairs):
            add(findings, "error", "reverse-dcf-eps-input", "company.json.valuation.reverse_dcf", "Reverse DCF must solve for cash-flow and capital assumptions, not EPS")
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


def clean_markdown_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 \2", value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"[`*_~]", "", value)
    return value.strip()


def mask_non_rendered_markdown(report: str) -> str:
    """Mask fenced code and HTML comments while preserving offsets and line breaks."""
    def mask_text(value: str) -> str:
        return "".join(char if char in "\r\n" else " " for char in value)

    report = re.sub(r"<!--.*?-->", lambda match: mask_text(match.group(0)), report, flags=re.S)
    opening_tags = list(re.finditer(r"<\s*([A-Za-z][\w:-]*)\b([^>]*)>", report, flags=re.S))
    for opening in reversed(opening_tags):
        tag = opening.group(1).lower()
        attributes = opening.group(2)
        hidden_attribute = re.search(
            r"(?:^|\s)hidden(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s]+))?(?=\s|/|$)",
            attributes,
            re.I | re.S,
        ) is not None
        style_match = re.search(r"(?:^|\s)style\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s]+))", attributes, re.I | re.S)
        style = next((value for value in style_match.groups() if value is not None), "") if style_match else ""
        hidden_style = re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)\b", style, re.I) is not None
        if tag not in {"template", "script", "style"} and not hidden_attribute and not hidden_style:
            continue
        closing = re.search(rf"<\s*/\s*{re.escape(tag)}\s*>", report[opening.end():], re.I)
        if closing is None:
            continue
        end = opening.end() + closing.end()
        report = report[:opening.start()] + mask_text(report[opening.start():end]) + report[end:]
    lines = report.splitlines(keepends=True)
    active_fence: tuple[str, int] | None = None
    masked: list[str] = []
    for line in lines:
        match = re.match(r"^[ \t]*([`~]{3,})", line)
        if active_fence is None and match:
            token = match.group(1)
            active_fence = (token[0], len(token))
            masked.append(mask_text(line))
            continue
        if active_fence is not None:
            masked.append(mask_text(line))
            if match and match.group(1)[0] == active_fence[0] and len(match.group(1)) >= active_fence[1]:
                active_fence = None
            continue
        masked.append(line)
    return "".join(masked)


def raw_html_tags(report: str) -> list[str]:
    tags: list[str] = []
    for match in re.finditer(r"<\s*/?\s*([A-Za-z][\w:-]*)\b[^>]*>", report, re.I | re.S):
        raw = match.group(0)
        tag = match.group(1).lower()
        if re.fullmatch(r"<\s*br\s*/?\s*>", raw, re.I):
            continue
        if re.fullmatch(r"<https?://[^>]+>", raw, re.I):
            continue
        tags.append(tag)
    return tags


def report_prose_text(value: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", value, flags=re.I)
    text = re.sub(r"https?://[^\s)>|]+", " ", text, flags=re.I)
    text = re.sub(r"\bSRC-[A-Za-z0-9_-]+\b", " ", text, flags=re.I)
    text = re.sub(r"(?m)^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$", " ", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"[`*_>#|~\-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_report_urls(value: str) -> set[str]:
    return {
        item.rstrip(".,;；。，、)]}〕】」』》〉\"'")
        for item in re.findall(r"https?://[^\s>|]+", value, re.I)
    }


def known_source_urls(company: dict[str, Any]) -> set[str]:
    return {
        str(item.get("url")).rstrip("/")
        for item in list_or_empty(company.get("sources"))
        if isinstance(item, dict) and nonblank(item.get("url"))
    }


def text_has_known_citation(company: dict[str, Any], value: str, allowed_ids: set[str] | None = None) -> bool:
    sources = [item for item in list_or_empty(company.get("sources")) if isinstance(item, dict)]
    known_ids = {str(item.get("id")) for item in sources if nonblank(item.get("id"))}
    if allowed_ids is not None:
        known_ids &= allowed_ids
    cited_ids = {match.group(0) for match in re.finditer(r"\bSRC-[A-Za-z0-9_-]+\b", value, re.I)}
    if any(any(item.lower() == cited.lower() for item in known_ids) for cited in cited_ids):
        return True
    allowed_urls = {
        str(item.get("url")).rstrip("/")
        for item in sources
        if nonblank(item.get("url")) and (allowed_ids is None or item.get("id") in allowed_ids)
    }
    return any(url.rstrip("/") in allowed_urls for url in extract_report_urls(value))


def canonical_confidence(value: Any) -> str | None:
    key = normalized_text(clean_markdown_text(value))
    for canonical, aliases in CONFIDENCE_ALIASES.items():
        if any(key == normalized_text(alias) for alias in aliases):
            return canonical
    return None


def parse_report_number(value: Any) -> float | None:
    cleaned = clean_markdown_text(value).replace(",", "")
    match = re.fullmatch(
        r"\s*[$¥€£]?\s*(-?\d+(?:\.\d+)?)\s*(%)?\s*"
        r"(?:USD|CNY|RMB|HKD|EUR|GBP|JPY|人民币元|美元|港元|欧元|英镑|日元|元)?"
        r"(?:\s*/\s*股)?\s*",
        cleaned,
        re.I,
    )
    if not match:
        return None
    number = float(match.group(1))
    return number / 100 if match.group(2) else number


def heading_key(value: Any) -> str:
    text = clean_markdown_text(value).lower()
    text = re.sub(r"^\s*(?:\u7b2c\s*)?(?:\d+|[一二三四五六七八九十百]+)\s*[.\u3001):\uff1a-]\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def heading_matches(value: Any, alternatives: tuple[str, ...]) -> bool:
    key = heading_key(value)
    for alternative in alternatives:
        token = alternative.lower().strip()
        if key == token or re.match(rf"^{re.escape(token)}(?:\s|[:\uff1a\-\u2014(/\uff08\u4e0e\u548c])", key):
            return True
    return False


def parse_heading_blocks(report: str) -> list[HeadingBlock]:
    matches = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", report))
    result: list[HeadingBlock] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        end = len(report)
        for candidate in matches[index + 1:]:
            if len(candidate.group(1)) <= level:
                end = candidate.start()
                break
        result.append(HeadingBlock(level, match.group(2).strip(), report[match.end():end].strip(), match.start(), end))
    return result


def parse_headings(report: str) -> list[tuple[str, str]]:
    """Compatibility wrapper returning heading titles with nested content included."""
    return [(block.title, block.body) for block in parse_heading_blocks(report)]


def markdown_cells(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return []
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def parse_markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = text.splitlines()
    tables: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index + 1 < len(lines):
        headers = markdown_cells(lines[index])
        separator = markdown_cells(lines[index + 1])
        if len(headers) >= 2 and len(separator) == len(headers) and table_separator(separator):
            rows: list[list[str]] = []
            cursor = index + 2
            while cursor < len(lines):
                cells = markdown_cells(lines[cursor])
                if not cells:
                    break
                if len(cells) < len(headers):
                    cells.extend([""] * (len(headers) - len(cells)))
                rows.append(cells[:len(headers)])
                cursor += 1
            tables.append((headers, rows))
            index = cursor
            continue
        index += 1
    return tables


def header_column(headers: list[str], alternatives: tuple[str, ...]) -> int | None:
    normalized_alternatives = [normalized_text(item) for item in alternatives]
    for index, header in enumerate(headers):
        key = normalized_text(clean_markdown_text(header))
        if any(token and token in key for token in normalized_alternatives):
            return index
    return None


def labelled_value(body: str, alternatives: tuple[str, ...]) -> str | None:
    for _, rows in parse_markdown_tables(body):
        for row in rows:
            if row and heading_matches(row[0], alternatives):
                return " | ".join(clean_markdown_text(cell) for cell in row[1:] if clean_markdown_text(cell))
    labels = "|".join(re.escape(item) for item in alternatives)
    pattern = re.compile(rf"^\s*(?:[-*+]\s*)?(?:\*\*)?(?:{labels})(?:\*\*)?\s*[:\uff1a]\s*(.+?)\s*$", re.I)
    for line in body.splitlines():
        match = pattern.match(line)
        if match:
            return clean_markdown_text(match.group(1))
    return None


def split_report_entries(value: str) -> list[str]:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"(?<!\w)(?=\d{1,2}\s*[.)\u3001])", "\n", value)
    pieces: list[str] = []
    for line in value.splitlines():
        for piece in re.split(r"[;\uff1b]", line):
            cleaned = re.sub(r"^\s*(?:[-*+]\s*|\d{1,2}\s*[.)\u3001]\s*)", "", clean_markdown_text(piece)).strip()
            if cleaned:
                pieces.append(cleaned)
    return pieces


def labelled_entries(body: str, alternatives: tuple[str, ...]) -> list[str]:
    inline = labelled_value(body, alternatives)
    if inline:
        return split_report_entries(inline)
    lines = body.splitlines()
    for index, line in enumerate(lines):
        candidate = re.sub(r"^\s*#{1,6}\s+", "", line)
        candidate = re.sub(r"^\s*(?:[-*+]\s*)?", "", candidate)
        if not heading_matches(candidate, alternatives):
            continue
        entries: list[str] = []
        for following in lines[index + 1:]:
            if re.match(r"^\s*#{1,6}\s+", following):
                break
            match = re.match(r"^\s*(?:[-*+]\s+|\d{1,2}\s*[.)\u3001]\s+)(.+?)\s*$", following)
            if match:
                entries.extend(split_report_entries(match.group(1)))
            elif entries and following.strip():
                break
        if entries:
            return entries
    return []


def contains_allowed_value(value: Any, allowed: set[str]) -> bool:
    key = normalized_text(clean_markdown_text(value))
    return any(normalized_text(item) in key for item in allowed)


def substantive_distinct_entries(values: list[str], minimum: int) -> bool:
    normalized = [normalized_text(item, replace_numbers=True) for item in values]
    return (
        all(substantive_text(item, minimum) and not looks_like_placeholder(item) for item in values)
        and len(normalized) == len(set(normalized))
        and not repeated_template_fingerprints(values, minimum_count=3)
        and not has_near_duplicate_cluster(values, minimum_count=3)
    )


def validate_conclusion_fields(body: str, findings: list[Finding], *, section: str, code_prefix: str) -> None:
    path = f"research-report.md#{section}"
    fields = (
        ("business-quality", ("企业质量", "商业质量", "business quality"), BUSINESS_QUALITY),
        ("valuation-status", ("估值状态", "valuation status"), VALUATION_STATUS),
        ("research-status", ("研究状态", "research status"), RESEARCH_STATUS),
        ("confidence", ("置信度", "置信水平", "confidence"), VERDICT_CONFIDENCE),
    )
    for code, labels, allowed in fields:
        value = labelled_value(body, labels)
        if value is None or canonical_conclusion_value(value, allowed) is None:
            add(findings, "error", f"{code_prefix}-{code}", path, f"{section} needs a labelled, valid {code} value")
    assumptions = labelled_entries(body, ("关键假设", "关键前提", "key assumptions"))
    if not 2 <= len(assumptions) <= 4 or not substantive_distinct_entries(assumptions, 8):
        add(findings, "error", f"{code_prefix}-key-assumptions", path, f"{section} needs 2–4 distinct, substantive key assumptions in a labelled field or list")
    breakers = labelled_entries(body, ("thesis breakers", "thesis breaker", "论点破坏点", "推翻条件"))
    if not breakers or not substantive_distinct_entries(breakers, 8):
        add(findings, "error", f"{code_prefix}-thesis-breakers", path, f"{section} needs a labelled list of substantive thesis breakers")


def validate_one_page_report(body: str, findings: list[Finding]) -> None:
    validate_conclusion_fields(body, findings, section="one-page-conclusion", code_prefix="report-one-page")


def canonical_conclusion_value(value: Any, allowed: set[str]) -> str | None:
    if allowed is VERDICT_CONFIDENCE:
        return canonical_confidence(value)
    key = normalized_text(clean_markdown_text(value))
    matched = next((item for item in allowed if key == normalized_text(item)), None)
    if matched is None:
        return None
    return normalized_text(matched)


def conclusion_status_values(body: str) -> dict[str, str | None]:
    specs = {
        "business_quality": (("企业质量", "商业质量", "business quality"), BUSINESS_QUALITY),
        "valuation_status": (("估值状态", "valuation status"), VALUATION_STATUS),
        "research_status": (("研究状态", "research status"), RESEARCH_STATUS),
        "confidence": (("置信度", "置信水平", "confidence"), VERDICT_CONFIDENCE),
    }
    return {
        key: canonical_conclusion_value(labelled_value(body, labels), allowed)
        for key, (labels, allowed) in specs.items()
    }


def normalized_entry_set(values: list[Any]) -> set[str]:
    return {normalized_text(clean_markdown_text(value)) for value in values if substantive_text(value, 4)}


def validate_conclusion_consistency(company: dict[str, Any], one_page: str, final: str, findings: list[Finding]) -> None:
    one_values = conclusion_status_values(one_page)
    final_values = conclusion_status_values(final)
    verdict = company.get("verdict") if isinstance(company.get("verdict"), dict) else {}
    allowed_by_key = {
        "business_quality": BUSINESS_QUALITY,
        "valuation_status": VALUATION_STATUS,
        "research_status": RESEARCH_STATUS,
        "confidence": VERDICT_CONFIDENCE,
    }
    mismatches: list[str] = []
    for key, allowed in allowed_by_key.items():
        company_value = canonical_conclusion_value(verdict.get(key), allowed)
        values = [one_values.get(key), final_values.get(key), company_value]
        present = [value for value in values if value is not None]
        if len(present) == 3 and len(set(present)) != 1:
            mismatches.append(key)
    if mismatches:
        add(findings, "error", "report-conclusion-consistency", "research-report.md#final-conclusion", f"one-page, final and company.verdict status values disagree: {mismatches!r}")
    entry_specs = (
        ("key-assumptions", ("关键假设", "关键前提", "key assumptions"), "key_assumptions"),
        ("thesis-breakers", ("thesis breakers", "thesis breaker", "论点破坏点", "推翻条件"), "thesis_breakers"),
    )
    for code, labels, company_key in entry_specs:
        one_entries = normalized_entry_set(labelled_entries(one_page, labels))
        final_entries = normalized_entry_set(labelled_entries(final, labels))
        company_entries = normalized_entry_set(verdict.get(company_key) if isinstance(verdict.get(company_key), list) else [])
        if not one_entries or one_entries != final_entries or one_entries != company_entries:
            add(findings, "error", f"report-conclusion-{code}-consistency", "research-report.md#final-conclusion", f"one-page, final and company.verdict {company_key} must map one-to-one")


def parse_score(value: Any) -> float | None:
    match = re.fullmatch(r"\s*([0-5](?:\.\d+)?)\s*(?:/\s*5)?\s*", clean_markdown_text(value))
    if not match:
        return None
    score = float(match.group(1))
    return score if 0 <= score <= 5 else None


def explicit_unscored(value: Any) -> bool:
    return normalized_text(clean_markdown_text(value)) in {
        normalized_text(item) for item in ("无法判断", "Too Hard", "N/A", "not applicable", "unscored")
    }


def gap_explained(value: str) -> bool:
    prose = report_prose_text(value)
    return substantive_text(prose, 10) and bool(re.search(
        r"缺口|未披露|待补|无法核实|证据不足|资料不足|不可得|insufficient|not disclosed|data gap|unavailable",
        prose,
        re.I,
    ))


def moat_dimension_kind(value: Any) -> str | None:
    key = normalized_text(clean_markdown_text(value))
    matches = [code for code, aliases in MOAT_CORE_DIMENSIONS if any(normalized_text(alias) in key for alias in aliases)]
    return matches[0] if len(matches) == 1 else None


def validate_final_scorecard(company: dict[str, Any], body: str, findings: list[Finding]) -> None:
    required_headers = {
        "dimension": ("维度", "dimension"),
        "score": ("评分", "分数", "score"),
        "confidence": ("置信度", "confidence"),
        "evidence": ("核心证据", "key evidence", "core evidence"),
        "counterevidence": ("最强反证", "主要反证", "strongest counterevidence", "main counterevidence"),
    }
    selected: tuple[list[str], list[list[str]], dict[str, int]] | None = None
    for headers, rows in parse_markdown_tables(body):
        columns = {key: header_column(headers, aliases) for key, aliases in required_headers.items()}
        if all(index is not None for index in columns.values()) and len(set(columns.values())) == len(columns):
            selected = (headers, rows, {key: int(index) for key, index in columns.items()})
            break
    if selected is None:
        add(findings, "error", "report-final-scorecard", "research-report.md#final-conclusion", "final conclusion needs a Markdown scorecard with dimension, score, confidence, core evidence and strongest counterevidence columns")
        return
    _, rows, columns = selected
    seen: set[str] = set()
    evidence_values: list[str] = []
    counter_values: list[str] = []
    invalid_rows = 0
    for row in rows:
        dimension = clean_markdown_text(row[columns["dimension"]])
        key = normalized_text(dimension)
        matches = [code for code, aliases in FINAL_SCORE_DIMENSIONS if any(normalized_text(alias) in key for alias in aliases)]
        if len(matches) != 1 or matches[0] in seen:
            invalid_rows += 1
            continue
        seen.add(matches[0])
        score_cell = row[columns["score"]]
        score = parse_score(score_cell)
        confidence = canonical_confidence(row[columns["confidence"]])
        evidence_raw = row[columns["evidence"]]
        counter_raw = row[columns["counterevidence"]]
        evidence = clean_markdown_text(evidence_raw)
        counter = clean_markdown_text(counter_raw)
        evidence_values.append(evidence)
        counter_values.append(counter)
        unscored = explicit_unscored(score_cell)
        if (
            confidence is None
            or (score is None and not (unscored and confidence == "low" and gap_explained(f"{evidence} {counter}")))
            or (unscored and not is_unable(company))
            or not substantive_text(report_prose_text(evidence), 10)
            or (not unscored and looks_like_placeholder(report_prose_text(evidence)))
            or not substantive_text(report_prose_text(counter), 8)
            or (not unscored and looks_like_placeholder(report_prose_text(counter)))
            or not text_has_known_citation(company, evidence_raw)
            or not text_has_known_citation(company, counter_raw)
        ):
            invalid_rows += 1
    missing = [code for code, _ in FINAL_SCORE_DIMENSIONS if code not in seen]
    evidence_prose = [report_prose_text(value) for value in evidence_values]
    counter_prose = [report_prose_text(value) for value in counter_values]
    if invalid_rows or missing or not substantive_distinct_entries(evidence_prose, 10) or not substantive_distinct_entries(counter_prose, 8):
        add(findings, "error", "report-final-scorecard-substance", "research-report.md#final-conclusion", f"final scorecard needs eight unique, substantive rows; missing={missing!r}, invalid_rows={invalid_rows}")


def validate_moat_report(company: dict[str, Any], body: str, findings: list[Finding]) -> None:
    required_headers = {
        "dimension": ("维度", "dimension"),
        "score": ("评分", "分数", "score"),
        "trend": ("趋势", "trend"),
        "confidence": ("置信度", "confidence"),
        "evidence": ("支持证据", "核心证据", "evidence"),
        "counterevidence": ("最强反证", "主要反证", "counterevidence"),
        "destroyer": ("破坏因素", "破坏条件", "最可能的破坏因素", "destroyer"),
    }
    selected: tuple[list[list[str]], dict[str, int]] | None = None
    for headers, rows in parse_markdown_tables(body):
        columns = {key: header_column(headers, aliases) for key, aliases in required_headers.items()}
        if all(index is not None for index in columns.values()) and len(set(columns.values())) == len(columns):
            selected = (rows, {key: int(index) for key, index in columns.items()})
            break
    if selected is None:
        add(findings, "error", "report-moat-matrix", "research-report.md#moat", "moat section needs separate score, trend, confidence, evidence, counterevidence and destroyer columns")
        return
    rows, columns = selected
    dimensions: set[str] = set()
    evidence_values: list[str] = []
    counter_values: list[str] = []
    destroyer_values: list[str] = []
    core_dimensions: set[str] = set()
    company_moat = {
        moat_dimension_kind(item.get("dimension")): item
        for item in list_or_empty(company.get("moat"))
        if isinstance(item, dict) and moat_dimension_kind(item.get("dimension")) is not None
    }
    score_mismatches: list[str] = []
    valid_rows = 0
    for row in rows:
        dimension = clean_markdown_text(row[columns["dimension"]])
        normalized_dimension = normalized_text(dimension)
        score_cell = row[columns["score"]]
        score = parse_score(score_cell)
        unscored = explicit_unscored(score_cell)
        trend = clean_markdown_text(row[columns["trend"]])
        confidence = canonical_confidence(row[columns["confidence"]])
        evidence_raw = row[columns["evidence"]]
        counter_raw = row[columns["counterevidence"]]
        evidence = clean_markdown_text(evidence_raw)
        counter = clean_markdown_text(counter_raw)
        destroyer = clean_markdown_text(row[columns["destroyer"]])
        core = moat_dimension_kind(dimension)
        module_item = company_moat.get(core)
        module_ids = {str(item) for item in module_item.get("source_ids", [])} if isinstance(module_item, dict) else None
        if (
            not substantive_text(dimension, 2)
            or normalized_dimension in dimensions
            or (score is None and not (unscored and confidence == "low" and gap_explained(f"{evidence} {counter}")))
            or not substantive_text(trend, 2)
            or looks_like_placeholder(trend)
            or confidence is None
            or not substantive_text(report_prose_text(evidence), 8)
            or (not unscored and looks_like_placeholder(report_prose_text(evidence)))
            or not substantive_text(report_prose_text(counter), 8)
            or (not unscored and looks_like_placeholder(report_prose_text(counter)))
            or not substantive_text(report_prose_text(destroyer), 8)
            or looks_like_placeholder(destroyer)
            or not text_has_known_citation(company, evidence_raw, module_ids)
            or not text_has_known_citation(company, counter_raw, module_ids)
        ):
            continue
        if isinstance(module_item, dict):
            module_score = module_item.get("score")
            if numeric(module_score) and (score is None or abs(score - float(module_score)) > 0.01):
                score_mismatches.append(core or dimension)
            elif module_score is None and score is not None:
                score_mismatches.append(core or dimension)
        dimensions.add(normalized_dimension)
        if core:
            core_dimensions.add(core)
        evidence_values.append(evidence)
        counter_values.append(counter)
        destroyer_values.append(destroyer)
        valid_rows += 1
    missing_core = []
    explained_not_applicable: set[str] = set()
    for code, aliases in MOAT_CORE_DIMENSIONS:
        if code in core_dimensions:
            continue
        na_line = next((line for line in body.splitlines() if any(alias.lower() in line.lower() for alias in aliases) and re.search(r"不适用|无法判断|not applicable|n/a", line, re.I)), "")
        if gap_explained(na_line) and text_has_known_citation(company, na_line):
            explained_not_applicable.add(code)
        else:
            missing_core.append(code)
    if (
        valid_rows + len(explained_not_applicable) < 4
        or not substantive_distinct_entries([report_prose_text(value) for value in evidence_values], 8)
        or not substantive_distinct_entries([report_prose_text(value) for value in counter_values], 8)
        or not substantive_distinct_entries([report_prose_text(value) for value in destroyer_values], 8)
    ):
        add(findings, "error", "report-moat-matrix-substance", "research-report.md#moat", "moat matrix needs at least four unique dimensions with substantive, non-repeated evidence, counterevidence and destroyers")
    if missing_core:
        add(findings, "error", "report-moat-core-coverage", "research-report.md#moat", f"moat matrix must cover four core dimensions or explain a sourced data gap: {missing_core!r}")
    if score_mismatches:
        add(findings, "error", "report-moat-score-consistency", "research-report.md#moat", f"moat scores must reconcile to company.moat by dimension: {score_mismatches!r}")


def probability_value(value: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?\s*%|\b(?:high|medium|low)\b|(?:极高|高|中高|中|中低|低|极低)(?:概率)?", value, re.I))


def impact_value(value: str) -> bool:
    return bool(re.search(r"\b(?:critical|severe|high|medium|low)\b|毁灭|严重|重大|极高|高|中高|中|中低|低", value, re.I))


def horizon_value(value: str) -> bool:
    return bool(re.search(r"\d+(?:\s*[–—-]\s*\d+)?\s*(?:年|月|季|years?|months?|quarters?)|随时|持续|短期|中期|长期", value, re.I))


def reversibility_value(value: str) -> bool:
    return bool(re.search(r"不可逆|可逆|部分可逆|极高|高|中高|中|中低|低|极低|\b(?:yes|no|partial|high|medium|low)\b", value, re.I))


def validate_pre_mortem_report(company: dict[str, Any], body: str, findings: list[Finding]) -> None:
    required_headers = {
        "path": ("失败路径", "failure path"),
        "probability": ("概率", "probability", "likelihood"),
        "impact": ("影响", "impact"),
        "horizon": ("期限", "时间", "horizon", "time frame"),
        "warning": ("最早预警", "早期信号", "earliest warning", "leading signal"),
        "reversibility": ("可逆性", "reversibility"),
        "mitigation": ("管理层缓解", "缓解能力", "management mitigation", "mitigation"),
    }
    selected: tuple[list[list[str]], dict[str, int]] | None = None
    for headers, rows in parse_markdown_tables(body):
        columns = {key: header_column(headers, aliases) for key, aliases in required_headers.items()}
        if all(index is not None for index in columns.values()) and len(set(columns.values())) == len(columns):
            selected = (rows, {key: int(index) for key, index in columns.items()})
            break
    if selected is None:
        add(findings, "error", "report-pre-mortem-matrix", "research-report.md#pre-mortem", "Pre-Mortem needs path, probability, impact, horizon, earliest warning, reversibility and management mitigation columns")
        return
    rows, columns = selected
    paths: list[str] = []
    valid_rows = 0
    for row in rows:
        path = clean_markdown_text(row[columns["path"]])
        probability = clean_markdown_text(row[columns["probability"]])
        impact = clean_markdown_text(row[columns["impact"]])
        horizon = clean_markdown_text(row[columns["horizon"]])
        warning = clean_markdown_text(row[columns["warning"]])
        reversibility = clean_markdown_text(row[columns["reversibility"]])
        mitigation = clean_markdown_text(row[columns["mitigation"]])
        if (
            not substantive_text(path, 8)
            or looks_like_placeholder(path)
            or not probability_value(probability)
            or not impact_value(impact)
            or not horizon_value(horizon)
            or not substantive_text(warning, 6)
            or looks_like_placeholder(warning)
            or not reversibility_value(reversibility)
            or not substantive_text(mitigation, 8)
            or looks_like_placeholder(mitigation)
        ):
            continue
        paths.append(path)
        valid_rows += 1
    if valid_rows < 5 or not substantive_distinct_entries(paths, 8):
        add(findings, "error", "report-pre-mortem-substance", "research-report.md#pre-mortem", "Pre-Mortem needs at least five distinct, fully specified failure paths")

    risks = company.get("risks") if isinstance(company.get("risks"), dict) else {}
    expected_paths = [item for item in list_or_empty(risks.get("pre_mortem")) if substantive_text(item, 8)]
    normalized_expected = [normalized_text(item) for item in expected_paths]
    matched_expected: list[int] = []
    path_mapping_valid = len(rows) == len(paths) == len(expected_paths) and bool(expected_paths)
    if path_mapping_valid:
        for path in paths:
            normalized_path = normalized_text(path)
            matches = [index for index, expected in enumerate(normalized_expected) if expected and expected in normalized_path]
            if matches:
                longest = max(len(normalized_expected[index]) for index in matches)
                matches = [index for index in matches if len(normalized_expected[index]) == longest]
            if len(matches) != 1:
                path_mapping_valid = False
                break
            matched_expected.append(matches[0])
        path_mapping_valid = path_mapping_valid and len(set(matched_expected)) == len(expected_paths)
    if not path_mapping_valid:
        add(findings, "error", "report-pre-mortem-path-mapping", "research-report.md#pre-mortem", "failure-path rows must uniquely contain and exhaust company.risks.pre_mortem, with no extra rows")

    verdict = company.get("verdict") if isinstance(company.get("verdict"), dict) else {}
    bear = labelled_value(body, ("最强反方观点", "最强悲观观点", "strongest bear case", "bear case"))
    expected_bear = risks.get("bear_case")
    bear_matches = (
        substantive_text(bear, 12)
        and not looks_like_placeholder(report_prose_text(bear or ""))
        and (
            (substantive_text(expected_bear, 12) and normalized_text(bear) == normalized_text(expected_bear))
            or (not substantive_text(expected_bear, 12) and is_unable(company) and gap_explained(bear or ""))
        )
    )
    if not bear_matches:
        add(findings, "error", "report-pre-mortem-bear-case", "research-report.md#pre-mortem", "Pre-Mortem needs a labelled strongest bear case matching company.risks.bear_case")

    fragile_labels = ("三个最脆弱假设", "最脆弱假设", "脆弱假设", "three fragile assumptions", "fragile assumptions")
    fragile = labelled_entries(body, fragile_labels)
    expected_fragile = list_or_empty(risks.get("fragile_assumptions"))
    fragile_matches = (
        len(fragile) == 3
        and substantive_distinct_entries(fragile, 8)
        and normalized_entry_set(fragile) == normalized_entry_set(expected_fragile)
    )
    if not fragile_matches:
        gap_value = labelled_value(body, fragile_labels)
        if not (is_unable(company) and not expected_fragile and gap_explained(gap_value or "")):
            add(findings, "error", "report-pre-mortem-fragile-assumptions", "research-report.md#pre-mortem", "Pre-Mortem needs exactly three fragile assumptions matching company.risks.fragile_assumptions")

    breaker_labels = ("thesis breakers", "thesis breaker", "论点破坏点", "推翻条件")
    breakers = labelled_entries(body, breaker_labels)
    expected_breakers = list_or_empty(verdict.get("thesis_breakers"))
    breakers_match = (
        bool(breakers)
        and substantive_distinct_entries(breakers, 8)
        and normalized_entry_set(breakers) == normalized_entry_set(expected_breakers)
    )
    if not breakers_match:
        gap_value = labelled_value(body, breaker_labels)
        if not (is_unable(company) and not expected_breakers and gap_explained(gap_value or "")):
            add(findings, "error", "report-pre-mortem-thesis-breakers", "research-report.md#pre-mortem", "Pre-Mortem thesis breakers must map one-to-one to company.verdict.thesis_breakers")

    bankruptcy = labelled_value(body, ("破产路径", "破产情景", "bankruptcy outcome", "bankruptcy case"))
    low_return = labelled_value(body, ("存活但股东回报差", "存活但低回报", "survives with poor returns", "survival with poor returns"))
    outcomes_valid = (
        substantive_text(report_prose_text(bankruptcy or ""), 12)
        and substantive_text(report_prose_text(low_return or ""), 12)
        and not looks_like_placeholder(report_prose_text(bankruptcy or ""))
        and not looks_like_placeholder(report_prose_text(low_return or ""))
        and normalized_text(bankruptcy) != normalized_text(low_return)
    )
    if not outcomes_valid:
        add(findings, "error", "report-pre-mortem-outcome-distinction", "research-report.md#pre-mortem", "Pre-Mortem must separately explain bankruptcy and survival with poor shareholder returns")


def report_number_matches(actual: float | None, expected: Any) -> bool:
    if actual is None or not numeric(expected):
        return False
    expected_number = float(expected)
    return abs(actual - expected_number) <= max(0.0005, abs(expected_number) * 0.02)


DISPLAY_MONEY_UNIT_RE = re.compile(
    r"(?:万亿元|亿元|万元|万亿(?:美元|港元|欧元|英镑|日元)|亿(?:美元|港元|欧元|英镑|日元)|"
    r"万(?:美元|港元|欧元|英镑|日元)|人民币元|美元|港元|欧元|英镑|日元|元)"
)
DISPLAY_SHARE_UNIT_RE = re.compile(r"(?:亿股|万股|股)")
DISPLAY_PER_SHARE_UNIT_RE = re.compile(r"(?:人民币元|美元|港元|欧元|英镑|日元|元)\s*/\s*股")
DISPLAY_PERCENT_UNIT_RE = re.compile(r"(?:%|个百分点|个?基点)")

DISPLAY_COLUMN_PATTERNS = (
    (
        "per_share",
        re.compile(r"(?:每股|股价|回购均价|市场价格|今日价值|公允价值)(?!.*(?:增长|涨跌))", re.I),
    ),
    (
        "shares",
        re.compile(r"(?:稀释后股数|总股本|股份数|股数|回购股数|发行股数)", re.I),
    ),
    (
        "percent",
        re.compile(
            r"(?:增长率|增速|利润率|毛利率|净利率|回报率|收益率|折现率|终值增长|永续增长|"
            r"初期现金流增长|起始现金流增长|终值占比|占比|比例|税率|ROIC|ROE|ROTCE|CET1|FCF\s*Yield)",
            re.I,
        ),
    ),
    ("duration", re.compile(r"(?:显性期|预测期|持有期|年限|期限)", re.I)),
    (
        "money",
        re.compile(
            r"(?:营收|总收入|收入金额|成本|费用|利润|现金流|FCFF|FCFE|Owner Earnings|"
            r"现金|债务|市值|企业价值|资本开支|回购金额|分红|初期.*总额|起始.*总额|"
            r"金额|价值总额|净资产|普通股权益)",
            re.I,
        ),
    ),
)


def display_column_kind(header: str) -> str | None:
    cleaned = clean_markdown_text(header)
    if re.search(r"(?:口径|期间|日期|来源|说明|比较|阈值)", cleaned, re.I):
        return None
    for kind, pattern in DISPLAY_COLUMN_PATTERNS:
        if pattern.search(cleaned):
            return kind
    return None


def display_unit_present(value: str, kind: str, *, header: bool = False) -> bool:
    cleaned = clean_markdown_text(value)
    if kind == "money":
        unit_pattern = DISPLAY_MONEY_UNIT_RE
    elif kind == "shares":
        unit_pattern = DISPLAY_SHARE_UNIT_RE
    elif kind == "per_share":
        unit_pattern = DISPLAY_PER_SHARE_UNIT_RE
    elif kind == "percent":
        unit_pattern = DISPLAY_PERCENT_UNIT_RE
    elif kind == "duration":
        unit_pattern = re.compile(r"年")
    else:
        return False
    if header:
        return bool(
            re.search(rf"[（(][^）)]*{unit_pattern.pattern}[^）)]*[）)]", cleaned, re.I)
            or re.search(rf"(?:单位\s*[:：]|/)\s*{unit_pattern.pattern}", cleaned, re.I)
        )
    return unit_pattern.search(cleaned) is not None


def display_unit_token(value: str, kind: str, header: str = "") -> str | None:
    for source, is_header in ((value, False), (header, True)):
        if not source or not display_unit_present(source, kind, header=is_header):
            continue
        pattern = {
            "money": DISPLAY_MONEY_UNIT_RE,
            "shares": DISPLAY_SHARE_UNIT_RE,
            "per_share": DISPLAY_PER_SHARE_UNIT_RE,
            "duration": re.compile(r"年"),
        }.get(kind)
        if pattern is not None:
            match = pattern.search(clean_markdown_text(source))
            if match:
                return match.group(0)
    return None


def parse_localized_display_number(value: Any, kind: str, header: str = "") -> float | None:
    """Parse a Chinese display value into base currency units, shares, per-share value or years."""
    cleaned = clean_markdown_text(value).replace(",", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if match is None:
        return None
    number = float(match.group(0))
    token = display_unit_token(cleaned, kind, header)
    if token is None:
        return None
    if kind == "money":
        if "万亿" in token:
            return number * 1e12
        if "亿" in token:
            return number * 1e8
        if token.startswith("万") or token == "万元":
            return number * 1e4
        return number
    if kind == "shares":
        if token == "亿股":
            return number * 1e8
        if token == "万股":
            return number * 1e4
        return number
    return number


def validate_chinese_display_units(report: str, findings: list[Finding], path: str = "research-report.md") -> None:
    """Keep storage units and unlabeled storage-scale values out of Chinese reader-facing text."""
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", report))
    if cjk_count < 10:
        return
    matches = sorted(
        {
            match.group(0).strip()
            for pattern in NONLOCALIZED_CHINESE_UNIT_PATTERNS
            for match in pattern.finditer(report)
        }
    )
    if matches:
        add(
            findings,
            "error",
            "report-display-units-not-localized",
            path,
            "Chinese reader-facing text must convert storage-scale units to 元/万/亿/万亿 and 亿股/万股; "
            f"found {matches!r}",
        )

    table_violations: set[str] = set()
    for headers, rows in parse_markdown_tables(report):
        for index, header in enumerate(headers):
            kind = display_column_kind(header)
            if kind is None:
                continue
            header_has_unit = display_unit_present(header, kind, header=True)
            for row in rows:
                if index >= len(row):
                    continue
                cell = clean_markdown_text(row[index])
                if not re.search(r"\d", cell):
                    continue
                if header_has_unit or display_unit_present(cell, kind):
                    continue
                table_violations.add(f"{clean_markdown_text(header)}={cell}")
    if table_violations:
        add(
            findings,
            "error",
            "report-display-unit-missing",
            path,
            "Numeric money, share, per-share, percentage and duration columns need a Chinese unit in the header or every numeric cell; "
            f"found {sorted(table_violations)[:8]!r}",
        )

    prose = "\n".join(line for line in report.splitlines() if not line.lstrip().startswith("|"))
    contextual_patterns = (
        (
            "money",
            re.compile(
                r"(?:初期|起始)?(?:可分配)?(?:现金流)?总额|市值|企业价值|净债务|总债务|"
                r"现金余额|营业收入|总收入|营收|净利润|自由现金流|资本开支|回购金额",
                re.I,
            ),
        ),
        ("shares", re.compile(r"稀释后股数|总股本|回购股数|发行股数", re.I)),
        ("per_share", re.compile(r"初期每股现金流|每股价值|股价|回购均价", re.I)),
        (
            "percent",
            re.compile(r"增长率|利润率|收益率|折现率|终值增长|永续增长|终值占比|ROIC|ROE", re.I),
        ),
    )
    prose_violations: set[str] = set()
    for kind, label_pattern in contextual_patterns:
        pattern = re.compile(
            rf"(?P<label>{label_pattern.pattern})\s*(?:约为|为|[:：])?\s*"
            r"(?P<number>[-+]?\d[\d,]*(?:\.\d+)?)",
            re.I,
        )
        for match in pattern.finditer(prose):
            tail = prose[match.start("number"):match.end("number") + 14]
            if not display_unit_present(tail, kind):
                prose_violations.add(f"{match.group('label')}={match.group('number')}")
    if prose_violations:
        add(
            findings,
            "error",
            "report-display-unit-missing",
            path,
            "Standalone financial figures must carry Chinese reader-facing units instead of exposing bare storage values; "
            f"found {sorted(prose_violations)[:8]!r}",
        )


def validate_valuation_report(company: dict[str, Any], body: str, findings: list[Finding], calculations: Any = None) -> None:
    if is_unable(company) and re.search(r"无法判断|too hard", body, re.I) and gap_explained(body):
        return
    valuation = company.get("valuation") if isinstance(company.get("valuation"), dict) else {}
    tables = parse_markdown_tables(body)
    start_record = next(
        (
            item
            for item in list_or_empty(calculations.get("calculations") if isinstance(calculations, dict) else [])
            if isinstance(item, dict) and item.get("valuation_role") == "starting_cash_flow"
        ),
        None,
    )
    input_headers = {
        "basis": ("现金流口径", "cash flow basis"),
        "period": ("基准期间", "基准期", "base period"),
        "total": ("初期现金流总额", "起始现金流总额", "starting cash flow"),
        "shares": ("稀释后股数", "diluted shares"),
        "per_share": ("初期每股现金流", "起始每股现金流", "starting cash flow per share"),
        "years": ("显性期", "显性预测期", "forecast years"),
    }
    input_valid = False
    financial_scale, share_scale = unit_scale(company)
    for headers, rows in tables:
        columns = {key: header_column(headers, aliases) for key, aliases in input_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        for row in rows:
            basis_text = clean_markdown_text(row[int(columns["basis"])]).lower()
            period_text = clean_markdown_text(row[int(columns["period"])]).lower()
            total_index = int(columns["total"])
            shares_index = int(columns["shares"])
            per_share_index = int(columns["per_share"])
            years_index = int(columns["years"])
            total = parse_localized_display_number(row[total_index], "money", headers[total_index])
            shares = parse_localized_display_number(row[shares_index], "shares", headers[shares_index])
            per_share = parse_localized_display_number(row[per_share_index], "per_share", headers[per_share_index])
            years = parse_localized_display_number(row[years_index], "duration", headers[years_index])
            if re.search(r"(?:^|[^a-z])eps(?:$|[^a-z])|earnings\s*per\s*share|每股收益", basis_text, re.I):
                add(findings, "error", "report-valuation-eps-input", "research-report.md#valuation", "DCF input table cannot use EPS as its cash-flow basis")
                continue
            allowed_basis_aliases = ("fcff", "fcfe", "owner earnings", "所有者收益", "distributable common cash", "股东可分配现金", "可分配普通股现金")
            row_valid = (
                any(alias in basis_text for alias in allowed_basis_aliases)
                and all(value is not None for value in (total, shares, per_share, years))
                and float(shares) > 0
                and float(years) > 0
            )
            if isinstance(start_record, dict):
                basis = start_record.get("cash_flow_basis")
                basis_aliases = {
                    "fcff": ("fcff",),
                    "fcfe": ("fcfe",),
                    "owner_earnings": ("owner earnings", "owner earnings", "所有者收益"),
                    "distributable_common_cash": ("distributable common cash", "股东可分配现金", "可分配普通股现金", "fcfe"),
                }
                row_valid = row_valid and any(alias in basis_text for alias in basis_aliases.get(str(basis), ()))
                row_valid = row_valid and normalized_text(start_record.get("period")) in normalized_text(period_text)
                expected_total = float(start_record.get("result")) * financial_scale if numeric(start_record.get("result")) else None
                expected_shares = float(start_record.get("diluted_shares")) * share_scale if numeric(start_record.get("diluted_shares")) else None
                row_valid = row_valid and report_number_matches(total, expected_total)
                row_valid = row_valid and report_number_matches(shares, expected_shares)
                row_valid = row_valid and report_number_matches(per_share, start_record.get("per_share"))
                row_valid = row_valid and report_number_matches(years, start_record.get("forecast_years"))
            input_valid = bool(row_valid)
            if input_valid:
                break
        break
    if not input_valid:
        add(findings, "error", "report-valuation-inputs", "research-report.md#valuation", "valuation section needs one reconciled DCF input table with cash-flow basis, base period, starting total/per-share cash flow, diluted shares and forecast years")

    scenario_headers = {
        "scenario": ("情景", "场景", "scenario"),
        "growth": ("初期现金流增长", "现金流增长", "fcf增长", "fcfe增长", "可分配现金增长", "收入增长", "营收增长", "cash flow growth", "revenue growth"),
        "discount": ("折现率", "discount rate"),
        "terminal": ("永续增长", "终值增长", "terminal growth"),
        "terminal_share": ("终值占比", "terminal value share"),
        "value": ("每股价值", "公允价值", "fair value"),
    }
    scenario_index: int | None = None
    scenario_valid = False
    expected_scenarios = {
        scenario_kind(item.get("name")): item
        for item in list_or_empty(valuation.get("dcf_scenarios"))
        if isinstance(item, dict) and scenario_kind(item.get("name")) is not None
    }
    for table_index, (headers, rows) in enumerate(tables):
        columns = {key: header_column(headers, aliases) for key, aliases in scenario_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        scenario_index = table_index
        kinds: set[str] = set()
        invalid = 0
        for row in rows:
            kind = scenario_kind(row[int(columns["scenario"])])
            expected = expected_scenarios.get(kind)
            values = {
                "revenue_growth": parse_report_number(row[int(columns["growth"])]),
                "discount_rate": parse_report_number(row[int(columns["discount"])]),
                "terminal_growth": parse_report_number(row[int(columns["terminal"])]),
                "fair_value_per_share": parse_report_number(row[int(columns["value"])]),
            }
            terminal_share = parse_report_number(row[int(columns["terminal_share"])] )
            if kind is None or kind in kinds or any(value is None for value in values.values()) or terminal_share is None or not 0 <= float(terminal_share) <= 1:
                invalid += 1
                continue
            kinds.add(kind)
            if isinstance(expected, dict) and any(not report_number_matches(actual, expected.get(key)) for key, actual in values.items()):
                invalid += 1
        scenario_valid = kinds == {"bear", "base", "bull"} and invalid == 0
        break
    if scenario_index is None or not scenario_valid or not re.search(r"\bdcf\b|现金流折现", body, re.I):
        add(findings, "error", "report-valuation-scenarios", "research-report.md#valuation", "valuation section needs a three-scenario cash-flow DCF table with growth, discount rate, terminal growth, terminal-value share and values reconciled to company.valuation")

    sensitivity_headers = {
        "discount": ("折现率", "discount rate"),
        "terminal": ("永续增长", "终值增长", "terminal growth"),
        "value": ("每股价值", "公允价值", "fair value"),
    }
    actual_cells: list[tuple[float, float, float]] = []
    for table_index, (headers, rows) in enumerate(tables):
        if table_index == scenario_index:
            continue
        columns = {key: header_column(headers, aliases) for key, aliases in sensitivity_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        for row in rows:
            values = tuple(parse_report_number(row[int(columns[key])]) for key in ("discount", "terminal", "value"))
            if all(value is not None for value in values):
                actual_cells.append((float(values[0]), float(values[1]), float(values[2])))
        break
    expected_cells = [
        (item.get("discount_rate"), item.get("terminal_growth"), item.get("fair_value_per_share"))
        for item in list_or_empty(valuation.get("dcf_sensitivity"))
        if isinstance(item, dict)
    ]
    unique_pairs = {(round(discount, 6), round(terminal, 6)) for discount, terminal, _ in actual_cells}
    cells_match = len(actual_cells) >= 4 and len(unique_pairs) >= 4
    if expected_cells:
        cells_match = cells_match and all(
            any(
                report_number_matches(actual_discount, expected[0])
                and report_number_matches(actual_terminal, expected[1])
                and report_number_matches(actual_value, expected[2])
                for actual_discount, actual_terminal, actual_value in actual_cells
            )
            for expected in expected_cells
        )
    if not cells_match or not re.search(r"敏感|sensitivity", body, re.I):
        add(findings, "error", "report-valuation-sensitivity", "research-report.md#valuation", "valuation section needs a distinct, reconciled DCF sensitivity table with at least four cells")

    reverse_headers = {
        "dimension": ("假设", "维度", "assumption", "dimension"),
        "implied": ("隐含值", "隐含假设", "implied value", "implied assumption"),
        "comparison": ("历史比较", "现实比较", "comparison"),
        "threshold": ("推翻阈值", "临界条件", "threshold", "breaker"),
    }
    reverse = valuation.get("reverse_dcf") if isinstance(valuation.get("reverse_dcf"), dict) else {}
    category_tokens = {
        "growth": ("growth", "cagr", "revenue", "sales", "cash_flow", "fcf", "fcfe", "增长", "收入", "营收", "现金流"),
        "profitability": ("margin", "roe", "roa", "roic", "rotce", "profit", "利润率", "回报率", "回报", "净利率"),
        "capital-cash": ("capital", "reinvest", "cash", "capex", "turnover", "payout", "retention", "buyback", "资本", "再投资", "现金", "周转", "留存", "分配", "回购"),
    }
    expected_by_category: dict[str, list[float]] = {key: [] for key in category_tokens}
    for path, value in flatten_leaves(reverse):
        if not numeric(value):
            continue
        for category, tokens in category_tokens.items():
            if any(token in path.lower() for token in tokens):
                expected_by_category[category].append(float(value))
                break
    reverse_categories: set[str] = set()
    reverse_valid = False
    for headers, rows in tables:
        columns = {key: header_column(headers, aliases) for key, aliases in reverse_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        invalid = 0
        for row in rows:
            dimension = clean_markdown_text(row[int(columns["dimension"])]).lower()
            implied = parse_report_number(row[int(columns["implied"])] )
            comparison = report_prose_text(row[int(columns["comparison"])] )
            threshold = report_prose_text(row[int(columns["threshold"])] )
            category = next(
                (name for name, tokens in category_tokens.items() if any(token in dimension for token in tokens)),
                None,
            )
            if re.search(r"(?:^|[^a-z])eps(?:$|[^a-z])|earnings\s*per\s*share|每股收益", dimension, re.I):
                category = None
            expected_values = expected_by_category.get(category, []) if category else []
            if (
                category is None
                or category in reverse_categories
                or not any(report_number_matches(implied, expected) for expected in expected_values)
                or not substantive_text(comparison, 8)
                or not substantive_text(threshold, 8)
            ):
                invalid += 1
                continue
            reverse_categories.add(category)
        reverse_valid = len(reverse_categories) >= 2 and invalid == 0
        break
    if not reverse_valid or not re.search(r"reverse\s*dcf|反向\s*dcf", body, re.I):
        add(findings, "error", "report-valuation-reverse-dcf", "research-report.md#valuation", "valuation section needs a reconciled Reverse DCF table with implied values, reality comparison and thesis-breaking thresholds")


def source_type_matches(value: str, source_type: Any) -> bool:
    if not nonblank(source_type):
        return False
    key = normalized_text(value)
    candidates = (str(source_type),) + SOURCE_TYPE_ALIASES.get(str(source_type), ())
    return any(normalized_text(candidate) in key for candidate in candidates)


def source_title_matches(value: str, title: Any) -> bool:
    if not substantive_text(title, 4):
        return False
    actual = normalized_text(value)
    expected = normalized_text(title)
    return bool(actual and expected and (actual in expected or expected in actual or SequenceMatcher(None, actual, expected, autojunk=False).ratio() >= 0.72))


def source_date_or_period_matches(value: str, source: dict[str, Any]) -> bool:
    published = source.get("published_at")
    if nonblank(published) and published in value:
        return True
    source_text = f"{source.get('title', '')} {source.get('notes', '')}"
    periods = set(re.findall(r"(?:fy)?20\d{2}(?:q[1-4]|h[12])?|20\d{2}(?:fy|q[1-4]|h[12])", source_text, flags=re.I))
    normalized_value = normalized_text(value)
    if any(normalized_text(period) in normalized_value for period in periods):
        return True
    if nonblank(published) or periods:
        return False
    return bool(re.search(r"\b20\d{2}(?:[-/]\d{2}(?:[-/]\d{2})?)?\b|\bFY20\d{2}\b|\b20\d{2}Q[1-4]\b", value, re.I))


def specific_source_location(value: str) -> bool:
    cleaned = clean_markdown_text(value)
    if looks_like_placeholder(cleaned):
        return False
    patterns = (
        r"\bpp?\.?\s*\d+",
        r"\bpages?\s+\d+",
        r"\bsections?\s+[\w.-]+",
        r"\bitems?\s+\d+[a-z]?",
        r"\bnotes?\s+\d+[a-z]?",
        r"\btables?\s+\d+",
        r"\bpart\s+[ivx]+",
        r"\bmd&a\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\b",
        r"第\s*\d+\s*页",
        r"第\s*[\u4e00-\u9fff0-9]+\s*章",
        r"页码\s*[:\uff1a]?\s*\d+",
        r"章节\s*[:\uff1a]?\s*[\u4e00-\u9fff\w.-]{2,}",
        r"表\s*\d+",
    )
    return any(re.search(pattern, cleaned, re.I) for pattern in patterns)


def source_page_limit(source: dict[str, Any]) -> int:
    for key in ("page_count", "pages", "total_pages"):
        value = source.get(key)
        if isinstance(value, int) and 1 <= value <= DEFAULT_SOURCE_PAGE_LIMIT:
            return value
    notes = str(source.get("notes", ""))
    match = re.search(r"(?:total|共)?\s*(\d{1,5})\s*(?:pages?|页)", notes, re.I)
    if match and 1 <= int(match.group(1)) <= DEFAULT_SOURCE_PAGE_LIMIT:
        return int(match.group(1))
    return DEFAULT_SOURCE_PAGE_LIMIT


def source_location_matches(value: str, source: dict[str, Any]) -> bool:
    if not specific_source_location(value):
        return False
    page_numbers: list[int] = []
    page_patterns = (
        r"\bpp?\.?\s*(\d+)(?:\s*[–—-]\s*(\d+))?",
        r"\bpages?\s+(\d+)(?:\s*[–—-]\s*(\d+))?",
        r"第\s*(\d+)\s*页",
        r"页码\s*[:\uff1a]?\s*(\d+)(?:\s*[–—-]\s*(\d+))?",
    )
    for pattern in page_patterns:
        for match in re.finditer(pattern, value, re.I):
            page_numbers.extend(int(item) for item in match.groups() if item is not None)
    if page_numbers:
        limit = source_page_limit(source)
        if any(page < 1 or page > limit for page in page_numbers):
            return False
    return True


def validate_source_index(company: dict[str, Any], report: str, blocks: list[HeadingBlock], findings: list[Finding]) -> None:
    source_block = next((block for block in blocks if heading_matches(block.title, REPORT_SOURCE_HEADINGS)), None)
    if source_block is not None:
        final_block = next((block for block in blocks if block.level == 2 and heading_matches(block.title, ("最终结论", "final conclusion"))), None)
        if final_block is not None and source_block.start < final_block.start:
            add(findings, "error", "report-source-index-order", "research-report.md#source-index", "source index must appear after the sixteenth required section")
    citation_scope = report[:source_block.start] if source_block is not None else report
    cited = {match.group(0) for match in re.finditer(r"\bSRC-[A-Za-z0-9_-]+\b", citation_scope, re.I)}
    if not cited:
        return
    if source_block is None:
        add(findings, "error", "report-source-index", "research-report.md", "a report citing SRC IDs needs a dedicated source index")
        return
    required_headers = {
        "id": ("来源id", "source id", "id"),
        "title": ("标题", "title"),
        "publisher_type": ("发布者/类型", "发布者或类型", "publisher/type", "publisher or type", "source type"),
        "date_period": ("日期/期间", "日期或期间", "date/period", "date or period"),
        "url": ("url", "link", "链接"),
        "location": ("页码/章节定位", "页码或章节定位", "location", "page/section"),
    }
    selected: tuple[list[list[str]], dict[str, int]] | None = None
    for headers, rows in parse_markdown_tables(source_block.body):
        columns = {key: header_column(headers, aliases) for key, aliases in required_headers.items()}
        if all(index is not None for index in columns.values()) and len(set(columns.values())) == len(columns):
            selected = (rows, {key: int(index) for key, index in columns.items()})
            break
    if selected is None:
        add(findings, "error", "report-source-index-structure", "research-report.md#source-index", "source index needs ID, title, publisher/type, date/period, URL and page/section columns")
        return
    known = {str(item.get("id")): item for item in list_or_empty(company.get("sources")) if isinstance(item, dict) and nonblank(item.get("id"))}
    rows, columns = selected
    indexed: set[str] = set()
    invalid: list[str] = []
    for row in rows:
        id_match = re.fullmatch(r"\s*(SRC-[A-Za-z0-9_-]+)\s*", clean_markdown_text(row[columns["id"]]), re.I)
        if not id_match:
            invalid.append("invalid-id")
            continue
        source_id = id_match.group(1)
        canonical_id = next((item for item in known if item.lower() == source_id.lower()), source_id)
        source = known.get(canonical_id)
        if source is None or canonical_id in indexed:
            invalid.append(source_id)
            continue
        title = clean_markdown_text(row[columns["title"]])
        publisher_type = clean_markdown_text(row[columns["publisher_type"]])
        date_period = clean_markdown_text(row[columns["date_period"]])
        url_cell = row[columns["url"]]
        location = clean_markdown_text(row[columns["location"]])
        urls = [item.rstrip(".,;\uff1b") for item in re.findall(r"https?://[^\s)>]+", url_cell)]
        expected_url = source.get("url")
        url_matches = nonblank(expected_url) and any(item.rstrip("/") == str(expected_url).rstrip("/") for item in urls)
        publisher_matches = nonblank(source.get("publisher")) and normalized_text(source.get("publisher")) in normalized_text(publisher_type)
        type_matches = source_type_matches(publisher_type, source.get("source_type"))
        if not (
            source_title_matches(title, source.get("title"))
            and publisher_matches
            and type_matches
            and source_date_or_period_matches(date_period, source)
            and url_matches
            and source_location_matches(location, source)
        ):
            invalid.append(canonical_id)
            continue
        indexed.add(canonical_id)
    canonical_cited = {next((item for item in known if item.lower() == source_id.lower()), source_id) for source_id in cited}
    unresolved = sorted(source_id for source_id in canonical_cited if source_id not in indexed)
    if invalid or not indexed or not cited or unresolved:
        add(findings, "error", "report-source-index-mapping", "research-report.md#source-index", f"every cited SRC ID needs complete, matching metadata; invalid={sorted(set(invalid))!r}, unresolved={unresolved!r}")


def validate_report(company: dict[str, Any], report: str, mode: str, findings: list[Finding], calculations: Any = None) -> None:
    report = mask_non_rendered_markdown(report)
    lowered = report.lower()
    blocks = parse_heading_blocks(report)
    if mode == "full":
        validate_chinese_display_units(report, findings)
        html_tags = sorted(set(raw_html_tags(report)))
        if html_tags:
            add(findings, "error", "report-raw-html", "research-report.md", f"formal Markdown permits only br tags; raw HTML tags found: {html_tags!r}")
        allowed_urls = known_source_urls(company)
        unknown_urls = sorted(url for url in extract_report_urls(report) if url.rstrip("/") not in allowed_urls)
        if unknown_urls:
            add(findings, "error", "report-source-url", "research-report.md", f"direct source URLs must match company.sources[].url: {unknown_urls!r}")
        major = [block for block in blocks if block.level == 2]
        positions: dict[str, int] = {}
        bodies: dict[str, str] = {}
        ambiguous: list[str] = []
        for index, block in enumerate(major):
            matches = [code for code, alternatives in REPORT_SECTIONS if heading_matches(block.title, alternatives)]
            if len(matches) > 1:
                ambiguous.append(block.title)
            elif len(matches) == 1:
                code = matches[0]
                if code in positions:
                    ambiguous.append(block.title)
                else:
                    positions[code] = index
                    bodies[code] = block.body
        if ambiguous:
            add(findings, "error", "report-section-ambiguous", "research-report.md", f"required section headings must be unique and cannot combine modules: {ambiguous!r}")
        for code, alternatives in REPORT_SECTIONS:
            if code not in positions:
                add(findings, "error", f"report-section-{code}", "research-report.md", f"missing level-two Markdown heading: {alternatives[0]}")
        ordered_positions = [positions[code] for code, _ in REPORT_SECTIONS if code in positions]
        if len(ordered_positions) == len(REPORT_SECTIONS) and ordered_positions != sorted(ordered_positions):
            add(findings, "error", "report-section-order", "research-report.md", "the sixteen required level-two sections are not in protocol order")
        section_bodies: list[str] = []
        for code, _ in REPORT_SECTIONS:
            if code not in bodies:
                continue
            body = report_prose_text(bodies[code])
            section_bodies.append(body)
            if len(normalized_text(body)) < 50 or looks_like_placeholder(body):
                add(findings, "error", "report-section-thin", f"research-report.md#{code}", "section body is too thin to support a formal conclusion")
            if code in REPORT_EVIDENCE_SECTIONS and not text_has_known_citation(company, bodies[code]):
                add(findings, "error", "report-section-citation", f"research-report.md#{code}", "key evidence section needs an inline SRC ID or direct source URL")
        fingerprints: dict[str, int] = {}
        for body in section_bodies:
            fingerprint = normalized_text(body, replace_numbers=True)
            fingerprints[fingerprint] = fingerprints.get(fingerprint, 0) + 1
        if any(count >= 2 for count in fingerprints.values()) or has_near_duplicate_cluster(section_bodies, minimum_count=2, ratio=0.94):
            add(findings, "error", "repeated-report-section", "research-report.md", "two or more required sections repeat the same body with only numbers or citations changed")
        if "one-page-conclusion" in bodies:
            validate_one_page_report(bodies["one-page-conclusion"], findings)
        if "moat" in bodies:
            validate_moat_report(company, bodies["moat"], findings)
        if "pre-mortem" in bodies:
            validate_pre_mortem_report(company, bodies["pre-mortem"], findings)
        if "valuation" in bodies:
            validate_valuation_report(company, bodies["valuation"], findings, calculations)
        if "final-conclusion" in bodies:
            validate_conclusion_fields(bodies["final-conclusion"], findings, section="final-conclusion", code_prefix="report-final")
            validate_final_scorecard(company, bodies["final-conclusion"], findings)
        if "one-page-conclusion" in bodies and "final-conclusion" in bodies:
            validate_conclusion_consistency(company, bodies["one-page-conclusion"], bodies["final-conclusion"], findings)
        validate_source_index(company, report, blocks, findings)
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    identities = [meta.get("company_name_cn"), meta.get("company_name_en"), meta.get("ticker")]
    if not any(nonblank(item) and item.lower() in lowered for item in identities):
        add(findings, "error", "report-company-identity", "research-report.md", "company name or ticker not found in report")
    source_ids = [item.get("id") for item in list_or_empty(company.get("sources")) if isinstance(item, dict)]
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
        and protocol.get("commit") != "0" * 40
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
    if mode == "full":
        validate_chinese_display_units(mask_non_rendered_markdown(completeness), findings, "research-completeness.md")
        gap_path = root / "schema-gap-report.md"
        if gap_path.is_file() and not gap_path.is_symlink():
            try:
                gap_text = gap_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                add(findings, "error", "text-encoding", "schema-gap-report.md", "text files must be UTF-8")
            else:
                validate_chinese_display_units(mask_non_rendered_markdown(gap_text), findings, "schema-gap-report.md")
    validate_completeness(completeness, findings)
    validate_financials(company, completeness, mode, findings)
    validate_sankey(company, findings)
    validate_research_modules(company, findings)
    validate_valuation(company, findings)
    validate_verdict_and_risks(company, findings)
    validate_report(company, report, mode, findings, calculations)
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
        "validator": "research-doujiao-value-company/2.1",
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
