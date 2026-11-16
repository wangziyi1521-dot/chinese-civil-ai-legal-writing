#!/usr/bin/env python3
"""Validate a UTF-8 JSONL legal corpus catalog and flag possible duplicates."""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


TARGET_AUTHOR = "王利明"
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+\Z", re.IGNORECASE)
ENUMS = {
    "type": {"journal_article", "book", "book_chapter", "newspaper", "commentary", "other"},
    "period": {"early", "middle", "recent"},
    "author_status": {"confirmed", "needs_review", "excluded"},
    "fulltext_status": {"available", "partial", "unavailable"},
    "extraction_quality": {"high", "medium", "low", "not_assessed"},
    "analysis_status": {"deep", "partial", "pending"},
    "citation_status": {"verified", "partial", "unverified"},
}
PERIODS = {"early": (-9999, 2009), "middle": (2010, 2019), "recent": (2020, 9999)}
VERSION_SUFFIX = re.compile(r"[（(【\[]\s*(?:修订稿|修订版|转载|重刊|重印|节选|网络首发)\s*[）)】\]]\s*$")


class CatalogError(ValueError):
    """A catalog cannot be used safely without correction."""


def read_catalog(path):
    records = []
    with Path(path).open(encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise CatalogError(f"第 {line_no} 行不是有效的 JSON：{error.msg}") from error
            if not isinstance(record, dict):
                raise CatalogError(f"第 {line_no} 行须为 JSON 对象")
            records.append(record)
    return records


def valid_url(value):
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        return False
    try:
        url = urlsplit(value)
        return url.scheme in {"http", "https"} and bool(url.hostname) and url.username is None
    except ValueError:
        return False


def nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def text_list(value):
    return isinstance(value, list) and bool(value) and all(nonempty_text(item) for item in value)


def normalize_doi(value):
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I).casefold()


def normalize_title(value):
    base = VERSION_SUFFIX.sub("", value)
    return "".join(char for char in unicodedata.normalize("NFKC", base).casefold() if char.isalnum())


def role_of(record):
    return record.get("corpus_role", "target")


def authorship_of(record):
    if len(record["authors"]) == 1:
        return "solo"
    if role_of(record) == "comparison":
        return "coauthored"
    return "first" if record["authors"][0] == TARGET_AUTHOR else "coauthor"


def lineage_root(record, by_id):
    """Resolve explicit links only. An invalid graph is a catalog error."""
    current = record
    seen = set()
    while current.get("version_of"):
        parent = current["version_of"]
        seen.add(current["id"])
        if parent in seen:
            raise CatalogError(f"{record['id']} 的 version_of 存在循环")
        if parent not in by_id:
            raise CatalogError(f"{record['id']} 的 version_of 指向未登记条目 {parent}")
        current = by_id[parent]
    return current["id"]


def validate_record(record):
    errors = []
    warnings = []
    identifier = record.get("id")
    if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
        errors.append("id 须为 1–80 位 ASCII 字母、数字、连字符或下划线，并以字母或数字开头")
    for field in ("title", "venue"):
        if not nonempty_text(record.get(field)):
            errors.append(f"{field} 缺少有效文本")
    for field in ("authors", "topics"):
        value = record.get(field)
        if not text_list(value):
            errors.append(f"{field} 须为非空字符串数组")
        elif any(item != item.strip() for item in value) or len(set(value)) != len(value):
            errors.append(f"{field} 须去除首尾空白和重复值")
    year = record.get("year")
    if type(year) is not int or not 1800 <= year <= 2100:
        errors.append("year 须为 1800–2100 之间的整数")
    elif isinstance(record.get("period"), str) and record["period"] in PERIODS:
        lower, upper = PERIODS[record["period"]]
        if not lower <= year <= upper:
            errors.append("period 与 year 不一致")
    for field, options in ENUMS.items():
        value = record.get(field)
        if not isinstance(value, str) or value not in options:
            errors.append(f"{field} 须为 " + " / ".join(sorted(options)))
    role = role_of(record)
    if role not in ("target", "comparison"):
        errors.append("corpus_role 须为 target 或 comparison")
    if not valid_url(record.get("source_url")):
        errors.append("source_url 须为无账户凭据的 HTTP(S) URL")
    if record.get("fulltext_url") is not None and not valid_url(record["fulltext_url"]):
        errors.append("fulltext_url 须为无账户凭据的 HTTP(S) URL")
    when = record.get("retrieved_on")
    try:
        if date.fromisoformat(when).isoformat() != when:
            raise ValueError
    except (ValueError, TypeError):
        errors.append("retrieved_on 须为 YYYY-MM-DD")
    doi = record.get("doi")
    if doi is not None and (not isinstance(doi, str) or not DOI_PATTERN.fullmatch(normalize_doi(doi))):
        errors.append("doi 应填写已知 DOI，缺失时省略或填 null")
    version_of = record.get("version_of")
    if version_of is not None and (not isinstance(version_of, str) or not ID_PATTERN.fullmatch(version_of)):
        errors.append("version_of 须为同一目录的条目 ID")
    authors = record.get("authors")
    if record.get("author_status") == "confirmed":
        if text_list(authors):
            if role == "target" and TARGET_AUTHOR not in authors:
                errors.append(f"target 已确认条目须有精确署名 {TARGET_AUTHOR}")
            if role == "comparison" and TARGET_AUTHOR in authors:
                errors.append("comparison 已确认条目不得包含目标作者")
        evidence = record.get("author_evidence")
        if not (nonempty_text(evidence) or text_list(evidence)):
            errors.append("已确认署名须填写 author_evidence，记录机构、署名、研究方向或交叉核验来源")
    elif role == "target" and text_list(authors) and TARGET_AUTHOR not in authors:
        warnings.append(f"未出现精确署名 {TARGET_AUTHOR}，核查同名或近名")
    if record.get("analysis_status") == "deep" and record.get("fulltext_status") != "available":
        errors.append("深度分析须有完整可读全文")
    if record.get("fulltext_status") == "unavailable" and record.get("extraction_quality") != "not_assessed":
        errors.append("未取得全文时 extraction_quality 须为 not_assessed")
    return errors, warnings


def duplicate_candidates(records, roots):
    buckets = defaultdict(list)
    for record in records:
        title = normalize_title(record["title"])
        if title:
            names = tuple(sorted(record["authors"]))
            buckets[("normalized_title_and_authors", title, names)].append(record["id"])
        if record.get("doi"):
            doi = normalize_doi(record["doi"])
            buckets[("doi", doi)].append(record["id"])
    return [
        {"signal": key[0], "ids": sorted(identifiers)}
        for key, identifiers in buckets.items()
        if len({roots[identifier] for identifier in identifiers}) > 1
    ]


def audit_catalog(records):
    errors, warnings = [], []
    by_id = {}
    for row_number, record in enumerate(records, 1):
        label = f"第 {row_number} 条 ({record.get('id', '未命名')})"
        row_errors, row_warnings = validate_record(record)
        errors.extend(f"{label}：{message}" for message in row_errors)
        warnings.extend(f"{label}：{message}" for message in row_warnings)
        identifier = record.get("id")
        if isinstance(identifier, str):
            if identifier in by_id:
                errors.append(f"{label}：id 重复")
            by_id[identifier] = record
    roots = {}
    if not errors:
        for record in records:
            try:
                root_id = lineage_root(record, by_id)
                if role_of(record) != role_of(by_id[root_id]):
                    raise CatalogError(f"{record['id']} 的版本谱系跨越 target 和 comparison")
                roots[record["id"]] = root_id
            except CatalogError as error:
                errors.append(str(error))
    duplicates = duplicate_candidates(records, roots) if not errors else []
    return {"errors": errors, "warnings": warnings, "lineage_roots": roots, "duplicate_candidates": duplicates}


def summarize_catalog(records, roots):
    selected = [
        record for record in records
        if record.get("author_status") == "confirmed"
        and role_of(record) == "target"
        and record.get("type") == "journal_article"
    ]
    return {
        "manifestation_count": len(records),
        "confirmed_target_journal_manifestations": len(selected),
        "confirmed_target_journal_works_by_explicit_lineage": len({roots[record["id"]] for record in selected}),
        "confirmed_target_journal_fulltext_works": len({
            roots[record["id"]] for record in selected if record["fulltext_status"] == "available"
        }),
        "confirmed_target_journal_deep_works": len({
            roots[record["id"]] for record in selected if record["analysis_status"] == "deep"
        }),
        "canonical_manifestations_by_period": dict(Counter(
            record["period"] for record in selected if record["id"] == roots[record["id"]]
        )),
        "canonical_manifestations_by_authorship": dict(Counter(
            authorship_of(record) for record in selected if record["id"] == roots[record["id"]]
        )),
        "canonical_manifestations_by_topic": dict(Counter(
            topic for record in selected if record["id"] == roots[record["id"]] for topic in record["topics"]
        )),
    }


def load_validated(path):
    records = read_catalog(path)
    audit = audit_catalog(records)
    if audit["errors"]:
        raise CatalogError("\n".join(audit["errors"]))
    return records, audit


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="UTF-8 JSONL catalog")
    args = parser.parse_args()
    try:
        records = read_catalog(args.catalog)
        report = audit_catalog(records)
        if not report["errors"]:
            report["summary"] = summarize_catalog(records, report["lineage_roots"])
        print_json(report)
    except (OSError, UnicodeError, CatalogError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return bool(report["errors"])


if __name__ == "__main__":
    sys.exit(main())
