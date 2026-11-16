#!/usr/bin/env python3
"""Index a lawfully acquired UTF-8 transcript or PDF in a private directory."""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from corpus_validation import CatalogError, load_validated, nonempty_text, normalize_title, print_json, valid_url


FORMAT_VERSION = 1
SKILL_DIR = Path(__file__).resolve().parent.parent
QUALITY = ("high", "medium", "low", "not_assessed")
HEADING_PREFIX = re.compile(r"^\s*(?:#{1,6}\s+|第[一二三四五六七八九十百0-9]+[编章节]\s*|"
                            r"[一二三四五六七八九十百]+[、．.\s]+|[（(][一二三四五六七八九十百0-9]+[）)]\s*|"
                            r"[0-9]{1,2}[、．.]\s+)")
SECTION_LABELS = {
    "引言": "introduction", "导论": "introduction", "前言": "introduction",
    "绪论": "introduction", "问题的提出": "introduction",
    "结论": "conclusion", "结语": "conclusion", "小结与展望": "conclusion", "结论与展望": "conclusion",
    "脚注": "footnotes", "注释": "footnotes", "尾注": "footnotes", "文末注": "footnotes",
    "参考文献": "references", "主要参考文献": "references",
}
ABSTRACT = re.compile(r"^(?:[【\[]\s*)?(?:摘\s*要|内容[提摘]要|abstract)(?=\s|[:：】\]]|$)", re.I)
KEYWORDS = re.compile(r"^(?:[【\[]\s*)?(?:关\s*键\s*词|key\s*words)(?=\s|[:：】\]]|$)", re.I)
FRONT_MATTER = re.compile(r"^(?:作者简介|基金项目|收稿日期|文章编号|中图分类号|文献标识码|引用格式|DOI)\s*[:：]", re.I)
FRONT_SECTIONS = {"abstract", "keywords"}
KEYWORD_SENTENCE_END = re.compile(r"[。！？!?]|\.\s*$")
PAGE_FOOTNOTE = re.compile(
    r"^(?:[①-⑳㉑-㉟㊱-㊿]|\[\d{1,3}\]|［\d{1,3}］|〔\d{1,3}〕|[¹²³⁰⁴-⁹]{1,3})\s*"
    r"(?:参见|另见|同上|前引|引自|转引自|详见|see\b|cf\.)",
    re.I,
)
BLANK_LINES = re.compile(r"\n[ \t\u3000]*\n+")
INVISIBLE_LAYOUT = str.maketrans("", "", "\ufeff\u200b\u200c\u200d\u00ad")


def json_hash(value):
    canonical = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def catalog_identity(record):
    return json_hash({
        field: record.get(field)
        for field in ("id", "title", "authors", "year", "venue", "volume", "issue", "pages", "doi", "type")
    })


def pdf_pages(raw):
    if shutil.which("pdftotext"):
        run = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", "-", "-"],
            input=raw, capture_output=True, check=False,
        )
        if run.returncode == 0:
            result = run.stdout.decode("utf-8").split("\f")
            if not result[-1].strip():
                result.pop()
            if any(page.strip() for page in result):
                return result, "pdftotext-layout"
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise CatalogError("PDF 未提取到文字。可使用 pdftotext 或 pypdf，或核对 OCR 后提供 UTF-8 TXT") from error
    try:
        reader = PdfReader(io.BytesIO(raw))
        return [page.extract_text() or "" for page in reader.pages], "pypdf"
    except Exception as error:
        raise CatalogError(f"pypdf 读取 PDF 失败：{error}") from error


def read_pages(path, raw):
    if path.suffix.lower() == ".pdf":
        return pdf_pages(raw)
    if path.suffix.lower() in {".txt", ".md"}:
        return raw.decode("utf-8-sig").split("\f"), "utf8"
    raise CatalogError("仅支持可读取的 PDF 或 UTF-8 TXT/MD")


def clean_page(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").translate(INVISIBLE_LAYOUT)
    return "\n".join(line.rstrip() for line in text.split("\n")).strip("\n")


def heading_info(line):
    plain = HEADING_PREFIX.sub("", line, count=1).strip().rstrip("：:")
    if plain in SECTION_LABELS:
        return True, SECTION_LABELS[plain]
    return bool(HEADING_PREFIX.match(line) and len(line) <= 80 and not re.search(r"[。！？；!?]", line)), None


def classify_blocks(pages, title, authors, from_pdf):
    blocks = []
    region = "body"
    resume_region = region
    front_has_text = False
    title_key = normalize_title(title)
    authors_key = "".join(authors)
    paginated = from_pdf or len(pages) > 1
    for page_number, page in enumerate(pages, 1):
        for chunk in BLANK_LINES.split(page):
            pending = []
            pending_region = region
            for source_line in chunk.splitlines():
                line = source_line.strip()
                heading, new_region = heading_info(line)
                line_key = normalize_title(line)
                abstract, keywords = ABSTRACT.match(line), KEYWORDS.match(line)
                if title_key and line_key == title_key:
                    kind = "title"
                elif line_key in {authors_key, f"作者{authors_key}"} or FRONT_MATTER.match(line):
                    kind = "front_matter"
                elif abstract:
                    kind = "abstract"
                elif keywords:
                    kind = "keywords"
                elif paginated and PAGE_FOOTNOTE.match(line):
                    kind = "page_footnote"
                elif heading:
                    kind = new_region or ("body" if region in FRONT_SECTIONS | {"introduction"} else region)
                elif pending_region == "keywords" and front_has_text and KEYWORD_SENTENCE_END.search(line):
                    kind = "end_keywords"
                else:
                    pending.append(source_line)
                    if pending_region in FRONT_SECTIONS and line:
                        front_has_text = True
                    continue
                if pending:
                    blocks.append((page_number, pending_region, False, "\n".join(pending).strip()))
                    pending.clear()
                if kind in {"title", "front_matter"}:
                    blocks.append((page_number, kind, False, line))
                    pending_region = region
                elif kind in FRONT_SECTIONS:
                    if region not in FRONT_SECTIONS:
                        resume_region = region
                    region = pending_region = kind
                    marker = abstract or keywords
                    front_has_text = bool(line[marker.end():].strip(" \t：:】]"))
                    pending.append(source_line)
                elif kind == "page_footnote":
                    pending_region = "footnotes"
                    pending.append(source_line)
                elif kind == "end_keywords":
                    region = pending_region = resume_region
                    front_has_text = False
                    pending.append(source_line)
                elif heading:
                    region = pending_region = kind
                    blocks.append((page_number, region, True, line))
            if pending:
                blocks.append((page_number, pending_region, False, "\n".join(pending).strip()))
            if region in FRONT_SECTIONS and front_has_text:
                # A blank boundary ends populated front matter. Review ambiguous multiline abstracts in preview.
                region = resume_region
                front_has_text = False
    return [
        {"id": f"p{index:05}", "page": page if paginated else None,
         "region": kind, "heading": heading, "text": text}
        for index, (page, kind, heading, text) in enumerate(blocks, 1)
    ]


def read_printed_pages(path, page_count):
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CatalogError("刊页映射须是合法 JSON") from error
    if not page_count:
        raise CatalogError("刊页映射需要 PDF 或含分页符的校对文本")
    if not isinstance(entries, list) or not entries:
        raise CatalogError("刊页映射须是非空的 [文件页序, 刊页标签] 列表")
    mapping = {}
    labels = set()
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != 2:
            raise CatalogError("每条刊页映射须包含文件页序和刊页标签")
        page, label = entry
        if type(page) is not int or not 1 <= page <= page_count:
            raise CatalogError("刊页映射的文件页序超出范围")
        if type(label) is int and label > 0:
            label = str(label)
        if not isinstance(label, str) or not (1 <= len(label) <= 32) or label != label.strip() or not label.isprintable():
            raise CatalogError("刊页标签须是正整数或 1–32 个可打印字符")
        if page in mapping or label in labels:
            raise CatalogError("刊页映射的文件页序和刊页标签均须唯一")
        mapping[page] = label
        labels.add(label)
    return mapping


def build_index(record, source, rights_note, source_url, quality, quality_note, printed_pages=None):
    raw = source.read_bytes()
    pages, extractor = read_pages(source, raw)
    pages = [clean_page(page) for page in pages]
    if not any(page.strip() for page in pages):
        raise CatalogError("没有提取到可用文字，请核对合法 OCR 文本后再入库")
    from_pdf = source.suffix.lower() == ".pdf"
    page_count = len(pages) if from_pdf or len(pages) > 1 else None
    blocks = classify_blocks(pages, record["title"], record["authors"], from_pdf)
    if not blocks:
        raise CatalogError("没有提取到可定位的文本块")
    if printed_pages is not None:
        mapping = read_printed_pages(printed_pages, page_count)
        for block in blocks:
            block["printed_page"] = mapping.get(block["page"])
    return {
        "format_version": FORMAT_VERSION,
        "catalog_id": record["id"],
        "catalog_identity_sha256": catalog_identity(record),
        "source_filename": source.name,
        "source_url": source_url,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "rights_note": rights_note,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "extractor": extractor,
        "physical_page_count": page_count,
        "quality": quality,
        "quality_note": quality_note,
        "empty_page_indexes": [i for i, page in enumerate(pages, 1) if not page.strip()],
        "blocks_sha256": json_hash(blocks),
        "blocks": blocks,
    }


def write_private_index(processed_dir, index, replace):
    processed_dir = processed_dir.resolve()
    if processed_dir == SKILL_DIR or SKILL_DIR in processed_dir.parents:
        raise CatalogError("请把含全文的派生索引写入 Skill 目录以外的私有位置")
    processed_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = processed_dir / f"{index['catalog_id']}.json"
    descriptor, scratch = tempfile.mkstemp(dir=processed_dir, prefix=".index-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        if replace:
            os.replace(scratch, path)
        else:
            try:
                os.link(scratch, path)
            except FileExistsError as error:
                raise CatalogError(f"{path.name} 已存在。核对版本和来源后可用 --replace") from error
    finally:
        Path(scratch).unlink(missing_ok=True)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("paper_id")
    parser.add_argument("source", type=Path)
    parser.add_argument("--processed-dir", type=Path, help="私有索引目录，预览时可省略")
    parser.add_argument("--quality", choices=QUALITY, default="not_assessed")
    parser.add_argument("--quality-note", help="人工核对版面、段序、OCR、脚注、漏页的简要记录")
    parser.add_argument("--rights-note", help="取得方式及适用的个人研究、访问、下载或再分发限制")
    parser.add_argument("--source-url", help="精确版本的公开回源链接，缺省用目录的全文链接或出版链接")
    parser.add_argument("--printed-pages", type=Path, help="人工核对的文件页序到原刊页标签 JSON")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--preview", action="store_true", help="仅预览提取分区和页码，不写索引")
    actions.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if not args.preview and args.processed_dir is None:
        parser.error("写入索引需要 --processed-dir")
    try:
        records, _ = load_validated(args.catalog)
        record = next((item for item in records if item["id"] == args.paper_id), None)
        if record is None:
            raise CatalogError("先登记原始出版信息和版本，再按该条目 ID 入库")
        rights = args.rights_note or record.get("rights_note")
        if not nonempty_text(rights):
            raise CatalogError("须用 --rights-note 或目录 rights_note 记录来源和使用限制")
        source_url = args.source_url or record.get("fulltext_url") or record["source_url"]
        if not valid_url(source_url):
            raise CatalogError("来源须为无账户凭据的 HTTP(S) URL")
        if args.quality != "not_assessed" and not nonempty_text(args.quality_note):
            raise CatalogError("已评价的质量等级须用 --quality-note 记录人工核对结果")
        index = build_index(record, args.source, rights, source_url, args.quality, args.quality_note, args.printed_pages)
        receipt = {
            "catalog_id": index["catalog_id"],
            "source_sha256": index["source_sha256"],
            "extractor": index["extractor"],
            "quality": index["quality"],
            "blocks": len(index["blocks"]),
            "physical_page_count": index["physical_page_count"],
            "empty_page_indexes": index["empty_page_indexes"],
        }
        if args.preview:
            receipt["preview"] = [
                {
                    "id": block["id"],
                    "region": block["region"],
                    "heading": block["heading"],
                    "page": block["page"],
                    "printed_page": block.get("printed_page"),
                    "start": " ".join(block["text"].split())[:40],
                }
                for block in index["blocks"]
            ]
        else:
            receipt["path"] = str(write_private_index(args.processed_dir, index, args.replace))
        print_json(receipt)
    except (OSError, UnicodeError, CatalogError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
