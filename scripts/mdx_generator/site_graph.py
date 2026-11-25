from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import CATEGORY_ORDER, GENERIC_JSON_STEMS, POISON_PAGE_TITLES
from .preprocessor import clean_page_title, load_and_check_json_file, slugify

_LEADING_NUM_RE = re.compile(r"^\d+[-_\s]+")
_FOLDER_SUFFIX_RE = re.compile(
    r"[-_\s]+(?:govcon[-_\s]*360[-_\s]*(?:internal|public[-_\s]*site)?(?:[-_\s]*liferay)?|asponte[-_\s]*technology[-_\s]*inc|liferay)$",
    re.IGNORECASE,
)


@dataclass
class PlannedDoc:
    json_path: Path
    route: str
    title: str
    category_slug: str
    category_label: str
    doc_slug: str
    rel_doc_path: str  # e.g. "market-intel/awards.mdx"


def normalize_route_path(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url.strip())
    path = parsed.path if parsed.scheme else raw_url.strip()
    path = path.split("?", 1)[0].split("#", 1)[0].strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or "/"


def _title_from_folder_name(folder_name: str) -> str:
    """Turn '009-vendors-asponte-technology-inc' into 'Vendors'."""
    name = _LEADING_NUM_RE.sub("", (folder_name or "").strip())
    # Strip trailing tenant/portal suffixes repeatedly if chained
    prev = None
    while prev != name:
        prev = name
        name = _FOLDER_SUFFIX_RE.sub("", name).strip("-_ ")
    if not name or name.lower() in GENERIC_JSON_STEMS:
        return ""
    return " ".join(w.capitalize() if w.islower() else w for w in re.split(r"[-_\s]+", name) if w)


def _extract_first_h1(rec: dict[str, Any]) -> str:
    headings = rec.get("headings")
    if isinstance(headings, dict):
        for level in ("h1", "h2"):
            items = headings.get(level) or []
            for h in items:
                if isinstance(h, str) and h.strip():
                    return h.strip()
    elif isinstance(headings, list):
        for h in headings:
            if isinstance(h, str) and h.strip():
                return h.strip()
    return ""


def _resolve_frontend_title(jf: Path, rec: dict[str, Any]) -> str:
    """Pick the cleanest human-readable title, never falling back to generic stems like 'page'."""
    candidates = [
        rec.get("pageHeading"),
        rec.get("pageTitle"),
        rec.get("title"),
        _extract_first_h1(rec),
        _title_from_folder_name(jf.parent.name),
        "" if jf.stem.lower() in GENERIC_JSON_STEMS else jf.stem,
    ]
    fallback_folder = _title_from_folder_name(jf.parent.name) or "Overview"
    for cand in candidates:
        if not cand or not isinstance(cand, str):
            continue
        cleaned = clean_page_title(cand, fallback_folder)
        if cleaned and cleaned.lower() not in GENERIC_JSON_STEMS:
            return cleaned
    return fallback_folder


def infer_category(route: str, title: str, nav_route_to_cat: dict[str, str]) -> tuple[str, str]:
    """Assign a page to its module category using navigation tree first, then route/title heuristics."""
    norm = normalize_route_path(route)
    low_title = title.lower()

    if norm in ("/", "/login", "/sign-in", "/forgot-password", "/reset-password", "/dashboard", "/downloads"):
        return "getting-started", CATEGORY_ORDER["getting-started"][0]
    if low_title in ("signing in", "dashboard", "finding your way around"):
        return "getting-started", CATEGORY_ORDER["getting-started"][0]

    if norm in nav_route_to_cat:
        cat_slug = nav_route_to_cat[norm]
        label = CATEGORY_ORDER.get(cat_slug, (cat_slug.replace("-", " ").title(), 50))[0]
        return cat_slug, label

    if norm.startswith("/data/") or any(k in norm for k in ("award", "solicitation", "vendor", "agenc", "people")):
        return "market-intel", CATEGORY_ORDER["market-intel"][0]
    if any(k in norm for k in ("lead", "recompete", "procurement-notice", "capture")):
        return "lead-prospector", CATEGORY_ORDER["lead-prospector"][0]
    if any(k in norm for k in ("opportunit", "account", "contact")):
        return "business-development", CATEGORY_ORDER["business-development"][0]
    if any(k in norm for k in ("partner", "teaming", "deal")):
        return "teaming-partnerships", CATEGORY_ORDER["teaming-partnerships"][0]
    if any(k in norm for k in ("proposal", "rfp")):
        return "proposals", CATEGORY_ORDER["proposals"][0]
    if any(k in norm for k in ("contract", "clause", "wage")):
        return "contracts", CATEGORY_ORDER["contracts"][0]
    if any(k in norm for k in ("user", "admin", "notification", "company-information", "saved-filter", "analytics")):
        return "administration", CATEGORY_ORDER["administration"][0]
    if any(k in norm for k in ("glossary", "naics", "psc", "sin", "sic", "terminology")):
        return "reference", CATEGORY_ORDER["reference"][0]

    return "general", CATEGORY_ORDER["general"][0]


def _extract_nav_categories(raw: dict[str, Any]) -> dict[str, str]:
    """Read dropdown-toggle -> dropdown-item pairs from crawled navigation arrays."""
    mapping: dict[str, str] = {}
    for nav in raw.get("navigation") or []:
        if not isinstance(nav, dict):
            continue
        current_cat = ""
        for lnk in nav.get("links") or []:
            if not isinstance(lnk, dict):
                continue
            cls = (lnk.get("className") or "").lower()
            text = (lnk.get("text") or "").strip()
            href = normalize_route_path(lnk.get("href") or "")
            if "dropdown-toggle" in cls and text:
                current_cat = slugify(text)
            elif "dropdown-item" in cls and current_cat and href and href != "/":
                mapping[href] = current_cat
    return mapping


def build_site_graph(json_files: list[Path]) -> tuple[list[PlannedDoc], dict[str, str]]:
    """Pass 1: Deduplicate crawled pages and build route -> relative doc path registry."""
    nav_route_to_cat: dict[str, str] = {}
    raw_records: list[tuple[Path, dict[str, Any]]] = []

    for jf in json_files:
        try:
            raw = load_and_check_json_file(jf)
        except Exception:
            continue
        if isinstance(raw, dict):
            nav_route_to_cat.update(_extract_nav_categories(raw))
            raw_records.append((jf, raw))

    planned: list[PlannedDoc] = []
    seen_dedupe_keys: set[tuple[str, str]] = set()
    used_rel_paths: set[str] = set()
    route_to_rel_path: dict[str, str] = {}

    for jf, rec in raw_records:
        title = _resolve_frontend_title(jf, rec)
        if title.lower() in POISON_PAGE_TITLES:
            continue

        url = rec.get("pageUrl") or rec.get("url") or rec.get("route") or f"/{jf.parent.name}"
        route = normalize_route_path(str(url))

        # Deduplicate identical pages (e.g., "/" and "/login" both yielding "Signing in")
        dedupe_key = (route, title.lower())
        if dedupe_key in seen_dedupe_keys:
            continue
        seen_dedupe_keys.add(dedupe_key)

        cat_slug, cat_label = infer_category(route, title, nav_route_to_cat)
        doc_slug = slugify(title if route == "/" else route.split("/")[-1])
        rel_path = f"{cat_slug}/{doc_slug}.mdx"

        if rel_path in used_rel_paths:
            continue  # Skip exact duplicate screen

        used_rel_paths.add(rel_path)
        route_to_rel_path[route] = rel_path
        planned.append(PlannedDoc(jf, route, title, cat_slug, cat_label, doc_slug, rel_path))

    return planned, route_to_rel_path


def compute_relative_doc_link(from_rel_path: str, to_rel_path: str) -> str:
    """Compute a Docusaurus-valid relative link between two .mdx files in different category folders."""
    from_dir = os.path.dirname(from_rel_path)
    rel = os.path.relpath(to_rel_path, start=from_dir).replace("\\", "/")
    if not rel.startswith("."):
        rel = "./" + rel
    return rel


def build_welcome_mdx(portal_label: str, planned_docs: list[PlannedDoc]) -> str:
    """Auto-generate a clean Welcome landing page (matching Image 1) with inline links."""
    by_cat: dict[str, list[PlannedDoc]] = {}
    for doc in planned_docs:
        by_cat.setdefault(doc.category_label, []).append(doc)

    lines = [
        "---",
        'id: "welcome"',
        f'title: "Welcome to {portal_label}"',
        'sidebar_label: "Welcome"',
        "sidebar_position: 0",
        'slug: "/"',
        f'description: "Documentation home for {portal_label}."',
        "---",
        "",
        f"{portal_label} brings federal market data, capture workflows, and team collaboration into one portal.",
        "",
        "## Start here",
        "",
    ]

    getting_started = by_cat.get("Getting started", [])
    if getting_started:
        for doc in getting_started[:5]:
            lines.append(f"- [{doc.title}](./{doc.rel_doc_path})")
    else:
        for doc in planned_docs[:3]:
            lines.append(f"- [{doc.title}](./{doc.rel_doc_path})")

    lines += ["", "## Sections", ""]
    for cat_label, docs in by_cat.items():
        if cat_label == "Getting started":
            continue
        sample_links = ", ".join(f"[{d.title}](./{d.rel_doc_path})" for d in docs[:4])
        lines.append(f"- **{cat_label}**: {sample_links}")

    lines.append("")
    return "\n".join(lines)