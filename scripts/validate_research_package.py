#!/usr/bin/env python3
"""Validate a Doujiao research package with fail-closed, stdlib-only gates."""

from __future__ import annotations

import argparse
import ast
from difflib import SequenceMatcher
import hashlib
import html
import ipaddress
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from validate_research_process import validate_research_process


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
VALIDATOR_VERSION = "research-doujiao-value-company/4.7"
INTEGRITY_PROFILE = "execution-bound-v1"
EXPECTED_PROTOCOL_AUTHORITY = "research-doujiao-value-company"
EXPECTED_PROTOCOL_REPOSITORY = "bits-bean/research-doujiao-value-company-skill"
COMPANY_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
LEGACY_LOGO_EXTENSIONS = "png|svg"
VISUAL_ASSET_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".svgz",
    ".tif",
    ".tiff",
    ".webp",
}
SIGNED_LOGO_QUERY_KEYS = {
    "access_token",
    "key",
    "sig",
    "signature",
    "token",
    "x-amz-credential",
    "x-amz-security-token",
    "x-amz-signature",
    "x-goog-algorithm",
    "x-goog-credential",
    "x-goog-date",
    "x-goog-expires",
    "x-goog-signature",
    "googleaccessid",
    "expires",
    "key-pair-id",
    "policy",
    "sharedaccesssignature",
}
PROTOCOL_DOCUMENT_PATHS = (
    "references/specs/automation-workflow.md",
    "references/specs/project-instructions.md",
    "references/specs/research-methodology.md",
)
BUNDLED_SCHEMA_PATH = "references/specs/company.schema.json"
SANKEY_COLOR_AUDIT_VERSION = "1.0.0"
SANKEY_COLOR_PROVIDER = "App Economy Insights"
SANKEY_COLOR_SITE_ORIGIN = "https://www.appeconomyinsights.com/"
SANKEY_DEFAULT_PALETTE_VERSION = "semantic-default-v1"
SANKEY_COLOR_IDENTITIES = ("english_name", "chinese_name", "ticker")
SANKEY_COLOR_QUERY_VARIANTS = ("sankey", "earnings_visuals")
SANKEY_COLOR_OUTCOMES = {"matched", "no_match", "blocked"}
SANKEY_COLOR_BLOCKERS = {
    "paywall",
    "login_required",
    "network_error",
    "candidate_unverifiable",
    "source_image_unavailable",
    "other_access_failure",
}
SANKEY_COLOR_PATTERN = re.compile(r"#[0-9A-F]{6}")
SANKEY_COLOR_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)
SANKEY_WINDOWS_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s('\"`])(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+)"
)
SANKEY_POSIX_ABSOLUTE_PATH = re.compile(r"(?:^|[\s('\"`])/(?!/)[^\s]+")
SANKEY_RELATIVE_PRIVATE_PATH = re.compile(
    r"(?:^|[\s('\"`])(?:\.{1,2}[\\/]|private[-_]?evidence[\\/])[^\s]+",
    re.IGNORECASE,
)
SANKEY_FILE_URI = re.compile(r"\bfile://", re.IGNORECASE)
TRUSTED_LOCK_KEYS = {"lock_version", "research_protocol", "execution_integrity", "company_schema"}
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
EXECUTION_INTEGRITY_KEYS = {
    "profile",
    "normative_digest_sha256",
    "toolchain_digest_sha256",
    "bundle_digest_sha256",
    "artifacts",
    "source_binding",
}
EXECUTION_ARTIFACT_KEYS = {"path", "role", "sha256", "size_bytes"}
SOURCE_BINDING_KEYS = {"repository", "ref", "payload_commit", "verification_status"}
CLASSIFICATIONS = {"fact", "management_claim", "third_party", "inference", "estimate"}
VALUATION_CASH_FLOW_BASES = {"fcff", "fcfe", "owner_earnings", "distributable_common_cash"}
CONFIDENCE = {"high", "medium", "low"}
VERDICT_CONFIDENCE = CONFIDENCE | {"高", "中", "低"}
BUSINESS_QUALITY = {"优秀", "良好", "一般", "较差", "无法判断"}
VALUATION_STATUS = {"明显低估", "可能低估", "接近合理", "偏高", "无法判断"}
RESEARCH_STATUS = {"深入研究", "观察名单", "等待价格", "放弃", "Too Hard"}
PRIMARY_SOURCE_TYPES = {"annual_report", "quarterly_report", "earnings_release", "regulatory_filing"}
CLASSIFICATION_OFFICIAL_SOURCE_TYPES = PRIMARY_SOURCE_TYPES | {"investor_presentation", "official_website"}
TOO_HARD_WARNING_CODES = {
    "insufficient-calculations",
    "insufficient-fy-history",
    "insubstantial-financial-history",
    "missing-latest-period",
    "missing-ttm",
    "empty-sankey",
    "sankey-one-sided",
    "moat-coverage",
    "unscored-moat",
    "management-score-coverage",
    "unscored-management",
    "management-commitments",
    "management-stop-doing",
    "capital-allocation-substance",
    "industry-metric-coverage",
    "returns-chart-coverage",
}
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "$comment",
    "title", "description", "default", "examples", "deprecated", "readOnly", "writeOnly",
    "type", "additionalProperties", "required", "properties", "items", "enum", "const",
    "allOf", "if", "then", "pattern", "minLength", "minimum", "exclusiveMinimum", "maximum", "exclusiveMaximum",
    "uniqueItems", "minItems", "maxItems", "format",
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
    ("culture-management", ("文化、不为清单、管理层和资本配置", "企业文化、管理层与资本配置", "文化与管理", "stop doing", "不为清单")),
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
REPORT_INTERNAL_IMPLEMENTATION_TOKENS = (
    "company.json",
    "calculation-ledger.json",
    "evidence-ledger.json",
    "research-manifest.json",
    "validation-report.json",
    "schema-gap-report.md",
    "research-completeness.md",
    "schema字段",
    "schema 字段",
    "validate_research_package.py",
    "验证器兼容",
    "校验器兼容",
)
REPORT_LEGACY_TERMS = ("不" + "做清单",)
REPORT_LOGO_ASSET_TOKENS = (
    "logo",
    "company_logo",
    "公司标志",
    "公司标识",
    "品牌标识文件",
)
REPORT_SANKEY_COLOR_WORKFLOW_TOKENS = (
    "app economy insights",
    "color_audit",
    "semantic-default-v1",
    "sankey palette",
    "桑基配色",
    "逐节点取样",
    "sample_x",
    "sample_y",
)
REPORT_GLOSSARY_TERMS = (
    "Thesis breakers",
    "Reverse DCF",
    "Owner Earnings",
    "Pre-Mortem",
    "P/TBV",
    "ROTCE",
    "CET1",
    "FCFF",
    "FCFE",
    "ROIC",
    "AFFO",
    "REIT",
    "NOPAT",
    "WACC",
    "SBC",
    "FCF",
    "EPS",
    "ROE",
    "RWA",
    "NAV",
    "PE",
    "EV",
    "DCF",
)
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

ACCOUNTING_RETURN_COMPATIBILITY = {
    "standard_corporate": {"standard_roic", "payments_credit", "payments_network", "software_platform"},
    "regulated_bank": {"regulated_bank", "payments_credit"},
    "insurer": {"insurer"},
    "reit": {"reit"},
    "resource_cycle": {"resource_cycle"},
}
EXPECTED_SECTOR_BY_ACCOUNTING = {
    "regulated_bank": "financials",
    "insurer": "financials",
    "reit": "real_estate",
}
COMMON_INDUSTRY_METRIC_TYPES = {
    "rotce": "ratio",
    "cet1_ratio": "ratio",
    "cet1_target_low": "ratio",
    "cet1_target_high": "ratio",
    "cet1_regulatory_minimum": "ratio",
    "capital_adequacy_ratio": "ratio",
    "capital_adequacy_target_low": "ratio",
    "capital_adequacy_target_high": "ratio",
    "capital_adequacy_regulatory_minimum": "ratio",
    "risk_weighted_assets": "amount",
    "net_interest_margin": "ratio",
    "deposit_cost": "ratio",
    "net_charge_off_rate": "ratio",
    "tangible_book_value_per_share": "per_share",
    "common_equity_per_share": "per_share",
    "book_value_per_share": "per_share",
    "buyback_impact_per_share": "per_share",
    "combined_ratio": "ratio",
    "solvency_ratio": "ratio",
    "float_amount": "amount",
    "float_cost": "ratio",
    "ffo": "amount",
    "affo": "amount",
    "ffo_per_share": "per_share",
    "affo_per_share": "per_share",
    "same_store_noi_growth": "ratio",
    "occupancy_rate": "ratio",
    "distribution_coverage": "ratio",
    "reserve_life": "index",
    "unit_cash_cost": "amount",
    "maintenance_capex": "amount",
    "midcycle_roic": "ratio",
    "net_revenue_retention": "ratio",
    "gross_retention": "ratio",
    "sbc_to_revenue": "ratio",
    "adjusted_roic_after_r_and_d": "ratio",
}

NONLOCALIZED_CHINESE_UNIT_PATTERNS = (
    re.compile(
        r"(?:[$€£¥]\s*)?[-+]?\d[\d,]*(?:\.\d+)?\s*"
        r"(?:thousand|million|billion|trillion)\b",
        re.I,
    ),
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
    re.compile(r"十亿\s*(?:美元|港元|人民币|欧元|英镑|日元|元|股)"),
    re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?\s*bp\b", re.I),
    re.compile(
        r"(?:单位|口径)\s*[:：]?\s*(?:USD|CNY|RMB|HKD|EUR|GBP|JPY|US\$)?\s*"
        r"(?:thousand|million|billion|trillion)\b",
        re.I,
    ),
    re.compile(r"(?:单位|口径)\s*[:：]?\s*百万(?:美元|港元|人民币|欧元|英镑|日元|元|股)?"),
)

NONLOCALIZED_PER_SHARE_PATTERN = re.compile(
    r"(?:EPS|每股收益|股价|现价|每股价值|回购均价|回购价|均价|基准(?:内在)?价值)"
    r"[^|\n]{0,32}?[-+]?\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:至|到|—|–|-)\s*[-+]?\d[\d,]*(?:\.\d+)?)?"
    r"\s*(?:人民币元|美元|港元|欧元|英镑|日元|元)(?!\s*/\s*股)",
    re.I,
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
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        delete=False,
    )
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


def canonical_inventory_digest(artifacts: list[dict[str, Any]]) -> str:
    """Hash a path-sorted execution artifact inventory without ambient metadata."""
    ordered = sorted(artifacts, key=lambda item: item["path"])
    encoded = json.dumps(
        ordered,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def expected_execution_artifacts() -> dict[str, str]:
    """Return the complete release inventory covered by execution integrity."""
    paths: dict[str, str] = {
        "SKILL.md": "normative",
        "agents/openai.yaml": "normative",
    }
    for path in sorted((SKILL_ROOT / "references").rglob("*.md")):
        paths[path.relative_to(SKILL_ROOT).as_posix()] = "normative"
    for path in sorted((SKILL_ROOT / "scripts").glob("*.py")):
        paths[path.relative_to(SKILL_ROOT).as_posix()] = "toolchain"
    return paths


def protocol_fingerprint(trusted: dict[str, Any]) -> dict[str, Any]:
    """Bind package execution to protocol, Schema, and exact validator code."""
    protocol = trusted.get("research_protocol", {})
    execution = trusted.get("execution_integrity", {})
    schema = trusted.get("company_schema", {})
    return {
        "research_protocol_digest_sha256": protocol.get("digest_sha256"),
        "execution_bundle_digest_sha256": execution.get("bundle_digest_sha256"),
        "schema_version": schema.get("schema_version"),
        "schema_sha256": schema.get("sha256"),
        "validator_sha256": file_sha256(Path(__file__).resolve()),
    }


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


def evaluate_custom_formula(
    formula: Any,
    inputs: Any,
    *,
    exact_decimal: bool = False,
) -> float | Decimal:
    """Evaluate a small arithmetic expression without calls, attributes or code execution."""
    if not isinstance(formula, str) or not formula.strip():
        raise FormulaEvaluationError("formula must be a nonblank string")
    if not isinstance(inputs, dict) or not inputs:
        raise FormulaEvaluationError("inputs must be a nonempty object")
    environment: dict[str, float | Decimal] = {}
    for name, value in inputs.items():
        if not isinstance(name, str) or not name.isidentifier() or name == "result":
            raise FormulaEvaluationError(f"input name {name!r} is not a safe expression variable")
        if not numeric(value):
            raise FormulaEvaluationError(f"input {name!r} must be a finite number")
        environment[name] = Decimal(str(value)) if exact_decimal else float(value)
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

    def evaluate(node: ast.AST, depth: int = 0) -> float | Decimal:
        nonlocal operations
        if depth > 24:
            raise FormulaEvaluationError("formula nesting is too deep")
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth + 1)
        if isinstance(node, ast.Constant):
            if not numeric(node.value):
                raise FormulaEvaluationError("only finite numeric constants are allowed")
            return Decimal(str(node.value)) if exact_decimal else float(node.value)
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
        result_is_finite = result.is_finite() if isinstance(result, Decimal) else numeric(result)
        if not result_is_finite:
            raise FormulaEvaluationError("formula produced a non-finite result")
        return result if exact_decimal else float(result)

    result = evaluate(tree)
    if operations == 0:
        raise FormulaEvaluationError("formula must perform at least one arithmetic operation")
    if used_names != set(environment):
        unused = sorted(set(environment).difference(used_names))
        raise FormulaEvaluationError(f"all and only declared inputs must be used; unused inputs: {unused!r}")
    return result if exact_decimal else float(result)


def nonblank_list(value: Any, minimum: int = 1) -> bool:
    return isinstance(value, list) and len(value) >= minimum and all(nonblank(item) for item in value)


def close_enough(actual: float, expected: float, tolerance: float | None = None) -> bool:
    maximum = max(0.01, abs(expected) * 0.001)
    allowed = float(tolerance) if numeric(tolerance) and 0 <= float(tolerance) <= maximum else maximum
    return abs(actual - expected) <= allowed


SANKEY_CENT = Decimal("0.01")


def sankey_decimal(value: Any) -> Decimal | None:
    """Convert a finite Sankey amount without introducing binary-float rounding."""
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if not numeric(value):
        return None
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return converted if converted.is_finite() else None


def sankey_amounts_equal(actual: Any, expected: Any) -> bool:
    """Compare audited statement amounts at exact-cent precision."""
    actual_decimal = sankey_decimal(actual)
    expected_decimal = sankey_decimal(expected)
    return (
        actual_decimal is not None
        and expected_decimal is not None
        and abs(actual_decimal - expected_decimal) <= SANKEY_CENT
    )


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
    for container in ("if", "then"):
        child = schema.get(container)
        if isinstance(child, dict):
            findings.extend(validate_schema_keywords(child, f"{path}.{container}"))
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for index, child in enumerate(all_of):
            if isinstance(child, dict):
                findings.extend(validate_schema_keywords(child, f"{path}.allOf[{index}]"))
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
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for child in all_of:
            if isinstance(child, dict):
                findings.extend(validate_schema(instance, child, root, path))
    conditional = schema.get("if")
    consequent = schema.get("then")
    if isinstance(conditional, dict) and isinstance(consequent, dict):
        if not validate_schema(instance, conditional, root, path):
            findings.extend(validate_schema(instance, consequent, root, path))
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
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            add(findings, "error", "schema-exclusive-minimum", path, f"must be above {schema['exclusiveMinimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            add(findings, "error", "schema-maximum", path, f"above {schema['maximum']}")
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            add(findings, "error", "schema-exclusive-maximum", path, f"must be below {schema['exclusiveMaximum']}")
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
        definition = schema["$defs"]["meta"]["properties"]["schema_version"]
    except (KeyError, TypeError):
        return None
    if not isinstance(definition, dict):
        return None
    has_const = "const" in definition
    has_enum = "enum" in definition
    const = definition.get("const")
    default = definition.get("default")
    allowed = definition.get("enum")
    if has_const:
        if not isinstance(const, str) or not const or has_enum:
            return None
        if "default" in definition and default != const:
            return None
        return const
    if (
        has_enum
        and isinstance(default, str)
        and default
        and isinstance(allowed, list)
        and bool(allowed)
        and all(isinstance(item, str) and item for item in allowed)
        and len(allowed) == len(set(allowed))
        and default in allowed
    ):
        return default
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


def validate_dcf_calculation_chain(
    calculations: dict[str, Any],
    company: dict[str, Any],
    start_record: dict[str, Any],
    findings: list[Finding],
) -> None:
    """Require three independently reproducible annual DCF paths and value bridges."""
    years = start_record.get("forecast_years")
    if not isinstance(years, int) or isinstance(years, bool) or years <= 0:
        return
    valuation = company.get("valuation") if isinstance(company.get("valuation"), dict) else {}
    scenarios = {
        scenario_kind(item.get("name")): item
        for item in list_or_empty(valuation.get("dcf_scenarios"))
        if isinstance(item, dict) and scenario_kind(item.get("name")) is not None
    }
    items = [item for item in calculations.get("calculations", []) if isinstance(item, dict)]
    annual: dict[tuple[str, int], dict[str, Any]] = {}
    terminal: dict[str, dict[str, Any]] = {}
    equity: dict[str, dict[str, Any]] = {}
    annual_invalid = False
    terminal_invalid = False
    equity_invalid = False

    for item in items:
        role = item.get("valuation_role")
        if role not in {"annual_discounted_cash_flow", "terminal_present_value", "equity_value_bridge"}:
            continue
        kind = scenario_kind(item.get("valuation_scenario"))
        if kind is None:
            if role == "annual_discounted_cash_flow":
                annual_invalid = True
            elif role == "terminal_present_value":
                terminal_invalid = True
            else:
                equity_invalid = True
            continue
        if role == "annual_discounted_cash_flow":
            year = item.get("forecast_year")
            inputs = item.get("inputs") if isinstance(item.get("inputs"), dict) else {}
            key = (kind, year) if isinstance(year, int) and not isinstance(year, bool) else None
            if (
                key is None
                or key in annual
                or not numeric(inputs.get("cash_flow"))
                or not numeric(inputs.get("discount_factor"))
                or not numeric(item.get("result"))
            ):
                annual_invalid = True
                continue
            annual[key] = item
        elif role == "terminal_present_value":
            if kind in terminal:
                terminal_invalid = True
            terminal[kind] = item
        else:
            if kind in equity:
                equity_invalid = True
            equity[kind] = item

    expected_years = set(range(1, years + 1))
    for kind in ("bear", "base", "bull"):
        scenario = scenarios.get(kind)
        actual_years = {year for scenario_kind_value, year in annual if scenario_kind_value == kind}
        if actual_years != expected_years or not isinstance(scenario, dict):
            annual_invalid = True
            continue
        discount_rate = scenario.get("discount_rate")
        if not numeric(discount_rate):
            annual_invalid = True
            continue
        for year in expected_years:
            record = annual[(kind, year)]
            inputs = record["inputs"]
            expected_factor = (1 + float(discount_rate)) ** (-year)
            if not close_enough(float(inputs["discount_factor"]), expected_factor, max(1e-6, expected_factor * 0.002)):
                annual_invalid = True

        terminal_record = terminal.get(kind)
        if not isinstance(terminal_record, dict):
            terminal_invalid = True
        else:
            inputs = terminal_record.get("inputs") if isinstance(terminal_record.get("inputs"), dict) else {}
            final_annual = annual[(kind, years)]
            final_cash_flow = final_annual["inputs"]["cash_flow"]
            required = ("last_year_cash_flow", "terminal_growth_rate", "discount_rate", "discount_factor")
            if (
                any(not numeric(inputs.get(key)) for key in required)
                or not numeric(terminal_record.get("result"))
                or not report_number_matches(float(inputs.get("last_year_cash_flow", 0)), final_cash_flow)
                or not report_number_matches(float(inputs.get("terminal_growth_rate", 0)), scenario.get("terminal_growth"))
                or not report_number_matches(float(inputs.get("discount_rate", 0)), scenario.get("discount_rate"))
                or not close_enough(
                    float(inputs.get("discount_factor", 0)),
                    float(final_annual["inputs"]["discount_factor"]),
                    max(1e-6, abs(float(final_annual["inputs"]["discount_factor"])) * 0.002),
                )
                or float(inputs.get("terminal_growth_rate", 0)) >= float(inputs.get("discount_rate", 0))
            ):
                terminal_invalid = True

        equity_record = equity.get(kind)
        if not isinstance(equity_record, dict) or not isinstance(terminal_record, dict):
            equity_invalid = True
            continue
        inputs = equity_record.get("inputs") if isinstance(equity_record.get("inputs"), dict) else {}
        explicit_pv = sum(float(annual[(kind, year)]["result"]) for year in expected_years)
        terminal_pv = terminal_record.get("result")
        shares = equity_record.get("diluted_shares")
        per_share = equity_record.get("per_share")
        if (
            not numeric(inputs.get("explicit_period_present_value"))
            or not numeric(inputs.get("terminal_present_value"))
            or not numeric(terminal_pv)
            or not numeric(equity_record.get("result"))
            or not numeric(shares)
            or float(shares) <= 0
            or not numeric(per_share)
            or not report_number_matches(float(inputs["explicit_period_present_value"]), explicit_pv)
            or not report_number_matches(float(inputs["terminal_present_value"]), terminal_pv)
            or not report_number_matches(float(per_share), float(equity_record["result"]) / float(shares))
            or not report_number_matches(float(shares), start_record.get("diluted_shares"))
            or not report_number_matches(float(per_share), scenario.get("fair_value_per_share"))
        ):
            equity_invalid = True

    if annual_invalid or len(annual) != years * 3:
        add(
            findings,
            "error",
            "valuation-annual-cash-flow-chain",
            "calculation-ledger.json.calculations",
            "bear/base/bull each need one reconciled annual_discounted_cash_flow record for every forecast year",
        )
    if terminal_invalid or set(terminal) != {"bear", "base", "bull"}:
        add(
            findings,
            "error",
            "valuation-terminal-value-chain",
            "calculation-ledger.json.calculations",
            "each DCF scenario needs one terminal_present_value record tied to its final-year cash flow, discount rate and terminal growth",
        )
    if equity_invalid or set(equity) != {"bear", "base", "bull"}:
        add(
            findings,
            "error",
            "valuation-equity-value-chain",
            "calculation-ledger.json.calculations",
            "each DCF scenario needs one equity_value_bridge reconciling explicit PV, terminal PV, diluted shares and fair value per share",
        )


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
            is_sankey_calculation = any(
                marker in item
                for marker in ("sankey_node_id", "sankey_source", "sankey_target")
            )
            if not substantive_text(item.get("review_method"), 16) or looks_like_placeholder(item.get("review_method")):
                add(findings, "error", "custom-calculation-review", path, "custom calculation requires a substantive independent review_method")
            if isinstance(inputs, dict) and any(not substantive_text(str(key), 2) for key in inputs):
                add(findings, "error", "custom-calculation-input-name", path, "custom input names must be descriptive")
            try:
                expected = evaluate_custom_formula(
                    formula,
                    inputs,
                    exact_decimal=is_sankey_calculation,
                )
            except FormulaEvaluationError as exc:
                add(findings, "error", "custom-calculation-formula", path, str(exc))
                continue
            if not numeric(result):
                continue
            if is_sankey_calculation:
                tolerance = item.get("tolerance")
                tolerance_decimal = sankey_decimal(tolerance) if tolerance is not None else SANKEY_CENT
                if (
                    tolerance is not None
                    and (
                        tolerance_decimal is None
                        or tolerance_decimal < 0
                        or tolerance_decimal > SANKEY_CENT
                    )
                ):
                    add(findings, "error", "calculation-tolerance", path, "Sankey calculation tolerance cannot exceed 0.01")
                    tolerance_decimal = SANKEY_CENT
                actual_decimal = sankey_decimal(result)
                expected_decimal = sankey_decimal(expected)
                allowed = tolerance_decimal if tolerance_decimal is not None else SANKEY_CENT
                if (
                    actual_decimal is None
                    or expected_decimal is None
                    or abs(actual_decimal - expected_decimal) > allowed
                ):
                    add(findings, "error", "custom-calculation-mismatch", path, f"result {result} does not reconcile to {expected} within exact-cent tolerance")
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
            validate_dcf_calculation_chain(calculations, company, record, findings)


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


def stable_public_http_url(value: Any) -> bool:
    """Return whether value is a credential-free public HTTP(S) URL on a real host."""
    if not nonblank(value) or value != value.strip() or "\\" in value:
        return False
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        return False
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        # Accessing port is intentional: urllib rejects malformed or out-of-range ports lazily.
        parsed.port
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    normalized_host = hostname.rstrip(".").lower()
    if not normalized_host or normalized_host == "localhost" or normalized_host.endswith(
        (".localhost", ".local", ".internal")
    ):
        return False
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        try:
            ascii_host = normalized_host.encode("idna").decode("ascii")
        except UnicodeError:
            return False
        labels = ascii_host.split(".")
        dns_label = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.I)
        if (
            len(ascii_host) > 253
            or len(labels) < 2
            or any(dns_label.fullmatch(label) is None for label in labels)
            or labels[-1].isdigit()
            or labels[-1] in {"example", "invalid", "localhost", "onion", "test"}
            or all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", label, re.I) is not None for label in labels)
        ):
            return False
    else:
        if not address.is_global:
            return False
    try:
        query_keys = {key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)}
    except ValueError:
        return False
    return not bool(query_keys & SIGNED_LOGO_QUERY_KEYS)


def validate_company_logo(
    company: dict[str, Any],
    completeness: str,
    company_slug: str,
    findings: list[Finding],
) -> None:
    """Require one exact Logo state and a slug-bound, source-verifiable path."""
    path_label = "company.json.brand_identity.company_logo"
    brand = company.get("brand_identity")
    logo = brand.get("company_logo") if isinstance(brand, dict) else None
    if not isinstance(logo, dict):
        add(findings, "error", "company-logo-shape", path_label, "company_logo must be an object")
        return

    asset_path = logo.get("asset_path")
    source_url = logo.get("source_url")
    alt = logo.get("alt")
    is_official = logo.get("is_official")
    absent = asset_path is None and source_url is None and alt is None and is_official is False
    if absent:
        visible_completeness = visible_markdown_disclosure_text(completeness)
        logo_lines = " ".join(
            line.strip().lower()
            for line in visible_completeness.splitlines()
            if "logo" in line.lower()
        )
        missing_dimensions: list[str] = []
        if not logo_lines or not any(
            token in logo_lines
            for token in (
                "缺失",
                "未找到",
                "未发现",
                "未提供",
                "尚未取得",
                "尚未找到",
                "尚未提供",
                "无法取得",
                "无法获取",
                "不可用",
                "missing",
                "unavailable",
                "not available",
            )
        ):
            missing_dimensions.append("missing status")
        completed_search = any(
            token in logo_lines
            for token in (
                "已尝试",
                "已检索",
                "已查找",
                "已核验",
                "已检查",
                "尝试过",
                "检索过",
                "查找过",
                "核验过",
                "检查过",
                "attempted",
                "searched",
                "checked",
                "verified",
            )
        )
        future_or_negated_search = any(
            token in logo_lines
            for token in (
                "尚未检查",
                "尚未检索",
                "未检查",
                "未检索",
                "计划检查",
                "计划检索",
                "下一步检查",
                "下一步检索",
                "待检查",
                "待检索",
                "not checked",
                "not searched",
                "not yet checked",
                "will check",
                "will search",
                "plan to check",
                "plan to search",
            )
        )
        if not (
            (
                any(token in logo_lines for token in ("官网", "投资者关系", "品牌中心", "媒体资料", "official"))
                or re.search(r"\bir\b", logo_lines) is not None
            )
            and completed_search
            and not future_or_negated_search
        ):
            missing_dimensions.append("attempted official sources")
        if not ("网站" in logo_lines and any(token in logo_lines for token in ("影响", "展示", "回退", "ticker", "代码", "fallback"))):
            missing_dimensions.append("website impact or ticker fallback")
        if not any(token in logo_lines for token in ("待补", "后续", "下一步", "待取得", "pending", "recheck", "重新检查")):
            missing_dimensions.append("pending evidence or recheck condition")
        if missing_dimensions:
            add(
                findings,
                "error",
                "unacknowledged-logo-warning",
                "research-completeness.md",
                "missing Logo-specific explanation of " + ", ".join(missing_dimensions),
            )
        add(
            findings,
            "warning",
            "unofficial-logo",
            path_label,
            "official company Logo unavailable; use the documented website fallback and do not synthesize one",
        )
        return

    if not isinstance(is_official, bool) or not all(nonblank(value) for value in (asset_path, source_url, alt)):
        code = "official-logo-metadata" if is_official is True else "company-logo-metadata"
        add(
            findings,
            "error",
            code,
            path_label,
            "company Logo must be either three nonempty strings with a boolean is_official classification or the exact null/null/null/false sentinel",
        )
        return

    assert isinstance(asset_path, str) and isinstance(source_url, str) and isinstance(alt, str)
    visible_logo_lines = [
        line.strip().lower()
        for line in visible_markdown_disclosure_text(completeness).splitlines()
        if "logo" in line.lower()
    ]
    visible_logo_text = " ".join(visible_logo_lines)
    if is_official is False:
        third_party_dimensions = {
            "third-party hosting disclosure": any(
                token in visible_logo_text
                for token in ("第三方托管", "第三方来源", "third-party hosted", "third party hosted")
            ),
            "completed official-source exhaustion": any(
                token in visible_logo_text
                for token in (
                    "官方来源已穷尽",
                    "已穷尽官方来源",
                    "官方候选已穷尽",
                    "official sources exhausted",
                    "no verified official logo remained",
                )
            ),
            "explicit user authorization": any(
                token in visible_logo_text
                for token in ("用户已授权", "用户授权", "user authorized", "user-approved")
            ),
            "identity verification": any(
                token in visible_logo_text
                for token in ("身份交叉核验", "身份核验", "图形一致", "品牌一致", "identity verified", "authenticity verified")
            ),
            "website display impact": "网站" in visible_logo_text
            and any(token in visible_logo_text for token in ("展示", "回退", "ticker", "fallback")),
        }
        missing_third_party = [
            label for label, satisfied in third_party_dimensions.items() if not satisfied
        ]
        if missing_third_party:
            add(
                findings,
                "error",
                "third-party-logo-evidence",
                "research-completeness.md",
                "verified third-party Logo metadata requires visible documentation of "
                + ", ".join(missing_third_party),
            )
    elif any(
        token in visible_logo_text
        for token in ("采用第三方", "第三方托管", "third-party hosted", "third party hosted")
    ):
        add(
            findings,
            "error",
            "company-logo-officiality-contradiction",
            "research-completeness.md",
            "a visibly disclosed third-party-hosted Logo cannot be labeled is_official true",
        )
    missing_markers = (
        "缺失",
        "未找到",
        "未发现",
        "未提供",
        "尚未取得",
        "尚未找到",
        "尚未提供",
        "仍缺",
        "待补",
        "继续回退",
        "无法取得",
        "无法获取",
        "不可用",
        "missing",
        "unavailable",
        "not available",
        "pending",
    )
    resolution_markers = (
        "不再缺失",
        "现已取得",
        "现已找到",
        "现已提供",
        "已经取得",
        "已经找到",
        "已经提供",
        "已恢复",
        "resolved",
        "now available",
        "obtained",
        "restored",
    )
    if any(
        any(marker in line for marker in missing_markers)
        and not any(marker in line for marker in resolution_markers)
        for line in visible_logo_lines
    ):
        add(
            findings,
            "error",
            "company-logo-completeness-contradiction",
            "research-completeness.md",
            "declared Logo metadata conflicts with an unresolved visible Logo-missing disclosure",
        )
    canonical = {
        f"companies/{company_slug}/assets/logo.svg",
        f"companies/{company_slug}/assets/logo.png",
    }
    legacy_pattern = rf"companies/{re.escape(company_slug)}/logo-primary\.(?:{LEGACY_LOGO_EXTENSIONS})"
    if asset_path != asset_path.strip() or "\\" in asset_path or (
        asset_path not in canonical and re.fullmatch(legacy_pattern, asset_path) is None
    ):
        add(
            findings,
            "error",
            "company-logo-path",
            f"{path_label}.asset_path",
            "must exactly match the requested company slug's canonical assets/logo.svg or assets/logo.png, or a supported logo-primary.* legacy path",
        )

    if not stable_public_http_url(source_url):
        add(
            findings,
            "error",
            "official-logo-source" if is_official else "third-party-logo-source",
            f"{path_label}.source_url",
            "company Logo requires a stable public http/https source URL without credentials or signed query parameters",
        )


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


def validate_incremental_roic_unavailability(
    company: dict[str, Any], calculations: Any, findings: list[Finding]
) -> set[str]:
    """Count evidenced nonpositive capital changes, never undocumented missing data."""
    if not isinstance(calculations, dict) or "incremental_roic_windows" not in calculations:
        return set()
    windows = calculations.get("incremental_roic_windows")
    if not isinstance(windows, list):
        add(findings, "error", "incremental-roic-unavailability", "calculation-ledger.json.incremental_roic_windows", "must be an array of evidenced unavailable rolling windows")
        return set()
    financials = {
        item.get("period"): item for item in list_or_empty(company.get("financials"))
        if isinstance(item, dict) and item.get("period_type") == "FY"
    }
    metrics = {
        (item.get("period"), item.get("code")): item
        for item in list_or_empty(company.get("industry_metrics")) if isinstance(item, dict)
    }
    source_types = {
        source.get("id"): source.get("source_type")
        for source in list_or_empty(company.get("sources")) if isinstance(source, dict)
    }
    records = {
        item.get("id"): item for item in list_or_empty(calculations.get("calculations"))
        if isinstance(item, dict)
    }
    official_types = {"annual_report", "regulatory_filing"}
    valid_windows: dict[str, set[int]] = {}
    observed_amounts: dict[tuple[str, str], Decimal] = {}
    capital_bases: dict[str, str] = {}
    seen: set[tuple[Any, Any]] = set()
    required_keys = {
        "period", "window_years", "start_period", "status", "reason_code",
        "capital_basis", "economic_reason", "delta_nopat_calculation_id",
        "delta_invested_capital_calculation_id", "source_ids",
    }
    for index, window in enumerate(windows):
        path = f"calculation-ledger.json.incremental_roic_windows[{index}]"
        problems: list[str] = []
        if not isinstance(window, dict) or set(window) != required_keys:
            add(findings, "error", "incremental-roic-unavailability", path, f"window keys must be exactly {sorted(required_keys)!r}")
            continue
        period, years = window.get("period"), window.get("window_years")
        if not isinstance(period, str) or not isinstance(window.get("start_period"), str) or not isinstance(years, int) or isinstance(years, bool):
            add(findings, "error", "incremental-roic-unavailability", path, "period/start_period must be FY strings and window_years must be integer 3 or 5")
            continue
        end_match = re.fullmatch(r"FY(\d{4})", str(period))
        start_match = re.fullmatch(r"FY(\d{4})", str(window.get("start_period")))
        if not isinstance(years, int) or isinstance(years, bool) or years not in {3, 5}:
            problems.append("window_years must be 3 or 5")
        if not end_match or not start_match or years not in {3, 5} or int(end_match.group(1)) - int(start_match.group(1)) != years:
            problems.append("start_period must be the actual FY exactly window_years before period")
        if (period, years) in seen:
            problems.append("period + window_years must be unique")
        seen.add((period, years))
        if period not in financials or financials[period].get("incremental_roic") is not None:
            problems.append("the ending financial FY must preserve incremental_roic=null")
        if window.get("status") != "unavailable" or window.get("reason_code") != "non_positive_invested_capital_change":
            problems.append("only evidenced non_positive_invested_capital_change is eligible")
        for field in ("capital_basis", "economic_reason"):
            if not substantive_text(window.get(field), 16) or looks_like_placeholder(window.get(field)):
                problems.append(f"{field} must explain the consistent capital definition and specific economic cause")
        if not re.search(r"回购|分红|派息|分配|剥离|营运资本|现金|债务|权益|repurchase|buyback|dividend|distribution|divest|working.capital|cash|debt|equity", str(window.get("economic_reason", "")), re.I):
            problems.append("economic_reason must identify a capital allocation or balance-sheet mechanism, not merely unavailable data")
        basis = normalized_text(window.get("capital_basis"))
        if period in capital_bases and capital_bases[period] != basis:
            problems.append("three- and five-year windows must use one consistent capital definition")
        capital_bases[period] = basis
        source_ids = window.get("source_ids")
        if not nonblank_list(source_ids) or any(source not in source_types for source in source_ids) or not any(source_types.get(source) in official_types for source in list_or_empty(source_ids)):
            problems.append("window needs resolved annual-report or regulatory-filing evidence")
        window_sources = set(source_ids) if isinstance(source_ids, list) and all(isinstance(source, str) for source in source_ids) else set()
        metric = metrics.get((period, f"incremental_roic_{years}y"))
        if (
            not isinstance(metric, dict) or metric.get("value") is not None
            or metric.get("value_type") != "ratio"
            or not substantive_text(metric.get("label"), 8)
            or not nonblank_list(metric.get("source_ids"))
            or not window_sources.issubset(set(metric["source_ids"]))
        ):
            problems.append("matching 3y/5y industry metric must preserve null, ratio, an explanatory label and all window sources")
        for kind in ("nopat", "invested_capital"):
            record_id = window.get(f"delta_{kind}_calculation_id")
            record = records.get(record_id) if isinstance(record_id, str) else None
            if not isinstance(record, dict):
                problems.append(f"missing delta_{kind} custom calculation")
                continue
            inputs = record.get("inputs")
            start_key, end_key = f"beginning_{kind}", f"ending_{kind}"
            expected_formula = f"{end_key}-{start_key}"
            record_sources = record.get("source_ids")
            if (
                record.get("metric") != "custom" or record.get("period") != period
                or not isinstance(inputs, dict) or set(inputs) != {start_key, end_key}
                or any(not numeric(inputs.get(key)) for key in (start_key, end_key))
                or re.sub(r"\s+", "", str(record.get("formula"))) != expected_formula
                or not nonblank_list(record_sources)
                or not set(record_sources).issubset(window_sources)
                or not any(source_types.get(source) in official_types for source in list_or_empty(record_sources))
            ):
                problems.append(f"delta_{kind} requires exact beginning/ending inputs, ending FY, ending-minus-beginning formula and covered official sources")
                continue
            delta = sankey_decimal(inputs[end_key]) - sankey_decimal(inputs[start_key])
            for input_key, input_period in ((start_key, window["start_period"]), (end_key, period)):
                observation_key = (kind, input_period)
                amount = sankey_decimal(inputs[input_key])
                if observation_key in observed_amounts and not sankey_amounts_equal(amount, observed_amounts[observation_key]):
                    problems.append(f"{kind} for {input_period} contradicts another rolling window's raw amount")
                observed_amounts[observation_key] = amount
            if not sankey_amounts_equal(delta, record.get("result")):
                problems.append(f"delta_{kind} result must reconcile to raw inputs within one cent")
            if kind == "invested_capital" and delta > 0:
                problems.append("a positive capital change cannot qualify for unavailable status")
        if problems:
            add(findings, "error", "incremental-roic-unavailability", path, "; ".join(problems))
        else:
            valid_windows.setdefault(period, set()).add(years)
    return {period for period, years in valid_windows.items() if years == {3, 5}}


def validate_classification_and_industry_metrics(
    company: dict[str, Any],
    completeness: str,
    mode: str,
    findings: list[Finding],
    calculations: Any = None,
) -> None:
    classification = company.get("classification")
    if not isinstance(classification, dict):
        return
    source_types = {
        source.get("id"): source.get("source_type")
        for source in list_or_empty(company.get("sources"))
        if isinstance(source, dict) and nonblank(source.get("id"))
    }
    classification_sources = classification.get("source_ids")
    if (
        not isinstance(classification_sources, list)
        or not any(source_types.get(source_id) in CLASSIFICATION_OFFICIAL_SOURCE_TYPES for source_id in classification_sources)
    ):
        add(
            findings,
            "error",
            "classification-provenance",
            "company.json.classification.source_ids",
            "classification must cite an official company or regulatory source",
        )
    primary = classification.get("primary_industry")
    secondary = classification.get("secondary_industries")
    if isinstance(primary, str) and isinstance(secondary, list) and primary in secondary:
        add(
            findings,
            "error",
            "classification-duplicate-industry",
            "company.json.classification.secondary_industries",
            "primary_industry must not be repeated in secondary_industries",
        )
    accounting = classification.get("accounting_profile")
    returns = classification.get("returns_profile")
    if returns not in ACCOUNTING_RETURN_COMPATIBILITY.get(accounting, set()):
        add(
            findings,
            "error",
            "classification-routing",
            "company.json.classification",
            "accounting_profile and returns_profile are incompatible; sector and industry tags cannot override chart routing",
        )
    expected_sector = EXPECTED_SECTOR_BY_ACCOUNTING.get(accounting)
    if expected_sector is not None and classification.get("sector") != expected_sector:
        add(
            findings,
            "error",
            "classification-sector",
            "company.json.classification.sector",
            f"{accounting} must use sector {expected_sector!r}",
        )

    metrics = company.get("industry_metrics")
    if not isinstance(metrics, list):
        return
    financials = [item for item in list_or_empty(company.get("financials")) if isinstance(item, dict)]
    financial_periods = {item.get("period") for item in financials if nonblank(item.get("period"))}
    reporting = company.get("reporting") if isinstance(company.get("reporting"), dict) else {}
    latest_report = reporting.get("latest_report") if isinstance(reporting.get("latest_report"), dict) else {}
    reporting_periods = {
        item
        for item in (latest_report.get("period"),)
        if nonblank(item)
    }
    allowed_metric_periods = financial_periods | reporting_periods
    fy_periods = {
        item.get("period")
        for item in financials
        if item.get("period_type") == "FY" and nonblank(item.get("period"))
    }
    seen: set[tuple[Any, Any]] = set()
    metric_values: dict[str, set[str]] = {}
    all_metric_values: dict[str, set[str]] = {}
    for index, item in enumerate(metrics):
        if not isinstance(item, dict):
            continue
        path = f"company.json.industry_metrics[{index}]"
        key = (item.get("period"), item.get("code"))
        if key in seen:
            add(findings, "error", "duplicate-industry-metric", path, "period + code must be unique")
        seen.add(key)
        if item.get("period") not in allowed_metric_periods:
            add(findings, "error", "industry-metric-period", path, "period must match a company.financials period or reporting.latest_report.period")
        expected_type = COMMON_INDUSTRY_METRIC_TYPES.get(item.get("code"))
        if expected_type is not None and item.get("value_type") != expected_type:
            add(
                findings,
                "error",
                "industry-metric-value-type",
                f"{path}.value_type",
                f"{item.get('code')} must use value_type {expected_type!r}",
            )
        if numeric(item.get("value")) and isinstance(item.get("code"), str) and isinstance(item.get("period"), str):
            all_metric_values.setdefault(item["code"], set()).add(item["period"])
            if item.get("period") in fy_periods:
                metric_values.setdefault(item["code"], set()).add(item["period"])

    unavailable_incremental_periods = validate_incremental_roic_unavailability(company, calculations, findings)
    if mode != "full" or not fy_periods:
        return
    severity = "warning" if is_unable(company) and documented_material_gap(completeness) else "error"
    required_history = min(8, len(fy_periods)) if not is_unable(company) else min(3, len(fy_periods))
    required_incremental = min(3, len(fy_periods))

    def financial_count(field: str) -> int:
        return sum(
            numeric(item.get(field))
            for item in financials
            if item.get("period_type") == "FY"
        )

    def metric_count(*codes: str) -> int:
        return max((len(metric_values.get(code, set())) for code in codes), default=0)

    def has_current_metric(code: str) -> bool:
        period = latest_report.get("period")
        return isinstance(period, str) and period in all_metric_values.get(code, set())

    def has_current_capital_gauge() -> bool:
        cet1_range = (
            has_current_metric("cet1_ratio")
            and (
                (has_current_metric("cet1_target_low") and has_current_metric("cet1_target_high"))
                or has_current_metric("cet1_regulatory_minimum")
            )
        )
        capital_adequacy_range = (
            has_current_metric("capital_adequacy_ratio")
            and (
                (
                    has_current_metric("capital_adequacy_target_low")
                    and has_current_metric("capital_adequacy_target_high")
                )
                or has_current_metric("capital_adequacy_regulatory_minimum")
            )
        )
        return cet1_range or capital_adequacy_range

    buyback_impact_periods = {
        item.get("period")
        for item in list_or_empty(company.get("buyback_ledger"))
        if (
            isinstance(item, dict)
            and item.get("period") in fy_periods
            and numeric(item.get("shares_outstanding_change"))
        )
    }
    buyback_impact_count = max(
        len(buyback_impact_periods),
        metric_count("buyback_impact_per_share"),
    )

    missing: list[str] = []
    if returns in {"standard_roic", "payments_network", "software_platform"}:
        if financial_count("roe") < required_history:
            missing.append(f"ROE<{required_history}FY")
        if financial_count("roic") < required_history:
            missing.append(f"ROIC<{required_history}FY")
        if financial_count("incremental_roic") + len(unavailable_incremental_periods) < required_incremental:
            missing.append(f"incremental_roic<{required_incremental}FY")
    elif returns in {"regulated_bank", "payments_credit"}:
        if max(financial_count("roe"), metric_count("rotce")) < required_history:
            missing.append(f"ROE/ROTCE<{required_history}FY")
        if not has_current_capital_gauge():
            missing.append("CET1/current-capital-gauge-with-target-or-regulatory-range")
        if (
            metric_count("tangible_book_value_per_share", "common_equity_per_share", "book_value_per_share")
            < required_history
            and buyback_impact_count < 3
        ):
            missing.append(f"per-share-equity<{required_history}FY-or-3Y-buyback-impact")
    elif returns == "insurer":
        if financial_count("roe") < required_history:
            missing.append(f"ROE<{required_history}FY")
        if metric_count("solvency_ratio") < required_history:
            missing.append(f"solvency_ratio<{required_history}FY")
        if metric_count("book_value_per_share", "tangible_book_value_per_share") < required_history:
            missing.append(f"per-share-book-value<{required_history}FY")
    elif returns == "reit":
        if metric_count("affo", "affo_per_share", "ffo", "ffo_per_share") < required_history:
            missing.append(f"FFO/AFFO<{required_history}FY")
        if metric_count("affo_per_share", "ffo_per_share") < required_history:
            missing.append(f"FFO/AFFO-per-share<{required_history}FY")
        if metric_count("occupancy_rate") < required_history:
            missing.append(f"occupancy_rate<{required_history}FY")
    elif returns == "resource_cycle":
        if financial_count("roic") < required_history:
            missing.append(f"ROIC<{required_history}FY")
        if metric_count("midcycle_roic") < required_incremental:
            missing.append(f"midcycle_roic<{required_incremental}FY")

    if missing:
        add(
            findings,
            severity,
            "returns-chart-coverage",
            "company.json.classification.returns_profile",
            f"{returns!r} routing lacks deterministic chart inputs: {', '.join(missing)}",
        )


def validate_durability(company: dict[str, Any], findings: list[Finding]) -> None:
    durability = company.get("durability")
    if not isinstance(durability, dict):
        return
    root_source_ids = {
        item for item in list_or_empty(durability.get("source_ids")) if isinstance(item, str)
    }
    if (
        not isinstance(durability.get("horizon_years"), int)
        or isinstance(durability.get("horizon_years"), bool)
        or durability.get("horizon_years", 0) < 20
        or durability.get("overall_status") not in {"durable", "conditional", "fragile", "too_hard"}
        or not substantive_text(durability.get("conclusion"), 12)
        or looks_like_placeholder(durability.get("conclusion"))
        or not nonblank_list(durability.get("source_ids"))
    ):
        add(
            findings,
            "error",
            "durability-conclusion",
            "company.json.durability",
            "durability requires a sourced 20+ year horizon, standardized overall status and substantive conclusion",
        )
    dimension_values: list[str] = []
    dimension_source_ids: set[str] = set()
    for key in ("demand_durability", "adaptability", "external_shocks"):
        item = durability.get(key)
        path = f"company.json.durability.{key}"
        evidence = item.get("evidence") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or item.get("status") not in {"strong", "adequate", "uncertain", "weak"}
            or not substantive_text(item.get("assessment"), 12)
            or looks_like_placeholder(item.get("assessment"))
            or not isinstance(evidence, list)
            or not evidence
            or any(not substantive_text(value, 8) or looks_like_placeholder(value) for value in evidence)
            or not substantive_text(item.get("breaker"), 10)
            or looks_like_placeholder(item.get("breaker"))
            or not nonblank_list(item.get("source_ids"))
        ):
            add(
                findings,
                "error",
                "durability-dimension",
                path,
                "each durability dimension requires status, assessment, evidence, a falsifiable breaker and source_ids",
            )
            continue
        dimension_values.extend([item["assessment"], item["breaker"]])
        dimension_source_ids.update(
            source_id for source_id in list_or_empty(item.get("source_ids")) if isinstance(source_id, str)
        )
    if not dimension_source_ids.issubset(root_source_ids):
        add(
            findings,
            "error",
            "durability-sources",
            "company.json.durability.source_ids",
            "durability root source_ids must cover every dimension source",
        )
    if len(dimension_values) == 6 and not substantive_distinct_entries(dimension_values, 10):
        add(
            findings,
            "error",
            "durability-distinction",
            "company.json.durability",
            "demand, adaptability and external-shock assessments must be distinct company-specific tests",
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


def validate_sankey_color_audit(
    company: dict[str, Any],
    ledger: dict[str, Any],
    node_by_id: dict[Any, dict[str, Any]],
    node_ids: set[Any],
    findings: list[Finding],
) -> None:
    """Validate the frozen App Economy Insights tri-state color audit."""

    path = "calculation-ledger.json.income_statement_sankey.color_audit"
    audit = ledger.get("color_audit")
    if not isinstance(audit, dict):
        add(
            findings,
            "error",
            "sankey-color-audit",
            path,
            "requires a company-level matched/not_found/blocked App Economy Insights color audit",
        )
        return

    def audit_strings(value: Any, item_path: str):
        if isinstance(value, str):
            yield item_path, value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield from audit_strings(item, f"{item_path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from audit_strings(item, f"{item_path}[{index}]")

    def contains_private_local_path(value: str) -> bool:
        return bool(
            SANKEY_FILE_URI.search(value)
            or SANKEY_WINDOWS_ABSOLUTE_PATH.search(value)
            or SANKEY_POSIX_ABSOLUTE_PATH.search(value)
            or SANKEY_RELATIVE_PRIVATE_PATH.search(value)
        )

    leaked_path = next(
        (
            item_path
            for item_path, value in audit_strings(audit, path)
            if contains_private_local_path(value)
        ),
        None,
    )
    if leaked_path is not None:
        add(
            findings,
            "error",
            "sankey-color-private-path",
            leaked_path,
            "color audit must not contain local or private evidence paths in any field",
        )

    required_keys = {
        "contract_version",
        "provider",
        "site_origin",
        "completed_at",
        "alias_review",
        "mode",
        "queries",
        "source_page_url",
        "opened_at",
        "direct_verification",
        "source_image",
        "node_samples",
        "default_palette_version",
        "blockers",
    }
    if set(audit) != required_keys:
        add(
            findings,
            "error",
            "sankey-color-audit-shape",
            path,
            f"color_audit keys must be exactly {sorted(required_keys)!r}",
        )
    if audit.get("contract_version") != SANKEY_COLOR_AUDIT_VERSION:
        add(findings, "error", "sankey-color-audit-version", path, f"contract_version must be {SANKEY_COLOR_AUDIT_VERSION}")
    if audit.get("provider") != SANKEY_COLOR_PROVIDER or audit.get("site_origin") != SANKEY_COLOR_SITE_ORIGIN:
        add(findings, "error", "sankey-color-audit-provider", path, "provider and site_origin must bind App Economy Insights")

    def parse_timestamp(value: Any, item_path: str) -> datetime | None:
        if not isinstance(value, str) or SANKEY_COLOR_TIMESTAMP.fullmatch(value) is None:
            add(findings, "error", "sankey-color-audit-time", item_path, "requires an RFC 3339 timestamp with an explicit timezone")
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            add(findings, "error", "sankey-color-audit-time", item_path, "contains an invalid timestamp")
            return None

    def app_economy_url(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
            and (host == "appeconomyinsights.com" or host.endswith(".appeconomyinsights.com"))
        )

    completed_at = parse_timestamp(audit.get("completed_at"), f"{path}.completed_at")
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    identities = {
        "english_name": meta.get("company_name_en"),
        "chinese_name": meta.get("company_name_cn"),
        "ticker": meta.get("ticker"),
    }
    source_by_id = {
        item.get("id"): item
        for item in list_or_empty(company.get("sources"))
        if isinstance(item, dict) and nonblank(item.get("id"))
    }
    alias_review = audit.get("alias_review")
    aliases: list[dict[str, Any]] = []
    alias_values: list[str] = []
    alias_review_keys = {"completed", "review_method", "aliases"}
    if not isinstance(alias_review, dict) or set(alias_review) != alias_review_keys:
        add(findings, "error", "sankey-color-alias-review", f"{path}.alias_review", f"alias_review keys must be exactly {sorted(alias_review_keys)!r}")
    else:
        if alias_review.get("completed") is not True or not substantive_text(alias_review.get("review_method"), 16):
            add(findings, "error", "sankey-color-alias-review", f"{path}.alias_review", "must document a completed review of company.json and official-source aliases")
        alias_items = alias_review.get("aliases")
        if not isinstance(alias_items, list):
            add(findings, "error", "sankey-color-alias-review", f"{path}.alias_review.aliases", "aliases must be an array")
        else:
            canonical_folded = {str(value).casefold() for value in identities.values()}
            seen_aliases: set[str] = set()
            alias_keys = {"value", "source_ids", "verification_note"}
            for index, alias in enumerate(alias_items):
                alias_path = f"{path}.alias_review.aliases[{index}]"
                if not isinstance(alias, dict) or set(alias) != alias_keys:
                    add(findings, "error", "sankey-color-alias", alias_path, f"alias keys must be exactly {sorted(alias_keys)!r}")
                    continue
                value = alias.get("value")
                folded = value.casefold() if isinstance(value, str) else ""
                source_ids = alias.get("source_ids")
                if not nonblank(value) or folded in canonical_folded or folded in seen_aliases:
                    add(findings, "error", "sankey-color-alias", alias_path, "alias value must be unique and distinct from canonical identities")
                else:
                    seen_aliases.add(folded)
                    alias_values.append(value)
                if (
                    not isinstance(source_ids, list)
                    or not source_ids
                    or any(not isinstance(source_id, str) for source_id in source_ids)
                    or len(source_ids) != len(set(source_ids))
                    or any(
                        source_id not in source_by_id
                        or source_by_id[source_id].get("source_type") not in CLASSIFICATION_OFFICIAL_SOURCE_TYPES
                        for source_id in source_ids
                    )
                    or not substantive_text(alias.get("verification_note"), 8)
                ):
                    add(findings, "error", "sankey-color-alias-source", alias_path, "alias requires resolved official source_ids and a verification note")
                aliases.append(alias)
            if alias_values != sorted(alias_values, key=str.casefold):
                add(findings, "error", "sankey-color-alias-order", f"{path}.alias_review.aliases", "aliases must be sorted case-insensitively")
    queries = audit.get("queries")
    observed_query_keys: list[tuple[Any, Any, Any]] = []
    query_outcomes: list[Any] = []
    matched_urls: set[str] = set()
    blocked_urls: set[str] = set()
    query_keys = {
        "identity_kind",
        "query_variant",
        "identity_value",
        "query",
        "searched_at",
        "outcome",
        "checked_urls",
        "blocker_code",
        "notes",
    }
    expected_query_count = 6 + 2 * len(alias_values)
    if not isinstance(queries, list) or len(queries) != expected_query_count:
        add(findings, "error", "sankey-color-search", f"{path}.queries", "must contain both variants for every canonical identity and verified alias")
        queries = []
    for index, query in enumerate(queries):
        query_path = f"{path}.queries[{index}]"
        if not isinstance(query, dict) or set(query) != query_keys:
            add(findings, "error", "sankey-color-search-shape", query_path, f"query keys must be exactly {sorted(query_keys)!r}")
            continue
        identity_kind = query.get("identity_kind")
        query_variant = query.get("query_variant")
        identity_value = query.get("identity_value")
        observed_query_keys.append((identity_kind, identity_value, query_variant))
        expected_identity_value = identities.get(identity_kind)
        if identity_kind not in (*SANKEY_COLOR_IDENTITIES, "alias") or query_variant not in SANKEY_COLOR_QUERY_VARIANTS:
            add(findings, "error", "sankey-color-search", query_path, "identity_kind or query_variant is invalid")
        elif identity_kind == "alias" and identity_value not in alias_values:
            add(findings, "error", "sankey-color-search-identity", query_path, "alias identity_value must resolve to alias_review")
        elif identity_kind != "alias" and identity_value != expected_identity_value:
            add(findings, "error", "sankey-color-search-identity", query_path, "identity_value must equal frozen company identity")
        else:
            expected_query = (
                f'site:appeconomyinsights.com "{identity_value}" Sankey'
                if query_variant == "sankey"
                else f'site:appeconomyinsights.com "{identity_value}" "earnings visuals"'
            )
            if query.get("query") != expected_query:
                add(findings, "error", "sankey-color-search-query", query_path, "query must equal the prescribed canonical search")
        searched_at = parse_timestamp(query.get("searched_at"), f"{query_path}.searched_at")
        if completed_at is not None and searched_at is not None and searched_at > completed_at:
            add(findings, "error", "sankey-color-audit-time", query_path, "query timestamp cannot follow completed_at")
        outcome = query.get("outcome")
        query_outcomes.append(outcome)
        if outcome not in SANKEY_COLOR_OUTCOMES:
            add(findings, "error", "sankey-color-search-outcome", query_path, "outcome must be matched, no_match, or blocked")
        urls = query.get("checked_urls")
        if (
            not isinstance(urls, list)
            or any(not isinstance(url, str) for url in urls)
            or len(urls) != len(set(urls))
            or any(not app_economy_url(url) for url in urls)
        ):
            add(findings, "error", "sankey-color-search-url", query_path, "checked_urls must be unique App Economy Insights HTTPS URLs")
            urls = []
        if outcome == "matched":
            if not urls:
                add(findings, "error", "sankey-color-search-outcome", query_path, "matched search requires a checked URL")
            matched_urls.update(urls)
        if outcome == "blocked":
            blocked_urls.update(urls)
            if query.get("blocker_code") not in SANKEY_COLOR_BLOCKERS:
                add(findings, "error", "sankey-color-search-blocker", query_path, "blocked search requires a recognized blocker_code")
        elif query.get("blocker_code") is not None:
            add(findings, "error", "sankey-color-search-blocker", query_path, "blocker_code must be null unless outcome is blocked")
        if not substantive_text(query.get("notes"), 8):
            add(findings, "error", "sankey-color-search-notes", query_path, "search notes must record the observed result")

    expected_query_keys = [
        (identity_kind, identities[identity_kind], query_variant)
        for identity_kind in SANKEY_COLOR_IDENTITIES
        for query_variant in SANKEY_COLOR_QUERY_VARIANTS
    ]
    expected_query_keys.extend(
        ("alias", alias_value, query_variant)
        for alias_value in alias_values
        for query_variant in SANKEY_COLOR_QUERY_VARIANTS
    )
    if observed_query_keys != expected_query_keys:
        add(findings, "error", "sankey-color-search-coverage", f"{path}.queries", "queries must be ordered and cover canonical identities plus every verified alias with both variants exactly once")

    blockers = audit.get("blockers")
    blocker_keys = {"code", "detail", "page_url"}
    if not isinstance(blockers, list):
        add(findings, "error", "sankey-color-blocker", f"{path}.blockers", "blockers must be an array")
        blockers = []
    for index, blocker in enumerate(blockers):
        blocker_path = f"{path}.blockers[{index}]"
        if not isinstance(blocker, dict) or set(blocker) != blocker_keys:
            add(findings, "error", "sankey-color-blocker", blocker_path, f"blocker keys must be exactly {sorted(blocker_keys)!r}")
            continue
        if blocker.get("code") not in SANKEY_COLOR_BLOCKERS or not substantive_text(blocker.get("detail"), 8):
            add(findings, "error", "sankey-color-blocker", blocker_path, "blocker requires a recognized code and substantive detail")
        page_url = blocker.get("page_url")
        if page_url is not None and (not app_economy_url(page_url) or page_url not in blocked_urls):
            add(findings, "error", "sankey-color-blocker", blocker_path, "page_url must bind a checked URL from a blocked query")

    mode = audit.get("mode")
    node_colors = {node_id: node_by_id.get(node_id, {}).get("color") for node_id in node_ids}
    empty_colors = all(color is None for color in node_colors.values())
    canonical_colors = all(isinstance(color, str) and SANKEY_COLOR_PATTERN.fullmatch(color) is not None for color in node_colors.values())
    null_match_fields = all(
        audit.get(key) is None
        for key in ("source_page_url", "opened_at", "direct_verification", "source_image")
    ) and audit.get("node_samples") == []

    if mode == "matched":
        if "matched" not in query_outcomes or blockers:
            add(findings, "error", "sankey-color-mode", path, "matched mode requires at least one directly verified match and no unresolved company-level blocker")
        if not canonical_colors:
            add(findings, "error", "sankey-color-node-coverage", "company.json.income_statement_sankey.nodes", "matched mode requires every node color as canonical #RRGGBB")
        if audit.get("default_palette_version") is not None:
            add(findings, "error", "sankey-color-default", path, "matched mode cannot bind the System default palette")
        source_page_url = audit.get("source_page_url")
        if not app_economy_url(source_page_url) or source_page_url not in matched_urls:
            add(findings, "error", "sankey-color-source", f"{path}.source_page_url", "must bind a checked matched App Economy Insights page")
        parse_timestamp(audit.get("opened_at"), f"{path}.opened_at")
        direct = audit.get("direct_verification")
        expected_direct = {
            "opened_actual_diagram": True,
            "company_identity_matches": True,
            "diagram_kind": "company-income-statement-sankey",
            "complete_diagram_visible": True,
        }
        if direct != expected_direct:
            add(findings, "error", "sankey-color-direct-verification", f"{path}.direct_verification", "must record direct verification of the complete company income-statement Sankey")
        source_image = audit.get("source_image")
        source_image_keys = {
            "original_url",
            "access_method",
            "captured_at",
            "media_type",
            "sha256",
            "width",
            "height",
            "size_bytes",
        }
        if not isinstance(source_image, dict) or set(source_image) != source_image_keys:
            add(findings, "error", "sankey-color-source-image", f"{path}.source_image", f"source_image keys must be exactly {sorted(source_image_keys)!r} and cannot include a private evidence path")
        else:
            parsed_original = urlparse(str(source_image.get("original_url", "")))
            if parsed_original.scheme != "https" or not parsed_original.netloc or parsed_original.username or parsed_original.password:
                add(findings, "error", "sankey-color-source-image", f"{path}.source_image.original_url", "must be a credential-free HTTPS URL")
            if source_image.get("access_method") != "direct-image-url" or source_image.get("media_type") != "image/png":
                add(findings, "error", "sankey-color-source-image", f"{path}.source_image", "must bind a directly retrieved PNG")
            parse_timestamp(source_image.get("captured_at"), f"{path}.source_image.captured_at")
            if re.fullmatch(r"[0-9a-f]{64}", str(source_image.get("sha256", ""))) is None:
                add(findings, "error", "sankey-color-source-image", f"{path}.source_image.sha256", "must be a lowercase SHA-256")
            if any(not isinstance(source_image.get(key), int) or isinstance(source_image.get(key), bool) or source_image.get(key) <= 0 for key in ("width", "height", "size_bytes")):
                add(findings, "error", "sankey-color-source-image", f"{path}.source_image", "width, height, and size_bytes must be positive integers")
        samples = audit.get("node_samples")
        sample_keys = {"node_id", "source_label", "mapping_note", "color", "sample_x", "sample_y"}
        sample_by_id: dict[Any, Any] = {}
        if not isinstance(samples, list):
            add(findings, "error", "sankey-color-samples", f"{path}.node_samples", "node_samples must be an array")
            samples = []
        for index, sample in enumerate(samples):
            sample_path = f"{path}.node_samples[{index}]"
            if not isinstance(sample, dict) or set(sample) != sample_keys:
                add(findings, "error", "sankey-color-sample-shape", sample_path, f"sample keys must be exactly {sorted(sample_keys)!r}")
                continue
            node_id = sample.get("node_id")
            if not isinstance(node_id, str):
                add(findings, "error", "sankey-color-sample", sample_path, "node_id must be a string graph node ID")
                continue
            if node_id in sample_by_id:
                add(findings, "error", "sankey-color-sample-coverage", sample_path, "node_id is duplicated")
            sample_by_id[node_id] = sample
            color = sample.get("color")
            if node_id not in node_ids or not isinstance(color, str) or SANKEY_COLOR_PATTERN.fullmatch(color) is None:
                add(findings, "error", "sankey-color-sample", sample_path, "sample must bind a graph node to canonical #RRGGBB")
            elif node_colors.get(node_id) != color:
                add(findings, "error", "sankey-color-node-mismatch", sample_path, "sample color must exactly equal company.json node color")
            if not substantive_text(sample.get("source_label"), 1) or not substantive_text(sample.get("mapping_note"), 8):
                add(findings, "error", "sankey-color-sample", sample_path, "sample requires source_label and a substantive mapping_note")
            if any(not isinstance(sample.get(key), int) or isinstance(sample.get(key), bool) or sample.get(key) < 1 for key in ("sample_x", "sample_y")):
                add(findings, "error", "sankey-color-sample", sample_path, "sample coordinates must be positive integers")
        if set(sample_by_id) != node_ids:
            add(findings, "error", "sankey-color-sample-coverage", f"{path}.node_samples", f"samples must cover every graph node exactly; mismatch {sorted(set(sample_by_id) ^ node_ids)!r}")
    elif mode == "not_found":
        if query_outcomes != ["no_match"] * expected_query_count or blockers:
            add(findings, "error", "sankey-color-mode", path, "not_found requires every canonical and verified-alias search to be no_match with no blockers")
        if not empty_colors:
            add(findings, "error", "sankey-color-default", "company.json.income_statement_sankey.nodes", "not_found requires every node color to be null or absent")
        if not null_match_fields or audit.get("default_palette_version") != SANKEY_DEFAULT_PALETTE_VERSION:
            add(findings, "error", "sankey-color-default", path, f"not_found must have no match payload and bind {SANKEY_DEFAULT_PALETTE_VERSION}")
    elif mode == "blocked":
        if "blocked" not in query_outcomes or "matched" in query_outcomes or not blockers:
            add(findings, "error", "sankey-color-mode", path, "blocked mode requires at least one blocked search and blocker, with no match")
        if not empty_colors or not null_match_fields or audit.get("default_palette_version") is not None:
            add(findings, "error", "sankey-color-blocked-state", path, "blocked mode cannot expose node colors, match evidence, samples, or a default palette")
        add(findings, "error", "sankey-color-audit-blocked", path, "App Economy Insights search or verification is blocked; formal validation, freeze, and archive must stop")
    else:
        add(findings, "error", "sankey-color-mode", path, "mode must be matched, not_found, or blocked")


def validate_sankey(
    company: dict[str, Any],
    findings: list[Finding],
    calculations: Any | None = None,
    known: set[str] | None = None,
) -> None:
    sankey = company.get("income_statement_sankey")
    if not isinstance(sankey, dict):
        return
    nodes, links = sankey.get("nodes"), sankey.get("links")
    if not isinstance(nodes, list) or not nodes or not isinstance(links, list) or not links:
        add(findings, "warning" if is_unable(company) else "error", "empty-sankey", "company.json.income_statement_sankey", "formal research requires nonempty Sankey nodes and links, or an acknowledged Too Hard gap")
        return

    valid_roles = {
        "revenue_source",
        "revenue_subtotal",
        "revenue_offset",
        "revenue_total",
        "cost_expense",
        "cost_offset",
        "cost_subtotal",
        "pretax_costs_total",
        "profit_addition",
        "profit_deduction",
        "profit_subtotal",
        "pretax_profit",
        "income_tax",
        "net_income",
    }
    schema_version = (
        company.get("meta", {}).get("schema_version")
        if isinstance(company.get("meta"), dict)
        else None
    )
    uses_signed_contract = schema_version in {"2.2.0", "2.3.0", "2.4.0"}
    supports_revenue_offsets = schema_version in {"2.3.0", "2.4.0"}
    supports_profit_deductions = schema_version == "2.4.0"
    node_records = [node for node in nodes if isinstance(node, dict)]
    ids = [node.get("id") for node in node_records]
    node_by_id = {node.get("id"): node for node in node_records}
    if len(node_records) != len(nodes) or any(not nonblank(node_id) for node_id in ids):
        add(findings, "error", "sankey-node-shape", "company.json.income_statement_sankey.nodes", "every Sankey node must be an object with a nonblank id")
    if len(ids) != len(set(ids)):
        add(findings, "error", "duplicate-sankey-node", "company.json.income_statement_sankey.nodes", "node IDs must be unique")
    node_ids = set(ids)

    role_ids: dict[str, list[Any]] = {role: [] for role in valid_roles}
    for index, node in enumerate(node_records):
        role = node.get("category")
        if role not in valid_roles:
            add(
                findings,
                "error",
                "sankey-role",
                f"company.json.income_statement_sankey.nodes[{index}].category",
                f"unsupported category {role!r}; expected one of {sorted(valid_roles)!r}",
            )
        else:
            role_ids[role].append(node.get("id"))
        value = node.get("value")
        statement_value = node.get("statement_value")
        if not numeric(value) or float(value) <= 0:
            add(findings, "error", "sankey-node-value", f"company.json.income_statement_sankey.nodes[{index}].value", "node values must be finite, positive base-unit flow magnitudes")
        if role in {"revenue_subtotal", "revenue_offset"} and not supports_revenue_offsets:
            add(findings, "error", "sankey-role-version", f"company.json.income_statement_sankey.nodes[{index}].category", "revenue_subtotal and revenue_offset require Schema 2.3.0 or later")
        if role == "profit_deduction" and not supports_profit_deductions:
            add(findings, "error", "sankey-role-version", f"company.json.income_statement_sankey.nodes[{index}].category", "profit_deduction requires Schema 2.4.0")
        if uses_signed_contract and not numeric(statement_value):
            add(findings, "error", "sankey-statement-value", f"company.json.income_statement_sankey.nodes[{index}].statement_value", "Schema 2.2.0 and later require every Sankey node to preserve its finite signed statement value")
        elif numeric(statement_value) and numeric(value) and not sankey_amounts_equal(value, abs(sankey_decimal(statement_value))):
            add(findings, "error", "sankey-statement-value", f"company.json.income_statement_sankey.nodes[{index}]", "node value must equal abs(statement_value)")
        if uses_signed_contract and numeric(statement_value):
            signed = sankey_decimal(statement_value)
            if signed == 0:
                add(findings, "error", "sankey-signed-role", f"company.json.income_statement_sankey.nodes[{index}]", "signed-contract Sankey statement_value must be nonzero")
            elif role in {"cost_offset", "revenue_offset", "profit_deduction"} and signed > 0:
                add(findings, "error", "sankey-signed-role", f"company.json.income_statement_sankey.nodes[{index}]", f"{role} must preserve a negative statement_value")
            elif role not in {"cost_offset", "revenue_offset", "profit_deduction"} and signed < 0:
                add(findings, "error", "sankey-signed-role", f"company.json.income_statement_sankey.nodes[{index}]", "only cost_offset, revenue_offset and profit_deduction may carry a negative statement_value in the signed positive-flow contract")

    roles_valid = True
    for role in ("revenue_total", "pretax_profit", "income_tax", "net_income"):
        if len(role_ids[role]) != 1:
            roles_valid = False
            add(findings, "error", "sankey-role", "company.json.income_statement_sankey.nodes", f"requires exactly one {role} node")
    for role in ("revenue_source", "cost_expense"):
        if not role_ids[role]:
            roles_valid = False
            add(findings, "error", "sankey-role", "company.json.income_statement_sankey.nodes", f"requires at least one {role} node")
    if len(role_ids["pretax_costs_total"]) > 1:
        roles_valid = False
        add(findings, "error", "sankey-role", "company.json.income_statement_sankey.nodes", "at most one pretax_costs_total node is allowed")

    role_by_id = {
        node_id: role
        for role, role_node_ids in role_ids.items()
        for node_id in role_node_ids
    }
    incoming: dict[Any, Decimal] = {node_id: Decimal(0) for node_id in node_ids}
    outgoing: dict[Any, Decimal] = {node_id: Decimal(0) for node_id in node_ids}
    parents: dict[Any, set[Any]] = {node_id: set() for node_id in node_ids}
    children: dict[Any, set[Any]] = {node_id: set() for node_id in node_ids}
    actual_edges: set[tuple[Any, Any]] = set()
    edge_values: dict[tuple[Any, Any], Decimal] = {}
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            add(findings, "error", "sankey-link-shape", f"company.json.income_statement_sankey.links[{index}]", "link must be an object")
            continue
        source, target, value = link.get("source"), link.get("target"), link.get("value")
        if source not in node_ids or target not in node_ids:
            add(findings, "error", "sankey-node-reference", f"company.json.income_statement_sankey.links[{index}]", "link references an unknown node")
            continue
        if source == target or (source, target) in actual_edges:
            add(findings, "error", "sankey-link-shape", f"company.json.income_statement_sankey.links[{index}]", "self-links and duplicate links are forbidden")
        if not numeric(value) or float(value) <= 0:
            add(findings, "error", "sankey-link-value", f"company.json.income_statement_sankey.links[{index}].value", "link values must be finite, positive base-unit flow magnitudes")
            continue
        actual_edges.add((source, target))
        amount = sankey_decimal(value)
        if amount is None:
            continue
        outgoing[source] += amount
        incoming[target] += amount
        children[source].add(target)
        parents[target].add(source)
        edge_values[(source, target)] = amount

    indegree = {node_id: len(parents[node_id]) for node_id in node_ids}
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(node_ids):
        add(findings, "error", "sankey-cycle", "company.json.income_statement_sankey.links", "income-statement Sankey must be acyclic")

    if sankey.get("reconciled") is not True:
        add(
            findings,
            "warning" if is_unable(company) else "error",
            "sankey-not-reconciled",
            "company.json.income_statement_sankey.reconciled",
            "a formal income-statement Sankey must be marked reconciled only after every node and intermediate subtotal balances",
        )

    for node_id in node_ids:
        node_value = node_by_id.get(node_id, {}).get("value")
        for direction, flow_value, has_flow in (
            ("incoming", incoming[node_id], bool(parents[node_id])),
            ("outgoing", outgoing[node_id], bool(children[node_id])),
        ):
            if has_flow and numeric(node_value) and not sankey_amounts_equal(node_value, flow_value):
                add(
                    findings,
                    "error",
                    "sankey-node-value-mismatch",
                    "company.json.income_statement_sankey",
                    f"node {node_id!r} value {node_value} does not match {direction} flow {flow_value}",
                )

    continuation_edges: set[tuple[Any, Any]] = set()
    if roles_valid:
        revenue_total = role_ids["revenue_total"][0]
        pretax_profit = role_ids["pretax_profit"][0]
        income_tax = role_ids["income_tax"][0]
        net_income = role_ids["net_income"][0]

        revenue_path_roles = {"revenue_source", "revenue_subtotal", "revenue_total"}
        for node_id in role_ids["revenue_source"]:
            targets = children[node_id]
            if parents[node_id] or len(targets) != 1 or role_by_id.get(next(iter(targets), None)) not in {"revenue_subtotal", "revenue_total"}:
                add(findings, "error", "sankey-revenue-chain", "company.json.income_statement_sankey.links", f"revenue source {node_id!r} must be a root with exactly one flow into a revenue subtotal or total revenue")

        for node_id in role_ids["revenue_subtotal"]:
            source_roles = {role_by_id.get(parent) for parent in parents[node_id]}
            continuation_children = [child for child in children[node_id] if role_by_id.get(child) in {"revenue_subtotal", "revenue_total"}]
            offset_children = [child for child in children[node_id] if role_by_id.get(child) == "revenue_offset"]
            other_children = children[node_id] - set(continuation_children) - set(offset_children)
            if (
                not parents[node_id]
                or not source_roles.issubset({"revenue_source", "revenue_subtotal"})
                or len(continuation_children) != 1
                or other_children
            ):
                add(findings, "error", "sankey-revenue-subtotal", "company.json.income_statement_sankey.links", f"revenue subtotal {node_id!r} must receive only revenue sources/subtotals, continue exactly once toward total revenue, and otherwise flow only to terminal revenue offsets")
            elif actual_edges:
                continuation_edges.add((node_id, continuation_children[0]))

        for node_id in role_ids["revenue_offset"]:
            if children[node_id] or len(parents[node_id]) != 1 or role_by_id.get(next(iter(parents[node_id]), None)) != "revenue_subtotal":
                add(findings, "error", "sankey-revenue-offset", "company.json.income_statement_sankey.links", f"revenue offset {node_id!r} must be a terminal deduction with exactly one revenue-subtotal parent")

        for node_id in role_ids["revenue_source"] + role_ids["revenue_subtotal"]:
            current_revenue = node_id
            seen_revenue_nodes: set[Any] = set()
            while current_revenue != revenue_total:
                if current_revenue in seen_revenue_nodes:
                    break
                seen_revenue_nodes.add(current_revenue)
                next_nodes = [child for child in children[current_revenue] if role_by_id.get(child) in revenue_path_roles]
                if len(next_nodes) != 1:
                    break
                current_revenue = next_nodes[0]
            if current_revenue != revenue_total:
                add(findings, "error", "sankey-revenue-chain", "company.json.income_statement_sankey.links", f"revenue node {node_id!r} must have one continuous path to total revenue")

        expected_revenue_parents = {"revenue_source"} if not role_ids["revenue_subtotal"] else {"revenue_subtotal"}
        if supports_profit_deductions:
            expected_revenue_parents = {"revenue_source", "revenue_subtotal"}
        if not parents[revenue_total] or any(role_by_id.get(parent) not in expected_revenue_parents for parent in parents[revenue_total]):
            add(findings, "error", "sankey-revenue-chain", "company.json.income_statement_sankey.links", "total revenue must receive only the complete revenue sources/subtotals permitted by its schema version; mixed levels require Schema 2.4.0 and unique source-to-total paths")
        if role_ids["revenue_offset"] and not role_ids["revenue_subtotal"]:
            add(findings, "error", "sankey-revenue-offset", "company.json.income_statement_sankey.links", "revenue offsets require a conserving revenue-subtotal bridge")
        if children[pretax_profit] != {income_tax, net_income} or parents[income_tax] != {pretax_profit} or parents[net_income] != {pretax_profit}:
            add(findings, "error", "sankey-profit-chain", "company.json.income_statement_sankey.links", "pretax profit must split only into income tax and net income")
        if children[income_tax] or children[net_income]:
            add(findings, "error", "sankey-profit-chain", "company.json.income_statement_sankey.links", "income tax and net income must be terminal nodes")

        profit_adjustment_targets = {"profit_subtotal", "pretax_profit"}
        for node_id in role_ids["profit_addition"]:
            targets = children[node_id]
            if parents[node_id] or len(targets) != 1 or role_by_id.get(next(iter(targets), None)) not in profit_adjustment_targets:
                add(findings, "error", "sankey-profit-addition", "company.json.income_statement_sankey.links", f"profit addition {node_id!r} must be a root with exactly one positive flow into a profit subtotal or pretax profit")

        for node_id in role_ids["profit_deduction"]:
            if children[node_id] or len(parents[node_id]) != 1 or role_by_id.get(next(iter(parents[node_id]), None)) != "profit_subtotal":
                add(findings, "error", "sankey-profit-deduction", "company.json.income_statement_sankey.links", f"profit deduction {node_id!r} must be terminal with exactly one profit-subtotal parent")

        for node_id in role_ids["cost_offset"]:
            targets = children[node_id]
            if parents[node_id] or len(targets) != 1 or role_by_id.get(next(iter(targets), None)) != "cost_subtotal":
                add(findings, "error", "sankey-cost-offset", "company.json.income_statement_sankey.links", f"cost offset {node_id!r} must be a root with exactly one positive flow into a cost subtotal")

        cost_roles = {"cost_expense", "cost_subtotal", "pretax_costs_total"}
        profit_addition_ids = set(role_ids["profit_addition"])
        cost_offset_ids = set(role_ids["cost_offset"])
        profit_chain: list[Any] = []
        current = revenue_total
        seen_profit_nodes = {current}
        while current != pretax_profit:
            current_children = children[current]
            profit_successors = [child for child in current_children if role_by_id.get(child) in {"profit_subtotal", "pretax_profit"}]
            cost_children = [child for child in current_children if role_by_id.get(child) in cost_roles]
            deduction_children = [child for child in current_children if role_by_id.get(child) == "profit_deduction"]
            other_children = current_children - set(profit_successors) - set(cost_children) - set(deduction_children)
            if len(profit_successors) != 1 or other_children:
                add(findings, "error", "sankey-profit-chain", "company.json.income_statement_sankey.links", f"{current!r} must have exactly one next profit node and no unsupported branches")
                break
            successor = profit_successors[0]
            continuation_edges.add((current, successor))
            unexpected_parents = parents[successor] - {current} - profit_addition_ids
            if current not in parents[successor] or unexpected_parents:
                add(findings, "error", "sankey-profit-chain", "company.json.income_statement_sankey.links", f"profit node {successor!r} must receive its bridge from {current!r} and may otherwise receive only controlled profit additions")
            addition_parents = parents[successor] & profit_addition_ids
            if not cost_children and not deduction_children and (current == revenue_total or not addition_parents):
                add(findings, "error", "sankey-profit-chain", "company.json.income_statement_sankey.links", f"{current!r} may omit a cost branch only when it is a profit subtotal and the next profit node receives at least one controlled profit addition")
            if current == revenue_total and successor == pretax_profit:
                if len(cost_children) != 1 or role_by_id.get(cost_children[0]) != "pretax_costs_total":
                    add(findings, "error", "sankey-cost-expansion", "company.json.income_statement_sankey.links", "minimum hierarchy requires total revenue -> calculated pretax cost total + pretax profit")
            elif any(role_by_id.get(child) == "pretax_costs_total" for child in cost_children):
                add(findings, "error", "sankey-cost-expansion", "company.json.income_statement_sankey.links", "a profit-subtotal ladder cannot also draw a duplicate pretax cost total branch")
            if successor in seen_profit_nodes:
                add(findings, "error", "sankey-cycle", "company.json.income_statement_sankey.links", "profit bridge contains a cycle")
                break
            seen_profit_nodes.add(successor)
            if role_by_id.get(successor) == "profit_subtotal":
                profit_chain.append(successor)
            current = successor
        if set(profit_chain) != set(role_ids["profit_subtotal"]):
            add(findings, "error", "sankey-profit-chain", "company.json.income_statement_sankey.links", "every profit_subtotal must appear exactly once on the total-revenue-to-pretax-profit chain")

        for node_id in role_ids["cost_subtotal"] + role_ids["pretax_costs_total"]:
            structural_parents = parents[node_id] - cost_offset_ids
            offset_parents = parents[node_id] & cost_offset_ids
            offset_allowed = role_by_id.get(node_id) == "cost_subtotal"
            if (
                len(structural_parents) != 1
                or (offset_parents and not offset_allowed)
                or not children[node_id]
                or any(role_by_id.get(child) not in {"cost_subtotal", "cost_expense"} for child in children[node_id])
            ):
                add(findings, "error", "sankey-cost-expansion", "company.json.income_statement_sankey.links", f"cost subtotal {node_id!r} must have one structural parent, may receive controlled cost offsets only when categorized cost_subtotal, and expand only to disclosed cost/expense leaves or lower cost subtotals")
        for node_id in role_ids["cost_expense"]:
            if children[node_id] or len(parents[node_id]) != 1:
                add(findings, "error", "sankey-cost-expansion", "company.json.income_statement_sankey.links", f"cost/expense {node_id!r} must be a terminal item with exactly one parent")

        reachable = {revenue_total}
        pending = [revenue_total]
        while pending:
            current = pending.pop()
            for adjacent in parents[current] | children[current]:
                if adjacent not in reachable:
                    reachable.add(adjacent)
                    pending.append(adjacent)
        if reachable != node_ids:
            add(findings, "error", "sankey-connectivity", "company.json.income_statement_sankey.links", f"the positive-flow graph must be weakly connected; mismatch {sorted(reachable ^ node_ids)!r}")

        def signed_node_value(node_id: Any) -> Any:
            node = node_by_id[node_id]
            value = node.get("statement_value")
            return value if numeric(value) else node.get("value")

        revenue_value = signed_node_value(revenue_total)
        pretax_value = signed_node_value(pretax_profit)
        tax_value = signed_node_value(income_tax)
        net_value = signed_node_value(net_income)
        pretax_decimal = sankey_decimal(pretax_value)
        tax_decimal = sankey_decimal(tax_value)
        net_decimal = sankey_decimal(net_value)
        if (
            pretax_decimal is not None
            and tax_decimal is not None
            and net_decimal is not None
            and not sankey_amounts_equal(pretax_decimal - tax_decimal, net_decimal)
        ):
            add(findings, "error", "sankey-equation-mismatch", "company.json.income_statement_sankey", f"net income {net_value} must equal pretax profit {pretax_value} minus income tax {tax_value}")

        fiscal_year = sankey.get("fiscal_year")
        matching_financials = [
            item for item in list_or_empty(company.get("financials"))
            if isinstance(item, dict) and item.get("period") == fiscal_year
        ]
        if len(matching_financials) != 1:
            add(
                findings,
                "error",
                "sankey-financial-period",
                "company.json.income_statement_sankey.fiscal_year",
                "Sankey fiscal_year must match exactly one company.financials period",
            )
        else:
            financial = matching_financials[0]
            comparisons = (
                ("revenue", revenue_total, financial.get("revenue")),
                ("net_income", net_income, financial.get("net_income")),
            )
            for metric, node_id, financial_value in comparisons:
                node_value = signed_node_value(node_id)
                if numeric(node_value) and numeric(financial_value) and not sankey_amounts_equal(node_value, financial_value):
                    add(
                        findings,
                        "error",
                        "sankey-financial-statement-mismatch",
                        "company.json.income_statement_sankey",
                        f"{metric} node {node_value} does not match company.financials {financial_value} for {fiscal_year}",
                    )

    ledger = calculations.get("income_statement_sankey") if isinstance(calculations, dict) else None
    calculation_items = calculations.get("calculations") if isinstance(calculations, dict) else None
    if not isinstance(ledger, dict) or not isinstance(calculation_items, list):
        add(findings, "error", "sankey-disclosure-ledger", "calculation-ledger.json.income_statement_sankey", "requires a disclosure inventory and calculated-node bindings")
        return
    if ledger.get("fiscal_year") != sankey.get("fiscal_year") or not substantive_text(ledger.get("review_method"), 16):
        add(findings, "error", "sankey-disclosure-ledger", "calculation-ledger.json.income_statement_sankey", "fiscal_year must match and review_method must document line-by-line annual-report review")

    validate_sankey_color_audit(company, ledger, node_by_id, node_ids, findings)

    known_sources = known if known is not None else set()
    annual_report_source_ids = {
        source.get("id")
        for source in list_or_empty(company.get("sources"))
        if isinstance(source, dict)
        and nonblank(source.get("id"))
        and source.get("source_type") == "annual_report"
    }

    def resolved_source_ids(value: Any) -> bool:
        return isinstance(value, list) and bool(value) and (not known_sources or all(source_id in known_sources for source_id in value))

    root_source_ids = sankey.get("source_ids")
    ledger_source_ids = ledger.get("source_ids")
    if not resolved_source_ids(root_source_ids) or not resolved_source_ids(ledger_source_ids):
        add(findings, "error", "sankey-disclosure-ledger", "calculation-ledger.json.income_statement_sankey.source_ids", "Sankey and disclosure ledger require nonempty resolved source_ids")

    disclosed = ledger.get("disclosed_line_items")
    calculated = ledger.get("calculated_nodes")
    if not isinstance(disclosed, list) or not disclosed or not isinstance(calculated, list):
        add(findings, "error", "sankey-disclosure-ledger", "calculation-ledger.json.income_statement_sankey", "disclosed_line_items must be nonempty and calculated_nodes must be an array")
        return

    disclosed_ids: set[Any] = set()
    calculated_ids: set[Any] = set()
    all_item_sources: set[Any] = set(ledger_source_ids) if isinstance(ledger_source_ids, list) else set()
    for index, item in enumerate(disclosed):
        path = f"calculation-ledger.json.income_statement_sankey.disclosed_line_items[{index}]"
        if not isinstance(item, dict):
            add(findings, "error", "sankey-disclosed-item", path, "disclosed item must be an object")
            continue
        node_id = item.get("node_id")
        source_ids = item.get("source_ids")
        if node_id in disclosed_ids or node_id not in node_ids:
            add(findings, "error", "sankey-disclosed-item", path, "node_id must be unique and resolve to a graph node")
        else:
            disclosed_ids.add(node_id)
        node_statement_value = node_by_id.get(node_id, {}).get("statement_value")
        if not numeric(node_statement_value):
            node_statement_value = node_by_id.get(node_id, {}).get("value")
        if not numeric(item.get("value")) or numeric(node_statement_value) and not sankey_amounts_equal(item.get("value"), node_statement_value):
            add(findings, "error", "sankey-disclosed-item", path, "disclosed value must match the graph node statement_value")
        if not resolved_source_ids(source_ids) or not substantive_text(item.get("location"), 4):
            add(findings, "error", "sankey-disclosed-item", path, "each disclosed line item requires resolved source_ids and a precise annual-report location")
        if (
            node_id in role_ids["revenue_offset"]
            and (
                not isinstance(source_ids, list)
                or not any(source_id in annual_report_source_ids for source_id in source_ids)
            )
        ):
            add(findings, "error", "sankey-revenue-offset-annual-report-source", path, "each revenue_offset disclosed item must cite at least one source_type=annual_report source; a generic regulatory filing or third-party source is insufficient")
        if isinstance(source_ids, list):
            all_item_sources.update(source_ids)

    calculations_by_id = {
        item.get("id"): item
        for item in calculation_items
        if isinstance(item, dict) and nonblank(item.get("id"))
    }
    for index, item in enumerate(calculated):
        path = f"calculation-ledger.json.income_statement_sankey.calculated_nodes[{index}]"
        if not isinstance(item, dict):
            add(findings, "error", "sankey-calculated-node", path, "calculated-node binding must be an object")
            continue
        node_id, calculation_id = item.get("node_id"), item.get("calculation_id")
        record = calculations_by_id.get(calculation_id)
        if node_id in calculated_ids or node_id not in node_ids:
            add(findings, "error", "sankey-calculated-node", path, "node_id must be unique and resolve to a graph node")
        else:
            calculated_ids.add(node_id)
        label = node_by_id.get(node_id, {}).get("label")
        if not isinstance(label, str) or not re.search(r"计算值|calculated", label, re.I):
            add(findings, "error", "sankey-calculated-node", path, "calculated aggregate node label must state 计算值/calculated")
        if (
            not isinstance(record, dict)
            or record.get("metric") != "custom"
            or record.get("sankey_node_id") != node_id
            or record.get("period") != sankey.get("fiscal_year")
            or not numeric(record.get("result"))
            or node_id not in node_by_id
            or not numeric(node_by_id.get(node_id, {}).get("statement_value", node_by_id.get(node_id, {}).get("value")))
            or not sankey_amounts_equal(record.get("result"), node_by_id.get(node_id, {}).get("statement_value", node_by_id.get(node_id, {}).get("value")))
            or not resolved_source_ids(record.get("source_ids"))
        ):
            add(findings, "error", "sankey-calculated-node", path, "binding must resolve to a same-period custom calculation with matching node statement_value, result and sources")
        if isinstance(record, dict) and isinstance(record.get("source_ids"), list):
            all_item_sources.update(record["source_ids"])

    calculated_links = ledger.get("calculated_links")
    if uses_signed_contract:
        if not isinstance(calculated_links, list):
            add(findings, "error", "sankey-calculated-link", "calculation-ledger.json.income_statement_sankey.calculated_links", "Schema 2.2.0 and later require calculated_links[] to cover every revenue and profit continuation edge")
            calculated_links = []
        covered_edges: set[tuple[Any, Any]] = set()
        link_calculation_ids: set[Any] = set()
        for index, item in enumerate(calculated_links):
            path = f"calculation-ledger.json.income_statement_sankey.calculated_links[{index}]"
            if not isinstance(item, dict):
                add(findings, "error", "sankey-calculated-link", path, "calculated-link binding must be an object")
                continue
            source = item.get("source")
            target = item.get("target")
            calculation_id = item.get("calculation_id")
            edge = (source, target)
            if not nonblank(source) or not nonblank(target) or not nonblank(calculation_id):
                add(findings, "error", "sankey-calculated-link", path, "source, target and calculation_id must be nonblank")
                continue
            if edge in covered_edges or calculation_id in link_calculation_ids:
                add(findings, "error", "sankey-calculated-link", path, "each continuation edge and calculation_id must be unique")
            covered_edges.add(edge)
            link_calculation_ids.add(calculation_id)
            record = calculations_by_id.get(calculation_id)
            if edge not in actual_edges or edge not in continuation_edges:
                add(findings, "error", "sankey-calculated-link", path, "binding must reference an actual revenue- or profit-chain continuation edge")
            if (
                not isinstance(record, dict)
                or record.get("metric") != "custom"
                or record.get("sankey_source") != source
                or record.get("sankey_target") != target
                or record.get("period") != sankey.get("fiscal_year")
                or not numeric(record.get("result"))
                or edge not in edge_values
                or not sankey_amounts_equal(record.get("result"), edge_values.get(edge))
                or not resolved_source_ids(record.get("source_ids"))
            ):
                add(findings, "error", "sankey-calculated-link", path, "binding must resolve to a same-period custom calculation whose Sankey endpoints, exact-cent result and sources match the continuation edge")
            direct_revenue_offsets = sorted(
                child
                for child in children.get(source, set())
                if role_by_id.get(child) == "revenue_offset"
            )
            if role_by_id.get(source) == "revenue_subtotal" and direct_revenue_offsets:
                expected_input_ids = {source, *direct_revenue_offsets}
                record_inputs = record.get("inputs") if isinstance(record, dict) else None
                inputs_match_signed_nodes = (
                    isinstance(record_inputs, dict)
                    and set(record_inputs) == expected_input_ids
                    and all(
                        sankey_amounts_equal(
                            record_inputs.get(node_id),
                            node_by_id.get(node_id, {}).get("statement_value"),
                        )
                        for node_id in expected_input_ids
                    )
                )
                if not inputs_match_signed_nodes:
                    add(
                        findings,
                        "error",
                        "sankey-revenue-offset-calculation-inputs",
                        path,
                        "a revenue-subtotal continuation with direct offsets must use exactly the source subtotal and direct offset node IDs as inputs, with each value equal to that node's signed statement_value",
                    )
            direct_profit_deductions = {
                child for child in children.get(source, set())
                if role_by_id.get(child) == "profit_deduction"
            }
            if role_by_id.get(source) == "profit_subtotal" and direct_profit_deductions:
                direct_costs = {
                    child for child in children.get(source, set())
                    if role_by_id.get(child) in {"cost_expense", "cost_subtotal", "pretax_costs_total"}
                }
                expected_input_ids = {source} | direct_profit_deductions | direct_costs
                record_inputs = record.get("inputs") if isinstance(record, dict) else None
                inputs_match = (
                    isinstance(record_inputs, dict)
                    and set(record_inputs) == expected_input_ids
                    and all(sankey_amounts_equal(record_inputs.get(node_id), node_by_id.get(node_id, {}).get("statement_value")) for node_id in expected_input_ids)
                )
                signed_values = {node_id: sankey_decimal(node_by_id.get(node_id, {}).get("statement_value")) for node_id in expected_input_ids}
                expected_continuation = None
                if all(value is not None for value in signed_values.values()):
                    expected_continuation = signed_values[source] - sum((signed_values[node_id] for node_id in direct_costs), Decimal(0)) + sum((signed_values[node_id] for node_id in direct_profit_deductions), Decimal(0))
                if not inputs_match or not sankey_amounts_equal(expected_continuation, edge_values.get(edge)):
                    add(findings, "error", "sankey-profit-deduction-calculation-inputs", path, "profit continuation must bind exactly the source subtotal, direct positive costs and direct negative deductions by node ID and preserve their signed statement values; continuation equals subtotal minus costs plus signed deductions")
            if isinstance(record, dict) and isinstance(record.get("source_ids"), list):
                all_item_sources.update(record["source_ids"])
        if covered_edges != continuation_edges:
            add(findings, "error", "sankey-calculated-link-coverage", "calculation-ledger.json.income_statement_sankey.calculated_links", f"must cover each revenue- and profit-chain continuation edge exactly once; mismatch {sorted(covered_edges ^ continuation_edges)!r}")

    if disclosed_ids & calculated_ids or disclosed_ids | calculated_ids != node_ids:
        add(findings, "error", "sankey-provenance-coverage", "calculation-ledger.json.income_statement_sankey", f"every graph node must appear exactly once as disclosed or calculated; mismatch {sorted((disclosed_ids | calculated_ids) ^ node_ids)!r}")
    undisclosed_revenue_offsets = set(role_ids["revenue_offset"]) - disclosed_ids
    if undisclosed_revenue_offsets:
        add(findings, "error", "sankey-revenue-offset-provenance", "calculation-ledger.json.income_statement_sankey.disclosed_line_items", f"every revenue_offset must be a separately disclosed annual-report line item; missing {sorted(undisclosed_revenue_offsets)!r}")
    if isinstance(root_source_ids, list) and not all_item_sources.issubset(set(root_source_ids)):
        add(findings, "error", "sankey-provenance-coverage", "company.json.income_statement_sankey.source_ids", "root source_ids must cover every disclosed and calculated node source")


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
    else:
        for index, item in enumerate(commitments):
            path = f"company.json.management.commitment_timeline[{index}]"
            validation = item.get("next_validation") if isinstance(item, dict) else None
            status = item.get("status") if isinstance(item, dict) else None
            outcome = item.get("outcome") if isinstance(item, dict) else None
            outcome_valid = (
                outcome is None and status == "pending"
            ) or (
                substantive_text(outcome, 8) and not looks_like_placeholder(outcome)
            )
            if (
                not isinstance(item, dict)
                or not substantive_text(item.get("date"), 4)
                or not substantive_text(item.get("commitment"), 8)
                or status not in {"fulfilled", "partially_fulfilled", "unfulfilled", "pending"}
                or not outcome_valid
                or not isinstance(validation, dict)
                or any(
                    not substantive_text(validation.get(key), minimum) or looks_like_placeholder(validation.get(key))
                    for key, minimum in (("method", 8), ("condition", 8), ("timeframe", 3))
                )
            ):
                add(
                    findings,
                    "error",
                    "management-commitment-substance",
                    path,
                    "commitment events require standardized status, an observed outcome unless still pending, and a substantive next-validation method, condition and timeframe",
                )
    stop_list = management.get("stop_doing_list")
    if not isinstance(stop_list, list) or len(stop_list) < 2 or any(not substantive_text(item, 6) for item in stop_list):
        add(findings, "warning" if is_unable(company) else "error", "management-stop-doing", "company.json.management.stop_doing_list", "requires at least two substantive stop-doing constraints, or an acknowledged Too Hard gap")
    allocation = company.get("capital_allocation")
    if not isinstance(allocation, list) or not allocation or not any(isinstance(item, dict) and numeric(item.get("amount")) for item in allocation):
        add(findings, "warning" if is_unable(company) else "error", "capital-allocation-substance", "company.json.capital_allocation", "requires at least one sourced numeric capital-allocation item or an acknowledged Too Hard gap")
    elif any(
        not isinstance(item, dict)
        or item.get("lane") not in {"reinvest", "risk_reduction", "shareholder_return"}
        or item.get("result_status") not in {"positive", "mixed", "negative", "pending"}
        or not substantive_text(item.get("result"), 8)
        or not substantive_text(item.get("assessment"), 8)
        or looks_like_placeholder(item.get("result"))
        or looks_like_placeholder(item.get("assessment"))
        for item in allocation
    ):
        add(
            findings,
            "error",
            "capital-allocation-result",
            "company.json.capital_allocation",
            "each allocation needs a three-lane classification, result status, observable result and per-share or resilience assessment",
        )


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
            discount = scenario.get("discount_rate")
            terminal = scenario.get("terminal_growth")
            value = scenario.get("fair_value_per_share")
            terminal_share = scenario.get("terminal_value_share")
            if not unable and not all(numeric(item) for item in (discount, terminal, value, terminal_share)):
                add(findings, "error", "dcf-scenario-inputs", f"company.json.valuation.dcf_scenarios[{index}]", "each scenario requires discount rate, terminal growth, terminal-value share and fair value")
            if numeric(discount) and numeric(terminal) and float(terminal) >= float(discount):
                add(findings, "error", "dcf-terminal-rate", f"company.json.valuation.dcf_scenarios[{index}]", "terminal growth must be below discount rate")
            if kind and numeric(value):
                values[kind] = float(value)
    if not unable and kinds != {"bear", "base", "bull"}:
        add(findings, "error", "dcf-scenarios", "company.json.valuation.dcf_scenarios", "requires 悲观 / 基准 / 乐观 scenarios")
    if all(kind in values for kind in ("bear", "base", "bull")) and not values["bear"] <= values["base"] <= values["bull"]:
        add(findings, "error", "dcf-order", "company.json.valuation.dcf_scenarios", "scenario values must be 悲观 ≤ 基准 ≤ 乐观")
    sensitivity = valuation.get("dcf_sensitivity")
    if not unable:
        valid_cells = [
            item
            for item in sensitivity
            if isinstance(item, dict)
            and all(numeric(item.get(key)) for key in ("discount_rate", "terminal_growth", "fair_value_per_share"))
        ] if isinstance(sensitivity, list) else []
        discounts = sorted({float(item["discount_rate"]) for item in valid_cells})
        terminals = sorted({float(item["terminal_growth"]) for item in valid_cells})
        combinations = {
            (float(item["discount_rate"]), float(item["terminal_growth"]))
            for item in valid_cells
        }
        expected_combinations = {(discount, terminal) for discount in discounts for terminal in terminals}
        base_scenario = next(
            (item for item in list_or_empty(scenarios) if isinstance(item, dict) and scenario_kind(item.get("name")) == "base"),
            None,
        )
        if (
            not isinstance(sensitivity, list)
            or len(sensitivity) != 9
            or len(valid_cells) != 9
            or len(discounts) != 3
            or len(terminals) != 3
            or combinations != expected_combinations
        ):
            add(
                findings,
                "error",
                "dcf-sensitivity-grid",
                "company.json.valuation.dcf_sensitivity",
                "requires exactly nine numeric cells forming three unique discount rates × three unique terminal growth rates",
            )
        elif any(terminal >= discount for discount, terminal in combinations):
            add(findings, "error", "dcf-sensitivity-rate", "company.json.valuation.dcf_sensitivity", "every terminal growth rate must be below its discount rate")
        elif not isinstance(base_scenario, dict) or not all(numeric(base_scenario.get(key)) for key in ("discount_rate", "terminal_growth", "fair_value_per_share")):
            add(findings, "error", "dcf-sensitivity-base", "company.json.valuation.dcf_sensitivity", "base scenario must provide numeric assumptions for the center cell")
        else:
            base_discount = float(base_scenario["discount_rate"])
            base_terminal = float(base_scenario["terminal_growth"])
            center = next(
                (
                    item
                    for item in valid_cells
                    if float(item["discount_rate"]) == base_discount and float(item["terminal_growth"]) == base_terminal
                ),
                None,
            )
            if discounts[1] != base_discount or terminals[1] != base_terminal or center is None:
                add(findings, "error", "dcf-sensitivity-base", "company.json.valuation.dcf_sensitivity", "base discount rate and terminal growth must be the middle row and column")
            elif not close_enough(float(center["fair_value_per_share"]), float(base_scenario["fair_value_per_share"])):
                add(findings, "error", "dcf-sensitivity-base-value", "company.json.valuation.dcf_sensitivity", "center cell must match the base scenario fair value")
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
    pre_mortem = risks.get("pre_mortem")
    path_values: list[Any] = []
    trigger_values: list[Any] = []
    if not isinstance(pre_mortem, list) or len(pre_mortem) < 5:
        add(findings, "error", "pre_mortem-substance", "company.json.risks.pre_mortem", "requires at least five structured failure paths")
    else:
        for index, item in enumerate(pre_mortem):
            path = f"company.json.risks.pre_mortem[{index}]"
            required_text = (
                ("failure_path", 8),
                ("trigger", 8),
                ("operating_impact", 8),
                ("capital_cash_impact", 8),
                ("value_impact", 8),
                ("time_horizon", 3),
                ("earliest_warning", 6),
            )
            if not isinstance(item, dict) or any(
                not substantive_text(item.get(key), minimum) or looks_like_placeholder(item.get(key))
                for key, minimum in required_text
            ) or (
                item.get("management_mitigation") is not None
                and (
                    not substantive_text(item.get("management_mitigation"), 8)
                    or looks_like_placeholder(item.get("management_mitigation"))
                )
            ):
                add(findings, "error", "pre_mortem-causal-chain", path, "requires trigger → operating → capital/cash → value impacts plus horizon and warning; mitigation may be null only when none is evidenced")
                continue
            causal_stages = [
                normalized_text(item.get(key), replace_numbers=True)
                for key in ("trigger", "operating_impact", "capital_cash_impact", "value_impact")
            ]
            if len(set(causal_stages)) != len(causal_stages):
                add(findings, "error", "pre_mortem-causal-chain", path, "causal stages cannot repeat the same placeholder text")
            path_values.append(item.get("failure_path"))
            trigger_values.append(item.get("trigger"))
        normalized_paths = [normalized_text(item, replace_numbers=True) for item in path_values]
        normalized_triggers = [normalized_text(item, replace_numbers=True) for item in trigger_values]
        if (
            len(path_values) != len(pre_mortem)
            or len(set(normalized_paths)) != len(normalized_paths)
            or len(set(normalized_triggers)) != len(normalized_triggers)
            or repeated_template_fingerprints(path_values, minimum_count=3)
            or has_near_duplicate_cluster(path_values, minimum_count=3)
        ):
            add(findings, "error", "pre_mortem-substance", "company.json.risks.pre_mortem", "failure paths and triggers must be distinct and company-specific")
    fragile = risks.get("fragile_assumptions")
    normalized_fragile = [normalized_text(item, replace_numbers=True) for item in fragile] if isinstance(fragile, list) else []
    if (
        not isinstance(fragile, list)
        or len(fragile) < 3
        or any(not substantive_text(item, 8) or looks_like_placeholder(item) for item in fragile)
        or len(set(normalized_fragile)) != len(normalized_fragile)
        or repeated_template_fingerprints(fragile, minimum_count=3)
        or has_near_duplicate_cluster(fragile, minimum_count=3)
    ):
        add(findings, "error", "fragile_assumptions-substance", "company.json.risks.fragile_assumptions", "requires at least three distinct, company-specific entries")
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
                for key, minimum in (
                    ("name", 3),
                    ("current_status", 5),
                    ("trigger", 8),
                    ("why_it_matters", 8),
                    ("recheck_method", 8),
                )
            ):
                add(findings, "error", "monitoring-substance", path, "requires name, current status, trigger, why it matters and a concrete recheck method")
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
        recheck_values = [item.get("recheck_method") for item in indicators if isinstance(item, dict)]
        if repeated_template_fingerprints(recheck_values) or has_near_duplicate_cluster(recheck_values):
            add(findings, "error", "repeated-monitoring-template", "company.json.risks.monitoring_indicators", "monitoring recheck methods repeat a placeholder template")


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
        if tag not in {"code", "pre", "template", "script", "style"} and not hidden_attribute and not hidden_style:
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


def visible_markdown_disclosure_text(value: str) -> str:
    """Return rendered prose signals, excluding code, comments, URL targets, and HTML attributes."""
    text = mask_non_rendered_markdown(value)
    text = re.sub(r"(?m)^[ \t]{0,3}\[[^\]\n]+\]:[^\n]*$", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^\n)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"`+[^`\n]*`+", " ", text)
    text = re.sub(r"(?m)^(?: {4}|\t).*?$", "", text)
    text = re.sub(r"<(?:\"[^\"]*\"|'[^']*'|[^'\">])*>", " ", text)
    return html.unescape(text)


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
    normalized_headers = [normalized_text(clean_markdown_text(header)) for header in headers]
    for index, key in enumerate(normalized_headers):
        if key in normalized_alternatives:
            return index
    for index, key in enumerate(normalized_headers):
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


def durability_status_value(value: Any, *, overall: bool = False) -> str | None:
    text = normalized_text(value)
    aliases = (
        {
            "durable": ("durable", "可长期生存", "持久"),
            "conditional": ("conditional", "有条件", "条件性"),
            "fragile": ("fragile", "脆弱"),
            "too_hard": ("too hard", "toohard", "无法判断", "资料不足"),
        }
        if overall
        else {
            "strong": ("strong", "强"),
            "adequate": ("adequate", "足够", "尚可"),
            "uncertain": ("uncertain", "不确定"),
            "weak": ("weak", "弱"),
        }
    )
    for canonical, values in aliases.items():
        if any(text == normalized_text(alias) for alias in values):
            return canonical
    return None


def durability_dimension_key(value: Any) -> str | None:
    text = normalized_text(value)
    aliases = {
        "demand_durability": ("需求持久性", "需求持久", "demand durability"),
        "adaptability": ("适应能力", "适应性", "adaptability"),
        "external_shocks": ("外部冲击", "外部冲击韧性", "external shocks"),
    }
    matches = [
        key
        for key, values in aliases.items()
        if any(normalized_text(alias) == text for alias in values)
    ]
    return matches[0] if len(matches) == 1 else None


def validate_durability_report(company: dict[str, Any], body: str, findings: list[Finding]) -> None:
    durability = company.get("durability") if isinstance(company.get("durability"), dict) else {}
    horizon = labelled_value(body, ("观察期限", "判断期限", "生存期限", "horizon"))
    overall = labelled_value(body, ("总体状态", "总体判断", "overall status"))
    conclusion = labelled_value(body, ("结论", "长期结论", "conclusion"))
    horizon_match = re.search(r"\d+", clean_markdown_text(horizon or ""))
    summary_valid = (
        horizon_match is not None
        and int(horizon_match.group(0)) == durability.get("horizon_years")
        and durability_status_value(overall, overall=True) == durability.get("overall_status")
        and normalized_text(conclusion) == normalized_text(durability.get("conclusion"))
    )
    if not summary_valid:
        add(
            findings,
            "error",
            "report-durability-summary",
            "research-report.md#durability",
            "durability section must reconcile the 20+ year horizon, standardized overall status and conclusion",
        )

    required_headers = {
        "dimension": ("维度", "dimension"),
        "status": ("状态", "status"),
        "assessment": ("判断", "评估", "assessment"),
        "evidence": ("证据", "evidence"),
        "breaker": ("破坏条件", "失效条件", "breaker"),
    }
    expected_keys = ("demand_durability", "adaptability", "external_shocks")
    matrix_valid = False
    for headers, rows in parse_markdown_tables(body):
        columns = {key: header_column(headers, aliases) for key, aliases in required_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        observed: set[str] = set()
        for row in rows:
            key = durability_dimension_key(row[int(columns["dimension"])])
            expected = durability.get(key) if key else None
            if not isinstance(expected, dict):
                continue
            evidence_text = normalized_text(row[int(columns["evidence"])])
            evidence_raw = row[int(columns["evidence"])]
            expected_evidence = [normalized_text(item) for item in list_or_empty(expected.get("evidence"))]
            expected_source_ids = {
                item for item in list_or_empty(expected.get("source_ids")) if isinstance(item, str)
            }
            if (
                durability_status_value(row[int(columns["status"])]) == expected.get("status")
                and normalized_text(row[int(columns["assessment"])]) == normalized_text(expected.get("assessment"))
                and expected_evidence
                and all(value and value in evidence_text for value in expected_evidence)
                and expected_source_ids
                and text_has_known_citation(company, evidence_raw, expected_source_ids)
                and normalized_text(row[int(columns["breaker"])]) == normalized_text(expected.get("breaker"))
            ):
                observed.add(key)
        matrix_valid = len(rows) == len(expected_keys) and observed == set(expected_keys)
        break
    if not matrix_valid:
        add(
            findings,
            "error",
            "report-durability-matrix",
            "research-report.md#durability",
            "durability section needs exactly three reconciled rows for demand durability, adaptability and external shocks, each with status, evidence and breaker",
        )


def risk_probability_category(value: Any) -> str | None:
    text = normalized_text(value)
    aliases = {
        "medium_low": ("mediumlow", "中低", "中低概率"),
        "medium_high": ("mediumhigh", "中高", "中高概率"),
        "medium": ("medium", "中", "中等", "中等概率"),
        "low": ("low", "低", "低概率"),
        "high": ("high", "高", "高概率"),
        "unknown": ("unknown", "insufficient", "无法判断", "资料不足", "未披露"),
    }
    for canonical, values in aliases.items():
        if text in {normalized_text(alias) for alias in values}:
            return canonical
    return None


def probability_value(value: str) -> bool:
    return risk_probability_category(value) is not None


def risk_impact_category(value: Any) -> str | None:
    text = normalized_text(value)
    aliases = {
        "catastrophic": ("catastrophic", "毁灭性", "灾难性"),
        "severe": ("severe", "critical", "严重"),
        "high": ("high", "高", "重大"),
        "medium": ("medium", "中", "中等"),
        "low": ("low", "低"),
        "unknown": ("unknown", "insufficient", "无法判断", "资料不足", "未披露"),
    }
    for canonical, values in aliases.items():
        if text in {normalized_text(alias) for alias in values}:
            return canonical
    return None


def impact_value(value: str) -> bool:
    return risk_impact_category(value) is not None


def horizon_value(value: str) -> bool:
    return bool(re.search(r"\d+(?:\s*(?:[–—-]|至)\s*\d+)?\s*(?:年|月|季|years?|months?|quarters?)|随时|即时|持续|短期|中期|长期", value, re.I))


def risk_reversibility_category(value: Any) -> str | None:
    text = normalized_text(value)
    aliases = {
        "reversible": ("reversible", "可逆"),
        "partially_reversible": ("partiallyreversible", "部分可逆"),
        "hard_to_reverse": ("hardtoreverse", "难以逆转", "难逆"),
        "irreversible": ("irreversible", "不可逆"),
    }
    for canonical, values in aliases.items():
        if text in {normalized_text(alias) for alias in values}:
            return canonical
    return None


def reversibility_value(value: str) -> bool:
    return risk_reversibility_category(value) is not None


def explicit_null_display(value: Any) -> bool:
    text = normalized_text(value)
    return text in {
        normalized_text(item)
        for item in ("无", "暂无", "没有", "未披露", "无法判断", "资料不足", "none", "not disclosed", "unknown")
    }


def nullable_report_text_matches(actual: Any, expected: Any) -> bool:
    if expected is None:
        return explicit_null_display(actual)
    return normalized_text(actual) == normalized_text(expected)


def validate_pre_mortem_report(company: dict[str, Any], body: str, findings: list[Finding]) -> None:
    required_headers = {
        "path": ("失败路径", "failure path"),
        "trigger": ("触发因素", "触发条件", "trigger"),
        "operating": ("经营影响", "operating impact"),
        "capital_cash": ("资本 / 现金影响", "资本/现金影响", "资本与现金影响", "capital cash impact"),
        "value": ("价值影响", "内在价值影响", "value impact"),
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
        add(findings, "error", "report-pre-mortem-matrix", "research-report.md#pre-mortem", "Pre-Mortem needs causal-chain, probability, impact, horizon, warning, reversibility and mitigation columns")
        return
    rows, columns = selected
    paths: list[str] = []
    causal_rows: list[dict[str, str]] = []
    valid_rows = 0
    for row in rows:
        path = clean_markdown_text(row[columns["path"]])
        trigger = clean_markdown_text(row[columns["trigger"]])
        operating = clean_markdown_text(row[columns["operating"]])
        capital_cash = clean_markdown_text(row[columns["capital_cash"]])
        value = clean_markdown_text(row[columns["value"]])
        probability = clean_markdown_text(row[columns["probability"]])
        impact = clean_markdown_text(row[columns["impact"]])
        horizon = clean_markdown_text(row[columns["horizon"]])
        warning = clean_markdown_text(row[columns["warning"]])
        reversibility = clean_markdown_text(row[columns["reversibility"]])
        mitigation = clean_markdown_text(row[columns["mitigation"]])
        probability_category = risk_probability_category(probability)
        impact_category = risk_impact_category(impact)
        reversibility_category = risk_reversibility_category(reversibility)
        if (
            not substantive_text(path, 8)
            or looks_like_placeholder(path)
            or any(
                not substantive_text(item, 8) or looks_like_placeholder(item)
                for item in (trigger, operating, capital_cash, value)
            )
            or probability_category is None
            or impact_category is None
            or not horizon_value(horizon)
            or not substantive_text(warning, 6)
            or looks_like_placeholder(warning)
            or reversibility_category is None
            or (
                not explicit_null_display(mitigation)
                and (not substantive_text(mitigation, 8) or looks_like_placeholder(mitigation))
            )
        ):
            continue
        paths.append(path)
        causal_rows.append(
            {
                "failure_path": path,
                "trigger": trigger,
                "operating_impact": operating,
                "capital_cash_impact": capital_cash,
                "value_impact": value,
                "probability": probability_category,
                "impact": impact_category,
                "time_horizon": horizon,
                "earliest_warning": warning,
                "reversibility": reversibility_category,
                "management_mitigation": mitigation,
            }
        )
        valid_rows += 1
    if valid_rows < 5 or not substantive_distinct_entries(paths, 8):
        add(findings, "error", "report-pre-mortem-substance", "research-report.md#pre-mortem", "Pre-Mortem needs at least five distinct, fully specified failure paths")

    risks = company.get("risks") if isinstance(company.get("risks"), dict) else {}
    expected_records = [
        item
        for item in list_or_empty(risks.get("pre_mortem"))
        if isinstance(item, dict) and substantive_text(item.get("failure_path"), 8)
    ]
    expected_paths = [item["failure_path"] for item in expected_records]
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
    if path_mapping_valid:
        for report_row, expected_index in zip(causal_rows, matched_expected):
            expected = expected_records[expected_index]
            if any(
                normalized_text(report_row[field]) != normalized_text(expected.get(field))
                for field in ("trigger", "operating_impact", "capital_cash_impact", "value_impact")
            ) or (
                report_row["probability"] != (expected.get("probability") if expected.get("probability") is not None else "unknown")
                or report_row["impact"] != (expected.get("impact") if expected.get("impact") is not None else "unknown")
                or normalized_text(report_row["time_horizon"]) != normalized_text(expected.get("time_horizon"))
                or normalized_text(report_row["earliest_warning"]) != normalized_text(expected.get("earliest_warning"))
                or report_row["reversibility"] != expected.get("reversibility")
                or not nullable_report_text_matches(report_row["management_mitigation"], expected.get("management_mitigation"))
            ):
                path_mapping_valid = False
                break
    if not path_mapping_valid:
        add(findings, "error", "report-pre-mortem-path-mapping", "research-report.md#pre-mortem", "failure-path rows must uniquely exhaust company.risks.pre_mortem and match each structured causal chain")

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
            r"(?:增长率|增速|收入增长|营收增长|现金流增长|利润增长|利润率|毛利率|净利率|回报率|收益率|"
            r"折现率|终值增长|永续增长|初期现金流增长|起始现金流增长|终值占比|占比|比例|税率|"
            r"ROIC|ROE|ROTCE|CET1|FCF\s*Yield)",
            re.I,
        ),
    ),
    ("duration", re.compile(r"(?:显性期|预测期|持有期|年限|期限)", re.I)),
    (
        "money",
        re.compile(
            r"(?:营收|总收入|收入金额|成本|费用|利润|现金流|FCFF|FCFE|Owner Earnings|"
            r"现金|债务|市值|企业价值|资本开支|回购金额|分红|基准日.*总额|估值基准日.*总额|初期.*总额|起始.*总额|"
            r"金额|价值总额|净资产|普通股权益)",
            re.I,
        ),
    ),
)


def display_column_kind(header: str) -> str | None:
    cleaned = clean_markdown_text(header)
    if re.search(r"(?:口径|期间|日期|来源|说明|比较|阈值)", cleaned, re.I):
        return None
    for kind in ("per_share", "shares", "percent", "money"):
        if display_unit_present(cleaned, kind, header=True):
            return kind
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
            matches = list(pattern.finditer(clean_markdown_text(source)))
            if matches:
                return matches[-1 if is_header else 0].group(0)
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
    visible_report = visible_markdown_disclosure_text(report)
    matches = sorted(
        {
            match.group(0).strip()
            for pattern in NONLOCALIZED_CHINESE_UNIT_PATTERNS
            for match in pattern.finditer(visible_report)
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
                r"(?:估值基准日|基准日|初期|起始)?(?:可分配)?(?:现金流)?总额|市值|企业价值|净债务|总债务|"
                r"现金余额|营业收入|总收入|营收|净利润|自由现金流|资本开支|回购金额",
                re.I,
            ),
        ),
        ("shares", re.compile(r"稀释后股数|总股本|回购股数|发行股数", re.I)),
        ("per_share", re.compile(r"基准日每股现金|初期每股现金流|每股价值|股价|回购均价", re.I)),
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
    prose_violations.update(
        match.group(0).strip()
        for match in NONLOCALIZED_PER_SHARE_PATTERN.finditer(visible_report)
    )
    if prose_violations:
        add(
            findings,
            "error",
            "report-display-unit-missing",
            path,
            "Standalone financial figures must carry Chinese reader-facing units instead of exposing bare storage values; "
            f"found {sorted(prose_violations)[:8]!r}",
        )


FORECAST_YEAR_RANGE_RE = re.compile(
    r"(?:第\s*)?(\d+)\s*(?:[—–-]|至|到)\s*(?:第\s*)?(\d+)\s*年",
    re.I,
)
VAGUE_VALUATION_STAGE_RE = re.compile(
    r"初期|前期|中期|后期|早期|后续阶段|第一阶段|第二阶段|长期增长",
    re.I,
)


def forecast_years_from_text(value: str) -> set[int]:
    years: set[int] = set()
    for match in FORECAST_YEAR_RANGE_RE.finditer(clean_markdown_text(value)):
        start, end = int(match.group(1)), int(match.group(2))
        if 1 <= start <= end <= 100:
            years.update(range(start, end + 1))
    return years


def parse_forecast_year(value: Any) -> int | None:
    match = re.search(r"(?:第\s*)?(\d+)\s*年", clean_markdown_text(value), re.I)
    if match is None:
        return None
    year = int(match.group(1))
    return year if 1 <= year <= 100 else None


def validate_report_reader_contract(report: str, findings: list[Finding]) -> None:
    lowered = report.lower()
    legacy_terms = sorted(term for term in REPORT_LEGACY_TERMS if term in report)
    if legacy_terms:
        add(
            findings,
            "error",
            "report-legacy-terminology",
            "research-report.md",
            "investor-facing prose must use the current terminology: 不为清单",
        )
    leaked = sorted({token for token in REPORT_INTERNAL_IMPLEMENTATION_TOKENS if token.lower() in lowered})
    if leaked:
        add(
            findings,
            "error",
            "report-internal-implementation-leak",
            "research-report.md",
            "investor-facing prose must move Schema/JSON/validator workflow explanations to sidecar files; "
            f"found {leaked!r}",
        )

    logo_asset_lines: list[str] = []
    for line in report.splitlines():
        normalized = clean_markdown_text(line).strip()
        lowered_line = normalized.lower()
        if any(token in lowered_line for token in REPORT_LOGO_ASSET_TOKENS):
            logo_asset_lines.append(normalized[:160])
    if logo_asset_lines:
        add(
            findings,
            "error",
            "report-logo-workflow-leak",
            "research-report.md",
            "investor-facing prose and its source index must not contain company Logo/identity-asset status; "
            "move asset workflow to sidecar/archive records and describe material brand changes as economic facts; "
            f"found {sorted(set(logo_asset_lines))!r}",
        )

    sankey_color_lines: list[str] = []
    for line in report.splitlines():
        normalized = clean_markdown_text(line).strip()
        lowered_line = normalized.lower()
        if any(token in lowered_line for token in REPORT_SANKEY_COLOR_WORKFLOW_TOKENS):
            sankey_color_lines.append(normalized[:160])
    if sankey_color_lines:
        add(
            findings,
            "error",
            "report-sankey-color-workflow-leak",
            "research-report.md",
            "investor-facing prose must not contain Sankey palette search, sampling, default, or rendering workflow; "
            f"found {sorted(set(sankey_color_lines))!r}",
        )

    non_heading_lines = [line for line in report.splitlines() if not re.match(r"^\s*#", line)]
    missing_annotations: list[str] = []
    for term in REPORT_GLOSSARY_TERMS:
        term_expression = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        term_pattern = re.compile(term_expression, re.I)
        first_line = next((line for line in non_heading_lines if term_pattern.search(line)), None)
        if first_line is None:
            continue
        annotation_patterns = (
            re.compile(rf"[（(]\s*{term_expression}\s*[:：][^）)\n]{{6,}}[）)]", re.I),
            re.compile(rf"{term_expression}\s*[（(][^）)\n]{{6,}}[）)]", re.I),
        )
        if not any(pattern.search(first_line) for pattern in annotation_patterns):
            missing_annotations.append(term)
    if missing_annotations:
        add(
            findings,
            "error",
            "report-term-first-use-annotation",
            "research-report.md",
            "professional terms need a same-line Chinese full name and plain-language parenthetical at first prose use; "
            f"missing {missing_annotations!r}",
        )


def validate_report_valuation_detail(
    company: dict[str, Any],
    body: str,
    tables: list[tuple[list[str], list[list[str]]]],
    forecast_years: int | None,
    calculations: Any,
    findings: list[Finding],
) -> None:
    if not isinstance(forecast_years, int) or forecast_years <= 0:
        return
    expected_years = set(range(1, forecast_years + 1))
    expected_keys = {(kind, year) for kind in ("bear", "base", "bull") for year in expected_years}
    calculation_items = list_or_empty(calculations.get("calculations") if isinstance(calculations, dict) else [])
    ledger_annual = {
        (scenario_kind(item.get("valuation_scenario")), item.get("forecast_year")): item
        for item in calculation_items
        if isinstance(item, dict)
        and item.get("valuation_role") == "annual_discounted_cash_flow"
        and scenario_kind(item.get("valuation_scenario")) is not None
        and isinstance(item.get("forecast_year"), int)
        and not isinstance(item.get("forecast_year"), bool)
    }
    ledger_terminal = {
        scenario_kind(item.get("valuation_scenario")): item
        for item in calculation_items
        if isinstance(item, dict)
        and item.get("valuation_role") == "terminal_present_value"
        and scenario_kind(item.get("valuation_scenario")) is not None
    }
    ledger_equity = {
        scenario_kind(item.get("valuation_scenario")): item
        for item in calculation_items
        if isinstance(item, dict)
        and item.get("valuation_role") == "equity_value_bridge"
        and scenario_kind(item.get("valuation_scenario")) is not None
    }

    annual_headers = {
        "scenario": ("情景", "场景", "scenario"),
        "year": ("预测年度", "预测年份", "forecast year"),
        "cash_flow": ("可分配现金流", "可分配现金", "cash flow"),
        "discount_factor": ("折现因子", "discount factor"),
        "present_value": ("现金流现值", "当年现值", "present value"),
    }
    annual_rows: dict[tuple[str, int], tuple[float, float, float]] = {}
    annual_invalid = False
    for headers, rows in tables:
        columns = {key: header_column(headers, aliases) for key, aliases in annual_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        for row in rows:
            kind = scenario_kind(row[int(columns["scenario"])])
            year = parse_forecast_year(row[int(columns["year"])])
            cash_index = int(columns["cash_flow"])
            pv_index = int(columns["present_value"])
            cash_flow = parse_localized_display_number(row[cash_index], "money", headers[cash_index])
            discount_factor = parse_report_number(row[int(columns["discount_factor"])])
            present_value = parse_localized_display_number(row[pv_index], "money", headers[pv_index])
            key = (kind, year) if kind is not None and year is not None else None
            if key is None or key in annual_rows or any(value is None for value in (cash_flow, discount_factor, present_value)):
                annual_invalid = True
                continue
            annual_rows[key] = (float(cash_flow), float(discount_factor), float(present_value))
            if not report_number_matches(float(present_value), float(cash_flow) * float(discount_factor)):
                annual_invalid = True
            expected = ledger_annual.get(key)
            if isinstance(expected, dict):
                inputs = expected.get("inputs") if isinstance(expected.get("inputs"), dict) else {}
                if (
                    not report_number_matches(float(cash_flow), inputs.get("cash_flow"))
                    or not report_number_matches(float(discount_factor), inputs.get("discount_factor"))
                    or not report_number_matches(float(present_value), expected.get("result"))
                ):
                    annual_invalid = True
        break
    if annual_invalid or set(annual_rows) != expected_keys or (ledger_annual and set(ledger_annual) != expected_keys):
        add(
            findings,
            "error",
            "report-valuation-yearly-path",
            "research-report.md#valuation",
            "valuation section needs bear/base/bull rows for every forecast year with reconciled cash flow, discount factor and present value",
        )

    terminal_headers = {
        "scenario": ("情景", "场景", "scenario"),
        "last_cash": ("最后一年现金流", "末年现金流", "final year cash flow"),
        "terminal_growth": ("永续增长", "终值增长", "terminal growth"),
        "discount": ("折现率", "discount rate"),
        "terminal_value": ("预测期末终值", "末年终值", "terminal value at"),
        "discount_factor": ("末年折现因子", "terminal discount factor"),
        "terminal_pv": ("终值现值", "terminal present value"),
    }
    terminal_rows: dict[str, tuple[float, float, float, float, float, float]] = {}
    terminal_invalid = False
    for headers, rows in tables:
        columns = {key: header_column(headers, aliases) for key, aliases in terminal_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        for row in rows:
            kind = scenario_kind(row[int(columns["scenario"])])
            money_values: dict[str, float | None] = {}
            for key in ("last_cash", "terminal_value", "terminal_pv"):
                index = int(columns[key])
                money_values[key] = parse_localized_display_number(row[index], "money", headers[index])
            terminal_growth = parse_report_number(row[int(columns["terminal_growth"])])
            discount = parse_report_number(row[int(columns["discount"])])
            discount_factor = parse_report_number(row[int(columns["discount_factor"])])
            values = (
                money_values["last_cash"], terminal_growth, discount,
                money_values["terminal_value"], discount_factor, money_values["terminal_pv"],
            )
            if kind is None or kind in terminal_rows or any(value is None for value in values):
                terminal_invalid = True
                continue
            numeric_values = tuple(float(value) for value in values)
            terminal_rows[kind] = numeric_values
            last_cash, growth, rate, terminal_value, factor, terminal_pv = numeric_values
            if rate <= growth or not report_number_matches(terminal_value, last_cash * (1 + growth) / (rate - growth)) or not report_number_matches(terminal_pv, terminal_value * factor):
                terminal_invalid = True
            expected = ledger_terminal.get(kind)
            if isinstance(expected, dict):
                inputs = expected.get("inputs") if isinstance(expected.get("inputs"), dict) else {}
                if (
                    not report_number_matches(last_cash, inputs.get("last_year_cash_flow"))
                    or not report_number_matches(growth, inputs.get("terminal_growth_rate"))
                    or not report_number_matches(rate, inputs.get("discount_rate"))
                    or not report_number_matches(factor, inputs.get("discount_factor"))
                    or not report_number_matches(terminal_pv, expected.get("result"))
                ):
                    terminal_invalid = True
        break
    if terminal_invalid or set(terminal_rows) != {"bear", "base", "bull"} or (ledger_terminal and set(ledger_terminal) != {"bear", "base", "bull"}):
        add(
            findings,
            "error",
            "report-valuation-terminal-bridge",
            "research-report.md#valuation",
            "valuation section needs a three-scenario terminal bridge from final-year cash flow through terminal value to discounted terminal present value",
        )

    value_headers = {
        "scenario": ("情景", "场景", "scenario"),
        "explicit_pv": ("显性期现金流现值", "显性期现值", "explicit period present value"),
        "terminal_pv": ("终值现值", "terminal present value"),
        "equity_value": ("股权价值", "equity value"),
        "shares": ("稀释后股数", "diluted shares"),
        "per_share": ("每股价值", "fair value per share"),
    }
    value_rows: dict[str, tuple[float, float, float, float, float, float]] = {}
    value_invalid = False
    bridge_adjustments = {
        "nonoperating_securities": (1, ("加回非经营证券", "非经营证券", "nonoperating securities")),
        "nonoperating_assets": (1, ("加回其他非经营资产", "其他非经营资产", "other nonoperating assets")),
        "minority_interests": (-1, ("扣减少数股东权益", "少数股东权益", "minority interests", "noncontrolling interests")),
        "preferred_equity": (-1, ("扣减优先股权益", "优先股权益", "preferred equity")),
    }
    expected_scenarios = {
        scenario_kind(item.get("name")): item
        for item in list_or_empty((company.get("valuation") or {}).get("dcf_scenarios") if isinstance(company.get("valuation"), dict) else [])
        if isinstance(item, dict) and scenario_kind(item.get("name")) is not None
    }
    for headers, rows in tables:
        columns = {key: header_column(headers, aliases) for key, aliases in value_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        net_debt_column = header_column(headers, ("净债务调整", "净债务", "net debt"))
        adjustment_columns = {key: header_column(headers, aliases) for key, (_, aliases) in bridge_adjustments.items()}
        for row in rows:
            kind = scenario_kind(row[int(columns["scenario"])])
            parsed: dict[str, float | None] = {}
            for key in ("explicit_pv", "terminal_pv", "equity_value"):
                index = int(columns[key])
                parsed[key] = parse_localized_display_number(row[index], "money", headers[index])
            shares_index = int(columns["shares"])
            per_share_index = int(columns["per_share"])
            shares = parse_localized_display_number(row[shares_index], "shares", headers[shares_index])
            per_share = parse_localized_display_number(row[per_share_index], "per_share", headers[per_share_index])
            net_debt = 0.0
            if net_debt_column is not None:
                parsed_net_debt = parse_localized_display_number(row[int(net_debt_column)], "money", headers[int(net_debt_column)])
                if parsed_net_debt is None:
                    value_invalid = True
                else:
                    net_debt = float(parsed_net_debt)
            values = (parsed["explicit_pv"], parsed["terminal_pv"], net_debt, parsed["equity_value"], shares, per_share)
            if kind is None or kind in value_rows or any(value is None for value in values):
                value_invalid = True
                continue
            numeric_values = tuple(float(value) for value in values)
            value_rows[kind] = numeric_values
            explicit_pv, terminal_pv, net_debt, equity_value, shares, per_share = numeric_values
            adjustments: dict[str, float] = {}
            for key, column in adjustment_columns.items():
                if column is None:
                    continue
                amount = parse_localized_display_number(row[column], "money", headers[column])
                if amount is None or amount < 0:
                    value_invalid = True
                else:
                    adjustments[key] = float(amount)
            expected_value = explicit_pv + terminal_pv - net_debt + sum(bridge_adjustments[key][0] * amount for key, amount in adjustments.items())
            if (
                shares <= 0
                or not report_number_matches(equity_value, expected_value)
                or not report_number_matches(per_share, equity_value / shares)
                or not report_number_matches(per_share, expected_scenarios.get(kind, {}).get("fair_value_per_share"))
            ):
                value_invalid = True
            expected = ledger_equity.get(kind)
            if isinstance(expected, dict):
                inputs = expected.get("inputs") if isinstance(expected.get("inputs"), dict) else {}
                adjustment_input_keys = set(inputs) & set(bridge_adjustments)
                allowed_inputs = {"explicit_period_present_value", "terminal_present_value", "net_debt"} | set(bridge_adjustments)
                if (
                    set(inputs) - allowed_inputs
                    or adjustment_input_keys != set(adjustments)
                    or any(not numeric(inputs[key]) or inputs[key] < 0 or not report_number_matches(adjustments[key], inputs[key]) for key in adjustment_input_keys)
                    or ("net_debt" in inputs and net_debt_column is None)
                ):
                    value_invalid = True
                try:
                    formula_value = evaluate_custom_formula(expected.get("formula"), inputs)
                except FormulaEvaluationError:
                    value_invalid = True
                else:
                    if not report_number_matches(expected_value, formula_value):
                        value_invalid = True
                if (
                    not report_number_matches(explicit_pv, inputs.get("explicit_period_present_value"))
                    or not report_number_matches(terminal_pv, inputs.get("terminal_present_value"))
                    or ("net_debt" in inputs and not report_number_matches(net_debt, inputs.get("net_debt")))
                    or not report_number_matches(equity_value, expected.get("result"))
                    or not report_number_matches(shares, expected.get("diluted_shares"))
                    or not report_number_matches(per_share, expected.get("per_share"))
                ):
                    value_invalid = True
            elif adjustments:
                # An extra report column never creates an unbound valuation asset.
                value_invalid = True
        break
    if value_invalid or set(value_rows) != {"bear", "base", "bull"} or (ledger_equity and set(ledger_equity) != {"bear", "base", "bull"}):
        add(
            findings,
            "error",
            "report-valuation-value-bridge",
            "research-report.md#valuation",
            "valuation section needs a three-scenario bridge from explicit PV and terminal PV through net debt and separately displayed, ledger-bound controlled nonoperating asset/minority/preferred adjustments to equity and per-share value",
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
    forecast_years = (
        start_record.get("forecast_years")
        if isinstance(start_record, dict)
        and isinstance(start_record.get("forecast_years"), int)
        and not isinstance(start_record.get("forecast_years"), bool)
        else None
    )
    vague_stage_lines = sorted(
        {
            clean_markdown_text(line)
            for line in body.splitlines()
            if VAGUE_VALUATION_STAGE_RE.search(line) and not FORECAST_YEAR_RANGE_RE.search(line)
        }
    )
    if vague_stage_lines:
        add(
            findings,
            "error",
            "report-valuation-vague-stage",
            "research-report.md#valuation",
            "valuation assumptions cannot use vague stage labels without an exact start-to-end forecast-year range; "
            f"found {vague_stage_lines[:6]!r}",
        )
    input_headers = {
        "basis": ("现金流口径", "cash flow basis"),
        "period": ("基准期间", "基准期", "base period"),
        "total": ("估值基准日现金总额", "基准日现金总额", "初期现金流总额", "起始现金流总额", "starting cash flow"),
        "shares": ("稀释后股数", "diluted shares"),
        "per_share": ("基准日每股现金", "估值基准日每股现金", "初期每股现金流", "起始每股现金流", "starting cash flow per share"),
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
                forecast_years = int(float(years))
                break
        break
    if not input_valid:
        add(findings, "error", "report-valuation-inputs", "research-report.md#valuation", "valuation section needs one reconciled DCF input table with cash-flow basis, base period, starting total/per-share cash flow, diluted shares and forecast years")

    scenario_headers = {
        "scenario": ("情景", "场景", "scenario"),
        "growth": ("现金流增长", "fcf增长", "fcfe增长", "可分配现金增长", "收入增长", "营收增长", "cash flow growth", "revenue growth"),
        "discount": ("折现率", "discount rate"),
        "terminal": ("永续增长", "终值增长", "terminal growth"),
        "terminal_share": ("终值占比", "terminal value share"),
        "value": ("每股价值", "公允价值", "fair value"),
    }
    scenario_index: int | None = None
    scenario_valid = False
    stage_years_valid = False
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
        covered_by_scenario: dict[str, set[int]] = {}
        for row in rows:
            kind = scenario_kind(row[int(columns["scenario"])])
            expected = expected_scenarios.get(kind)
            values = {
                "revenue_growth": parse_report_number(row[int(columns["growth"])]),
                "discount_rate": parse_report_number(row[int(columns["discount"])]),
                "terminal_growth": parse_report_number(row[int(columns["terminal"])]),
                "terminal_value_share": parse_report_number(row[int(columns["terminal_share"])]),
                "fair_value_per_share": parse_report_number(row[int(columns["value"])]),
            }
            terminal_share = values["terminal_value_share"]
            if kind is None or kind in kinds or any(value is None for value in values.values()) or not 0 <= float(terminal_share) <= 1:
                invalid += 1
                continue
            kinds.add(kind)
            covered_by_scenario[kind] = forecast_years_from_text(" ".join(headers + row))
            if isinstance(expected, dict) and any(not report_number_matches(actual, expected.get(key)) for key, actual in values.items()):
                invalid += 1
        scenario_valid = kinds == {"bear", "base", "bull"} and invalid == 0
        if isinstance(forecast_years, int) and forecast_years > 0:
            expected_forecast_years = set(range(1, forecast_years + 1))
            stage_years_valid = (
                set(covered_by_scenario) == {"bear", "base", "bull"}
                and all(years == expected_forecast_years for years in covered_by_scenario.values())
            )
        break
    if scenario_index is None or not scenario_valid or not re.search(r"\bdcf\b|现金流折现", body, re.I):
        add(findings, "error", "report-valuation-scenarios", "research-report.md#valuation", "valuation section needs a three-scenario cash-flow DCF table with growth, discount rate, terminal growth, terminal-value share and values reconciled to company.valuation")
    if not stage_years_valid:
        add(
            findings,
            "error",
            "report-valuation-stage-years",
            "research-report.md#valuation",
            "each DCF scenario must label assumptions with exact forecast-year ranges covering every year in the explicit forecast",
        )

    validate_report_valuation_detail(company, body, tables, forecast_years, calculations, findings)

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
    report_discounts = {round(discount, 6) for discount, _, _ in actual_cells}
    report_terminals = {round(terminal, 6) for _, terminal, _ in actual_cells}
    cells_match = (
        len(actual_cells) == 9
        and len(unique_pairs) == 9
        and len(report_discounts) == 3
        and len(report_terminals) == 3
        and unique_pairs == {(discount, terminal) for discount in report_discounts for terminal in report_terminals}
    )
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
        add(findings, "error", "report-valuation-sensitivity", "research-report.md#valuation", "valuation section needs a distinct, reconciled 3×3 DCF sensitivity table with exactly nine cells")

    reverse_headers = {
        "dimension": ("假设", "维度", "assumption", "dimension"),
        "implied": ("隐含值", "隐含假设", "implied value", "implied assumption"),
        "comparison": ("历史比较", "现实比较", "comparison"),
        "threshold": ("推翻阈值", "临界条件", "threshold", "breaker"),
    }
    reverse = valuation.get("reverse_dcf") if isinstance(valuation.get("reverse_dcf"), dict) else {}
    category_tokens = {
        "profitability": ("margin", "roe", "roa", "roic", "rotce", "profit", "利润率", "回报率", "回报", "净利率"),
        "growth": ("growth", "cagr", "revenue", "sales", "cash_flow", "fcf", "fcfe", "增长", "收入", "营收", "现金流"),
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


def validate_culture_report(company: dict[str, Any], body: str, findings: list[Finding]) -> None:
    tables = parse_markdown_tables(body)
    management = company.get("management") if isinstance(company.get("management"), dict) else {}
    commitments = [item for item in list_or_empty(management.get("commitment_timeline")) if isinstance(item, dict)]
    commitment_headers = {
        "date": ("日期", "date"),
        "commitment": ("承诺", "commitment"),
        "status": ("兑现状态", "状态", "status"),
        "outcome": ("结果", "实际结果", "outcome"),
        "next": ("下一次验证", "未来验证", "next validation"),
    }
    commitment_valid = False
    for headers, rows in tables:
        columns = {key: header_column(headers, aliases) for key, aliases in commitment_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        observed: set[str] = set()
        for row in rows:
            commitment = clean_markdown_text(row[int(columns["commitment"])])
            match = next(
                (item for item in commitments if normalized_text(item.get("commitment")) == normalized_text(commitment)),
                None,
            )
            if not isinstance(match, dict):
                continue
            validation = match.get("next_validation") if isinstance(match.get("next_validation"), dict) else {}
            next_text = clean_markdown_text(row[int(columns["next"])])
            if (
                normalized_text(row[int(columns["date"])]) == normalized_text(match.get("date"))
                and normalized_text(row[int(columns["status"])]) == normalized_text(match.get("status"))
                and nullable_report_text_matches(row[int(columns["outcome"])], match.get("outcome"))
                and all(normalized_text(validation.get(key)) in normalized_text(next_text) for key in ("method", "condition", "timeframe"))
            ):
                observed.add(normalized_text(commitment))
        commitment_valid = len(rows) == len(commitments) == len(observed) and bool(commitments)
        break
    if not commitment_valid:
        add(findings, "error", "report-culture-commitments", "research-report.md#culture-management", "culture section must reconcile every promise, status, outcome and next validation")

    allocation = [item for item in list_or_empty(company.get("capital_allocation")) if isinstance(item, dict)]
    allocation_headers = {
        "period": ("期间", "period"),
        "category": ("类别", "项目", "category"),
        "lane": ("车道", "资本去向", "lane"),
        "status": ("结果状态", "status"),
        "result": ("结果", "result"),
        "assessment": ("评价", "assessment"),
    }
    allocation_valid = False
    for headers, rows in tables:
        columns = {key: header_column(headers, aliases) for key, aliases in allocation_headers.items()}
        if not all(index is not None for index in columns.values()) or len(set(columns.values())) != len(columns):
            continue
        observed: set[tuple[str, str]] = set()
        for row in rows:
            period = clean_markdown_text(row[int(columns["period"])])
            category = clean_markdown_text(row[int(columns["category"])])
            match = next(
                (
                    item
                    for item in allocation
                    if normalized_text(item.get("period")) == normalized_text(period)
                    and normalized_text(item.get("category")) == normalized_text(category)
                ),
                None,
            )
            if not isinstance(match, dict):
                continue
            if all(
                normalized_text(row[int(columns[column])]) == normalized_text(match.get(field))
                for column, field in (("lane", "lane"), ("status", "result_status"), ("result", "result"), ("assessment", "assessment"))
            ):
                observed.add((normalized_text(period), normalized_text(category)))
        allocation_valid = len(rows) == len(allocation) == len(observed) and bool(allocation)
        break
    if not allocation_valid:
        add(findings, "error", "report-capital-allocation-results", "research-report.md#culture-management", "capital-allocation table must reconcile lane, result status, result and assessment")

    missing_stops = [
        item
        for item in list_or_empty(management.get("stop_doing_list"))
        if substantive_text(item, 6) and normalized_text(item) not in normalized_text(body)
    ]
    if missing_stops:
        add(findings, "error", "report-stop-doing", "research-report.md#culture-management", "culture section must include every structured stop-doing constraint")


def validate_monitoring_report(company: dict[str, Any], body: str, findings: list[Finding]) -> None:
    risks = company.get("risks") if isinstance(company.get("risks"), dict) else {}
    indicators = [item for item in list_or_empty(risks.get("monitoring_indicators")) if isinstance(item, dict)]
    required_headers = {
        "name": ("指标", "名称", "indicator", "name"),
        "current": ("当前状态", "current status"),
        "trigger": ("触发阈值", "触发条件", "trigger"),
        "why": ("为什么重要", "重要性", "why it matters"),
        "recheck": ("复查方法", "如何复查", "recheck method"),
    }
    selected = None
    for headers, rows in parse_markdown_tables(body):
        columns = {key: header_column(headers, aliases) for key, aliases in required_headers.items()}
        if all(index is not None for index in columns.values()) and len(set(columns.values())) == len(columns):
            selected = (rows, {key: int(index) for key, index in columns.items()})
            break
    if selected is None:
        add(findings, "error", "report-monitoring-matrix", "research-report.md#monitoring", "monitoring section needs indicator, status, trigger, importance and recheck-method columns")
        return
    rows, columns = selected
    observed: set[str] = set()
    for row in rows:
        name = clean_markdown_text(row[columns["name"]])
        match = next((item for item in indicators if normalized_text(item.get("name")) == normalized_text(name)), None)
        if not isinstance(match, dict):
            continue
        if all(
            normalized_text(row[columns[column]]) == normalized_text(match.get(field))
            for column, field in (("current", "current_status"), ("trigger", "trigger"), ("why", "why_it_matters"), ("recheck", "recheck_method"))
        ):
            observed.add(normalized_text(name))
    if len(rows) != len(indicators) or len(observed) != len(indicators) or not 5 <= len(indicators) <= 10:
        add(findings, "error", "report-monitoring-mapping", "research-report.md#monitoring", "monitoring rows must uniquely reconcile all structured indicators")


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
        validate_report_reader_contract(report, findings)
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
        if "durability" in bodies:
            validate_durability_report(company, bodies["durability"], findings)
        if "culture-management" in bodies:
            validate_culture_report(company, bodies["culture-management"], findings)
        if "pre-mortem" in bodies:
            validate_pre_mortem_report(company, bodies["pre-mortem"], findings)
        if "monitoring" in bodies:
            validate_monitoring_report(company, bodies["monitoring"], findings)
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
        or lock.get("lock_version") != "3.0"
    ):
        add(
            findings,
            "error",
            "trusted-spec-lock-shape",
            str(path),
            "bundled lock must use lock_version 3.0 and contain only lock_version, research_protocol, execution_integrity, and company_schema",
        )
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

    execution = lock.get("execution_integrity")
    artifacts = execution.get("artifacts") if isinstance(execution, dict) else None
    source_binding = execution.get("source_binding") if isinstance(execution, dict) else None
    execution_valid = (
        isinstance(execution, dict)
        and set(execution) == EXECUTION_INTEGRITY_KEYS
        and execution.get("profile") == INTEGRITY_PROFILE
        and re.fullmatch(r"[0-9a-f]{64}", str(execution.get("normative_digest_sha256", ""))) is not None
        and re.fullmatch(r"[0-9a-f]{64}", str(execution.get("toolchain_digest_sha256", ""))) is not None
        and re.fullmatch(r"[0-9a-f]{64}", str(execution.get("bundle_digest_sha256", ""))) is not None
        and isinstance(artifacts, list)
        and isinstance(source_binding, dict)
        and set(source_binding) == SOURCE_BINDING_KEYS
        and source_binding.get("repository") == EXPECTED_PROTOCOL_REPOSITORY
        and source_binding.get("ref") == "main"
        and source_binding.get("payload_commit") is None
        and source_binding.get("verification_status") == "unverified"
    )
    if not execution_valid:
        add(
            findings,
            "error",
            "trusted-execution-integrity-shape",
            str(path),
            "execution_integrity must bind the complete local release with profile execution-bound-v1 and an explicit unverified source binding",
        )
    else:
        expected_artifacts = expected_execution_artifacts()
        seen_artifacts: list[str] = []
        valid_entries: list[dict[str, Any]] = []
        for index, entry in enumerate(artifacts):
            item_path = f"{path}.execution_integrity.artifacts[{index}]"
            if not isinstance(entry, dict) or set(entry) != EXECUTION_ARTIFACT_KEYS:
                add(findings, "error", "trusted-execution-artifact-shape", item_path, "artifact entries require only path, role, sha256, and size_bytes")
                continue
            relative = entry.get("path")
            role = entry.get("role")
            digest = entry.get("sha256")
            size = entry.get("size_bytes")
            if (
                not isinstance(relative, str)
                or relative not in expected_artifacts
                or role != expected_artifacts.get(relative)
                or re.fullmatch(r"[0-9a-f]{64}", str(digest or "")) is None
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
            ):
                add(findings, "error", "trusted-execution-artifact-shape", item_path, "artifact inventory contains an unsafe path, role, hash, or size")
                continue
            seen_artifacts.append(relative)
            valid_entries.append(entry)
            local = SKILL_ROOT / relative
            if local.is_symlink() or not local.is_file():
                add(findings, "error", "trusted-execution-artifact-file", relative, "integrity artifact must be a non-symlink regular file")
            elif file_sha256(local) != digest or local.stat().st_size != size:
                add(findings, "error", "trusted-execution-artifact-mismatch", relative, "integrity artifact differs from the bundled execution lock")
        expected_paths_sorted = sorted(expected_artifacts)
        if seen_artifacts != expected_paths_sorted:
            add(findings, "error", "trusted-execution-artifact-set", str(path), f"execution artifacts must be unique and sorted as {expected_paths_sorted!r}")
        if len(valid_entries) == len(artifacts):
            normative = [item for item in valid_entries if item["role"] == "normative"]
            toolchain = [item for item in valid_entries if item["role"] == "toolchain"]
            expected_digests = {
                "normative_digest_sha256": canonical_inventory_digest(normative),
                "toolchain_digest_sha256": canonical_inventory_digest(toolchain),
                "bundle_digest_sha256": canonical_inventory_digest(valid_entries),
            }
            for key, expected_digest in expected_digests.items():
                if execution.get(key) != expected_digest:
                    add(findings, "error", f"trusted-execution-{key.replace('_sha256', '').replace('_', '-')}", str(path), f"{key} does not match the path-sorted artifact inventory")

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
        try:
            bundled_schema = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            add(findings, "error", "trusted-company-schema-json", BUNDLED_SCHEMA_PATH, "bundled Schema must be valid UTF-8 JSON")
        else:
            active_version = extract_schema_version(bundled_schema)
            if active_version is None or active_version != company_schema["schema_version"]:
                add(
                    findings,
                    "error",
                    "trusted-company-schema-version",
                    BUNDLED_SCHEMA_PATH,
                    "bundled Schema active/default version must match the trusted company_schema lock",
                )

    if any(item.severity == "error" and item.code.startswith("trusted-") for item in findings):
        return None
    return lock


def validate_manifest(
    root: Path,
    schema_path: Path,
    company: dict[str, Any],
    mode: str,
    company_slug: str,
    findings: list[Finding],
) -> None:
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
            add(findings, "error", "manifest-research-protocol", "research-manifest.json.research_protocol", "research_protocol must exactly match the bundled compatibility protocol lock")
        integrity_profile = manifest.get("integrity_profile")
        execution_integrity = manifest.get("execution_integrity")
        if integrity_profile is None and execution_integrity is None and mode == "audit":
            add(
                findings,
                "warning",
                "legacy-v2-execution-audit-only",
                "research-manifest.json",
                "legacy v2 manifest lacks execution integrity and may only be audited; rebuild a new frozen baseline before incremental or archive work",
            )
        else:
            if integrity_profile != INTEGRITY_PROFILE:
                add(findings, "error", "manifest-integrity-profile", "research-manifest.json.integrity_profile", f"must be {INTEGRITY_PROFILE!r}")
            if execution_integrity != trusted["execution_integrity"]:
                add(findings, "error", "manifest-execution-integrity", "research-manifest.json.execution_integrity", "must exactly match the bundled complete execution lock")
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    research = manifest.get("research")
    if not isinstance(research, dict):
        add(findings, "error", "manifest-research", "research-manifest.json", "research identity block is missing")
    else:
        for key in ("company_name_cn", "company_name_en", "ticker", "exchange", "report_currency", "data_as_of", "valuation_date", "source_version"):
            if research.get(key) != meta.get(key):
                add(findings, "error", "manifest-research-mismatch", f"research-manifest.json.research.{key}", "does not match company.json")
        if manifest_version == "2.0" and research.get("company_slug") != company_slug:
            add(
                findings,
                "error",
                "manifest-company-slug",
                "research-manifest.json.research.company_slug",
                "must exactly match the company slug used for validation and delivery",
            )
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or validation.get("mode") != "full" or validation.get("errors") != 0:
        add(findings, "error", "manifest-validation", "research-manifest.json.validation", "frozen package must record full validation with zero errors")
    else:
        warning_count = validation.get("warnings")
        if not isinstance(warning_count, int) or isinstance(warning_count, bool) or warning_count < 0:
            add(findings, "error", "manifest-validation", "research-manifest.json.validation.warnings", "must be a non-negative integer")
        elif warning_count > 0 and manifest.get("warning_acknowledged") is not True:
            add(
                findings,
                "error",
                "manifest-warning-acknowledgement",
                "research-manifest.json.warning_acknowledged",
                "must be true when frozen validation records warnings",
            )
    if isinstance(validation, dict) and validation.get("mode") == "full" and validation.get("errors") == 0 and manifest.get("integrity_profile") == INTEGRITY_PROFILE and trusted is not None:
        expected_validation_integrity = {
            "validator": VALIDATOR_VERSION,
            "company_slug": company_slug,
            "integrity_profile": INTEGRITY_PROFILE,
            "validator_sha256": file_sha256(Path(__file__).resolve()),
            "toolchain_digest_sha256": trusted["execution_integrity"]["toolchain_digest_sha256"],
            "protocol_fingerprint": protocol_fingerprint(trusted),
        }
        for key, expected_value in expected_validation_integrity.items():
            if validation.get(key) != expected_value:
                add(findings, "error", "manifest-validation-integrity", f"research-manifest.json.validation.{key}", "does not match the current locked validator execution")
    try:
        validation_report = load_json(root / "validation-report.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        add(findings, "error", "validation-report-load", "validation-report.json", str(exc))
    else:
        if not isinstance(validation_report, dict) or validation_report.get("mode") != "full" or validation_report.get("errors") != 0:
            add(findings, "error", "validation-report-status", "validation-report.json", "must record full validation with zero errors")
        elif isinstance(validation, dict):
            comparison_keys = ["validator", "mode", "errors", "warnings"]
            if manifest_version == "2.0":
                comparison_keys.append("company_slug")
            if manifest.get("integrity_profile") == INTEGRITY_PROFILE:
                comparison_keys.extend(("integrity_profile", "validator_sha256", "toolchain_digest_sha256", "protocol_fingerprint"))
            for key in comparison_keys:
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


def validate_research_package(root: Path, schema_path: Path, mode: str, company_slug: str) -> list[Finding]:
    findings: list[Finding] = []
    if COMPANY_SLUG_PATTERN.fullmatch(company_slug) is None:
        add(findings, "error", "company-slug", "company_slug", "must contain only lowercase letters, digits, and single hyphens")
    allowed_entries = set(FROZEN_HASH_FILES) | {"research-manifest.json", "schema-gap-report.md"}
    for candidate in root.iterdir():
        if candidate.name not in allowed_entries:
            visual_like = (
                candidate.suffix.lower() in VISUAL_ASSET_EXTENSIONS
                or candidate.name.lower() in {"assets", "images", "visuals"}
                or "logo" in candidate.name.lower()
            )
            add(
                findings,
                "error",
                "visual-asset-in-package" if visual_like else "unexpected-package-entry",
                candidate.name,
                "the research package accepts only its exact managed files; Logo and every other asset must stay outside",
            )
        elif candidate.is_symlink() or not candidate.is_file():
            add(findings, "error", "invalid-package-entry", candidate.name, "managed package entries must be regular files")
    for name in REQUIRED_FILES:
        path = root / name
        if path.is_symlink():
            add(findings, "error", "symlink-input", name, "research inputs must be regular files")
        elif not path.is_file():
            add(findings, "error", "missing-file", name, "required research package file is missing")
    if findings:
        return findings
    markdown_image_pattern = re.compile(r"!\s*\[", re.I)
    embedded_data_pattern = re.compile(
        r"data(?:\s*:\s*|\\+u0*03a)(?:image|video|audio)/",
        re.I,
    )
    decoded_data_pattern = re.compile(r"data\s*:\s*(?:image|video|audio)/", re.I)
    raw_html_tag_pattern = re.compile(
        r"<\s*/?\s*[A-Za-z][A-Za-z0-9-]*(?=\s|/?>)",
        re.I,
    )
    for candidate in root.iterdir():
        if candidate.suffix.lower() not in {".json", ".md"} or not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            add(findings, "error", "text-encoding", candidate.name, "managed text and JSON files must be UTF-8")
            continue
        markdown_without_br = re.sub(r"<\s*br\s*/?\s*>", "", text, flags=re.I)
        embeds_media = embedded_data_pattern.search(text) is not None
        embeds_media = embeds_media or markdown_image_pattern.search(text) is not None
        embeds_media = embeds_media or raw_html_tag_pattern.search(markdown_without_br) is not None
        if candidate.suffix.lower() == ".json":
            try:
                decoded_json = json.loads(text)
            except json.JSONDecodeError:
                decoded_json = None
            pending: list[Any] = [decoded_json]
            while pending and not embeds_media:
                value = pending.pop()
                if isinstance(value, str):
                    decoded_without_br = re.sub(r"<\s*br\s*/?\s*>", "", value, flags=re.I)
                    embeds_media = (
                        decoded_data_pattern.search(value) is not None
                        or markdown_image_pattern.search(value) is not None
                        or raw_html_tag_pattern.search(decoded_without_br) is not None
                    )
                elif isinstance(value, dict):
                    pending.extend(value.keys())
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
        if embeds_media:
            add(
                findings,
                "error",
                "embedded-visual-asset",
                candidate.name,
                "research files cannot embed Markdown images, raw HTML other than plain br, or data-URI media; company Logo stays outside the package",
            )
    try:
        schema = load_json(schema_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [Finding("error", "schema-load", str(schema_path), str(exc))]
    if not isinstance(schema, dict):
        return [Finding("error", "schema-root", str(schema_path), "Schema must be an object")]
    if schema.get("$schema") != EXPECTED_SCHEMA_DRAFT or schema.get("$id") != EXPECTED_SCHEMA_ID:
        add(findings, "error", "schema-identity", str(schema_path), "must be the Doujiao Draft 2020-12 company Schema")
    findings.extend(validate_schema_keywords(schema))
    trusted = load_trusted_spec_lock(findings)
    if any(item.severity == "error" for item in findings):
        return findings
    if trusted is not None and mode != "audit":
        trusted_schema = trusted["company_schema"]
        if trusted_schema["sha256"] not in schema_sha256_candidates(schema_path):
            add(
                findings,
                "error",
                "schema-lock-sha256",
                str(schema_path),
                "supplied Schema bytes do not match the current trusted company_schema lock",
            )
        if trusted_schema["blob_sha1"] not in git_blob_sha1_candidates(schema_path):
            add(
                findings,
                "error",
                "schema-lock-blob",
                str(schema_path),
                "supplied Schema Git blob does not match the current trusted company_schema lock",
            )
        if extract_schema_version(schema) != trusted_schema["schema_version"]:
            add(
                findings,
                "error",
                "schema-lock-version",
                str(schema_path),
                "supplied Schema active/default version does not match the current trusted company_schema lock",
            )
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
    if trusted is not None:
        process_issues = validate_research_process(
            evidence=evidence,
            company=company,
            calculations=calculations,
            source_records=source_records,
            mode=mode,
            expected_fingerprint=protocol_fingerprint(trusted),
        )
        for issue in process_issues:
            add(findings, issue.severity, issue.code, issue.path, issue.message)
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
    validate_company_logo(company, completeness, company_slug, findings)
    validate_classification_and_industry_metrics(company, completeness, mode, findings, calculations)
    validate_financials(company, completeness, mode, findings)
    validate_sankey(company, findings, calculations, known)
    validate_durability(company, findings)
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
    validate_manifest(root, schema_path, company, mode, company_slug, findings)
    return findings


def report_payload(
    root: Path,
    schema_path: Path,
    mode: str,
    findings: list[Finding],
    company_slug: str,
) -> dict[str, Any]:
    integrity_findings: list[Finding] = []
    trusted = load_trusted_spec_lock(integrity_findings)
    execution = trusted.get("execution_integrity", {}) if isinstance(trusted, dict) else {}
    try:
        schema = load_json(schema_path)
    except (OSError, ValueError, json.JSONDecodeError):
        schema = {}
    return {
        "validator": VALIDATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "root": ".",
        "company_slug": company_slug,
        "schema": {
            "id": schema.get("$id") if isinstance(schema, dict) else None,
            "version": extract_schema_version(schema) if isinstance(schema, dict) else None,
            "sha256": file_sha256(schema_path) if schema_path.is_file() else None,
        },
        "mode": mode,
        "integrity_profile": execution.get("profile"),
        "validator_sha256": file_sha256(Path(__file__).resolve()),
        "toolchain_digest_sha256": execution.get("toolchain_digest_sha256"),
        "protocol_fingerprint": protocol_fingerprint(trusted) if isinstance(trusted, dict) else None,
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
    parser.add_argument("--company-slug", required=False, help="Safe company slug used by Logo paths")
    parser.add_argument("--mode", choices=("full", "incremental", "audit"), default="full")
    parser.add_argument("--output", type=Path, help="Write JSON validation report")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.root is None or args.schema is None or args.company_slug is None:
        parser.error("root, --schema, and --company-slug are required unless --self-test is used")
    root, schema_path = args.root.resolve(), args.schema.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if not schema_path.is_file():
        parser.error(f"schema does not exist: {schema_path}")
    findings = validate_research_package(root, schema_path, args.mode, args.company_slug)
    payload = report_payload(root, schema_path, args.mode, findings, args.company_slug)
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
