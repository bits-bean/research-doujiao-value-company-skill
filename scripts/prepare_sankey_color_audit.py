#!/usr/bin/env python3
"""Normalize and optionally write the company-level Sankey color audit.

The private App Economy Insights PNG is used only to verify sampled pixels. Its
path and bytes are deliberately excluded from the research package. The frozen
rendering truth is company.json.income_statement_sankey.nodes[].color; the
calculation ledger stores only the reproducible search and sampling audit.
"""

from __future__ import annotations

import argparse
import binascii
import copy
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CONTRACT_VERSION = "1.0.0"
PROVIDER = "App Economy Insights"
SITE_ORIGIN = "https://www.appeconomyinsights.com/"
DEFAULT_PALETTE_VERSION = "semantic-default-v1"
IDENTITY_KINDS = ("english_name", "chinese_name", "ticker")
QUERY_VARIANTS = ("sankey", "earnings_visuals")
QUERY_OUTCOMES = {"matched", "no_match", "blocked"}
BLOCKER_CODES = {
    "paywall",
    "login_required",
    "network_error",
    "candidate_unverifiable",
    "source_image_unavailable",
    "other_access_failure",
}
OFFICIAL_SOURCE_TYPES = {
    "annual_report",
    "quarterly_report",
    "earnings_release",
    "regulatory_filing",
    "investor_presentation",
    "official_website",
}
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
NODE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
WINDOWS_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s('\"`])(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+)"
)
POSIX_ABSOLUTE_PATH = re.compile(r"(?:^|[\s('\"`])/(?!/)[^\s]+")
RELATIVE_PRIVATE_PATH = re.compile(
    r"(?:^|[\s('\"`])(?:\.{1,2}[\\/]|private[-_]?evidence[\\/])[^\s]+",
    re.IGNORECASE,
)
FILE_URI = re.compile(r"\bfile://", re.IGNORECASE)
RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_EVIDENCE_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 100_000_000


class AuditError(ValueError):
    """Raised when the audit draft or private evidence is invalid."""


def fail(message: str) -> None:
    raise AuditError(message)


def is_object(value: Any) -> bool:
    return isinstance(value, dict)


def exact_keys(value: Any, expected: set[str], label: str) -> None:
    if not is_object(value):
        fail(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        fail(f"{label} keys must be exactly: {', '.join(sorted(expected))}")


def normalized_text(
    value: Any,
    label: str,
    maximum: int = 1000,
    *,
    minimum: int = 1,
) -> str:
    if not isinstance(value, str):
        fail(f"{label} must be a string")
    result = value.strip()
    if len(result) < minimum or len(result) > maximum:
        fail(f"{label} must contain between {minimum} and {maximum} characters")
    return result


def contains_private_local_path(value: str) -> bool:
    return bool(
        FILE_URI.search(value)
        or WINDOWS_ABSOLUTE_PATH.search(value)
        or POSIX_ABSOLUTE_PATH.search(value)
        or RELATIVE_PRIVATE_PATH.search(value)
    )


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def normalized_time(value: Any, label: str) -> str:
    if not isinstance(value, str) or RFC3339.fullmatch(value) is None:
        fail(f"{label} must be an RFC 3339 timestamp with an explicit timezone")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        fail(f"{label} must be a valid RFC 3339 timestamp")
    if parsed.tzinfo is None:
        fail(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalized_url(value: Any, label: str, *, app_economy_only: bool = False) -> str:
    if not isinstance(value, str):
        fail(f"{label} must be a URL string")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        fail(f"{label} must be a credential-free HTTPS URL")
    host = (parsed.hostname or "").lower()
    if app_economy_only and host != "appeconomyinsights.com" and not host.endswith(
        ".appeconomyinsights.com"
    ):
        fail(f"{label} must point to appeconomyinsights.com")
    return value


def normalized_color(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX_COLOR.fullmatch(value) is None:
        fail(f"{label} must be #RRGGBB")
    return value.upper()


def canonical_query(identity_value: str, query_variant: str) -> str:
    if query_variant == "sankey":
        return f'site:appeconomyinsights.com "{identity_value}" Sankey'
    return f'site:appeconomyinsights.com "{identity_value}" "earnings visuals"'


def company_identity(company: dict[str, Any]) -> dict[str, str]:
    meta = company.get("meta")
    if not isinstance(meta, dict):
        fail("company.json.meta must be an object")
    return {
        "english_name": normalized_text(meta.get("company_name_en"), "company.json.meta.company_name_en", 300),
        "chinese_name": normalized_text(meta.get("company_name_cn"), "company.json.meta.company_name_cn", 300),
        "ticker": normalized_text(meta.get("ticker"), "company.json.meta.ticker", 100),
    }


def normalize_alias_review(value: Any, company: dict[str, Any], identities: dict[str, str]) -> dict[str, Any]:
    exact_keys(value, {"completed", "review_method", "aliases"}, "search.alias_review")
    if value["completed"] is not True:
        fail("search.alias_review.completed must be true")
    if not isinstance(value["aliases"], list):
        fail("search.alias_review.aliases must be an array")
    source_by_id = {
        item.get("id"): item
        for item in company.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    canonical_values = {item.casefold() for item in identities.values()}
    aliases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value["aliases"]):
        label = f"search.alias_review.aliases[{index}]"
        exact_keys(item, {"value", "source_ids", "verification_note"}, label)
        alias = normalized_text(item["value"], f"{label}.value", 200)
        folded = alias.casefold()
        if folded in canonical_values or folded in seen:
            fail(f"{label}.value must be a unique non-canonical alias")
        seen.add(folded)
        source_ids = item["source_ids"]
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or any(not isinstance(source_id, str) for source_id in source_ids)
            or len(source_ids) != len(set(source_ids))
            or any(
                source_id not in source_by_id
                or source_by_id[source_id].get("source_type") not in OFFICIAL_SOURCE_TYPES
                for source_id in source_ids
            )
        ):
            fail(
                f"{label}.source_ids must be non-empty, unique, and resolve only to official company or regulatory sources"
            )
        aliases.append(
            {
                "value": alias,
                "source_ids": sorted(source_ids),
                "verification_note": normalized_text(
                    item["verification_note"],
                    f"{label}.verification_note",
                    1000,
                    minimum=8,
                ),
            }
        )
    aliases.sort(key=lambda item: item["value"].casefold())
    return {
        "completed": True,
        "review_method": normalized_text(
            value["review_method"],
            "search.alias_review.review_method",
            2000,
            minimum=16,
        ),
        "aliases": aliases,
    }


def sankey_nodes(company: dict[str, Any]) -> list[dict[str, Any]]:
    sankey = company.get("income_statement_sankey")
    nodes = sankey.get("nodes") if isinstance(sankey, dict) else None
    if not isinstance(nodes, list) or not nodes:
        fail("company.json must contain a non-empty income_statement_sankey.nodes array")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            fail(f"company.json income_statement_sankey.nodes[{index}] has no valid id")
        node_id = node["id"]
        if NODE_ID.fullmatch(node_id) is None or node_id in seen:
            fail(f"company.json income_statement_sankey.nodes[{index}].id is invalid or duplicated")
        seen.add(node_id)
        result.append(node)
    return result


def normalize_query(
    value: Any,
    index: int,
    identities: dict[str, str],
    aliases: list[dict[str, Any]],
) -> dict[str, Any]:
    label = f"search.queries[{index}]"
    exact_keys(
        value,
        {
            "identity_kind",
            "query_variant",
            "identity_value",
            "query",
            "searched_at",
            "outcome",
            "checked_urls",
            "blocker_code",
            "notes",
        },
        label,
    )
    identity_kind = value["identity_kind"]
    query_variant = value["query_variant"]
    if identity_kind not in (*IDENTITY_KINDS, "alias"):
        fail(f"{label}.identity_kind is invalid")
    if query_variant not in QUERY_VARIANTS:
        fail(f"{label}.query_variant is invalid")
    if identity_kind == "alias":
        alias_values = {item["value"] for item in aliases}
        identity_value = value["identity_value"]
        if identity_value not in alias_values:
            fail(f"{label}.identity_value is not a verified alias")
    else:
        identity_value = identities[identity_kind]
        if value["identity_value"] != identity_value:
            fail(f"{label}.identity_value does not match company.json")
    expected_query = canonical_query(identity_value, query_variant)
    if value["query"] != expected_query:
        fail(f"{label}.query must exactly equal the prescribed canonical query")
    outcome = value["outcome"]
    if outcome not in QUERY_OUTCOMES:
        fail(f"{label}.outcome is invalid")
    if not isinstance(value["checked_urls"], list):
        fail(f"{label}.checked_urls must be an array")
    checked_urls = [
        normalized_url(item, f"{label}.checked_urls[{url_index}]", app_economy_only=True)
        for url_index, item in enumerate(value["checked_urls"])
    ]
    if len(checked_urls) != len(set(checked_urls)):
        fail(f"{label}.checked_urls must not contain duplicates")
    blocker_code = value["blocker_code"]
    if outcome == "blocked":
        if blocker_code not in BLOCKER_CODES:
            fail(f"{label}.blocker_code is required for a blocked query")
    elif blocker_code is not None:
        fail(f"{label}.blocker_code must be null unless outcome is blocked")
    if outcome == "matched" and not checked_urls:
        fail(f"{label} with matched outcome must record a checked page URL")
    return {
        "identity_kind": identity_kind,
        "query_variant": query_variant,
        "identity_value": identity_value,
        "query": expected_query,
        "searched_at": normalized_time(value["searched_at"], f"{label}.searched_at"),
        "outcome": outcome,
        "checked_urls": sorted(checked_urls),
        "blocker_code": blocker_code,
        "notes": normalized_text(value["notes"], f"{label}.notes", 2000, minimum=8),
    }


def normalize_search(
    value: Any,
    company: dict[str, Any],
    identities: dict[str, str],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    exact_keys(value, {"site_origin", "completed_at", "alias_review", "queries"}, "search")
    if normalized_url(value["site_origin"], "search.site_origin", app_economy_only=True) != SITE_ORIGIN:
        fail(f"search.site_origin must be exactly {SITE_ORIGIN}")
    if not isinstance(value["queries"], list):
        fail("search.queries must be an array")
    alias_review = normalize_alias_review(value["alias_review"], company, identities)
    aliases = alias_review["aliases"]
    queries = [normalize_query(item, index, identities, aliases) for index, item in enumerate(value["queries"])]
    expected_keys = {
        (identity_kind, identity_value, query_variant)
        for identity_kind in IDENTITY_KINDS
        for identity_value in (identities[identity_kind],)
        for query_variant in QUERY_VARIANTS
    }
    expected_keys.update(
        ("alias", alias["value"], query_variant)
        for alias in aliases
        for query_variant in QUERY_VARIANTS
    )
    observed_keys = {
        (item["identity_kind"], item["identity_value"], item["query_variant"])
        for item in queries
    }
    if len(queries) != len(expected_keys) or observed_keys != expected_keys:
        fail("search.queries must cover all canonical identities and every verified alias with both variants exactly once")
    alias_order = {item["value"]: index for index, item in enumerate(aliases)}
    queries.sort(
        key=lambda item: (
            IDENTITY_KINDS.index(item["identity_kind"])
            if item["identity_kind"] in IDENTITY_KINDS
            else len(IDENTITY_KINDS) + alias_order[item["identity_value"]],
            QUERY_VARIANTS.index(item["query_variant"]),
        )
    )
    completed_at = normalized_time(value["completed_at"], "search.completed_at")
    completed_timestamp = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    for item in queries:
        searched_timestamp = datetime.fromisoformat(item["searched_at"].replace("Z", "+00:00"))
        if searched_timestamp > completed_timestamp:
            fail("search.completed_at cannot precede a query timestamp")
    return completed_at, alias_review, queries


def normalize_blocker(value: Any, index: int) -> dict[str, Any]:
    label = f"decision.blockers[{index}]"
    exact_keys(value, {"code", "detail", "page_url"}, label)
    if value["code"] not in BLOCKER_CODES:
        fail(f"{label}.code is invalid")
    page_url = (
        None
        if value["page_url"] is None
        else normalized_url(value["page_url"], f"{label}.page_url", app_economy_only=True)
    )
    return {
        "code": value["code"],
        "detail": normalized_text(value["detail"], f"{label}.detail", 1000, minimum=8),
        "page_url": page_url,
    }


def paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    distances = (
        (abs(prediction - left), left),
        (abs(prediction - above), above),
        (abs(prediction - upper_left), upper_left),
    )
    return min(distances, key=lambda item: item[0])[1]


def decode_png(data: bytes) -> tuple[int, int, int, bytes]:
    if not data.startswith(PNG_SIGNATURE):
        fail("private Sankey evidence must be a PNG")
    offset = len(PNG_SIGNATURE)
    width = height = color_type = bit_depth = interlace = None
    idat: list[bytes] = []
    saw_iend = False
    chunk_index = 0
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(data):
            fail("private Sankey evidence has a truncated PNG chunk")
        chunk_type = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : end])[0]
        if (binascii.crc32(chunk_type + payload) & 0xFFFFFFFF) != expected_crc:
            fail("private Sankey evidence has a PNG chunk CRC mismatch")
        name = chunk_type.decode("ascii", errors="strict")
        if name == "IHDR":
            if chunk_index != 0 or length != 13 or width is not None:
                fail("private Sankey evidence has an invalid IHDR chunk")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if compression != 0 or filtering != 0:
                fail("private Sankey evidence uses unsupported PNG compression or filtering")
        elif name == "IDAT":
            idat.append(payload)
        elif name == "IEND":
            if length != 0:
                fail("private Sankey evidence has an invalid IEND chunk")
            saw_iend = True
            offset = end
            break
        elif name == "tRNS":
            fail("private Sankey evidence must not use a tRNS chunk")
        elif name[0].isupper() and name != "PLTE":
            fail(f"private Sankey evidence uses unsupported critical PNG chunk {name}")
        offset = end
        chunk_index += 1
    if not saw_iend or offset != len(data) or width is None or not idat:
        fail("private Sankey evidence is missing required PNG chunks or has trailing bytes")
    if width <= 0 or height <= 0 or width > 32768 or height > 32768 or width * height > MAX_PIXELS:
        fail("private Sankey evidence has invalid or excessive dimensions")
    if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
        fail("private Sankey evidence must be a non-interlaced 8-bit RGB or RGBA PNG")
    channels = 4 if color_type == 6 else 3
    stride = width * channels
    try:
        inflated = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        fail(f"private Sankey evidence has invalid compressed pixels: {exc}")
    if len(inflated) != height * (stride + 1):
        fail("private Sankey evidence has an unexpected pixel payload length")
    pixels = bytearray(height * stride)
    for y in range(height):
        input_start = y * (stride + 1)
        filter_type = inflated[input_start]
        if filter_type > 4:
            fail("private Sankey evidence uses an invalid row filter")
        output_start = y * stride
        for x in range(stride):
            raw = inflated[input_start + 1 + x]
            left = pixels[output_start + x - channels] if x >= channels else 0
            above = pixels[output_start - stride + x] if y else 0
            upper_left = pixels[output_start - stride + x - channels] if y and x >= channels else 0
            if filter_type == 1:
                raw += left
            elif filter_type == 2:
                raw += above
            elif filter_type == 3:
                raw += (left + above) // 2
            elif filter_type == 4:
                raw += paeth(left, above, upper_left)
            pixels[output_start + x] = raw & 0xFF
    return width, height, channels, bytes(pixels)


def assert_sample(
    image: tuple[int, int, int, bytes],
    x: Any,
    y: Any,
    color: str,
    label: str,
) -> None:
    width, height, channels, pixels = image
    if not isinstance(x, int) or isinstance(x, bool) or not isinstance(y, int) or isinstance(y, bool):
        fail(f"{label} coordinates must be integers")
    if x < 1 or y < 1 or x >= width - 1 or y >= height - 1:
        fail(f"{label} must leave a one-pixel interior margin")
    expected = bytes.fromhex(color[1:])
    stride = width * channels
    for sample_y in range(y - 1, y + 2):
        for sample_x in range(x - 1, x + 2):
            start = sample_y * stride + sample_x * channels
            actual = pixels[start : start + channels]
            if actual[:3] != expected or (channels == 4 and actual[3] != 255):
                fail(f"{label} does not point to a 3x3 opaque pure-color node interior")


def load_private_png(
    source_image: Any,
    package_root: Path,
    evidence_root: Path,
) -> tuple[dict[str, Any], tuple[int, int, int, bytes]]:
    exact_keys(
        source_image,
        {"private_path", "original_url", "access_method", "captured_at"},
        "decision.match.source_image",
    )
    private_path = normalized_text(source_image["private_path"], "decision.match.source_image.private_path", 500)
    if Path(private_path).is_absolute() or ".." in Path(private_path).parts:
        fail("decision.match.source_image.private_path must be relative to --evidence-root")
    evidence_root = evidence_root.resolve(strict=True)
    package_root = package_root.resolve(strict=True)
    try:
        evidence_root.relative_to(package_root)
    except ValueError:
        pass
    else:
        fail("--evidence-root must stay outside the research package")
    candidate = evidence_root.joinpath(*Path(private_path).parts)
    if candidate.is_symlink() or not candidate.is_file():
        fail("private Sankey evidence must be a regular non-symlink file")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(evidence_root)
    except ValueError:
        fail("private Sankey evidence escapes --evidence-root")
    data = resolved.read_bytes()
    if not data or len(data) > MAX_EVIDENCE_BYTES:
        fail("private Sankey evidence has an invalid size")
    image = decode_png(data)
    width, height, _, _ = image
    if source_image["access_method"] != "direct-image-url":
        fail("decision.match.source_image.access_method must be direct-image-url")
    document = {
        "original_url": normalized_url(source_image["original_url"], "decision.match.source_image.original_url"),
        "access_method": "direct-image-url",
        "captured_at": normalized_time(source_image["captured_at"], "decision.match.source_image.captured_at"),
        "media_type": "image/png",
        "sha256": hashlib.sha256(data).hexdigest(),
        "width": width,
        "height": height,
        "size_bytes": len(data),
    }
    return document, image


def normalize_match(
    value: Any,
    package_root: Path,
    evidence_root: Path,
    matched_urls: set[str],
    node_ids: set[str],
) -> tuple[str, str, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    exact_keys(
        value,
        {"page_url", "opened_at", "direct_verification", "source_image", "node_samples"},
        "decision.match",
    )
    page_url = normalized_url(value["page_url"], "decision.match.page_url", app_economy_only=True)
    if page_url not in matched_urls:
        fail("decision.match.page_url must appear in a matched query checked_urls")
    direct = value["direct_verification"]
    exact_keys(
        direct,
        {"opened_actual_diagram", "company_identity_matches", "diagram_kind", "complete_diagram_visible"},
        "decision.match.direct_verification",
    )
    expected_direct = {
        "opened_actual_diagram": True,
        "company_identity_matches": True,
        "diagram_kind": "company-income-statement-sankey",
        "complete_diagram_visible": True,
    }
    if direct != expected_direct:
        fail("matched mode requires direct verification of a complete company income-statement Sankey")
    source_image, image = load_private_png(value["source_image"], package_root, evidence_root)
    if not isinstance(value["node_samples"], list) or not value["node_samples"]:
        fail("decision.match.node_samples must be a non-empty array")
    samples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, sample in enumerate(value["node_samples"]):
        label = f"decision.match.node_samples[{index}]"
        exact_keys(sample, {"node_id", "source_label", "mapping_note", "color", "sample_x", "sample_y"}, label)
        node_id = sample["node_id"]
        if not isinstance(node_id, str) or NODE_ID.fullmatch(node_id) is None or node_id in seen:
            fail(f"{label}.node_id is invalid or duplicated")
        seen.add(node_id)
        color = normalized_color(sample["color"], f"{label}.color")
        assert_sample(image, sample["sample_x"], sample["sample_y"], color, label)
        samples.append(
            {
                "node_id": node_id,
                "source_label": normalized_text(sample["source_label"], f"{label}.source_label", 256),
                "mapping_note": normalized_text(sample["mapping_note"], f"{label}.mapping_note", 1000),
                "color": color,
                "sample_x": sample["sample_x"],
                "sample_y": sample["sample_y"],
            }
        )
    if seen != node_ids:
        fail(
            "matched node_samples must cover every company Sankey node exactly; "
            f"missing={sorted(node_ids - seen)}, extra={sorted(seen - node_ids)}"
        )
    samples.sort(key=lambda item: item["node_id"])
    return (
        page_url,
        normalized_time(value["opened_at"], "decision.match.opened_at"),
        expected_direct,
        source_image,
        samples,
    )


def prepare_audit(
    draft: dict[str, Any],
    company: dict[str, Any],
    package_root: Path,
    evidence_root: Path | None,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    exact_keys(draft, {"contract_version", "search", "decision"}, "draft")
    if draft["contract_version"] != CONTRACT_VERSION:
        fail(f"contract_version must be {CONTRACT_VERSION}")
    identities = company_identity(company)
    nodes = sankey_nodes(company)
    node_ids = {node["id"] for node in nodes}
    completed_at, alias_review, queries = normalize_search(draft["search"], company, identities)
    decision = draft["decision"]
    exact_keys(decision, {"mode", "match", "blockers"}, "decision")
    mode = decision["mode"]
    if mode not in {"matched", "not_found", "blocked"}:
        fail("decision.mode must be matched, not_found, or blocked")
    if not isinstance(decision["blockers"], list):
        fail("decision.blockers must be an array")
    blockers = [normalize_blocker(item, index) for index, item in enumerate(decision["blockers"])]
    blockers.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    matched_urls = {
        url for item in queries if item["outcome"] == "matched" for url in item["checked_urls"]
    }
    blocked_urls = {
        url for item in queries if item["outcome"] == "blocked" for url in item["checked_urls"]
    }
    for blocker in blockers:
        if blocker["page_url"] is not None and blocker["page_url"] not in blocked_urls:
            fail("blocked page_url must appear in an outcome=blocked query checked_urls")

    source_page_url = None
    opened_at = None
    direct_verification = None
    source_image = None
    samples: list[dict[str, Any]] = []
    default_palette_version = None
    proposed_colors: dict[str, str | None]
    outcomes = {item["outcome"] for item in queries}
    if mode == "matched":
        if not matched_urls or blockers or decision["match"] is None:
            fail("matched mode requires a directly verified match and no unresolved company-level blocker")
        if evidence_root is None:
            fail("--evidence-root is required for matched mode")
        (
            source_page_url,
            opened_at,
            direct_verification,
            source_image,
            samples,
        ) = normalize_match(
            decision["match"], package_root, evidence_root, matched_urls, node_ids
        )
        completed_timestamp = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        for timestamp, label in (
            (opened_at, "opened_at"),
            (source_image["captured_at"], "source_image.captured_at"),
        ):
            if datetime.fromisoformat(timestamp.replace("Z", "+00:00")) > completed_timestamp:
                fail(f"{label} cannot follow search.completed_at")
        proposed_colors = {sample["node_id"]: sample["color"] for sample in samples}
    elif mode == "not_found":
        if decision["match"] is not None or blockers or outcomes != {"no_match"}:
            fail("not_found mode requires all canonical and verified-alias queries to finish with no_match and no blocker")
        default_palette_version = DEFAULT_PALETTE_VERSION
        proposed_colors = {node_id: None for node_id in node_ids}
    else:
        if decision["match"] is not None or not blockers or "blocked" not in outcomes or "matched" in outcomes:
            fail("blocked mode requires at least one blocked query and blocker, with no match")
        proposed_colors = {node_id: None for node_id in node_ids}

    document = {
        "contract_version": CONTRACT_VERSION,
        "provider": PROVIDER,
        "site_origin": SITE_ORIGIN,
        "completed_at": completed_at,
        "alias_review": alias_review,
        "mode": mode,
        "queries": queries,
        "source_page_url": source_page_url,
        "opened_at": opened_at,
        "direct_verification": direct_verification,
        "source_image": source_image,
        "node_samples": samples,
        "default_palette_version": default_palette_version,
        "blockers": blockers,
    }
    serialized = json.dumps(document, ensure_ascii=False)
    if (
        "private_path" in serialized
        or any(contains_private_local_path(item) for item in iter_strings(document))
        or (evidence_root is not None and str(evidence_root) in serialized)
    ):
        fail("normalized color audit leaked a private evidence path")
    return document, proposed_colors


def write_json_atomic(path: Path, value: Any) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_audit(
    package_root: Path,
    company: dict[str, Any],
    calculations: dict[str, Any],
    audit: dict[str, Any],
    proposed_colors: dict[str, str | None],
) -> None:
    updated_company = copy.deepcopy(company)
    for node in sankey_nodes(updated_company):
        node["color"] = proposed_colors[node["id"]]
    updated_calculations = copy.deepcopy(calculations)
    ledger = updated_calculations.get("income_statement_sankey")
    if not isinstance(ledger, dict):
        fail("calculation-ledger.json.income_statement_sankey must be an object")
    ledger["color_audit"] = audit
    write_json_atomic(package_root / "company.json", updated_company)
    try:
        write_json_atomic(package_root / "calculation-ledger.json", updated_calculations)
    except Exception:
        write_json_atomic(package_root / "company.json", company)
        raise


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"cannot read {label}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def make_test_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend(pixels[y * width + x])
        rows.append(bytes(row))
    return PNG_SIGNATURE + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(b"".join(rows))) + png_chunk(b"IEND", b"")


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        package = root / "package"
        evidence = root / "private-evidence"
        package.mkdir()
        evidence.mkdir()
        node_specs = (
            ("revenue", "#4285F4", 3, 3),
            ("cost", "#CC0000", 11, 3),
            ("tax", "#FBBC04", 3, 11),
            ("profit", "#2CA02C", 11, 11),
        )
        pixels = [(255, 255, 255, 255)] * (16 * 16)
        for _, color, center_x, center_y in node_specs:
            rgb = tuple(bytes.fromhex(color[1:])) + (255,)
            for y in range(center_y - 1, center_y + 2):
                for x in range(center_x - 1, center_x + 2):
                    pixels[y * 16 + x] = rgb
        (evidence / "source.png").write_bytes(make_test_png(16, 16, pixels))
        company = {
            "meta": {"company_name_en": "Test Company", "company_name_cn": "测试公司", "ticker": "TEST"},
            "sources": [{"id": "SRC-OFFICIAL", "source_type": "annual_report"}],
            "income_statement_sankey": {
                "nodes": [
                    {"id": node_id, "color": None} for node_id, _, _, _ in node_specs
                ]
            },
        }
        queries = []
        for identity_kind in IDENTITY_KINDS:
            identity_value = company_identity(company)[identity_kind]
            for variant in QUERY_VARIANTS:
                queries.append(
                    {
                        "identity_kind": identity_kind,
                        "query_variant": variant,
                        "identity_value": identity_value,
                        "query": canonical_query(identity_value, variant),
                        "searched_at": "2026-09-01T10:00:00+08:00",
                        "outcome": "no_match",
                        "checked_urls": [],
                        "blocker_code": None,
                        "notes": "Completed prescribed public search; no matching diagram found.",
                    }
                )
        for variant in QUERY_VARIANTS:
            queries.append(
                {
                    "identity_kind": "alias",
                    "query_variant": variant,
                    "identity_value": "TestCo",
                    "query": canonical_query("TestCo", variant),
                    "searched_at": "2026-09-01T10:02:00+08:00",
                    "outcome": "no_match",
                    "checked_urls": [],
                    "blocker_code": None,
                    "notes": "Completed prescribed verified-alias search; no matching diagram found.",
                }
            )
        base = {
            "contract_version": CONTRACT_VERSION,
            "search": {
                "site_origin": SITE_ORIGIN,
                "completed_at": "2026-09-01T10:30:00+08:00",
                "alias_review": {
                    "completed": True,
                    "review_method": "Reviewed frozen identity fields and official sources for common names and brands.",
                    "aliases": [
                        {
                            "value": "TestCo",
                            "source_ids": ["SRC-OFFICIAL"],
                            "verification_note": "The official company profile uses this short brand name.",
                        }
                    ],
                },
                "queries": queries,
            },
            "decision": {"mode": "not_found", "match": None, "blockers": []},
        }
        not_found, colors = prepare_audit(base, company, package, None)
        if not_found["default_palette_version"] != DEFAULT_PALETTE_VERSION or any(colors.values()):
            fail("not_found self-test did not bind the default palette and empty colors")

        matched = copy.deepcopy(base)
        page_url = "https://www.appeconomyinsights.com/p/test-company"
        matched["search"]["queries"][0]["outcome"] = "blocked"
        matched["search"]["queries"][0]["blocker_code"] = "network_error"
        matched["search"]["queries"][6]["outcome"] = "matched"
        matched["search"]["queries"][6]["checked_urls"] = [page_url]
        matched["decision"] = {
            "mode": "matched",
            "blockers": [],
            "match": {
                "page_url": page_url,
                "opened_at": "2026-09-01T10:10:00+08:00",
                "direct_verification": {
                    "opened_actual_diagram": True,
                    "company_identity_matches": True,
                    "diagram_kind": "company-income-statement-sankey",
                    "complete_diagram_visible": True,
                },
                "source_image": {
                    "private_path": "source.png",
                    "original_url": "https://cdn.example.test/test-company.png",
                    "access_method": "direct-image-url",
                    "captured_at": "2026-09-01T10:12:00+08:00",
                },
                "node_samples": [
                    {
                        "node_id": node_id,
                        "source_label": node_id.title(),
                        "mapping_note": "Direct semantic node mapping from the verified diagram.",
                        "color": color,
                        "sample_x": x,
                        "sample_y": y,
                    }
                    for node_id, color, x, y in node_specs
                ],
            },
        }
        normalized, matched_colors = prepare_audit(matched, company, package, evidence)
        serialized = json.dumps(normalized, ensure_ascii=False)
        if normalized["mode"] != "matched" or matched_colors["cost"] != "#CC0000":
            fail("matched self-test lost colors")
        if "private_path" in serialized or str(evidence) in serialized:
            fail("matched self-test leaked private evidence")
        bad = copy.deepcopy(matched)
        bad["decision"]["match"]["node_samples"][0]["color"] = "#FFFFFF"
        try:
            prepare_audit(bad, company, package, evidence)
        except AuditError as exc:
            if "3x3 opaque pure-color" not in str(exc):
                raise
        else:
            fail("bad pixel self-test unexpectedly passed")

        unofficial = copy.deepcopy(base)
        unofficial_company = copy.deepcopy(company)
        unofficial_company["sources"][0]["source_type"] = "news"
        try:
            prepare_audit(unofficial, unofficial_company, package, None)
        except AuditError as exc:
            if "official company or regulatory sources" not in str(exc):
                raise
        else:
            fail("unofficial alias provenance self-test unexpectedly passed")

        leaked_path = copy.deepcopy(matched)
        leaked_path["search"]["queries"][0]["notes"] += (
            r" Private evidence remained at D:\private-evidence\app-economy-source.png."
        )
        try:
            prepare_audit(leaked_path, company, package, evidence)
        except AuditError as exc:
            if "private evidence path" not in str(exc):
                raise
        else:
            fail("private-path leakage self-test unexpectedly passed")

        blocked = copy.deepcopy(base)
        blocked["search"]["queries"][0]["outcome"] = "blocked"
        blocked["search"]["queries"][0]["blocker_code"] = "network_error"
        blocked["decision"] = {
            "mode": "blocked",
            "match": None,
            "blockers": [{"code": "network_error", "detail": "Search could not complete.", "page_url": None}],
        }
        blocked_audit, blocked_colors = prepare_audit(blocked, company, package, None)
        if blocked_audit["mode"] != "blocked" or any(blocked_colors.values()):
            fail("blocked self-test did not remain fail-closed")
    print("prepare_sankey_color_audit self-test passed")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--write", action="store_true", help="write normalized audit and node colors into the research package")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        if any((args.package, args.input, args.evidence_root, args.write)):
            parser.error("--self-test cannot be combined with package arguments")
        return args
    if args.package is None or args.input is None:
        parser.error("--package and --input are required")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        self_test()
        return 0
    if args.package.is_symlink() or not args.package.is_dir():
        fail("--package must be a regular directory")
    package_root = args.package.resolve(strict=True)
    company_path = package_root / "company.json"
    calculations_path = package_root / "calculation-ledger.json"
    if company_path.is_symlink() or calculations_path.is_symlink():
        fail("company.json and calculation-ledger.json must be regular non-symlink files")
    company = read_json(company_path, "company.json")
    calculations = read_json(calculations_path, "calculation-ledger.json")
    draft = read_json(args.input, "audit draft")
    if args.evidence_root is not None and (
        args.evidence_root.is_symlink() or not args.evidence_root.is_dir()
    ):
        fail("--evidence-root must be a regular non-symlink directory")
    evidence_root = args.evidence_root.resolve(strict=True) if args.evidence_root is not None else None
    audit, proposed_colors = prepare_audit(draft, company, package_root, evidence_root)
    result = {"color_audit": audit, "proposed_node_colors": proposed_colors, "written": bool(args.write)}
    if args.write:
        apply_audit(package_root, company, calculations, audit, proposed_colors)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if audit["mode"] == "blocked" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AuditError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
