#!/usr/bin/env python3
"""Audit whether source document titles appear in public web search results.

The script reads source titles from data/content_lists/*_content_list.json,
queries Bing RSS, scores the first results for title relevance, and writes a
CSV plus JSON summary under reports/.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTENT_LISTS_DIR = PROJECT_ROOT / "data" / "content_lists"
REPORTS_DIR = PROJECT_ROOT / "reports"
CACHE_DIR = REPORTS_DIR / ".public_search_cache"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/124.0 Safari/537.36"
)

GENERIC_DOMAINS = {
    "aiqicha.baidu.com",
    "baike.baidu.com",
    "chashudi.com",
    "countrycodebase.com",
    "dataunitconverter.com",
    "eastmoney.com",
    "gbt.org.cn",
    "gongsi.com.cn",
    "gsxt.gov.cn",
    "hitman.huijiwiki.com",
    "jobui.com",
    "niuqicha.com",
    "quote.eastmoney.com",
    "qcc.com",
    "snh48.com",
    "tianyancha.com",
    "wordplays.com",
    "49tk.la",
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "part",
    "pdf",
    "doc",
    "docx",
    "html",
    "www",
    "com",
    "cn",
    "2026",
}

STANDARD_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:GB\s*/?\s*T|GB[_\s]*T|GBT|GB|DL\s*/?\s*T|DLT|DL|NB\s*/?\s*T|"
    r"NB|HJ|JGJ|JG\s*/?\s*T|SL|Q\s*/?\s*GDW|T\s*/?\s*CEC)"
    r"[\s_/.-]*[A-Za-z0-9.]+(?:[\s_/.-]*\d{4})?(?![A-Za-z0-9])",
    re.IGNORECASE,
)
DOC_NO_RE = re.compile(r"[\u4e00-\u9fffA-Za-z]{1,12}[〔\[]\d{4}[〕\]]\s*\d+\s*号")
FBM_RE = re.compile(r"\(?FBM-CLI-[^)]+?\)?", re.IGNORECASE)
LEADING_NO_RE = re.compile(r"^\s*\d{1,3}(?:[.、]\s*|-\s*|\s+|(?=【))")


@dataclass
class SearchItem:
    title: str
    link: str
    description: str


@dataclass
class AuditRow:
    index: int
    source_title: str
    query: str
    status: str
    confidence: str
    score: float
    matched_title: str
    matched_url: str
    matched_domain: str
    evidence: str
    notes: str


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u3000", " ")).strip()


def strip_title_noise(title: str) -> str:
    value = re.sub(r"_content_list(?:\.json)?$", "", title)
    value = normalize_spaces(value)
    value = value.replace("／", "/").replace("∕", "/").replace("╱", "/")
    value = value.replace(" - 副本", "").replace("- 副本", "")
    value = value.replace("（高清版）", "").replace("(高清版)", "")
    value = FBM_RE.sub("", value)
    value = LEADING_NO_RE.sub("", value)
    return normalize_spaces(value.strip(" -_"))


def split_cjk_terms(text: str) -> list[str]:
    terms: list[str] = []
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(chunk) <= 6:
            terms.append(chunk)
        else:
            for size in (6, 4):
                for i in range(0, len(chunk) - size + 1, size):
                    token = chunk[i : i + size]
                    if len(token) >= 2:
                        terms.append(token)
    return terms


def tokenize(text: str) -> set[str]:
    text = normalize_spaces(text).lower()
    terms = set(split_cjk_terms(text))
    for token in re.findall(r"[a-z0-9]+(?:/[a-z0-9]+)?", text):
        if len(token) >= 2 and token not in STOPWORDS:
            terms.add(token)
    return terms


def domain_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def build_query(title: str) -> str:
    return build_queries(title)[0]


def build_queries(title: str) -> list[str]:
    cleaned = strip_title_noise(title)
    queries: list[str] = []
    doc_no = DOC_NO_RE.search(cleaned)
    codes = STANDARD_CODE_RE.findall(cleaned)
    if doc_no:
        rest = cleaned.replace(doc_no.group(0), "")
        rest = normalize_spaces(rest)
        queries.append(f'"{doc_no.group(0)}" {rest[:42]}'.strip())
        queries.append(cleaned)
    elif codes:
        code = normalize_spaces(codes[0].replace("_", " "))
        without_code = normalize_spaces(STANDARD_CODE_RE.sub("", cleaned))
        queries.append(f'"{code}" {without_code[:56]}'.strip())
        queries.append(f"{code} {without_code[:70]}".strip())
        queries.append(f'"{cleaned[:90]}"')
    else:
        quoted = cleaned if len(cleaned) <= 90 else cleaned[:90]
        queries.append(f'"{quoted}"')
        queries.append(cleaned[:110])

    deduped: list[str] = []
    for query in queries:
        query = normalize_spaces(query)
        if query and query not in deduped:
            deduped.append(query)
    return deduped or [f'"{cleaned}"']


def cache_path(query: str) -> Path:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.xml"


def fetch_bing_rss(query: str, delay_seconds: float, timeout: int, cache: bool) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(query)
    if cache and path.exists():
        return path.read_text(encoding="utf-8", errors="replace")

    params = urllib.parse.urlencode(
        {"format": "rss", "q": query, "setlang": "zh-CN", "cc": "CN"}
    )
    request = urllib.request.Request(
        f"https://www.bing.com/search?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,text/xml,*/*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    if cache:
        path.write_text(body, encoding="utf-8")
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    return body


def parse_rss(body: str) -> list[SearchItem]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    items: list[SearchItem] = []
    for item in root.findall("./channel/item"):
        title = html.unescape(item.findtext("title", default=""))
        link = html.unescape(item.findtext("link", default=""))
        description = html.unescape(item.findtext("description", default=""))
        items.append(
            SearchItem(
                title=normalize_spaces(title),
                link=normalize_spaces(link),
                description=normalize_spaces(description),
            )
        )
    return items


def score_item(source_title: str, item: SearchItem) -> float:
    cleaned = strip_title_noise(source_title)
    haystack = f"{item.title} {item.description}"
    haystack_norm = normalize_spaces(haystack).lower()
    cleaned_norm = normalize_spaces(cleaned).lower()
    domain = domain_from_url(item.link)

    if re.fullmatch(r"\d{1,3}号附[件加]\d+(?:\s*\(\d+\))?", cleaned):
        return 1.0 if cleaned_norm and cleaned_norm in haystack_norm else 0.0

    if "共 0 条" in haystack or "共0条" in haystack or "1 / 0" in haystack:
        return 0.0

    if cleaned_norm and cleaned_norm in haystack_norm:
        return 1.0

    codes = STANDARD_CODE_RE.findall(cleaned)
    code_bonus = 0.0
    for code in codes:
        code_norm = normalize_code(code)
        hay_no_space = normalize_code(haystack)
        if code_norm and code_norm in hay_no_space:
            code_bonus = max(code_bonus, 0.35)

    doc_no = DOC_NO_RE.search(cleaned)
    doc_bonus = 0.0
    if doc_no and normalize_spaces(doc_no.group(0)).lower() in haystack_norm:
        doc_bonus = 0.4

    source_terms = tokenize(cleaned)
    result_terms = tokenize(haystack)
    if not source_terms:
        overlap_score = 0.0
    else:
        overlap_score = len(source_terms & result_terms) / len(source_terms)

    generic_penalty = 0.35 if domain in GENERIC_DOMAINS else 0.0
    return max(0.0, min(1.0, overlap_score + code_bonus + doc_bonus - generic_penalty))


def normalize_code(text: str) -> str:
    value = text.lower()
    value = value.replace("／", "/").replace("∕", "/").replace("╱", "/")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def classify(score: float, best: SearchItem | None) -> tuple[str, str, str]:
    if best is None:
        return "not_found", "low", "No search result item returned."
    if score >= 0.74:
        return "public_searchable", "high", "Search result closely matches title/code."
    if score >= 0.52:
        return "public_searchable", "medium", "Search result partially matches title/code."
    if score >= 0.36:
        return "uncertain", "low", "Weak match; manual review recommended."
    return "not_found", "low", "Only generic or unrelated results found."


def iter_titles(limit: int | None = None, offset: int = 0) -> Iterable[str]:
    files = sorted(CONTENT_LISTS_DIR.glob("*_content_list.json"))
    selected = files[offset:]
    if limit is not None:
        selected = selected[:limit]
    for path in selected:
        yield path.name.replace("_content_list.json", "")


def audit_title(index: int, title: str, args: argparse.Namespace) -> AuditRow:
    queries = build_queries(title)[: args.max_queries]
    best_score = 0.0
    best_item: SearchItem | None = None
    best_query = queries[0]
    errors: list[str] = []

    for query in queries:
        try:
            body = fetch_bing_rss(query, args.delay, args.timeout, not args.no_cache)
            items = parse_rss(body)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{query}: {exc}")
            continue

        scored = sorted(((score_item(title, item), item) for item in items), reverse=True, key=lambda x: x[0])
        if scored and scored[0][0] > best_score:
            best_score, best_item = scored[0]
            best_query = query
        if best_score >= 0.74:
            break

    if errors and best_item is None:
        query = " || ".join(queries)
        error_text = "; ".join(errors[:3])
        if len(errors) > 3:
            error_text += f"; ... {len(errors) - 3} more"
        return AuditRow(
            index=index,
            source_title=title,
            query=query,
            status="error",
            confidence="low",
            score=0.0,
            matched_title="",
            matched_url="",
            matched_domain="",
            evidence="",
            notes=f"Search request failed: {error_text}",
        )

    query = best_query
    status, confidence, notes = classify(best_score, best_item)
    if len(queries) > 1:
        notes = f"{notes} Queries tried: {len(queries)}."

    if best_item is None:
        return AuditRow(
            index=index,
            source_title=title,
            query=query,
            status=status,
            confidence=confidence,
            score=round(best_score, 3),
            matched_title="",
            matched_url="",
            matched_domain="",
            evidence="",
            notes=notes,
        )

    return AuditRow(
        index=index,
        source_title=title,
        query=query,
        status=status,
        confidence=confidence,
        score=round(best_score, 3),
        matched_title=best_item.title,
        matched_url=best_item.link,
        matched_domain=domain_from_url(best_item.link),
        evidence=best_item.description[:260],
        notes=notes,
    )


def write_outputs(rows: list[AuditRow], prefix: str) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS_DIR / f"{prefix}.csv"
    json_path = REPORTS_DIR / f"{prefix}.summary.json"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()) if rows else [])
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
        confidence_counts[row.confidence] = confidence_counts.get(row.confidence, 0) + 1
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(rows),
        "status_counts": counts,
        "confidence_counts": confidence_counts,
        "csv": str(csv_path.relative_to(PROJECT_ROOT)),
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Limit number of titles.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many titles.")
    parser.add_argument("--delay", type=float, default=0.25, help="Delay between uncached requests.")
    parser.add_argument("--timeout", type=int, default=20, help="Request timeout seconds.")
    parser.add_argument("--max-queries", type=int, default=1, help="Max query variants per title.")
    parser.add_argument("--no-cache", action="store_true", help="Do not read/write query cache.")
    parser.add_argument("--prefix", default=None, help="Output filename prefix without extension.")
    args = parser.parse_args()

    titles = list(iter_titles(args.limit, args.offset))
    if not titles:
        print("No titles found.", file=sys.stderr)
        return 2

    rows: list[AuditRow] = []
    total = len(titles)
    for pos, title in enumerate(titles, start=1 + args.offset):
        row = audit_title(pos, title, args)
        rows.append(row)
        if len(rows) % 25 == 0 or len(rows) == total:
            print(
                f"audited {len(rows)}/{total}: "
                f"{row.status} score={row.score} title={title[:40]}",
                flush=True,
            )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = args.prefix or f"public_search_audit_{timestamp}"
    csv_path, json_path = write_outputs(rows, prefix)
    print(f"CSV: {csv_path}")
    print(f"SUMMARY: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
