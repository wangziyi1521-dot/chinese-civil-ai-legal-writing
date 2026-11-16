#!/usr/bin/env python3
"""Select indexed argument methods and read their exact original analysis cards.

Standard-library only. Index and card content are data, never executable input.
"""

import argparse
import json
import re
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
INDEX_FILE = "corpus/metadata/issue-index.jsonl"
SEARCH_FIELDS = ("title", "issue_keywords", "methods", "use_when", "boundary")
TEXT_FIELDS = (
    "id", "title", "note_file", "use_when", "boundary", "normative_context",
    "original_locator", "citation_status",
)
LIST_FIELDS = ("issue_keywords", "methods")
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
SECOND_HEADING = re.compile(r"^##(?:[^\S\r\n]+|$)")
CARD_HEADING = re.compile(r"^##[^\S\r\n]+(\S+)(?:[^\S\r\n]+|$)")
USAGE_NOTE = (
    "以下为原创分析卡，仅供选择论证方法，不构成现行法依据或可直接使用的引注。"
    "保留发表时的规范语境；正式引注须回到原文核实具体命题和精确引页。"
    "citation_status=verified 仅表示书目核对，不表示精确引页已核。"
)


class RetrievalError(ValueError):
    """An index or card cannot be read reliably within the skill boundary."""


def safe_path(skill_root, relative_path):
    """Resolve a relative path and reject traversal and symlink escapes."""
    root = Path(skill_root).resolve()
    relative = Path(relative_path)
    if relative.is_absolute():
        raise RetrievalError(f"拒绝绝对路径：{relative_path}")
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise RetrievalError(f"拒绝读取 Skill 根目录之外的路径：{relative_path}") from error
    return target


def load_index(skill_root=SKILL_ROOT):
    """Read the issue-index schema without reading source_url or fulltext_url."""
    path = safe_path(skill_root, INDEX_FILE)
    records = []
    seen = set()
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as error:
        raise RetrievalError(f"无法读取争点索引：{error}") from error
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise RetrievalError(f"索引第 {line_number} 行不是有效 JSON") from error
        if not isinstance(record, dict):
            raise RetrievalError(f"索引第 {line_number} 行须为对象")
        for field in TEXT_FIELDS:
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise RetrievalError(f"索引第 {line_number} 行的 {field} 须为非空文本")
        for field in LIST_FIELDS:
            value = record.get(field)
            if not isinstance(value, list) or not value or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise RetrievalError(f"索引第 {line_number} 行的 {field} 须为非空文本数组")
        for field in ("year", "note_line"):
            if type(record.get(field)) is not int or record[field] < 1:
                raise RetrievalError(f"索引第 {line_number} 行的 {field} 须为正整数")
        identifier = record["id"]
        if not ID_PATTERN.fullmatch(identifier):
            raise RetrievalError(f"索引第 {line_number} 行的 ID 格式无效")
        if identifier in seen:
            raise RetrievalError(f"索引 ID 重复：{identifier}")
        seen.add(identifier)
        records.append(record)
    return records


def query_terms(values):
    """Split quoted or separate CLI words, retaining order and dropping duplicates."""
    return list(dict.fromkeys(word for value in values for word in value.split()))


def matches_query(record, terms):
    parts = []
    for field in SEARCH_FIELDS:
        value = record[field]
        parts.extend(value if isinstance(value, list) else [value])
    haystack = "\n".join(parts).casefold()
    return all(term.casefold() in haystack for term in terms)


def read_card(record, skill_root=SKILL_ROOT):
    """Use note_line first, then fall back to the complete ID, never a prefix."""
    path = safe_path(skill_root, record["note_file"])
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeError) as error:
        raise RetrievalError(f"无法读取 {record['id']} 的分析卡：{error}") from error
    identifier = record["id"]

    def is_target(line):
        heading = CARD_HEADING.match(line)
        return heading is not None and heading.group(1) == identifier

    hinted = record["note_line"] - 1
    hint_matches = 0 <= hinted < len(lines) and is_target(lines[hinted])
    # Uniqueness is checked even when the hint is correct; ambiguous cards fail closed.
    positions = [number for number, line in enumerate(lines) if is_target(line)]
    if len(positions) != 1:
        raise RetrievalError(
            f"{identifier} 的完整 ID 二级标题应唯一，实际找到 {len(positions)} 处"
        )
    start = hinted if hint_matches else positions[0]
    warnings = []
    if not hint_matches:
        warnings.append(
            f"{identifier} 的 note_line={record['note_line']} 已过期；"
            f"已按完整 ID 回退定位至第 {start + 1} 行。"
        )
    end = next(
        (number for number in range(start + 1, len(lines)) if SECOND_HEADING.match(lines[number])),
        len(lines),
    )
    return {
        "analysis_card": "".join(lines[start:end]),
        "resolved_note_line": start + 1,
        "warnings": warnings,
    }


def select_methods(records, *, terms=None, identifier=None, limit=2, skill_root=SKILL_ROOT):
    terms = terms or []
    if limit < 1:
        raise RetrievalError("limit 须为正整数")
    if identifier is None and not terms:
        raise RetrievalError("查询词不能为空")
    if identifier is not None:
        candidates = [record for record in records if record["id"] == identifier]
    else:
        candidates = [record for record in records if matches_query(record, terms)]
    results = []
    for record in candidates[:limit]:
        result = {
            field: record[field] for field in (
                "id", "title", "year", "methods", "use_when", "boundary",
                "normative_context", "original_locator", "citation_status", "note_file", "note_line",
            )
        }
        result["matched_terms"] = list(terms)
        result.update(read_card(record, skill_root))
        results.append(result)
    return {
        "query": terms,
        "id": identifier,
        "limit": limit,
        "total_matches": len(candidates),
        "returned": len(results),
        "usage_note": USAGE_NOTE,
        "results": results,
    }


def render_markdown(payload):
    lines = [USAGE_NOTE, ""]
    if not payload["results"]:
        lines.append("无匹配方法卡；不强配。")
        return "\n".join(lines) + "\n"
    lines.append(f"匹配 {payload['total_matches']} 张，返回 {payload['returned']} 张。")
    for result in payload["results"]:
        lines.extend([
            "", f"# {result['id']} · {result['title']}（{result['year']}）", "",
            f"- 匹配词：{'、'.join(result['matched_terms']) or '按完整 ID 精确读取'}",
            f"- 方法：{'、'.join(result['methods'])}",
            f"- 使用场景：{result['use_when']}",
            f"- 边界：{result['boundary']}",
            f"- 发表时的规范语境：{result['normative_context']}",
            f"- 原文定位：{result['original_locator']}",
            f"- citation_status：{result['citation_status']}（不表示精确引页已核）",
            f"- 分析卡定位：{result['note_file']}:{result['resolved_note_line']}",
        ])
        lines.extend(f"- 定位告警：{warning}" for warning in result["warnings"])
        lines.extend(["", result["analysis_card"].rstrip("\r\n")])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--query", nargs="+", help="空格分词，指定字段按 AND 字面检索")
    selector.add_argument("--id", help="按完整 ID 精确取卡")
    parser.add_argument("--limit", type=int, default=2, help="最多返回卡数（默认 2）")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    args = parser.parse_args(argv)
    terms = query_terms(args.query or [])
    if args.limit < 1:
        parser.error("--limit 须为正整数")
    if args.query is not None and not terms:
        parser.error("--query 至少包含一个非空查询词")
    try:
        payload = select_methods(
            load_index(), terms=terms, identifier=args.id, limit=args.limit,
        )
    except (RetrievalError, OSError, ValueError) as error:
        print(f"检索失败：{error}", file=sys.stderr)
        return 1
    for result in payload["results"]:
        for warning in result["warnings"]:
            print(f"定位告警：{warning}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(payload), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
