#!/usr/bin/env python3
"""Create a fail-closed GitHub delivery plan for an accepted frozen research package."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import secrets
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from freeze_research import TRUSTED_LOCK_PATH, verify_previous_manifest
from validate_research_package import (
    file_sha256,
    load_json,
    stable_public_http_url,
    validate_research_package,
    write_json,
)


TARGET_REPOSITORY = "bits-bean/doujiao-value-system"
TARGET_BRANCH = "main"
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SCHEMA_VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
IDENTITY_FIELDS = ("company_name_cn", "company_name_en", "ticker", "exchange")
CANONICAL_IDENTITY_FIELDS = IDENTITY_FIELDS + ("schema_version",)
COMPANY_PACKAGE_STATE_KEYS = {"repository", "branch", "base_head", "root", "exists", "files"}
MANAGED_PACKAGE_FILENAMES = {
    "research-report.md",
    "company.json",
    "research-completeness.md",
    "evidence-ledger.json",
    "calculation-ledger.json",
    "validation-report.json",
    "schema-gap-report.md",
    "research-manifest.json",
}
SLUG_REGISTRY_STATE_KEYS = {
    "repository",
    "branch",
    "base_head",
    "company_slug",
    "identity",
    "slug_exists",
    "slug_identity",
    "identity_slugs",
}
CANONICAL_STATE_KEYS = {"repository", "branch", "base_head", "path", "exists", "content"}
IDENTITY_ASSET_STATE_KEYS = {"repository", "branch", "base_head", "company_slug", "assets"}
IDENTITY_ASSET_ENTRY_KEYS = {"path", "exists", "source_path", "sha256", "size_bytes"}
LEGACY_LOGO_EXTENSIONS = "png|svg"
LOGO_CROP_OPERATION = "center-square-crop-v1"
LOGO_CROP_STAGING_FILES = {"logo.png", "logo-original.png", "logo-provenance.json"}
LOGO_SEARCH_SURFACES = {
    "official-site-runtime-assets",
    "investor-relations",
    "brand-media",
    "official-product-support",
}
LOGO_PROVENANCE_KEYS = {
    "version",
    "company_slug",
    "operation",
    "source",
    "selection",
    "crop",
    "output",
}
LOGO_PROVENANCE_SOURCE_KEYS = {
    "file",
    "page_url",
    "asset_url",
    "sha256",
    "size_bytes",
    "width",
    "height",
}
LOGO_PROVENANCE_SELECTION_KEYS = {
    "square_official_candidate_found",
    "search_surfaces",
    "candidates",
}
LOGO_PROVENANCE_SEARCH_SURFACE_KEYS = {"surface", "status", "urls", "note"}
LOGO_PROVENANCE_CANDIDATE_KEYS = {
    "asset_url",
    "source_page_url",
    "format",
    "width",
    "height",
    "gate_status",
    "identity_verified",
    "is_official",
    "officiality_evidence",
    "decision",
    "reason",
}
LOGO_PROVENANCE_CROP_KEYS = {
    "left",
    "top",
    "width",
    "height",
    "resampled",
    "padded",
    "stretched",
    "redrawn",
}
LOGO_PROVENANCE_OUTPUT_KEYS = {"file", "sha256", "size_bytes", "width", "height"}
SVG_ROOT_TAG = "{http://www.w3.org/2000/svg}svg"
ANIMATED_PNG_CHUNKS = {b"acTL", b"fcTL", b"fdAT"}
CROP_UNSAFE_COPY_ALLOWED_CHUNKS = {
    b"PLTE",
    b"tRNS",
    b"cHRM",
    b"gAMA",
    b"iCCP",
    b"sBIT",
    b"sRGB",
    b"bKGD",
    b"cICP",
    b"mDCV",
    b"cLLI",
}
TRUSTED_RUNTIME_BUNDLE_VERSION = "26.812.11052"
TRUSTED_RUNTIME_ROOT = Path("/opt/codex/runtimes/codex-primary-runtime")
TRUSTED_RUNTIME_NODE = TRUSTED_RUNTIME_ROOT / "dependencies/node/bin/node"
TRUSTED_RUNTIME_NODE_MODULES = TRUSTED_RUNTIME_ROOT / "dependencies/node/node_modules"
TRUSTED_RUNTIME_NODE_SHA256 = "bc17c508ffeed0ec622934f9b7fa72f8e78da65350e63c3eceb56fa688aa5e12"
TRUSTED_DESKTOP_RUNTIME_BUNDLE_VERSION = "26.818.41509"
TRUSTED_DESKTOP_RUNTIME_ROOT = Path("/Applications/ChatGPT.app/Contents/Resources/cua_node")
TRUSTED_DESKTOP_RUNTIME_NODE = TRUSTED_DESKTOP_RUNTIME_ROOT / "bin/node"
TRUSTED_DESKTOP_RUNTIME_NODE_MODULES = TRUSTED_DESKTOP_RUNTIME_ROOT / "lib/node_modules"
TRUSTED_DESKTOP_RUNTIME_NODE_SHA256 = "94d7ccb9c512a45711fb83fa9c270b36abfb1b3dc187b07ecd3c45eb84d8ccd1"
TRUSTED_SHARP_ENTRY_SHA256 = "d69f275bc49fcd2a6188b26b35c986d4db32a1b008653fef88adb4598688232a"
TRUSTED_SHARP_PACKAGE_SHA256 = "0f3a7e7eb4f22978dfde46e6c7c6ecf3b86b43e33c3d366de88b334b4610c3ff"
TRUSTED_RUNTIME_PROFILES = (
    {
        "bundle_version": TRUSTED_RUNTIME_BUNDLE_VERSION,
        "runtime_root": TRUSTED_RUNTIME_ROOT,
        "node": TRUSTED_RUNTIME_NODE,
        "node_modules": TRUSTED_RUNTIME_NODE_MODULES,
        "node_sha256": TRUSTED_RUNTIME_NODE_SHA256,
    },
    {
        "bundle_version": TRUSTED_DESKTOP_RUNTIME_BUNDLE_VERSION,
        "runtime_root": TRUSTED_DESKTOP_RUNTIME_ROOT,
        "node": TRUSTED_DESKTOP_RUNTIME_NODE,
        "node_modules": TRUSTED_DESKTOP_RUNTIME_NODE_MODULES,
        "node_sha256": TRUSTED_DESKTOP_RUNTIME_NODE_SHA256,
    },
)
SENSITIVE_PATTERNS = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|-----BEGIN PGP PRIVATE KEY BLOCK-----"),
    ),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("authorization-header", re.compile(r"(?i)\bauthorization\s*:\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}")),
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|token|secret|password)\b\s*[=:]\s*[\"']?[A-Za-z0-9_./+\-]{16,}"
        ),
    ),
    (
        "signed-url",
        re.compile(
            r"(?i)https?://\S+[?&](?:x-amz-signature|x-amz-credential|signature|sig|token|access_token|key|sharedaccesssignature)="
        ),
    ),
)


class ArchivePlanError(ValueError):
    """Raised when a package cannot be safely planned for GitHub delivery."""


@dataclass(frozen=True)
class LogoGeometry:
    """Canvas geometry verified from the original Logo file."""

    format: str
    width: float
    height: float
    is_square: bool


@dataclass(frozen=True)
class PngRaster:
    """Validated non-interlaced PNG samples used to prove a pixel-exact crop."""

    width: int
    height: int
    bit_depth: int
    color_type: int
    channels: int
    rows: tuple[bytes, ...]
    preserved_chunks: tuple[tuple[str, bytes, bytes], ...]


def _safe_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ArchivePlanError(f"{label} must be a non-symlink regular file")
    return path.resolve()


def _same_file(left: Path, right: Path, label: str) -> bool:
    """Compare existing files by identity, failing closed on an indeterminate result."""
    try:
        return os.path.samefile(left, right)
    except OSError as exc:
        raise ArchivePlanError(f"cannot verify {label} file identity: {exc}") from exc


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ArchivePlanError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArchivePlanError(f"{label} must be a JSON object")
    return payload


def _meta(company: dict[str, Any], label: str) -> dict[str, Any]:
    meta = company.get("meta")
    if not isinstance(meta, dict):
        raise ArchivePlanError(f"{label} lacks a meta object")
    return meta


def _schema_version_tuple(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = SCHEMA_VERSION_PATTERN.fullmatch(value)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def _current_locked_schema_version() -> str:
    lock = _read_object(TRUSTED_LOCK_PATH, "trusted specification lock")
    company_schema = lock.get("company_schema")
    if not isinstance(company_schema, dict):
        raise ArchivePlanError("trusted specification lock lacks company_schema")
    version = company_schema.get("schema_version")
    if _schema_version_tuple(version) is None:
        raise ArchivePlanError("trusted specification lock has an invalid company Schema version")
    return version


def _iso_date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ArchivePlanError(f"{label} must be an ISO date") from exc


def canonical_action(
    new_company_path: Path,
    *,
    existing_company_path: Path | None,
    canonical_absent: bool,
    confirm_same_date_revision: bool,
    confirm_schema_migration: bool = False,
    locked_schema_version: str | None = None,
) -> str:
    """Return create/update/noop after identity and monotonicity checks."""
    if existing_company_path is not None and canonical_absent:
        raise ArchivePlanError("existing canonical file and canonical-absent are mutually exclusive")
    if canonical_absent:
        return "create"
    if existing_company_path is None:
        return "remote-preflight-required"

    existing_path = _safe_regular_file(existing_company_path, "existing canonical company.json")
    if new_company_path.read_bytes() == existing_path.read_bytes():
        return "noop"

    new_company = _read_object(new_company_path, "new company.json")
    existing_company = _read_object(existing_path, "existing canonical company.json")
    new_meta = _meta(new_company, "new company.json")
    existing_meta = _meta(existing_company, "existing canonical company.json")

    for field in IDENTITY_FIELDS:
        if new_meta.get(field) != existing_meta.get(field):
            raise ArchivePlanError(f"canonical company.json conflicts on {field}")

    new_schema = new_meta.get("schema_version")
    existing_schema = existing_meta.get("schema_version")
    schema_migration = new_schema != existing_schema
    if schema_migration:
        existing_version = _schema_version_tuple(existing_schema)
        new_version = _schema_version_tuple(new_schema)
        current_schema = locked_schema_version or _current_locked_schema_version()
        current_version = _schema_version_tuple(current_schema)
        supported_legacy = (
            existing_version is not None
            and (
                existing_version[0] == 1
                or existing_version in {(2, 0, 0), (2, 1, 0)}
            )
        )
        allowed = (
            supported_legacy
            and current_version is not None
            and new_version == current_version
            and existing_version < current_version
        )
        if not allowed:
            raise ArchivePlanError(
                "canonical company.json only permits a supported legacy Schema upgrade "
                "to the current locked Schema version"
            )
        if not confirm_schema_migration:
            raise ArchivePlanError("canonical Schema migration requires explicit confirmation")

    new_date = _iso_date(new_meta.get("data_as_of"), "new company.json meta.data_as_of")
    existing_date = _iso_date(existing_meta.get("data_as_of"), "existing company.json meta.data_as_of")
    new_valuation = _iso_date(new_meta.get("valuation_date"), "new company.json meta.valuation_date")
    existing_valuation = _iso_date(existing_meta.get("valuation_date"), "existing company.json meta.valuation_date")
    if new_date < existing_date:
        raise ArchivePlanError("canonical company.json would roll back data_as_of")
    if new_valuation < existing_valuation:
        raise ArchivePlanError("canonical company.json would roll back valuation_date")
    if new_date == existing_date:
        if not confirm_same_date_revision:
            raise ArchivePlanError(
                "canonical company.json has different content for the same data_as_of; "
                "explicitly confirm the accepted same-date revision"
            )
        return "update-confirmed-schema-migration" if schema_migration else "update-confirmed-revision"
    return "update-confirmed-schema-migration" if schema_migration else "update"


def scan_sensitive_material(paths: list[Path]) -> None:
    findings: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ArchivePlanError(f"cannot safely inspect publication file {path.name}: {exc}") from exc
        decoded_variants = [text]
        for _ in range(8):
            decoded = html.unescape(unquote(decoded_variants[-1]))
            if decoded == decoded_variants[-1]:
                break
            decoded_variants.append(decoded)
        for code, pattern in SENSITIVE_PATTERNS:
            if any(pattern.search(candidate) for candidate in decoded_variants):
                findings.append(f"{path.name}:{code}")
    if findings:
        raise ArchivePlanError(f"sensitive material scan failed: {', '.join(sorted(findings))}")


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _public_http_url(value: Any, label: str) -> str:
    if not stable_public_http_url(value):
        raise ArchivePlanError(
            f"{label} must use a stable public http/https URL without credentials or signed query parameters"
        )
    return str(value)


def _company_logo_asset_path(company: dict[str, Any], company_slug: str) -> str | None:
    brand = company.get("brand_identity")
    if not isinstance(brand, dict):
        raise ArchivePlanError("company.json lacks brand_identity")
    logo = brand.get("company_logo")
    if not isinstance(logo, dict):
        raise ArchivePlanError("company.json lacks brand_identity.company_logo")
    value = logo.get("asset_path")
    if value is None:
        if logo.get("source_url") is not None or logo.get("alt") is not None or logo.get("is_official") is not False:
            raise ArchivePlanError("absent company logo must use the exact null/null/null/false sentinel")
        return None
    if not _nonblank(value):
        raise ArchivePlanError("company logo asset_path must be null or a nonempty path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ArchivePlanError("company logo asset_path is unsafe")
    company_root = f"companies/{company_slug}/"
    if not value.startswith(company_root):
        raise ArchivePlanError("company logo asset_path belongs to a different company")
    canonical = {
        f"companies/{company_slug}/assets/logo.svg",
        f"companies/{company_slug}/assets/logo.png",
    }
    legacy = re.fullmatch(
        rf"companies/{re.escape(company_slug)}/logo-primary\.(?:{LEGACY_LOGO_EXTENSIONS})",
        value,
    )
    if value not in canonical and legacy is None:
        raise ArchivePlanError(
            "company logo asset_path must be canonical assets/logo.svg or assets/logo.png, or an existing logo-primary.* legacy path"
        )
    _public_http_url(logo.get("source_url"), "company_logo.source_url")
    if not _nonblank(logo.get("alt")) or logo.get("is_official") is not True:
        raise ArchivePlanError("declared company logo requires alt text and is_official true")
    return value


def _untrusted_existing_logo(company: dict[str, Any], company_slug: str) -> tuple[str | None, Any]:
    """Extract only a safe old path so an explicitly staged repair cannot be blocked by bad legacy metadata."""
    brand = company.get("brand_identity")
    logo = brand.get("company_logo") if isinstance(brand, dict) else None
    value = logo.get("asset_path") if isinstance(logo, dict) else None
    if not isinstance(value, str) or not value or "\\" in value:
        return None, logo
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        return None, logo
    canonical = {
        f"companies/{company_slug}/assets/logo.svg",
        f"companies/{company_slug}/assets/logo.png",
    }
    legacy = re.fullmatch(rf"companies/{re.escape(company_slug)}/logo-primary\.[A-Za-z0-9]+", value)
    return (value if value in canonical or legacy is not None else None), logo


def _validate_svg(path: Path) -> LogoGeometry:
    if path.stat().st_size <= 0 or path.stat().st_size > 512_000:
        raise ArchivePlanError("logo.svg must be nonempty and no larger than 512,000 bytes")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ArchivePlanError(f"logo.svg must be UTF-8 SVG: {exc}") from exc
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered or re.search(r"<\?(?!xml\s)", text, re.I):
        raise ArchivePlanError("logo.svg contains an unsafe declaration or processing instruction")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ArchivePlanError(f"logo.svg is not a well-formed SVG document: {exc}") from exc

    def local_name(name: str) -> str:
        return name.rsplit("}", 1)[-1].lower()

    def decode_reference(value: str) -> str:
        decoded = value
        for _ in range(8):
            next_value = html.unescape(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        return decoded.strip()

    def validate_css_references(value: str) -> None:
        decoded = decode_reference(value)
        without_comments = re.sub(r"/\*.*?\*/", "", decoded, flags=re.S)
        if (
            "\\" in without_comments
            or re.search(r"@\s*import\b", without_comments, re.I)
            or re.search(r"@\s*font-face\b", without_comments, re.I)
            or re.search(r"(?:font(?:-family)?|behavior|-moz-binding)\s*:", without_comments, re.I)
            or re.search(r"expression\s*\(", without_comments, re.I)
            or re.search(r"(?:var|env)\s*\(", without_comments, re.I)
            or re.search(
                r"(?:lab|lch|oklab|oklch|hwb|device-cmyk|color|color-mix|light-dark)\s*\(",
                without_comments,
                re.I,
            )
            or re.search(r"(?:image-set|image|cross-fade|src)\s*\(", without_comments, re.I)
            or re.search(r"(?:https?:|data:|(?<!:)//)", without_comments, re.I)
        ):
            raise ArchivePlanError("logo.svg contains an obfuscated or imported CSS resource")
        for match in re.finditer(r"url\s*\(\s*([^)]*?)\s*\)", without_comments, re.I):
            reference = decode_reference(match.group(1).strip().strip("\"'"))
            if reference and not reference.startswith("#"):
                raise ArchivePlanError("logo.svg contains an external or embedded resource reference")

    stylesheet_references: set[str] = set()

    def validate_stylesheet(value: str) -> None:
        """Allow only deterministic, resource-free SVG presentation rules."""
        decoded = decode_reference(value)
        without_comments = re.sub(r"/\*.*?\*/", "", decoded, flags=re.S)
        validate_css_references(without_comments)
        if "@" in without_comments:
            raise ArchivePlanError("logo.svg stylesheet at-rules are not allowed")

        safe_properties = {
            "clip-path",
            "clip-rule",
            "color",
            "fill",
            "fill-opacity",
            "fill-rule",
            "opacity",
            "shape-rendering",
            "stroke",
            "stroke-dasharray",
            "stroke-dashoffset",
            "stroke-linecap",
            "stroke-linejoin",
            "stroke-miterlimit",
            "stroke-opacity",
            "stroke-width",
            "vector-effect",
        }
        identifier = r"[-_A-Za-z][-_A-Za-z0-9]*"
        simple_selector = re.compile(
            rf"(?:\*|[A-Za-z][-_A-Za-z0-9]*|[.#]{identifier})(?:[.#]{identifier})*"
        )
        rule_pattern = re.compile(r"([^{}]+)\{([^{}]*)\}")
        cursor = 0
        rule_count = 0
        for match in rule_pattern.finditer(without_comments):
            if without_comments[cursor : match.start()].strip():
                raise ArchivePlanError("logo.svg contains a malformed or nested stylesheet rule")
            cursor = match.end()
            selectors, body = match.groups()
            selector_items = [item.strip() for item in selectors.split(",")]
            if not selector_items or any(simple_selector.fullmatch(item) is None for item in selector_items):
                raise ArchivePlanError("logo.svg contains an unsupported stylesheet selector")

            declaration_count = 0
            for declaration in body.split(";"):
                declaration = declaration.strip()
                if not declaration:
                    continue
                if ":" not in declaration:
                    raise ArchivePlanError("logo.svg contains a malformed stylesheet declaration")
                raw_name, raw_value = declaration.split(":", 1)
                name = raw_name.strip().lower()
                value_text = re.sub(r"\s*!\s*important\s*$", "", raw_value.strip(), flags=re.I)
                if name not in safe_properties or not value_text or "!" in value_text:
                    raise ArchivePlanError("logo.svg contains an unsupported stylesheet property or value")
                validate_css_references(value_text)
                for reference_match in re.finditer(r"url\s*\(\s*([^)]*?)\s*\)", value_text, re.I):
                    reference = decode_reference(reference_match.group(1).strip().strip("\"'"))
                    if len(reference) <= 1 or not reference.startswith("#"):
                        raise ArchivePlanError("logo.svg contains an external or embedded stylesheet resource")
                    stylesheet_references.add(reference[1:])
                declaration_count += 1
            if declaration_count == 0:
                raise ArchivePlanError("logo.svg contains an empty stylesheet rule")
            rule_count += 1
        if rule_count == 0 or without_comments[cursor:].strip():
            raise ArchivePlanError("logo.svg contains a malformed stylesheet")

    if root.tag != SVG_ROOT_TAG:
        raise ArchivePlanError("logo.svg root element must use the standard SVG namespace")
    banned_elements = {
        "a",
        "animate",
        "animatecolor",
        "animatemotion",
        "animatetransform",
        "audio",
        "cursor",
        "discard",
        "embed",
        "font",
        "font-face",
        "font-face-uri",
        "foreignobject",
        "glyph",
        "handler",
        "iframe",
        "image",
        "link",
        "listener",
        "filter",
        "mask",
        "missing-glyph",
        "object",
        "script",
        "set",
        "text",
        "textpath",
        "tspan",
        "video",
    }
    element_count = 0
    stack: list[tuple[ET.Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        element_count += 1
        if element_count > 10_000 or depth > 256:
            raise ArchivePlanError("logo.svg exceeds the safe element-count or nesting-depth limit")
        stack.extend((child, depth + 1) for child in element)

    ids: dict[str, ET.Element] = {}
    for element in root.iter():
        if not isinstance(element.tag, str) or not element.tag.startswith("{http://www.w3.org/2000/svg}"):
            raise ArchivePlanError("logo.svg render elements must all use the standard SVG namespace")
        element_name = local_name(element.tag)
        if element_name == "style":
            style_attributes = {local_name(name) for name in element.attrib}
            if not style_attributes.issubset({"id", "space", "type"}):
                raise ArchivePlanError("logo.svg style elements contain unsupported attributes")
            style_type = element.attrib.get("type")
            if style_type is not None and style_type.strip().lower() != "text/css":
                raise ArchivePlanError("logo.svg style elements must use text/css")
            validate_stylesheet("".join(element.itertext()))
        if element_name in banned_elements:
            raise ArchivePlanError("logo.svg contains executable or active content")
        for raw_name, raw_value in element.attrib.items():
            name = local_name(raw_name)
            if raw_name.startswith("{"):
                namespace = raw_name[1:].split("}", 1)[0]
                allowed_namespaced = (
                    namespace == "http://www.w3.org/1999/xlink" and name == "href"
                ) or (
                    namespace == "http://www.w3.org/XML/1998/namespace" and name in {"lang", "space"}
                )
                if not allowed_namespaced:
                    raise ArchivePlanError("logo.svg contains an unsupported namespaced attribute")
            if (
                raw_name.startswith("{http://www.w3.org/2001/xml-events}")
                or raw_name == "{http://www.w3.org/XML/1998/namespace}base"
                or name.startswith("on")
                or name.startswith("font")
                or name in {"requiredextensions", "requiredfeatures", "systemlanguage"}
                or "javascript:" in decode_reference(raw_value).lower()
            ):
                raise ArchivePlanError("logo.svg contains executable or active content")
            if name in {"href", "src"}:
                reference = decode_reference(raw_value)
                if reference and not reference.startswith("#"):
                    raise ArchivePlanError("logo.svg contains an external or embedded resource reference")
            if name in {"filter", "mask"} and decode_reference(raw_value).lower() != "none":
                raise ArchivePlanError("logo.svg contains an unsupported filter or mask effect")
            if name == "style" and re.search(r"(?:^|;)\s*(?:filter|mask)\s*:", raw_value, re.I):
                raise ArchivePlanError("logo.svg contains an unsupported inline filter or mask effect")
            validate_css_references(raw_value)
        element_id = element.attrib.get("id")
        if element_id is not None:
            if not element_id.strip() or element_id in ids:
                raise ArchivePlanError("logo.svg contains an empty or duplicate element id")
            ids[element_id] = element

    for element in root.iter():
        for raw_name, raw_value in element.attrib.items():
            decoded = decode_reference(raw_value)
            if local_name(raw_name) in {"href", "src"} and decoded.startswith("#"):
                if len(decoded) == 1 or decoded[1:] not in ids:
                    raise ArchivePlanError("logo.svg contains a dangling internal element reference")
            without_comments = re.sub(r"/\*.*?\*/", "", decoded, flags=re.S)
            for match in re.finditer(r"url\s*\(\s*([^)]*?)\s*\)", without_comments, re.I):
                reference = decode_reference(match.group(1).strip().strip("\"'"))
                if len(reference) <= 1 or not reference.startswith("#") or reference[1:] not in ids:
                    raise ArchivePlanError("logo.svg contains a dangling internal paint or clipping reference")
    if any(reference not in ids for reference in stylesheet_references):
        raise ArchivePlanError("logo.svg contains a dangling internal stylesheet resource reference")

    number_pattern = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
    length_pattern = re.compile(
        rf"({number_pattern.pattern})(?:px|pt|pc|mm|cm|in|em|ex|%)?",
        re.I,
    )
    canvas_length_pattern = re.compile(
        rf"({number_pattern.pattern})(px|pt|pc|mm|cm|in)?",
        re.I,
    )

    def parsed_length(value: Any) -> float | None:
        if not isinstance(value, str):
            return None
        match = length_pattern.fullmatch(value.strip())
        if match is None:
            return None
        try:
            result = float(match.group(1))
        except ValueError:
            return None
        return result if math.isfinite(result) else None

    def parsed_canvas_length(value: Any) -> float | None:
        """Resolve context-free outer SVG dimensions to CSS pixels."""
        if not isinstance(value, str):
            return None
        match = canvas_length_pattern.fullmatch(value.strip())
        if match is None:
            return None
        try:
            number = float(match.group(1))
        except ValueError:
            return None
        if not math.isfinite(number):
            return None
        unit = (match.group(2) or "px").lower()
        factors = {
            "px": 1.0,
            "pt": 96.0 / 72.0,
            "pc": 16.0,
            "mm": 96.0 / 25.4,
            "cm": 96.0 / 2.54,
            "in": 96.0,
        }
        return number * factors[unit]

    root_inline_style = re.sub(r"/\*.*?\*/", "", root.attrib.get("style", ""), flags=re.S)
    if re.search(
        r"(?:^|;)\s*(?:(?:min-|max-)?(?:width|height|inline-size|block-size)|aspect-ratio)\s*:",
        root_inline_style,
        re.I,
    ):
        raise ArchivePlanError("logo.svg root CSS sizing properties make the canvas dimensions ambiguous")
    declared_dimensions: dict[str, float] = {}
    for dimension in ("width", "height"):
        if dimension in root.attrib:
            value = parsed_canvas_length(root.attrib[dimension])
            if value is None or value <= 0:
                raise ArchivePlanError(
                    "logo.svg has a zero, negative, malformed, or context-dependent canvas dimension"
                )
            declared_dimensions[dimension] = value
    viewport: tuple[float, float, float, float] | None = None
    if "viewBox" in root.attrib:
        view_box = root.attrib["viewBox"].strip()
        values = number_pattern.findall(view_box)
        residue = number_pattern.sub("", view_box)
        if (
            len(values) != 4
            or re.fullmatch(r"[\s,]*", residue) is None
            or any(not math.isfinite(float(value)) for value in values)
            or float(values[2]) <= 0
            or float(values[3]) <= 0
        ):
            raise ArchivePlanError("logo.svg has an invalid or non-positive viewBox")
        viewport = tuple(float(value) for value in values)

    def numeric_attribute(element: ET.Element, name: str, default: float = 0.0) -> float:
        value = element.attrib.get(name)
        if value is None:
            return default
        parsed = parsed_length(value)
        return parsed if parsed is not None else default

    def style_properties(element: ET.Element) -> dict[str, str]:
        style = re.sub(r"/\*.*?\*/", "", element.attrib.get("style", ""), flags=re.S)
        properties: dict[str, str] = {}
        for declaration in style.split(";"):
            if ":" not in declaration:
                continue
            name, value = declaration.split(":", 1)
            normalized = re.sub(r"\s*!\s*important\s*$", "", value.strip(), flags=re.I)
            if "!" in normalized:
                raise ArchivePlanError("logo.svg contains a malformed inline CSS priority")
            properties[name.strip().lower()] = normalized
        return properties

    def presentation_value(element: ET.Element, properties: dict[str, str], name: str) -> str | None:
        if name in properties:
            return properties[name]
        value = element.attrib.get(name)
        return value.strip() if isinstance(value, str) else None

    def opacity_value(value: str | None, default: float) -> float:
        if value is None:
            return default
        stripped = value.strip()
        percent = stripped.endswith("%")
        parsed = parsed_length(stripped)
        if parsed is None:
            return 0.0
        return parsed / 100 if percent else parsed

    def number_list(value: str) -> list[float] | None:
        matches = list(number_pattern.finditer(value))
        cursor = 0
        numbers: list[float] = []
        for match in matches:
            if re.fullmatch(r"[\s,]*", value[cursor : match.start()]) is None:
                return None
            cursor = match.end()
            number = float(match.group(0))
            if not math.isfinite(number):
                return None
            numbers.append(number)
        if re.fullmatch(r"[\s,]*", value[cursor:]) is None:
            return None
        return numbers

    def collapsed_transform(element: ET.Element) -> bool:
        properties = style_properties(element)
        transform = presentation_value(element, properties, "transform")
        if transform is None or transform.strip().lower() == "none":
            return False
        function_pattern = re.compile(r"([A-Za-z]+)\s*\(([^()]*)\)")
        matches = list(function_pattern.finditer(transform))
        cursor = 0
        collapsed = False
        arities = {
            "matrix": {6},
            "translate": {1, 2},
            "scale": {1, 2},
            "rotate": {1, 3},
            "skewx": {1},
            "skewy": {1},
        }
        for match in matches:
            if re.fullmatch(r"[\s,]*", transform[cursor : match.start()]) is None:
                raise ArchivePlanError("logo.svg contains a malformed transform")
            cursor = match.end()
            name = match.group(1).lower()
            values = number_list(match.group(2))
            if name not in arities or values is None or len(values) not in arities[name]:
                raise ArchivePlanError("logo.svg contains an unsupported or malformed transform")
            if name == "scale":
                scale_x = values[0]
                scale_y = values[-1]
                collapsed = collapsed or math.isclose(scale_x * scale_y, 0.0, abs_tol=1e-15)
            elif name == "matrix":
                collapsed = collapsed or math.isclose(
                    values[0] * values[3] - values[1] * values[2],
                    0.0,
                    abs_tol=1e-15,
                )
        if not matches or re.fullmatch(r"[\s,]*", transform[cursor:]) is None:
            raise ArchivePlanError("logo.svg contains a malformed transform")
        return collapsed

    def hidden(element: ET.Element) -> bool:
        properties = style_properties(element)
        display = presentation_value(element, properties, "display")
        visibility = presentation_value(element, properties, "visibility")
        opacity = opacity_value(presentation_value(element, properties, "opacity"), 1.0)
        return (
            (display or "").lower() == "none"
            or (visibility or "").lower() in {"hidden", "collapse"}
            or opacity <= 0
            or collapsed_transform(element)
        )

    def href_value(element: ET.Element) -> str | None:
        for raw_name, raw_value in element.attrib.items():
            if local_name(raw_name) == "href":
                return decode_reference(raw_value)
        return None

    path_token_pattern = re.compile(rf"[AaCcHhLlMmQqSsTtVvZz]|{number_pattern.pattern}")
    path_arity = {
        "m": 2,
        "l": 2,
        "h": 1,
        "v": 1,
        "c": 6,
        "s": 4,
        "q": 4,
        "t": 2,
        "a": 7,
        "z": 0,
    }

    def meaningful_path(data: str) -> bool:
        matches = list(path_token_pattern.finditer(data))
        if not matches or matches[0].group(0).lower() != "m":
            return False
        cursor = 0
        for match in matches:
            if re.fullmatch(r"[\s,]*", data[cursor : match.start()]) is None:
                return False
            cursor = match.end()
        if re.fullmatch(r"[\s,]*", data[cursor:]) is None:
            return False
        current_command: str | None = None
        current_numbers: list[float] = []
        saw_drawing = False
        all_numbers: list[float] = []

        def finish_command() -> bool:
            nonlocal saw_drawing
            if current_command is None:
                return not current_numbers
            command = current_command.lower()
            arity = path_arity[command]
            count = len(current_numbers)
            if arity == 0:
                return count == 0
            if count < arity or count % arity:
                return False
            if command == "m":
                saw_drawing = saw_drawing or count > 2
            else:
                saw_drawing = True
            return True

        for match in matches:
            token = match.group(0)
            if len(token) == 1 and token.isalpha():
                if not finish_command():
                    return False
                current_command = token
                current_numbers = []
            else:
                if current_command is None or current_command.lower() == "z":
                    return False
                try:
                    number = float(token)
                except ValueError:
                    return False
                if not math.isfinite(number):
                    return False
                current_numbers.append(number)
                all_numbers.append(number)
        return finish_command() and saw_drawing and len(set(all_numbers)) >= 2

    def meaningful_points(value: str, minimum_pairs: int) -> bool:
        numbers = number_list(value)
        return (
            numbers is not None
            and len(numbers) >= minimum_pairs * 2
            and len(numbers) % 2 == 0
            and len(set(numbers)) >= 2
        )

    def points_have_area(value: str) -> bool:
        numbers = number_list(value)
        if numbers is None or len(numbers) < 6 or len(numbers) % 2:
            return False
        points = list(zip(numbers[::2], numbers[1::2]))
        double_area = sum(
            x1 * y2 - x2 * y1
            for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
        )
        return not math.isclose(double_area, 0.0, abs_tol=1e-12)

    def linear_path_has_area(data: str) -> bool:
        tokens = [match.group(0) for match in path_token_pattern.finditer(data)]
        groups: list[tuple[str, list[float]]] = []
        command: str | None = None
        numbers: list[float] = []
        for token in tokens:
            if len(token) == 1 and token.isalpha():
                if command is not None:
                    groups.append((command, numbers))
                command = token
                numbers = []
            else:
                numbers.append(float(token))
        if command is not None:
            groups.append((command, numbers))

        current_x = 0.0
        current_y = 0.0
        start_x = 0.0
        start_y = 0.0
        points: list[tuple[float, float]] = []

        def current_area() -> bool:
            if len(points) < 3:
                return False
            double_area = sum(
                x1 * y2 - x2 * y1
                for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
            )
            return not math.isclose(double_area, 0.0, abs_tol=1e-12)

        for raw_command, values in groups:
            lower = raw_command.lower()
            relative = raw_command.islower()
            if lower == "m":
                if current_area():
                    return True
                points = []
                for index in range(0, len(values), 2):
                    x, y = values[index : index + 2]
                    if relative:
                        x += current_x
                        y += current_y
                    current_x, current_y = x, y
                    if index == 0:
                        start_x, start_y = x, y
                    points.append((x, y))
            elif lower == "l":
                for index in range(0, len(values), 2):
                    x, y = values[index : index + 2]
                    if relative:
                        x += current_x
                        y += current_y
                    current_x, current_y = x, y
                    points.append((x, y))
            elif lower == "h":
                for value in values:
                    current_x = current_x + value if relative else value
                    points.append((current_x, current_y))
            elif lower == "v":
                for value in values:
                    current_y = current_y + value if relative else value
                    points.append((current_x, current_y))
            elif lower == "z":
                if current_area():
                    return True
                current_x, current_y = start_x, start_y
        return current_area()

    def path_has_fill_area(data: str) -> bool:
        commands = [match.group(0).lower() for match in re.finditer(r"[AaCcHhLlMmQqSsTtVvZz]", data)]
        drawing = [command for command in commands if command not in {"m", "z"}]
        if any(command in {"a", "c", "q", "s", "t"} for command in drawing):
            return True
        return linear_path_has_area(data)

    def primitive_is_meaningful(element: ET.Element) -> bool:
        name = local_name(element.tag)
        if name == "path":
            return meaningful_path(element.attrib.get("d", ""))
        if name == "rect":
            return numeric_attribute(element, "width") > 0 and numeric_attribute(element, "height") > 0
        if name == "circle":
            return numeric_attribute(element, "r") > 0
        if name == "ellipse":
            return numeric_attribute(element, "rx") > 0 and numeric_attribute(element, "ry") > 0
        if name == "line":
            return (numeric_attribute(element, "x1"), numeric_attribute(element, "y1")) != (
                numeric_attribute(element, "x2"),
                numeric_attribute(element, "y2"),
            )
        if name in {"polygon", "polyline"}:
            return meaningful_points(element.attrib.get("points", ""), 3 if name == "polygon" else 2)
        return False

    def resolved_paint(
        element: ET.Element,
        inherited: tuple[str, str, float, float, float, float, str],
    ) -> tuple[str, str, float, float, float, float, str]:
        inherited_fill, inherited_stroke, inherited_fill_opacity, inherited_stroke_opacity, inherited_width, inherited_opacity, inherited_color = inherited
        properties = style_properties(element)
        fill = presentation_value(element, properties, "fill") or inherited_fill
        stroke = presentation_value(element, properties, "stroke") or inherited_stroke
        fill_opacity = opacity_value(
            presentation_value(element, properties, "fill-opacity"),
            inherited_fill_opacity,
        )
        stroke_opacity = opacity_value(
            presentation_value(element, properties, "stroke-opacity"),
            inherited_stroke_opacity,
        )
        width_value = presentation_value(element, properties, "stroke-width")
        stroke_width = parsed_length(width_value) if width_value is not None else inherited_width
        if stroke_width is None:
            stroke_width = 0.0
        opacity = inherited_opacity * opacity_value(
            presentation_value(element, properties, "opacity"),
            1.0,
        )
        color = presentation_value(element, properties, "color") or inherited_color
        return fill, stroke, fill_opacity, stroke_opacity, stroke_width, opacity, color

    def alpha_is_visible(value: str) -> bool:
        stripped = value.strip()
        percent = stripped.endswith("%")
        if percent:
            stripped = stripped[:-1].strip()
        try:
            alpha = float(stripped)
        except ValueError:
            return False
        if not math.isfinite(alpha):
            return False
        return alpha > 0 if not percent else alpha > 0

    def paint_value_visible(value: str, seen_servers: frozenset[str] = frozenset()) -> bool:
        lowered = value.strip().lower()
        if lowered in {"none", "transparent"}:
            return False
        if re.fullmatch(r"#[0-9a-f]{4}", lowered):
            return lowered[-1] != "0"
        if re.fullmatch(r"#[0-9a-f]{8}", lowered):
            return lowered[-2:] != "00"
        functional = re.fullmatch(r"(rgba?|hsla?|color)\((.*)\)", lowered)
        if functional is not None:
            function, body = functional.groups()
            if "/" in body:
                return alpha_is_visible(body.rsplit("/", 1)[1])
            if function in {"rgba", "hsla"}:
                parts = [part.strip() for part in body.split(",")]
                return len(parts) == 4 and alpha_is_visible(parts[-1])
            return True
        server = re.search(r"url\s*\(\s*['\"]?#([^)'\"\s]+)['\"]?\s*\)", lowered, re.I)
        if server is None:
            return True
        server_id = server.group(1)
        if server_id in seen_servers or len(seen_servers) >= 256:
            return False
        target = ids.get(server_id)
        if target is None:
            return False
        target_name = local_name(target.tag)
        if target_name in {"lineargradient", "radialgradient"}:
            stops = [item for item in target if local_name(item.tag) == "stop"]
            if not stops:
                inherited = href_value(target)
                inherited_id = inherited[1:] if inherited and inherited.startswith("#") else ""
                if inherited_id:
                    return paint_value_visible(f"url(#{inherited_id})", seen_servers | {server_id})
                return False
            for stop in stops:
                properties = style_properties(stop)
                color = presentation_value(stop, properties, "stop-color") or "black"
                opacity = opacity_value(presentation_value(stop, properties, "stop-opacity"), 1.0)
                if opacity > 0 and paint_value_visible(color, seen_servers | {server_id}):
                    return True
            return False
        if target_name == "pattern":
            return definition_has_geometry(target)
        return False

    def visible_paint(name: str, paint: tuple[str, str, float, float, float, float, str], element: ET.Element) -> bool:
        fill, stroke, fill_opacity, stroke_opacity, stroke_width, opacity, color = paint
        if opacity <= 0:
            return False
        if fill.strip().lower() == "currentcolor":
            fill = color
        if stroke.strip().lower() == "currentcolor":
            stroke = color
        fill_visible = paint_value_visible(fill) and fill_opacity > 0
        stroke_visible = (
            paint_value_visible(stroke)
            and stroke_opacity > 0
            and stroke_width > 0
        )
        if name == "line":
            return stroke_visible
        if name == "path" and not path_has_fill_area(element.attrib.get("d", "")):
            fill_visible = False
        if name in {"polygon", "polyline"} and not points_have_area(element.attrib.get("points", "")):
            fill_visible = False
        return fill_visible or stroke_visible

    def primitive_intersects_viewport(element: ET.Element) -> bool:
        if viewport is None:
            return True
        name = local_name(element.tag)
        bounds: tuple[float, float, float, float] | None = None
        if name == "rect":
            x, y = numeric_attribute(element, "x"), numeric_attribute(element, "y")
            bounds = (x, y, x + numeric_attribute(element, "width"), y + numeric_attribute(element, "height"))
        elif name == "circle":
            cx, cy, radius = numeric_attribute(element, "cx"), numeric_attribute(element, "cy"), numeric_attribute(element, "r")
            bounds = (cx - radius, cy - radius, cx + radius, cy + radius)
        elif name == "ellipse":
            cx, cy = numeric_attribute(element, "cx"), numeric_attribute(element, "cy")
            rx, ry = numeric_attribute(element, "rx"), numeric_attribute(element, "ry")
            bounds = (cx - rx, cy - ry, cx + rx, cy + ry)
        elif name == "line":
            x1, y1 = numeric_attribute(element, "x1"), numeric_attribute(element, "y1")
            x2, y2 = numeric_attribute(element, "x2"), numeric_attribute(element, "y2")
            bounds = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        elif name in {"polygon", "polyline"}:
            values = number_list(element.attrib.get("points", ""))
            if values:
                bounds = (min(values[::2]), min(values[1::2]), max(values[::2]), max(values[1::2]))
        if bounds is None:
            return True
        view_x, view_y, view_width, view_height = viewport
        min_x, min_y, max_x, max_y = bounds
        return not (
            max_x < view_x
            or max_y < view_y
            or min_x > view_x + view_width
            or min_y > view_y + view_height
        )

    definition_containers = {"clippath", "defs", "marker", "mask", "pattern", "symbol"}

    def definition_has_geometry(element: ET.Element, seen: frozenset[str] = frozenset()) -> bool:
        if hidden(element):
            return False
        if primitive_is_meaningful(element):
            return True
        if local_name(element.tag) == "use":
            reference = href_value(element)
            target_id = reference[1:] if reference and reference.startswith("#") else ""
            if not target_id or target_id in seen or len(seen) >= 256 or target_id not in ids:
                return False
            return definition_has_geometry(ids[target_id], seen | {target_id})
        return any(definition_has_geometry(child, seen) for child in element)

    def clip_allows_geometry(element: ET.Element) -> bool:
        properties = style_properties(element)
        value = presentation_value(element, properties, "clip-path")
        if value is None or value.strip().lower() == "none":
            return True
        match = re.fullmatch(r"url\s*\(\s*['\"]?#([^)'\"\s]+)['\"]?\s*\)", value.strip(), re.I)
        if match is None:
            return False
        target = ids.get(match.group(1))
        return target is not None and local_name(target.tag) == "clippath" and definition_has_geometry(target)

    def tree_has_geometry(
        element: ET.Element,
        *,
        definition_root: bool = False,
        seen_references: frozenset[str] = frozenset(),
        inherited_paint: tuple[str, str, float, float, float, float, str] = ("black", "none", 1.0, 1.0, 1.0, 1.0, "black"),
        transformed: bool = False,
    ) -> bool:
        if hidden(element):
            return False
        if not clip_allows_geometry(element):
            return False
        name = local_name(element.tag)
        paint = resolved_paint(element, inherited_paint)
        properties = style_properties(element)
        has_transform = transformed or presentation_value(element, properties, "transform") not in {None, "none"}
        if name in definition_containers and not definition_root:
            return False
        if (
            primitive_is_meaningful(element)
            and visible_paint(name, paint, element)
            and (has_transform or primitive_intersects_viewport(element))
        ):
            return True
        if name == "use":
            reference = href_value(element)
            if not reference or not reference.startswith("#") or len(reference) == 1:
                return False
            target_id = reference[1:]
            if target_id in seen_references or len(seen_references) >= 256 or target_id not in ids:
                return False
            return tree_has_geometry(
                ids[target_id],
                definition_root=True,
                seen_references=seen_references | {target_id},
                inherited_paint=paint,
                transformed=has_transform,
            )
        return any(
            tree_has_geometry(
                child,
                seen_references=seen_references,
                inherited_paint=paint,
                transformed=has_transform,
            )
            for child in element
        )

    try:
        drawable = tree_has_geometry(root)
    except RecursionError as exc:
        raise ArchivePlanError("logo.svg reference graph exceeds the safe recursion limit") from exc
    if not drawable:
        raise ArchivePlanError("logo.svg contains no drawable Logo geometry")
    _validate_svg_render(path)
    if {"width", "height"} <= set(declared_dimensions):
        width = declared_dimensions["width"]
        height = declared_dimensions["height"]
        return LogoGeometry(
            "svg",
            width,
            height,
            math.isclose(width, height, rel_tol=1e-9, abs_tol=1e-9),
        )
    if declared_dimensions:
        return LogoGeometry(
            "svg",
            declared_dimensions.get("width", 0.0),
            declared_dimensions.get("height", 0.0),
            False,
        )
    if viewport is not None:
        width, height = viewport[2], viewport[3]
        return LogoGeometry(
            "svg",
            width,
            height,
            math.isclose(width, height, rel_tol=1e-9, abs_tol=1e-9),
        )
    return LogoGeometry("svg", 0.0, 0.0, False)


def _validate_svg_render(path: Path) -> None:
    """Rasterize the sanitized SVG and require at least one nontransparent output pixel."""
    runtime_root_value = os.environ.get("CODEX_PRIMARY_RUNTIME_ROOT")
    node_value = os.environ.get("CODEX_PRIMARY_RUNTIME_NODE")
    runtime_modules_value = os.environ.get("CODEX_PRIMARY_RUNTIME_NODE_MODULES")
    bundle_version = os.environ.get("CODEX_PRIMARY_RUNTIME_BUNDLE_VERSION")
    if not runtime_root_value or not node_value or not runtime_modules_value or not bundle_version:
        raise ArchivePlanError("trusted SVG raster runtime is unavailable")
    version_profiles = [
        profile for profile in TRUSTED_RUNTIME_PROFILES
        if bundle_version == profile["bundle_version"]
    ]
    if not version_profiles:
        raise ArchivePlanError("trusted SVG raster runtime bundle version does not match the locked release")
    runtime_root = Path(runtime_root_value)
    node_path = Path(node_value)
    runtime_modules = Path(runtime_modules_value)
    if (
        not runtime_root.is_absolute()
        or not node_path.is_absolute()
        or not runtime_modules.is_absolute()
        or runtime_root.is_symlink()
        or node_path.is_symlink()
        or runtime_modules.is_symlink()
        or not runtime_root.is_dir()
        or not node_path.is_file()
        or not runtime_modules.is_dir()
    ):
        raise ArchivePlanError("trusted SVG raster runtime paths are invalid")
    resolved_runtime_root = runtime_root.resolve()
    resolved_node_path = node_path.resolve()
    resolved_runtime_modules = runtime_modules.resolve()
    if (
        resolved_runtime_root != runtime_root
        or resolved_node_path != node_path
        or resolved_runtime_modules != runtime_modules
    ):
        raise ArchivePlanError("trusted SVG raster runtime paths cannot traverse symbolic links")
    runtime_root = resolved_runtime_root
    node_path = resolved_node_path
    runtime_modules = resolved_runtime_modules
    runtime_profile = next(
        (
            profile for profile in version_profiles
            if runtime_root == profile["runtime_root"]
            and node_path == profile["node"]
            and runtime_modules == profile["node_modules"]
        ),
        None,
    )
    if runtime_profile is None:
        raise ArchivePlanError("trusted SVG raster runtime paths do not match the locked platform release")
    try:
        node_path.relative_to(runtime_root)
        runtime_modules.relative_to(runtime_root)
    except ValueError as exc:
        raise ArchivePlanError("trusted SVG raster runtime paths escape the primary runtime") from exc
    sharp_entry = runtime_modules / "sharp/dist/index.cjs"
    sharp_package = runtime_modules / "sharp/package.json"
    if sharp_entry.is_symlink() or not sharp_entry.is_file():
        raise ArchivePlanError("trusted Sharp renderer entry is unavailable")
    if sharp_package.is_symlink() or not sharp_package.is_file():
        raise ArchivePlanError("trusted Sharp package metadata is unavailable")
    sharp_entry = sharp_entry.resolve()
    try:
        sharp_entry.relative_to(runtime_modules)
    except ValueError as exc:
        raise ArchivePlanError("trusted Sharp renderer entry escapes the module root") from exc
    if (
        file_sha256(node_path) != runtime_profile["node_sha256"]
        or file_sha256(sharp_entry) != TRUSTED_SHARP_ENTRY_SHA256
        or file_sha256(sharp_package) != TRUSTED_SHARP_PACKAGE_SHA256
    ):
        raise ArchivePlanError("trusted SVG raster runtime artifact digest does not match the locked release")
    challenge = secrets.token_hex(32)
    javascript = r"""
const sharp = require(process.argv[2]);
const input = process.argv[1];
const challenge = process.argv[3];
(async () => {
  const requiredVersions = {
    sharp: '0.35.3',
    vips: '8.18.3',
    rsvg: '2.62.90'
  };
  for (const [component, required] of Object.entries(requiredVersions)) {
    if (sharp.versions[component] !== required) {
      throw new Error(
        `untrusted renderer version for ${component}: ` +
        `${sharp.versions[component] || 'missing'} (required ${required})`
      );
    }
  }
  const result = await sharp(input, {
    density: 96,
    failOn: 'error',
    limitInputPixels: 16777216
  })
    .resize({
      width: 256,
      height: 256,
      fit: 'contain',
      background: { r: 0, g: 0, b: 0, alpha: 0 }
    })
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { data, info } = result;
  let visible = false;
  for (let offset = 3; offset < data.length; offset += info.channels) {
    if (data[offset] > 0) { visible = true; break; }
  }
  process.stdout.write(JSON.stringify({
    protocol: 'doujiao-logo-render-v1',
    challenge,
    visible,
    versions: {
      sharp: sharp.versions.sharp,
      vips: sharp.versions.vips,
      rsvg: sharp.versions.rsvg
    }
  }));
  process.exitCode = visible ? 0 : 2;
})().catch((error) => {
  process.stderr.write(String(error && error.message ? error.message : error));
  process.exit(1);
});
"""
    # Do not inherit NODE_OPTIONS, preload hooks, NODE_PATH, or dynamic-library
    # injection variables from the caller. Sharp is loaded only by its validated
    # absolute entry inside the platform-owned runtime.
    environment: dict[str, str] = {}
    try:
        completed = subprocess.run(
            [str(node_path), "-e", javascript, str(path), str(sharp_entry), challenge],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=15,
            env=environment,
            cwd=runtime_root,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ArchivePlanError(f"safe SVG raster validation failed: {exc}") from exc
    if completed.returncode not in {0, 2}:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:240]
        raise ArchivePlanError(f"safe SVG raster validation failed: {detail or 'renderer error'}")
    try:
        receipt = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchivePlanError("safe SVG raster validation returned an invalid receipt") from exc
    expected_versions = {"sharp": "0.35.3", "vips": "8.18.3", "rsvg": "2.62.90"}
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {"protocol", "challenge", "visible", "versions"}
        or receipt.get("protocol") != "doujiao-logo-render-v1"
        or receipt.get("challenge") != challenge
        or not isinstance(receipt.get("visible"), bool)
        or receipt.get("versions") != expected_versions
        or (completed.returncode == 0) != receipt.get("visible")
    ):
        raise ArchivePlanError("safe SVG raster validation returned an untrusted receipt")
    if not receipt["visible"]:
        raise ArchivePlanError("logo.svg rasterizes to no visible Logo pixel")


def _decode_png(path: Path) -> PngRaster:
    """Validate a PNG and return exact decoded samples for crop proofs."""
    if path.stat().st_size <= 0 or path.stat().st_size > 512_000:
        raise ArchivePlanError("company Logo must be nonempty and no larger than 512,000 bytes")
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ArchivePlanError("observed company Logo is not a PNG")
    position = 8
    seen_ihdr = False
    seen_idat = False
    seen_iend = False
    seen_plte = False
    idat_ended = False
    expected_decoded_size = 0
    scanline_size = 0
    png_height = 0
    png_width = 0
    png_color_type = -1
    png_bit_depth = -1
    palette: bytes | None = None
    transparency: bytes | None = None
    compressed = bytearray()
    preserved_chunks: list[tuple[str, bytes, bytes]] = []
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_end = position + 12 + length
        if length > 512_000 or chunk_end > len(data):
            raise ArchivePlanError("observed PNG has a truncated or oversized chunk")
        payload = data[position + 8 : position + 8 + length]
        recorded_crc = struct.unpack(">I", data[position + 8 + length : chunk_end])[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != recorded_crc:
            raise ArchivePlanError("observed PNG has an invalid chunk checksum")
        if re.fullmatch(rb"[A-Za-z]{4}", chunk_type) is None or not 65 <= chunk_type[2] <= 90:
            raise ArchivePlanError("observed PNG contains an invalid chunk type")
        if chunk_type in ANIMATED_PNG_CHUNKS:
            raise ArchivePlanError("animated PNG chunks are not allowed in a company Logo")
        if chunk_type == b"IHDR" and seen_ihdr:
            raise ArchivePlanError("observed PNG contains duplicate IHDR")
        if chunk_type == b"PLTE" and seen_plte:
            raise ArchivePlanError("observed PNG contains duplicate PLTE")
        if not seen_ihdr:
            if chunk_type != b"IHDR" or length != 13:
                raise ArchivePlanError("observed PNG must begin with IHDR")
            width, height = struct.unpack(">II", payload[:8])
            if width <= 0 or height <= 0 or width > 8192 or height > 8192 or width * height > 16_000_000:
                raise ArchivePlanError("observed PNG has invalid Logo dimensions")
            bit_depth, color_type, compression, filter_method, interlace = payload[8:13]
            legal_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                bit_depth not in legal_depths.get(color_type, set())
                or compression != 0
                or filter_method != 0
                or interlace != 0
            ):
                raise ArchivePlanError("observed PNG uses unsupported or invalid IHDR encoding")
            channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
            scanline_size = (width * channels * bit_depth + 7) // 8
            expected_decoded_size = (scanline_size + 1) * height
            if expected_decoded_size <= 0 or expected_decoded_size > 64_000_000:
                raise ArchivePlanError("observed PNG expands beyond the safe Logo limit")
            png_height = height
            png_width = width
            png_color_type = color_type
            png_bit_depth = bit_depth
            seen_ihdr = True
        elif chunk_type == b"PLTE":
            palette_entries = length // 3
            if (
                seen_idat
                or transparency is not None
                or png_color_type in {0, 4}
                or length == 0
                or length > 768
                or length % 3
                or (png_color_type == 3 and palette_entries > 2**png_bit_depth)
            ):
                raise ArchivePlanError("observed PNG has an invalid PLTE")
            palette = payload
            seen_plte = True
        elif chunk_type == b"tRNS":
            if transparency is not None or seen_idat:
                raise ArchivePlanError("observed PNG has invalid or duplicate transparency data")
            palette_entries = len(palette) // 3 if palette is not None else 0
            valid_transparency = (
                (png_color_type == 0 and length == 2)
                or (png_color_type == 2 and length == 6)
                or (png_color_type == 3 and seen_plte and 0 < length <= palette_entries)
            )
            if not valid_transparency:
                raise ArchivePlanError("observed PNG has invalid transparency data")
            max_sample = (1 << png_bit_depth) - 1
            if png_color_type == 0 and int.from_bytes(payload, "big") > max_sample:
                raise ArchivePlanError("observed PNG grayscale transparency sample is out of range")
            if png_color_type == 2 and any(
                int.from_bytes(payload[index : index + 2], "big") > max_sample
                for index in (0, 2, 4)
            ):
                raise ArchivePlanError("observed PNG truecolor transparency sample is out of range")
            transparency = payload
        elif chunk_type == b"IDAT":
            if idat_ended or (png_color_type == 3 and not seen_plte):
                raise ArchivePlanError("observed PNG has invalid IDAT ordering")
            seen_idat = True
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            if length != 0 or chunk_end != len(data):
                raise ArchivePlanError("observed PNG has an invalid IEND")
            seen_iend = True
            position = chunk_end
            break
        elif seen_idat:
            idat_ended = True
        if chunk_type not in {b"IHDR", b"PLTE", b"IDAT", b"IEND"} and chunk_type[:1].isupper():
            raise ArchivePlanError("observed PNG contains an unknown critical chunk")
        if chunk_type not in {b"IHDR", b"IDAT", b"IEND"}:
            preserved_chunks.append(("after-idat" if seen_idat else "before-idat", chunk_type, payload))
        position = chunk_end
    if not (seen_ihdr and seen_idat and seen_iend):
        raise ArchivePlanError("observed PNG lacks complete image data")
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(bytes(compressed), expected_decoded_size + 1)
        remaining = expected_decoded_size + 1 - len(decoded)
        if remaining > 0:
            decoded += decompressor.flush(remaining)
    except zlib.error as exc:
        raise ArchivePlanError(f"observed PNG has invalid compressed image data: {exc}") from exc
    if (
        not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
        or len(decoded) != expected_decoded_size
    ):
        raise ArchivePlanError("observed PNG compressed image data is incomplete or excessive")
    for row in range(png_height):
        if decoded[row * (scanline_size + 1)] > 4:
            raise ArchivePlanError("observed PNG contains an invalid scanline filter")

    bytes_per_pixel = max(1, (png_bit_depth * {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[png_color_type] + 7) // 8)

    def paeth(left: int, above: int, upper_left: int) -> int:
        estimate = left + above - upper_left
        left_distance = abs(estimate - left)
        above_distance = abs(estimate - above)
        upper_left_distance = abs(estimate - upper_left)
        if left_distance <= above_distance and left_distance <= upper_left_distance:
            return left
        if above_distance <= upper_left_distance:
            return above
        return upper_left

    reconstructed_rows: list[bytes] = []
    previous = bytes(scanline_size)
    for row_index in range(png_height):
        offset = row_index * (scanline_size + 1)
        filter_type = decoded[offset]
        filtered = decoded[offset + 1 : offset + 1 + scanline_size]
        reconstructed = bytearray(scanline_size)
        for index, value in enumerate(filtered):
            left = reconstructed[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            else:
                predictor = paeth(left, above, upper_left)
            reconstructed[index] = (value + predictor) & 0xFF
        previous = bytes(reconstructed)
        reconstructed_rows.append(previous)
    del decoded

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[png_color_type]

    def unpack_samples(row: bytes) -> list[int]:
        required = png_width * channels
        if png_bit_depth == 8:
            return list(row[:required])
        if png_bit_depth == 16:
            return [int.from_bytes(row[index : index + 2], "big") for index in range(0, required * 2, 2)]
        mask = (1 << png_bit_depth) - 1
        values: list[int] = []
        for byte in row:
            for shift in range(8 - png_bit_depth, -1, -png_bit_depth):
                values.append((byte >> shift) & mask)
                if len(values) == required:
                    return values
        return values

    transparent_gray = int.from_bytes(transparency, "big") if transparency is not None and png_color_type == 0 else None
    transparent_rgb = (
        tuple(int.from_bytes(transparency[index : index + 2], "big") for index in (0, 2, 4))
        if transparency is not None and png_color_type == 2
        else None
    )
    visible_pixel = False
    palette_entries = len(palette) // 3 if palette is not None else 0
    for row in reconstructed_rows:
        samples = unpack_samples(row)
        if len(samples) != png_width * channels:
            raise ArchivePlanError("observed PNG pixel samples are incomplete")
        for index in range(0, len(samples), channels):
            pixel = samples[index : index + channels]
            if png_color_type == 6:
                visible = pixel[3] > 0
            elif png_color_type == 4:
                visible = pixel[1] > 0
            elif png_color_type == 3:
                palette_index = pixel[0]
                if palette_index >= palette_entries:
                    raise ArchivePlanError("observed PNG references a missing palette entry")
                alpha = transparency[palette_index] if transparency is not None and palette_index < len(transparency) else 255
                visible = alpha > 0
            elif png_color_type == 0:
                visible = transparent_gray is None or pixel[0] != transparent_gray
            else:
                visible = transparent_rgb is None or tuple(pixel) != transparent_rgb
            if visible:
                visible_pixel = True
    if not visible_pixel:
        raise ArchivePlanError("observed PNG contains no visible Logo pixel")
    packed_rows = tuple(reconstructed_rows)
    return PngRaster(
        width=png_width,
        height=png_height,
        bit_depth=png_bit_depth,
        color_type=png_color_type,
        channels=channels,
        rows=packed_rows,
        preserved_chunks=tuple(preserved_chunks),
    )


def _validate_observed_logo(path: Path, target_path: str) -> LogoGeometry:
    if path.stat().st_size <= 0 or path.stat().st_size > 512_000:
        raise ArchivePlanError("company Logo must be nonempty and no larger than 512,000 bytes")
    suffix = Path(target_path).suffix.lower()
    if suffix == ".svg":
        geometry = _validate_svg(path)
        scan_sensitive_material([path])
        return geometry
    if suffix != ".png":
        raise ArchivePlanError("observed company Logo must be SVG or PNG")
    raster = _decode_png(path)
    return LogoGeometry("png", raster.width, raster.height, raster.width == raster.height)


def _strict_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ArchivePlanError(f"{label} must contain exactly {sorted(keys)!r}")
    return value


def _positive_logo_dimension(value: Any, label: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ArchivePlanError(f"{label} must be a positive finite number")
    return float(value)


def _validate_logo_search_record(
    selection_value: Any,
    *,
    source_page_url: str,
    source_asset_url: str,
    source_width: int,
    source_height: int,
) -> None:
    """Require an auditable official-source search before permitting a crop."""
    selection = _strict_object(
        selection_value,
        LOGO_PROVENANCE_SELECTION_KEYS,
        "logo provenance selection",
    )
    if selection.get("square_official_candidate_found") is not False:
        raise ArchivePlanError("logo crop provenance must state that no verified official square candidate was found")

    surfaces = selection.get("search_surfaces")
    if not isinstance(surfaces, list):
        raise ArchivePlanError("logo provenance search_surfaces must be an array")
    observed_surfaces: set[str] = set()
    checked_surface_urls: set[str] = set()
    for index, raw_surface in enumerate(surfaces):
        surface = _strict_object(
            raw_surface,
            LOGO_PROVENANCE_SEARCH_SURFACE_KEYS,
            f"logo provenance search_surfaces[{index}]",
        )
        name = surface.get("surface")
        status = surface.get("status")
        urls = surface.get("urls")
        note = surface.get("note")
        if name not in LOGO_SEARCH_SURFACES or name in observed_surfaces:
            raise ArchivePlanError("logo provenance search surfaces must be complete, unique, and recognized")
        observed_surfaces.add(str(name))
        if status not in {"checked", "not-applicable"}:
            raise ArchivePlanError("logo provenance search surface status must be checked or not-applicable")
        if not isinstance(urls, list) or any(not isinstance(url, str) for url in urls):
            raise ArchivePlanError("logo provenance search surface urls must be an array of public URLs")
        for url_index, url in enumerate(urls):
            _public_http_url(url, f"logo provenance search_surfaces[{index}].urls[{url_index}]")
        if status == "checked" and not urls:
            raise ArchivePlanError("a checked logo provenance search surface must record at least one URL")
        if status == "checked":
            checked_surface_urls.update(urls)
        if status == "not-applicable" and not _nonblank(note):
            raise ArchivePlanError("a not-applicable logo provenance search surface must explain why")
        if not isinstance(note, str):
            raise ArchivePlanError("logo provenance search surface note must be a string")
    if observed_surfaces != LOGO_SEARCH_SURFACES:
        raise ArchivePlanError("logo provenance must cover every required official search surface")
    if source_page_url not in checked_surface_urls:
        raise ArchivePlanError("logo crop source page must be bound to a checked official search surface")

    candidates = selection.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ArchivePlanError("logo provenance must record at least one official candidate")
    selected_count = 0
    observed_asset_urls: set[str] = set()
    for index, raw_candidate in enumerate(candidates):
        candidate = _strict_object(
            raw_candidate,
            LOGO_PROVENANCE_CANDIDATE_KEYS,
            f"logo provenance candidates[{index}]",
        )
        asset_url = _public_http_url(candidate.get("asset_url"), f"logo provenance candidates[{index}].asset_url")
        candidate_page_url = _public_http_url(
            candidate.get("source_page_url"),
            f"logo provenance candidates[{index}].source_page_url",
        )
        logo_format = candidate.get("format")
        gate_status = candidate.get("gate_status")
        identity_verified = candidate.get("identity_verified")
        is_official = candidate.get("is_official")
        officiality_evidence = candidate.get("officiality_evidence")
        decision = candidate.get("decision")
        reason = candidate.get("reason")
        if asset_url in observed_asset_urls:
            raise ArchivePlanError("logo provenance candidate asset URLs must be unique")
        observed_asset_urls.add(asset_url)
        if candidate_page_url not in checked_surface_urls:
            raise ArchivePlanError("every logo candidate must be bound to a checked official source page")
        if logo_format not in {"svg", "png", "other"}:
            raise ArchivePlanError("logo provenance candidate format must be svg, png, or other")
        if gate_status not in {"pass", "rejected"}:
            raise ArchivePlanError("logo provenance candidate gate_status must be pass or rejected")
        if not isinstance(identity_verified, bool) or not isinstance(is_official, bool):
            raise ArchivePlanError("logo provenance candidate identity and officiality flags must be booleans")
        if not _nonblank(officiality_evidence):
            raise ArchivePlanError("logo provenance candidate must record officiality evidence")
        if gate_status == "pass" and (
            logo_format not in {"svg", "png"}
            or identity_verified is not True
            or is_official is not True
        ):
            raise ArchivePlanError("a gate-passing logo candidate must be a verified official SVG or PNG")
        if decision not in {"selected-crop-source", "rejected"}:
            raise ArchivePlanError("logo provenance candidate decision must be selected-crop-source or rejected")
        if not _nonblank(reason):
            raise ArchivePlanError("logo provenance candidate must record a nonempty decision reason")
        width = _positive_logo_dimension(
            candidate.get("width"),
            f"logo provenance candidates[{index}].width",
            nullable=True,
        )
        height = _positive_logo_dimension(
            candidate.get("height"),
            f"logo provenance candidates[{index}].height",
            nullable=True,
        )
        if (width is None) != (height is None):
            raise ArchivePlanError("logo provenance candidate width and height must both be known or both null")
        if gate_status == "pass" and (width is None or height is None):
            raise ArchivePlanError("a gate-passing logo candidate must record dimensions")
        if (
            gate_status == "pass"
            and width is not None
            and height is not None
            and math.isclose(width, height, rel_tol=1e-9, abs_tol=1e-9)
        ):
            raise ArchivePlanError("a verified official square candidate exists, so cropping is not permitted")
        if decision == "selected-crop-source":
            selected_count += 1
            if (
                gate_status != "pass"
                or logo_format != "png"
                or identity_verified is not True
                or is_official is not True
                or candidate_page_url != source_page_url
                or asset_url != source_asset_url
                or width != float(source_width)
                or height != float(source_height)
            ):
                raise ArchivePlanError("selected crop source must be the verified official non-square source PNG")
    if selected_count != 1:
        raise ArchivePlanError("logo provenance must select exactly one official crop source")


def _validate_center_square_crop(
    staging_root: Path,
    *,
    company_slug: str,
    company: dict[str, Any],
    canonical_logo: Path,
) -> dict[str, Any]:
    """Prove that a staged PNG is the exact centered square of an official PNG."""
    original = _safe_regular_file(staging_root / "logo-original.png", "logo-original.png")
    provenance_path = _safe_regular_file(staging_root / "logo-provenance.json", "logo-provenance.json")
    if provenance_path.stat().st_size <= 0 or provenance_path.stat().st_size > 128_000:
        raise ArchivePlanError("logo-provenance.json must be nonempty and no larger than 128,000 bytes")
    if _same_file(original, canonical_logo, "original and cropped Logo"):
        raise ArchivePlanError("logo-original.png and logo.png must be distinct files")
    if _same_file(provenance_path, original, "provenance and original Logo") or _same_file(
        provenance_path,
        canonical_logo,
        "provenance and cropped Logo",
    ):
        raise ArchivePlanError("logo provenance must be a distinct file")
    scan_sensitive_material([provenance_path])
    provenance = _strict_object(
        _read_object(provenance_path, "logo crop provenance"),
        LOGO_PROVENANCE_KEYS,
        "logo crop provenance",
    )
    if provenance.get("version") != "1.0":
        raise ArchivePlanError("logo crop provenance version must be 1.0")
    if provenance.get("company_slug") != company_slug:
        raise ArchivePlanError("logo crop provenance belongs to a different company")
    if provenance.get("operation") != LOGO_CROP_OPERATION:
        raise ArchivePlanError(f"logo crop provenance operation must be {LOGO_CROP_OPERATION}")

    source = _strict_object(
        provenance.get("source"),
        LOGO_PROVENANCE_SOURCE_KEYS,
        "logo crop provenance source",
    )
    output = _strict_object(
        provenance.get("output"),
        LOGO_PROVENANCE_OUTPUT_KEYS,
        "logo crop provenance output",
    )
    crop = _strict_object(
        provenance.get("crop"),
        LOGO_PROVENANCE_CROP_KEYS,
        "logo crop provenance crop",
    )
    if source.get("file") != "logo-original.png" or output.get("file") != "logo.png":
        raise ArchivePlanError("logo crop provenance must bind logo-original.png to logo.png")
    source_page_url = _public_http_url(source.get("page_url"), "logo crop provenance source.page_url")
    source_asset_url = _public_http_url(source.get("asset_url"), "logo crop provenance source.asset_url")
    company_logo = company["brand_identity"]["company_logo"]
    if company_logo.get("source_url") not in {source_page_url, source_asset_url}:
        raise ArchivePlanError("company_logo.source_url must match the official crop source page or asset URL")

    original_raster = _decode_png(original)
    output_raster = _decode_png(canonical_logo)
    if original_raster.width == original_raster.height:
        raise ArchivePlanError("an already-square official PNG must be used unchanged instead of cropped")
    side = min(original_raster.width, original_raster.height)
    expected_left = (original_raster.width - side) // 2
    expected_top = (original_raster.height - side) // 2
    for _phase, chunk_type, _payload in original_raster.preserved_chunks:
        if 65 <= chunk_type[3] <= 90 and chunk_type not in CROP_UNSAFE_COPY_ALLOWED_CHUNKS:
            raise ArchivePlanError(
                "official PNG contains an ancillary chunk that is unsafe to copy after cropping"
            )

    def require_file_record(
        record: dict[str, Any],
        path: Path,
        raster: PngRaster,
        label: str,
    ) -> None:
        if SHA256_PATTERN.fullmatch(str(record.get("sha256"))) is None:
            raise ArchivePlanError(f"{label}.sha256 must be a lowercase SHA-256")
        if record.get("sha256") != file_sha256(path):
            raise ArchivePlanError(f"{label}.sha256 does not match the staged bytes")
        size_bytes = record.get("size_bytes")
        width = record.get("width")
        height = record.get("height")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0:
            raise ArchivePlanError(f"{label}.size_bytes must be a positive integer")
        if size_bytes != path.stat().st_size:
            raise ArchivePlanError(f"{label}.size_bytes does not match the staged bytes")
        if (
            not isinstance(width, int)
            or isinstance(width, bool)
            or not isinstance(height, int)
            or isinstance(height, bool)
            or width != raster.width
            or height != raster.height
        ):
            raise ArchivePlanError(f"{label} dimensions do not match the decoded PNG")

    require_file_record(source, original, original_raster, "logo crop provenance source")
    require_file_record(output, canonical_logo, output_raster, "logo crop provenance output")
    expected_crop = {
        "left": expected_left,
        "top": expected_top,
        "width": side,
        "height": side,
        "resampled": False,
        "padded": False,
        "stretched": False,
        "redrawn": False,
    }
    if (
        any(
            not isinstance(crop.get(key), int) or isinstance(crop.get(key), bool)
            for key in ("left", "top", "width", "height")
        )
        or any(crop.get(key) is not False for key in ("resampled", "padded", "stretched", "redrawn"))
        or crop != expected_crop
    ):
        raise ArchivePlanError("logo crop provenance must record the exact deterministic center-square crop")
    if output_raster.width != side or output_raster.height != side:
        raise ArchivePlanError("cropped company Logo must have the exact square output dimensions")
    if (
        output_raster.bit_depth != original_raster.bit_depth
        or output_raster.color_type != original_raster.color_type
        or output_raster.channels != original_raster.channels
        or output_raster.preserved_chunks != original_raster.preserved_chunks
    ):
        raise ArchivePlanError("cropped company Logo changed PNG color interpretation or preserved metadata")

    def row_sample_slice(raster: PngRaster, row_index: int, left: int, width: int) -> bytes:
        """Return exact encoded sample values without expanding the whole image to Python ints."""
        row = raster.rows[row_index]
        sample_start = left * raster.channels
        sample_end = (left + width) * raster.channels
        if raster.bit_depth in {8, 16}:
            bytes_per_sample = raster.bit_depth // 8
            return row[sample_start * bytes_per_sample : sample_end * bytes_per_sample]
        mask = (1 << raster.bit_depth) - 1
        values = bytearray()
        for sample_index in range(sample_start, sample_end):
            bit_index = sample_index * raster.bit_depth
            byte_index = bit_index // 8
            shift = 8 - raster.bit_depth - (bit_index % 8)
            values.append((row[byte_index] >> shift) & mask)
        return bytes(values)

    for output_row_index in range(side):
        output_samples = row_sample_slice(output_raster, output_row_index, 0, side)
        source_samples = row_sample_slice(
            original_raster,
            expected_top + output_row_index,
            expected_left,
            side,
        )
        if output_samples != source_samples:
            raise ArchivePlanError("cropped company Logo pixels are not the exact deterministic center crop")

    _validate_logo_search_record(
        provenance.get("selection"),
        source_page_url=source_page_url,
        source_asset_url=source_asset_url,
        source_width=original_raster.width,
        source_height=original_raster.height,
    )
    return {
        "provenance_path": str(provenance_path),
        "provenance_sha256": file_sha256(provenance_path),
        "provenance_size_bytes": provenance_path.stat().st_size,
        "original_source_path": str(original),
        "record": provenance,
        "verification": {
            "pixel_exact_center_crop": True,
            "format_preserved": True,
            "render_metadata_preserved": True,
            "official_square_candidate_found": False,
        },
    }


def prepare_identity_asset_files(
    staging_root: Path | None,
    *,
    company_slug: str,
    company: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Validate a square official original or a proven PNG center crop."""
    if staging_root is None:
        return [], None
    if staging_root.is_symlink() or not staging_root.is_dir():
        raise ArchivePlanError("identity assets root must be a non-symlink directory")
    staging_root = staging_root.resolve()
    entries = list(staging_root.iterdir())
    if any(item.is_symlink() or not item.is_file() for item in entries):
        raise ArchivePlanError("identity assets root may contain only direct non-symlink files")
    declared_path = _company_logo_asset_path(company, company_slug)
    canonical_paths = {
        f"companies/{company_slug}/assets/logo.svg",
        f"companies/{company_slug}/assets/logo.png",
    }
    if declared_path not in canonical_paths:
        raise ArchivePlanError(
            "staged company Logo must exactly match company.json's canonical assets/logo.svg or assets/logo.png path"
        )
    expected_name = Path(declared_path).name
    entry_names = {item.name for item in entries}
    crop_mode = declared_path.endswith("/logo.png") and entry_names == LOGO_CROP_STAGING_FILES
    if not crop_mode and entry_names != {expected_name}:
        raise ArchivePlanError(
            f"identity assets root must contain exactly one {expected_name}, or the exact verified PNG crop set"
        )

    logo = _safe_regular_file(staging_root / expected_name, expected_name)
    geometry = _validate_observed_logo(logo, declared_path)
    crop_provenance = (
        _validate_center_square_crop(
            staging_root,
            company_slug=company_slug,
            company=company,
            canonical_logo=logo,
        )
        if crop_mode
        else None
    )
    if not geometry.is_square:
        raise ArchivePlanError(
            "new canonical company Logo must be an official square original or a verified deterministic PNG center crop"
        )
    files = [
        {
            "source_path": str(logo),
            "target_path": declared_path,
            "sha256": file_sha256(logo),
            "size_bytes": logo.stat().st_size,
        }
    ]
    return files, crop_provenance


def identity_asset_action(
    company_slug: str,
    local_files: list[dict[str, Any]],
    declared_logo_path: str | None,
    observation_paths: set[str],
    remote_state: dict[str, Any] | None,
    expected_base_head: str | None,
    *,
    confirm_replacement: bool,
    clear_reference: bool = False,
    confirm_clear: bool = False,
) -> tuple[str, str | None]:
    if clear_reference and (local_files or declared_logo_path is not None):
        raise ArchivePlanError("company Logo reference clear cannot also stage or declare a Logo")
    if clear_reference and not confirm_clear:
        raise ArchivePlanError("clearing a claimed company Logo reference requires explicit authorization")
    if not local_files:
        if declared_logo_path is None:
            if clear_reference:
                if observation_paths and remote_state is None:
                    return "remote-preflight-required", None
                if not observation_paths and remote_state is None:
                    return "clear-reference", expected_base_head
            elif remote_state is not None:
                raise ArchivePlanError("remote identity asset state was supplied without a declared company logo")
            else:
                return "preserve", expected_base_head
        if remote_state is None:
            return "remote-preflight-required", None
    if remote_state is None:
        return "remote-preflight-required", None
    if set(remote_state) != IDENTITY_ASSET_STATE_KEYS:
        raise ArchivePlanError("remote identity asset state has unexpected or missing fields")
    base_head = _state_base_head(remote_state, "remote identity asset state", expected_base_head)
    if remote_state.get("company_slug") != company_slug:
        raise ArchivePlanError("remote identity asset state is for a different company")
    observed = remote_state.get("assets")
    if not isinstance(observed, list):
        raise ArchivePlanError("remote identity asset state assets must be an array")
    write_expected = {item["target_path"]: (item["sha256"], item["size_bytes"]) for item in local_files}
    staged_sources = {Path(item["source_path"]).resolve() for item in local_files}
    expected_paths = set(write_expected) | observation_paths
    if not local_files and declared_logo_path is not None:
        expected_paths.add(declared_logo_path)
    actual: dict[str, tuple[bool, Any, Any]] = {}
    for entry in observed:
        if not isinstance(entry, dict) or set(entry) != IDENTITY_ASSET_ENTRY_KEYS:
            raise ArchivePlanError("remote identity asset observation is malformed")
        path = entry.get("path")
        exists = entry.get("exists")
        if not isinstance(path, str) or path not in expected_paths or path in actual or not isinstance(exists, bool):
            raise ArchivePlanError("remote identity asset observation has an unexpected path or duplicate")
        source_path, sha256, size = entry.get("source_path"), entry.get("sha256"), entry.get("size_bytes")
        if exists:
            if (
                SHA256_PATTERN.fullmatch(str(sha256)) is None
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
            ):
                raise ArchivePlanError("existing remote identity asset needs a valid SHA-256 and size")
            if not _nonblank(source_path):
                raise ArchivePlanError("existing remote identity asset needs downloaded source_path bytes")
            observed_file = _safe_regular_file(Path(source_path), "observed remote company Logo")
            if observed_file in staged_sources or any(
                _same_file(observed_file, staged, "observed and staged Logo")
                for staged in staged_sources
            ):
                raise ArchivePlanError("observed remote company Logo bytes cannot alias the staged Logo input")
            if file_sha256(observed_file) != sha256 or observed_file.stat().st_size != size:
                raise ArchivePlanError("observed remote company Logo hash or size does not match its state")
            replacement_will_remove_reference = bool(
                (
                    confirm_replacement
                    and local_files
                    and (path not in write_expected or write_expected[path] != (sha256, size))
                )
                or (confirm_clear and clear_reference and path in observation_paths)
            )
            if not replacement_will_remove_reference and (size <= 0 or size > 512_000):
                raise ArchivePlanError("preserved remote identity asset must be nonempty and no larger than 512,000 bytes")
            if size <= 512_000:
                try:
                    _validate_observed_logo(observed_file, str(path))
                except ArchivePlanError:
                    if not replacement_will_remove_reference:
                        raise
        elif source_path is not None or sha256 is not None or size is not None:
            raise ArchivePlanError("absent remote identity asset must use null source_path, hash, and size")
        actual[path] = (exists, sha256, size)
    if set(actual) != expected_paths:
        raise ArchivePlanError("remote identity asset observation does not cover every required Logo path")

    if clear_reference:
        return "clear-reference", base_head
    if not local_files:
        exists, _remote_sha, _remote_size = actual[declared_logo_path]
        if not exists:
            raise ArchivePlanError("declared company logo is missing from the observed remote path")
        return "preserve", base_head

    creates = 0
    replacements = 0
    changes = 0
    for path, (sha256, size) in write_expected.items():
        exists, remote_sha, remote_size = actual[path]
        if not exists:
            creates += 1
            changes += 1
        elif (remote_sha, remote_size) != (sha256, size):
            replacements += 1
            changes += 1
    if replacements and not confirm_replacement:
        raise ArchivePlanError("company logo replacement requires explicit authorization")
    if not changes:
        return "noop", base_head
    return ("create" if creates == len(write_expected) else "update"), base_head



def package_action(
    company_root: str,
    local_files: list[dict[str, Any]],
    remote_state: dict[str, Any] | None,
) -> tuple[str, str | None, list[str]]:
    """Resolve create/update/noop for the company's single current package directory."""
    if remote_state is None:
        return "remote-preflight-required", None, []
    if set(remote_state) != COMPANY_PACKAGE_STATE_KEYS:
        raise ArchivePlanError("remote company package state has unexpected or missing fields")
    if remote_state.get("repository") != TARGET_REPOSITORY or remote_state.get("branch") != TARGET_BRANCH:
        raise ArchivePlanError("remote company package state has the wrong repository or branch")
    if remote_state.get("root") != company_root:
        raise ArchivePlanError("remote company package state is for a different company path")
    base_head = str(remote_state.get("base_head", ""))
    if SHA1_PATTERN.fullmatch(base_head) is None or base_head == "0" * 40:
        raise ArchivePlanError("remote company package state lacks an exact base_head")
    exists = remote_state.get("exists")
    if not isinstance(exists, bool):
        raise ArchivePlanError("remote company package state exists must be boolean")
    remote_files = remote_state.get("files")
    if not isinstance(remote_files, list):
        raise ArchivePlanError("remote company package state files must be an array")
    if not exists:
        if remote_files:
            raise ArchivePlanError("absent remote company package directory cannot contain direct files")
        return "create", base_head, []

    expected = {
        Path(item["target_path"]).name: (item["sha256"], item["size_bytes"])
        for item in local_files
    }
    if not {"company.json", "research-manifest.json"}.issubset(expected):
        raise ArchivePlanError("local company package lacks required managed files")
    if not set(expected).issubset(MANAGED_PACKAGE_FILENAMES):
        raise ArchivePlanError("local company package contains an unmanaged target filename")
    actual: dict[str, tuple[str, int]] = {}
    for entry in remote_files:
        if not isinstance(entry, dict):
            raise ArchivePlanError("remote company package state contains an invalid file entry")
        name = entry.get("path")
        sha256 = entry.get("sha256")
        size = entry.get("size_bytes")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or SHA256_PATTERN.fullmatch(str(sha256)) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or name in actual
        ):
            raise ArchivePlanError("remote company package state contains an unsafe or malformed direct file")
        actual[name] = (str(sha256), size)
    managed_actual = {name: value for name, value in actual.items() if name in MANAGED_PACKAGE_FILENAMES}
    if managed_actual == expected:
        return "noop", base_head, []
    delete_paths = [f"{company_root}/{name}" for name in sorted(set(managed_actual) - set(expected))]
    return "update", base_head, delete_paths


def _research_identity(research: dict[str, Any]) -> dict[str, str]:
    identity: dict[str, str] = {}
    for field in IDENTITY_FIELDS:
        value = research.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ArchivePlanError(f"verified manifest research identity lacks {field}")
        identity[field] = value
    return identity


def _state_base_head(state: dict[str, Any], label: str, expected_base_head: str | None) -> str:
    if state.get("repository") != TARGET_REPOSITORY or state.get("branch") != TARGET_BRANCH:
        raise ArchivePlanError(f"{label} has the wrong repository or branch")
    base_head = str(state.get("base_head", ""))
    if SHA1_PATTERN.fullmatch(base_head) is None or base_head == "0" * 40:
        raise ArchivePlanError(f"{label} lacks an exact base_head")
    if expected_base_head is not None and base_head != expected_base_head:
        raise ArchivePlanError(f"{label} and remote company package state came from different base heads")
    return base_head


def slug_binding_action(
    company_slug: str,
    identity: dict[str, str],
    remote_state: dict[str, Any] | None,
    expected_base_head: str | None,
) -> tuple[str, str | None]:
    if remote_state is None:
        return "remote-preflight-required", None
    if set(remote_state) != SLUG_REGISTRY_STATE_KEYS:
        raise ArchivePlanError("remote slug registry state has unexpected or missing fields")
    base_head = _state_base_head(remote_state, "remote slug registry state", expected_base_head)
    if remote_state.get("company_slug") != company_slug:
        raise ArchivePlanError("remote slug registry state is for a different company slug")
    if remote_state.get("identity") != identity:
        raise ArchivePlanError("remote slug registry requested identity does not match the frozen research package")
    slug_exists = remote_state.get("slug_exists")
    if not isinstance(slug_exists, bool):
        raise ArchivePlanError("remote slug registry state slug_exists must be boolean")
    identity_slugs = remote_state.get("identity_slugs")
    if (
        not isinstance(identity_slugs, list)
        or any(not isinstance(item, str) or SLUG_PATTERN.fullmatch(item) is None for item in identity_slugs)
        or len(identity_slugs) != len(set(identity_slugs))
    ):
        raise ArchivePlanError("remote slug registry state identity_slugs must be unique safe slugs")
    slug_identity = remote_state.get("slug_identity")
    if slug_exists:
        if slug_identity != identity:
            raise ArchivePlanError("remote company slug is bound to a different company identity")
        if identity_slugs != [company_slug]:
            raise ArchivePlanError("remote company identity is not bound one-to-one to the requested slug")
        return "verified-bound", base_head
    if slug_identity is not None:
        raise ArchivePlanError("absent remote company slug cannot carry a bound identity")
    if identity_slugs:
        raise ArchivePlanError("remote company identity is already registered under a different slug")
    return "verified-available", base_head


def _canonical_identity(company: dict[str, Any], label: str) -> dict[str, Any]:
    meta = _meta(company, label)
    return {field: meta.get(field) for field in CANONICAL_IDENTITY_FIELDS}


def canonical_preflight_action(
    new_company_path: Path,
    *,
    company_slug: str,
    confirm_same_date_revision: bool,
    confirm_schema_migration: bool,
    remote_state: dict[str, Any] | None,
    expected_base_head: str | None,
    locked_schema_version: str,
) -> tuple[str, str | None, bool | None]:
    if remote_state is None:
        return "remote-preflight-required", None, None
    if set(remote_state) != CANONICAL_STATE_KEYS:
        raise ArchivePlanError("remote canonical state has unexpected or missing fields")
    base_head = _state_base_head(remote_state, "remote canonical state", expected_base_head)
    expected_path = f"companies/{company_slug}/company.json"
    if remote_state.get("path") != expected_path:
        raise ArchivePlanError("remote canonical state is for a different company path")
    exists = remote_state.get("exists")
    if not isinstance(exists, bool):
        raise ArchivePlanError("remote canonical state exists must be boolean")
    content = remote_state.get("content")
    if not exists:
        if content is not None:
            raise ArchivePlanError("absent remote canonical state cannot contain file content")
        return "create", base_head, False
    if not isinstance(content, dict):
        raise ArchivePlanError("existing remote canonical state requires content metadata")
    if set(content) != {"source_path", "sha256", "size_bytes", "identity"}:
        raise ArchivePlanError("remote canonical content must contain only source_path, sha256, size_bytes, and identity")
    source_value = content.get("source_path")
    if not isinstance(source_value, str) or not source_value:
        raise ArchivePlanError("remote canonical content requires a source_path")
    source_path = _safe_regular_file(Path(source_value), "remote canonical company.json")
    sha256 = content.get("sha256")
    size_bytes = content.get("size_bytes")
    if SHA256_PATTERN.fullmatch(str(sha256)) is None:
        raise ArchivePlanError("remote canonical content has an invalid SHA-256")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        raise ArchivePlanError("remote canonical content has an invalid size")
    if file_sha256(source_path) != sha256 or source_path.stat().st_size != size_bytes:
        raise ArchivePlanError("remote canonical content hash or size does not match the downloaded file")
    existing_company = _read_object(source_path, "remote canonical company.json")
    if content.get("identity") != _canonical_identity(existing_company, "remote canonical company.json"):
        raise ArchivePlanError("remote canonical content identity does not match the downloaded file")
    action = canonical_action(
        new_company_path,
        existing_company_path=source_path,
        canonical_absent=False,
        confirm_same_date_revision=confirm_same_date_revision,
        confirm_schema_migration=confirm_schema_migration,
        locked_schema_version=locked_schema_version,
    )
    return action, base_head, True


def build_archive_plan(
    root: Path,
    schema_path: Path,
    *,
    company_slug: str,
    strategy: str,
    write_authorized: bool = False,
    direct_main_authorized: bool = False,
    remote_company_state: dict[str, Any] | None = None,
    remote_slug_registry_state: dict[str, Any] | None = None,
    remote_canonical_state: dict[str, Any] | None = None,
    identity_assets_root: Path | None = None,
    remote_identity_assets_state: dict[str, Any] | None = None,
    confirm_same_date_revision: bool = False,
    confirm_schema_migration: bool = False,
    confirm_identity_asset_replacement: bool = False,
    confirm_identity_asset_clear: bool = False,
    confirm_new_company_without_logo: bool = False,
    trusted_lock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise ArchivePlanError("research package root must be a non-symlink directory")
    if schema_path.is_symlink() or not schema_path.is_file():
        raise ArchivePlanError("Schema must be a non-symlink regular file")
    if SLUG_PATTERN.fullmatch(company_slug) is None:
        raise ArchivePlanError("company-slug must contain only lowercase letters, digits, and single hyphens")
    if strategy not in {"pull-request", "direct-main"}:
        raise ArchivePlanError("strategy must be pull-request or direct-main")
    if strategy == "direct-main" and not direct_main_authorized:
        raise ArchivePlanError("direct-main requires explicit direct-main authorization")

    root = root.resolve()
    schema_path = schema_path.resolve()
    manifest_path = _safe_regular_file(root / "research-manifest.json", "research-manifest.json")
    if trusted_lock is None:
        trusted_lock = _read_object(TRUSTED_LOCK_PATH, "trusted specification lock")
    company_schema_lock = trusted_lock.get("company_schema")
    if not isinstance(company_schema_lock, dict):
        raise ArchivePlanError("trusted specification lock lacks company_schema")
    locked_schema_version = company_schema_lock.get("schema_version")
    if not isinstance(locked_schema_version, str) or not locked_schema_version.strip():
        raise ArchivePlanError("trusted specification lock has an invalid company Schema version")
    manifest, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock, company_slug)
    if manifest is None or errors:
        detail = "; ".join(errors) if errors else "manifest could not be verified"
        raise ArchivePlanError(f"frozen package verification failed: {detail}")

    fresh_findings = validate_research_package(root, schema_path, "full", company_slug)
    fresh_errors = [item for item in fresh_findings if item.severity == "error"]
    fresh_warnings = [item for item in fresh_findings if item.severity == "warning"]
    if fresh_errors:
        codes = ", ".join(sorted({item.code for item in fresh_errors}))
        raise ArchivePlanError(f"fresh full validation failed: {codes}")
    recorded_validation = manifest.get("validation")
    if not isinstance(recorded_validation, dict):
        raise ArchivePlanError("verified manifest lacks validation metadata")
    if recorded_validation.get("errors") != len(fresh_errors) or recorded_validation.get("warnings") != len(fresh_warnings):
        raise ArchivePlanError("fresh validation counts do not match the frozen manifest")
    if fresh_warnings and manifest.get("warning_acknowledged") is not True:
        raise ArchivePlanError("fresh validation warnings were not acknowledged")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ArchivePlanError("verified manifest has no files array")
    company_root = f"companies/{company_slug}"
    package_files: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ArchivePlanError("verified manifest contains an invalid file entry")
        name = entry["path"]
        source = _safe_regular_file(root / name, f"frozen file {name}")
        package_files.append(
            {
                "source_path": str(source),
                "target_path": f"{company_root}/{name}",
                "sha256": file_sha256(source),
                "size_bytes": source.stat().st_size,
            }
        )
    package_files.append(
        {
            "source_path": str(manifest_path),
            "target_path": f"{company_root}/research-manifest.json",
            "sha256": file_sha256(manifest_path),
            "size_bytes": manifest_path.stat().st_size,
        }
    )
    scan_sensitive_material([Path(item["source_path"]) for item in package_files])
    remote_action, base_head, delete_paths = package_action(
        company_root,
        package_files,
        remote_company_state,
    )

    company_path = _safe_regular_file(root / "company.json", "company.json")
    company = _read_object(company_path, "company.json")
    research = manifest.get("research") if isinstance(manifest.get("research"), dict) else {}
    identity = _research_identity(research)
    slug_action, slug_head = slug_binding_action(
        company_slug,
        identity,
        remote_slug_registry_state,
        base_head,
    )
    canonical, canonical_head, canonical_exists = canonical_preflight_action(
        company_path,
        company_slug=company_slug,
        confirm_same_date_revision=confirm_same_date_revision,
        confirm_schema_migration=confirm_schema_migration,
        remote_state=remote_canonical_state,
        expected_base_head=base_head,
        locked_schema_version=locked_schema_version,
    )
    if (
        remote_company_state is not None
        and remote_slug_registry_state is not None
        and remote_canonical_state is not None
    ):
        observed_files = remote_company_state.get("files")
        company_entries = (
            [item for item in observed_files if isinstance(item, dict) and item.get("path") == "company.json"]
            if isinstance(observed_files, list)
            else []
        )
        canonical_in_package = bool(remote_company_state.get("exists") and len(company_entries) == 1)
        if canonical_exists is not canonical_in_package:
            raise ArchivePlanError("remote company package and canonical observations disagree on company.json existence")
        if canonical_exists:
            canonical_content = remote_canonical_state.get("content")
            if not isinstance(canonical_content, dict) or (
                company_entries[0].get("sha256"),
                company_entries[0].get("size_bytes"),
            ) != (
                canonical_content.get("sha256"),
                canonical_content.get("size_bytes"),
            ):
                raise ArchivePlanError("remote company package and canonical observations disagree on company.json bytes")
        if remote_slug_registry_state.get("slug_exists") is not canonical_exists:
            raise ArchivePlanError("remote slug registry and canonical observations disagree on company existence")
    if identity_assets_root is not None:
        resolved_identity_assets_root = identity_assets_root.resolve()
        try:
            resolved_identity_assets_root.relative_to(root)
        except ValueError:
            pass
        else:
            raise ArchivePlanError("identity assets root must stay outside the frozen research package")
    logo_path = _company_logo_asset_path(company, company_slug)
    identity_files, crop_provenance = prepare_identity_asset_files(
        identity_assets_root,
        company_slug=company_slug,
        company=company,
    )
    new_company_without_logo = canonical_exists is False and logo_path is None
    if confirm_new_company_without_logo and not new_company_without_logo:
        raise ArchivePlanError(
            "--confirm-new-company-without-logo is valid only after exact remote observation proves a new company with no verified Logo"
        )
    if new_company_without_logo and not confirm_new_company_without_logo:
        raise ArchivePlanError(
            "new company without a verified official Logo requires explicit no-Logo delivery authorization"
        )
    new_logo_record = company["brand_identity"]["company_logo"]
    existing_logo_path: str | None = None
    existing_logo_record: Any = None
    if canonical_exists is True and remote_canonical_state is not None:
        content = remote_canonical_state.get("content") if isinstance(remote_canonical_state, dict) else None
        source_value = content.get("source_path") if isinstance(content, dict) else None
        existing_company = _read_object(
            _safe_regular_file(Path(source_value), "remote canonical company.json"),
            "remote canonical company.json",
        )
        existing_logo_path, existing_logo_record = _untrusted_existing_logo(existing_company, company_slug)

    staged_targets = {item["target_path"] for item in identity_files}
    logo_metadata_changed = canonical_exists is True and (
        existing_logo_path != logo_path or existing_logo_record != new_logo_record
    )
    existing_record_is_absent = isinstance(existing_logo_record, dict) and set(existing_logo_record) == {
        "asset_path",
        "source_url",
        "alt",
        "is_official",
    } and (
        existing_logo_record.get("asset_path") is None
        and existing_logo_record.get("source_url") is None
        and existing_logo_record.get("alt") is None
        and existing_logo_record.get("is_official") is False
    )
    existing_logo_claimed = existing_logo_record is not None and not existing_record_is_absent
    clear_reference = bool(
        logo_metadata_changed
        and logo_path is None
        and existing_logo_claimed
    )
    if logo_metadata_changed and logo_path is not None and logo_path not in staged_targets:
        raise ArchivePlanError("company logo metadata changed without staging the verified canonical logo")
    if clear_reference and not confirm_identity_asset_clear:
        raise ArchivePlanError("clearing a claimed company Logo reference requires explicit authorization")
    if (
        logo_metadata_changed
        and existing_logo_claimed
        and not clear_reference
        and not confirm_identity_asset_replacement
    ):
        raise ArchivePlanError("company logo path or metadata replacement requires explicit authorization")

    observation_paths = {path for path in (logo_path, existing_logo_path) if path is not None}
    identity_action, identity_head = identity_asset_action(
        company_slug,
        identity_files,
        logo_path,
        observation_paths,
        remote_identity_assets_state,
        base_head,
        confirm_replacement=confirm_identity_asset_replacement,
        clear_reference=clear_reference,
        confirm_clear=confirm_identity_asset_clear,
    )
    if remote_identity_assets_state is not None and remote_company_state is not None:
        observed_assets = remote_identity_assets_state.get("assets")
        if (
            isinstance(observed_assets, list)
            and any(isinstance(item, dict) and item.get("exists") is True for item in observed_assets)
            and remote_company_state.get("exists") is not True
        ):
            raise ArchivePlanError("remote identity asset and company package observations disagree on directory existence")

    if logo_path in staged_targets:
        logo_guard = "staged"
    elif clear_reference:
        logo_guard = "cleared-explicitly" if identity_action == "clear-reference" else "remote-preflight-required"
    elif remote_canonical_state is None:
        logo_guard = "remote-preflight-required"
    elif canonical_exists is False:
        if logo_path is not None:
            raise ArchivePlanError("new company.json declares a company logo but no verified logo was staged")
        logo_guard = "missing-explicitly-authorized"
    else:
        if logo_path is None:
            logo_guard = "not-declared"
        elif identity_action == "preserve":
            logo_guard = "preserve-existing"
        else:
            logo_guard = "remote-preflight-required"

    ready_for_write = (
        write_authorized
        and remote_action in {"create", "update", "noop"}
        and slug_action in {"verified-bound", "verified-available"}
        and canonical in {"create", "update", "update-confirmed-revision", "update-confirmed-schema-migration", "noop"}
        and identity_action in {"preserve", "create", "update", "noop", "clear-reference"}
        and logo_guard in {
            "not-declared",
            "staged",
            "preserve-existing",
            "cleared-explicitly",
            "missing-explicitly-authorized",
        }
    )
    return {
        "plan_version": "9.4",
        "repository": TARGET_REPOSITORY,
        "target_branch": TARGET_BRANCH,
        "strategy": strategy,
        "delivery_mode": "single-company-directory",
        "write_authorized": write_authorized,
        "direct_main_authorized": direct_main_authorized,
        "requires_atomic_commit": True,
        "force_update_allowed": False,
        "base_head": base_head,
        "ready_for_write": ready_for_write,
        "source": {
            "manifest_sha256": file_sha256(manifest_path),
            "manifest_version": manifest.get("manifest_version"),
            "human_review_status": manifest.get("human_review_status"),
            "data_as_of": research.get("data_as_of"),
            "valuation_date": research.get("valuation_date"),
            "research_protocol": manifest.get("research_protocol"),
            "integrity_profile": manifest.get("integrity_profile"),
            "execution_integrity": manifest.get("execution_integrity"),
            "validator_sha256": recorded_validation.get("validator_sha256"),
            "specification": manifest.get("specification"),
        },
        "slug_binding": {
            "company_slug": company_slug,
            "identity": identity,
            "remote_action": slug_action,
            "base_head": slug_head,
        },
        "company_package": {
            "root": company_root,
            "remote_action": remote_action,
            "replacement_policy": "managed-research-files",
            "preserve_unmanaged_company_assets": True,
            "files": package_files,
            "delete_paths": delete_paths,
        },
        "identity_assets": {
            "remote_action": identity_action,
            "remote_base_head": identity_head,
            "logo_guard": logo_guard,
            "company_logo_asset_path": logo_path,
            "preparation": (
                "verified-center-square-crop"
                if crop_provenance is not None
                else ("official-original-square" if identity_files else "not-staged")
            ),
            "official_source_derived": crop_provenance is not None,
            "crop_provenance": crop_provenance,
            "replacement_confirmed": confirm_identity_asset_replacement,
            "clear_confirmed": confirm_identity_asset_clear,
            "new_company_without_logo_confirmed": confirm_new_company_without_logo,
            "preserve_unlisted_assets": True,
            "files": identity_files,
            "delete_paths": [],
        },
        "canonical_guard": {
            "source_path": str(company_path),
            "target_path": f"companies/{company_slug}/company.json",
            "sha256": file_sha256(company_path),
            "size_bytes": company_path.stat().st_size,
            "action": canonical,
            "remote_base_head": canonical_head,
            "remote_exists": canonical_exists,
            "schema_migration_confirmed": confirm_schema_migration,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Accepted frozen research package root")
    parser.add_argument("--schema", type=Path, required=True, help="Locked company.schema.json used to freeze")
    parser.add_argument("--company-slug", required=True)
    parser.add_argument("--strategy", choices=("pull-request", "direct-main"), default="pull-request")
    parser.add_argument("--confirm-write-authorization", action="store_true")
    parser.add_argument("--confirm-direct-main-authorization", action="store_true")
    parser.add_argument(
        "--remote-company-state",
        type=Path,
        help="Connector-produced JSON describing direct files in companies/<company-slug> at one exact main head",
    )
    parser.add_argument(
        "--remote-slug-registry-state",
        type=Path,
        help="Connector-produced exact-main-head slug/identity registry observation",
    )
    parser.add_argument(
        "--remote-canonical-state",
        type=Path,
        help="Connector-produced exact-main-head canonical path/content observation",
    )
    parser.add_argument(
        "--identity-assets-root",
        type=Path,
        help=(
            "Optional staging directory outside the frozen package containing one verified square logo.svg/logo.png, "
            "or logo.png + logo-original.png + logo-provenance.json for a proven center crop"
        ),
    )
    parser.add_argument(
        "--remote-identity-assets-state",
        type=Path,
        help="Exact-main-head observation plus downloaded bytes for every declared, old, or staged company Logo path",
    )
    parser.add_argument(
        "--confirm-same-date-revision",
        action="store_true",
        help="Allow an accepted correction to replace different canonical content for the same data_as_of",
    )
    parser.add_argument(
        "--confirm-schema-migration",
        action="store_true",
        help="Allow an accepted older-Schema package to be replaced by a fully rebuilt package under the current locked Schema",
    )
    parser.add_argument(
        "--confirm-identity-asset-replacement",
        action="store_true",
        help="Allow the explicitly staged verified company Logo to replace different bytes at the same path",
    )
    parser.add_argument(
        "--confirm-identity-asset-clear",
        action="store_true",
        help="Allow an accepted null-Logo package to clear a claimed legacy Logo reference without deleting the old file",
    )
    parser.add_argument(
        "--confirm-new-company-without-logo",
        action="store_true",
        help="Allow first delivery of a new company only after the user explicitly accepts the documented missing official Logo",
    )
    parser.add_argument("--output", type=Path, help="Write plan outside the frozen package; default stdout")
    args = parser.parse_args()

    try:
        remote_company_state = (
            _read_object(
                _safe_regular_file(args.remote_company_state, "remote company package state"),
                "remote company package state",
            )
            if args.remote_company_state is not None
            else None
        )
        remote_slug_registry_state = (
            _read_object(
                _safe_regular_file(args.remote_slug_registry_state, "remote slug registry state"),
                "remote slug registry state",
            )
            if args.remote_slug_registry_state is not None
            else None
        )
        remote_canonical_state = (
            _read_object(
                _safe_regular_file(args.remote_canonical_state, "remote canonical state"),
                "remote canonical state",
            )
            if args.remote_canonical_state is not None
            else None
        )
        remote_identity_assets_state = (
            _read_object(
                _safe_regular_file(args.remote_identity_assets_state, "remote identity asset state"),
                "remote identity asset state",
            )
            if args.remote_identity_assets_state is not None
            else None
        )
        plan = build_archive_plan(
            args.root,
            args.schema,
            company_slug=args.company_slug,
            strategy=args.strategy,
            write_authorized=args.confirm_write_authorization,
            direct_main_authorized=args.confirm_direct_main_authorization,
            remote_company_state=remote_company_state,
            remote_slug_registry_state=remote_slug_registry_state,
            remote_canonical_state=remote_canonical_state,
            identity_assets_root=args.identity_assets_root,
            remote_identity_assets_state=remote_identity_assets_state,
            confirm_same_date_revision=args.confirm_same_date_revision,
            confirm_schema_migration=args.confirm_schema_migration,
            confirm_identity_asset_replacement=args.confirm_identity_asset_replacement,
            confirm_identity_asset_clear=args.confirm_identity_asset_clear,
            confirm_new_company_without_logo=args.confirm_new_company_without_logo,
        )
        if args.output is not None:
            output = args.output
            if output.is_symlink():
                raise ArchivePlanError("output cannot be a symlink")
            root_resolved = args.root.resolve()
            output_resolved = output.resolve(strict=False)
            try:
                output_resolved.relative_to(root_resolved)
            except ValueError:
                pass
            else:
                raise ArchivePlanError("delivery plan must be written outside the frozen package")
            skill_root = Path(__file__).resolve().parents[1]
            try:
                output_resolved.relative_to(skill_root)
            except ValueError:
                pass
            else:
                raise ArchivePlanError("delivery plan cannot overwrite files inside the Skill")
            forbidden = {
                args.schema.resolve(),
                TRUSTED_LOCK_PATH.resolve(),
                *(Path(item["source_path"]).resolve() for item in plan["company_package"]["files"]),
            }
            for observation in (
                args.remote_company_state,
                args.remote_slug_registry_state,
                args.remote_canonical_state,
                args.remote_identity_assets_state,
            ):
                if observation is not None:
                    forbidden.add(observation.resolve())
            content = remote_canonical_state.get("content") if isinstance(remote_canonical_state, dict) else None
            if isinstance(content, dict) and isinstance(content.get("source_path"), str):
                forbidden.add(Path(content["source_path"]).resolve())
            observed_assets = (
                remote_identity_assets_state.get("assets")
                if isinstance(remote_identity_assets_state, dict)
                else None
            )
            if isinstance(observed_assets, list):
                for entry in observed_assets:
                    source_path = entry.get("source_path") if isinstance(entry, dict) else None
                    if isinstance(source_path, str) and source_path:
                        forbidden.add(Path(source_path).resolve())
            forbidden.update(Path(item["source_path"]).resolve() for item in plan["identity_assets"]["files"])
            output_aliases_input = output_resolved in forbidden
            if output.exists() and not output_aliases_input:
                output_aliases_input = any(
                    _same_file(output, input_path, "delivery output and input")
                    for input_path in forbidden
                )
            if output_aliases_input:
                raise ArchivePlanError("delivery plan output would overwrite an input or frozen file")
            if args.identity_assets_root is not None:
                try:
                    output_resolved.relative_to(args.identity_assets_root.resolve())
                except ValueError:
                    pass
                else:
                    raise ArchivePlanError("delivery plan must be written outside the identity assets root")
            output.parent.mkdir(parents=True, exist_ok=True)
            write_json(output, plan)
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
    except (ArchivePlanError, OSError) as exc:
        print(f"Delivery plan refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
