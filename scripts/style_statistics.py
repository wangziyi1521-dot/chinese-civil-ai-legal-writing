#!/usr/bin/env python3
"""Compute auditable descriptive statistics from private corpus indices."""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from corpus_analysis import FORMAT_VERSION, QUALITY, catalog_identity, json_hash
from corpus_validation import CatalogError, authorship_of, load_validated, nonempty_text, print_json, role_of, valid_url


HAN = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U000323af"
HAN_CHAR = re.compile(f"[{HAN}]")
WORD_CANDIDATES = re.compile(f"[{HAN}]+|[A-Za-z0-9]+")
CHAR_UNITS = re.compile(f"[{HAN}]|[A-Za-z0-9]+")
SENTENCE_END = re.compile(r"[。！？!?]+|…{2,}")
BODY_REGIONS = {"body", "introduction", "conclusion"}
REVIEWED_QUALITY = {"high", "medium"}
CONNECTORS = {
    "转折或让步": ["然而", "但是", "不过", "尽管", "即便", "即使", "反之", "相反", "固然"],
    "递进或并列": ["不仅", "不但", "而且", "并且", "此外", "同时", "进而", "尤其", "进一步", "一方面", "另一方面"],
    "条件或限定": ["如果", "倘若", "只要", "除非", "只有", "在此意义上", "原则上", "在一定程度上", "通常"],
    "因果或推导": ["因为", "因此", "因而", "所以", "从而", "由此可见", "据此", "鉴于"],
    "归结或说明": ["综上所述", "综上", "总而言之", "换言之", "也就是说", "例如", "具体而言", "由此"],
}
BASE_LEXICON = frozenset("""
民法 民法典 民法总则 法律 法律关系 法律行为 法律规范 规范 规则 原则 制度 法律制度
权利 义务 权益 合法权益 法益 人格 人格权 一般人格权 人格利益 个人信息 个人资料 个人数据
隐私 隐私权 身份 自然人 法人 主体 意思表示 意思自治 自主决定 公共利益
责任 民事责任 侵权 侵权责任 违约 违约责任 损害 损害赔偿 赔偿 过错 过失
因果关系 过错推定 注意义务 安全保障义务 构成要件 请求权 救济 行为义务
权利行使 权利保护 法律保护 权利冲突 利益衡量 价值判断 法律解释 体系解释 目的解释
文义解释 比较法 历史解释 解释 立法 司法 适用 要件 例外 类型 归责 规范目的
物权 所有权 债权 债务 占有 合同 合同法 合同义务 合同解释 合同履行 合同解除
环境 环境法 生态环境 环境损害 环境污染 污染防治 生态修复 人工智能 算法 数据
数据法 风险 风险防范 保护义务 责任主体 损害结果 举证责任 法律效果 立法目的
""".split())


def load_index(path, record):
    with path.open(encoding="utf-8") as handle:
        index = json.load(handle)
    if (
        not isinstance(index, dict)
        or index.get("format_version") != FORMAT_VERSION
        or index.get("catalog_id") != record["id"]
        or index.get("catalog_identity_sha256") != catalog_identity(record)
    ):
        raise CatalogError(f"{record['id']} 的索引与目录版本不符，请核对后重新入库")
    blocks = index.get("blocks")
    if not isinstance(blocks, list) or index.get("blocks_sha256") != json_hash(blocks):
        raise CatalogError(f"{record['id']} 的文本块校验失败，请从原始文件重建索引")
    if not all(
        isinstance(block, dict)
        and nonempty_text(block.get("id"))
        and nonempty_text(block.get("region"))
        and isinstance(block.get("heading"), bool)
        and nonempty_text(block.get("text"))
        and "page" in block
        for block in blocks
    ):
        raise CatalogError(f"{record['id']} 的文本块结构无效，请重建索引")
    if not re.fullmatch(r"[0-9a-f]{64}", str(index.get("source_sha256", ""))):
        raise CatalogError(f"{record['id']} 的原始文件校验值缺失，请重建索引")
    if index.get("quality") not in QUALITY or not valid_url(index.get("source_url")) or not nonempty_text(index.get("rights_note")):
        raise CatalogError(f"{record['id']} 的质量或来源字段无效，请重建索引")
    return index


def tokenizer_for(name, extra_words):
    if name == "chars":
        return CHAR_UNITS.findall, "Han unigram + ASCII alphanumeric run"
    if name == "lexicon":
        words = BASE_LEXICON | set(extra_words) | {term for forms in CONNECTORS.values() for term in forms}
        pattern = re.compile(f"{longest_match(words).pattern}|{CHAR_UNITS.pattern}")
        return pattern.findall, {
            "method": "longest match in generic legal lexicon, other Han characters as unigrams",
            "entry_count": len(words),
            "lexicon_sha256": json_hash(sorted(words)),
        }
    try:
        import jieba
    except ImportError as error:
        raise CatalogError("未安装可选的 jieba。安装后重试，或明确选择 --tokenizer chars") from error
    segmenter = jieba.Tokenizer()

    def tokenize(text):
        tokens = []
        for match in WORD_CANDIDATES.finditer(text):
            unit = match.group()
            tokens.extend(segmenter.cut(unit, HMM=False) if HAN_CHAR.match(unit) else [unit])
        return tokens

    return tokenize, f"jieba {getattr(jieba, '__version__', 'unknown')} with HMM disabled"


def distribution(lengths):
    if not lengths:
        return {"count": 0}
    lengths = sorted(lengths)
    return {
        "count": len(lengths),
        "mean": round(mean(lengths), 2),
        "median": median(lengths),
        "min": lengths[0],
        "p10_nearest_rank": lengths[math.ceil(len(lengths) * .1) - 1],
        "p90_nearest_rank": lengths[math.ceil(len(lengths) * .9) - 1],
        "max": lengths[-1],
    }


def measured_length(text):
    return sum(len(match.group()) for match in WORD_CANDIDATES.finditer(text))


def longest_match(values):
    return re.compile("|".join(re.escape(value) for value in sorted(values, key=lambda value: (-len(value), value))))


def load_terms(path):
    with path.open(encoding="utf-8") as handle:
        terms = json.load(handle)
    if not isinstance(terms, dict):
        raise CatalogError("术语文件须为 JSON 对象，键为术语，值为需核查的近似词数组")
    lookup = {}
    for canonical, variants in terms.items():
        if not nonempty_text(canonical) or not isinstance(variants, list) or not all(nonempty_text(v) for v in variants):
            raise CatalogError("术语及近似词须为非空字符串")
        for value in [canonical, *variants]:
            if value in lookup and lookup[value] != canonical:
                raise CatalogError(f"术语 {value} 属于多个术语组，请分开核查")
            lookup[value] = canonical
    return lookup


def load_lexicon(path):
    with path.open(encoding="utf-8") as handle:
        return {line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")}


def document_statistics(index, tokenize, term_lookup):
    blocks = [block for block in index["blocks"] if block["region"] in BODY_REGIONS and not block["heading"]]
    connector_lookup = {term: label for label, terms in CONNECTORS.items() for term in terms}
    connector_pattern = longest_match(connector_lookup)
    term_pattern = longest_match(term_lookup) if term_lookup else None
    token_counts = Counter()
    connector_counts = Counter()
    term_locations = defaultdict(Counter)
    sentence_lengths, paragraph_lengths = [], []
    han_characters = 0
    for block in blocks:
        paragraph = re.sub(r"(?<=[A-Za-z0-9])[ \t]*\n[ \t]*(?=[A-Za-z0-9])", " ", block["text"])
        paragraph = re.sub(r"[ \t]*\n[ \t]*", "", paragraph)
        token_counts.update(token.casefold() for token in tokenize(paragraph))
        connector_counts.update(match.group() for match in connector_pattern.finditer(paragraph))
        paragraph_lengths.append(measured_length(paragraph))
        han_characters += len(HAN_CHAR.findall(paragraph))
        sentence_lengths.extend(filter(None, (measured_length(part) for part in SENTENCE_END.split(paragraph))))
        if term_pattern:
            for match in term_pattern.finditer(paragraph):
                term_locations[match.group()][block["id"]] += 1
    return {
        "token_counts": token_counts,
        "connector_counts": connector_counts,
        "term_locations": term_locations,
        "sentence_lengths": sentence_lengths,
        "paragraph_lengths": list(filter(None, paragraph_lengths)),
        "han_characters": han_characters,
        "headings": [
            {
                "block_id": block["id"], "page": block["page"], "region": block["region"],
                "printed_page": block.get("printed_page"),
            }
            for block in index["blocks"] if block["heading"]
        ],
    }


def merge_counts(documents, key):
    counts, incidence = Counter(), Counter()
    for document in documents:
        counts.update(document[key])
        incidence.update(document[key].keys())
    return counts, incidence


def counts_table(counts, incidence, denominator, top):
    return [
        {
            "value": value, "count": count, "papers": incidence[value],
            "per_10000": round(count * 10000 / denominator, 3) if denominator else None,
        }
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top]
    ]


def report_group(identifiers, statistics, top):
    documents = [statistics[identifier] for identifier in identifiers]
    tokens, token_incidence = merge_counts(documents, "token_counts")
    connectors, connector_incidence = merge_counts(documents, "connector_counts")
    token_denominator = sum(tokens.values())
    han_denominator = sum(doc["han_characters"] for doc in documents)
    token_table = counts_table(tokens, token_incidence, token_denominator, top)
    connector_table = counts_table(connectors, connector_incidence, han_denominator, None)
    connector_lookup = {term: label for label, terms in CONNECTORS.items() for term in terms}
    for row in connector_table:
        row["category_hint"] = connector_lookup[row["value"]]
    return {
        "papers": len(identifiers),
        "paper_ids": sorted(identifiers),
        "han_characters": han_denominator,
        "token_units": token_denominator,
        "sentence_length": distribution([size for doc in documents for size in doc["sentence_lengths"]]),
        "paragraph_length": distribution([size for doc in documents for size in doc["paragraph_lengths"]]),
        "top_token_units": token_table,
        "connector_matches": connector_table,
    }


def groups_for(record, dimension):
    labels = {
        "corpus_role": ["all"],
        "period": [record["period"]],
        "topic": record["topics"],
        "authorship": [authorship_of(record)],
        "venue": [record["venue"]],
        "paper": [record["id"]],
    }
    return [(role_of(record), label) for label in labels[dimension]]


def eligible_indices(records, audit, directory, include_low_quality):
    roots = audit["lineage_roots"]
    candidates, excluded = [], []
    for record in records:
        identifier = record["id"]
        path = directory / f"{identifier}.json"
        if record["type"] != "journal_article" or record["author_status"] != "confirmed":
            reason = "not_confirmed_journal_article"
        elif record["fulltext_status"] != "available":
            reason = "catalog_fulltext_not_available"
        elif not path.is_file():
            reason = "no_local_index"
        else:
            index = load_index(path, record)
            if index.get("quality") not in REVIEWED_QUALITY and not include_low_quality:
                reason = "not_reviewed_high_or_medium"
            elif not any(
                block["region"] in BODY_REGIONS and not block["heading"] and measured_length(block["text"])
                for block in index["blocks"]
            ):
                reason = "no_measurable_body"
            else:
                candidates.append((record, index))
                continue
        excluded.append({"id": identifier, "reason": reason})
    candidate_ids = {record["id"] for record, _ in candidates}
    for conflict in audit["duplicate_candidates"]:
        ids = set(conflict["ids"]) & candidate_ids
        if len({roots[identifier] for identifier in ids}) > 1:
            raise CatalogError(f"样本有未核查的重复候选：{', '.join(sorted(ids))}。核对版次后登记 version_of")
    chosen = {}
    for record, index in sorted(candidates, key=lambda item: (
        item[0]["id"] != roots[item[0]["id"]],
        item[1]["quality"] != "high",
        item[1]["quality"] != "medium",
        item[0]["year"],
        item[0]["id"],
    )):
        root = roots[record["id"]]
        if root in chosen:
            excluded.append({"id": record["id"], "reason": "alternative_version", "kept": chosen[root][0]["id"]})
        else:
            chosen[root] = record, index
    return chosen.values(), excluded


def run_statistics(catalog, directory, tokenizer_name, group_dimension, terms, top, include_low_quality, extra_words):
    records, audit = load_validated(catalog)
    indices, excluded = eligible_indices(records, audit, directory, include_low_quality)
    tokenize, tokenizer_description = tokenizer_for(tokenizer_name, extra_words)
    by_group, statistics, samples = defaultdict(list), {}, []
    for record, index in indices:
        identifier = record["id"]
        statistics[identifier] = document_statistics(index, tokenize, terms)
        for group in groups_for(record, group_dimension):
            by_group[group].append(identifier)
        samples.append({
            "id": identifier, "period": record["period"], "venue": record["venue"],
            "corpus_role": role_of(record), "authorship": authorship_of(record), "topics": record["topics"],
            "quality": index["quality"], "source_sha256": index["source_sha256"], "source_url": index["source_url"],
            "headings": statistics[identifier]["headings"],
        })
    return {
        "methods": {
            "tokenizer": tokenizer_description,
            "group_by": group_dimension,
            "regions": sorted(BODY_REGIONS),
            "headings_included": False,
            "quality_filter": "all" if include_low_quality else "high_or_medium",
            "token_rate_denominator": "token units",
            "connector_rate_denominator": "Han characters",
            "length_unit": "Han characters and ASCII alphanumeric characters excluding punctuation",
            "sentence_boundaries": "。！？!?，连续省略号及段末；分号不切分",
            "limit": "字符串匹配未做词义判定。分层、长度、主题和期刊差异须复核；统计量不是作者指纹。",
        },
        "status": "descriptive_only" if samples else "no_eligible_local_texts",
        "samples": samples,
        "excluded": excluded,
        "groups": [
            {"corpus_role": role, "label": label, **report_group(identifiers, statistics, top)}
            for (role, label), identifiers in sorted(by_group.items())
        ],
        "term_matches": [
            {
                "paper_id": identifier,
                "canonical": terms[form],
                "form": form,
                "count": sum(locations.values()),
                "block_counts": dict(locations),
            }
            for identifier, document in statistics.items()
            for form, locations in sorted(document["term_locations"].items())
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--processed-dir", required=True, type=Path)
    parser.add_argument("--tokenizer", choices=("chars", "lexicon", "jieba"), default="lexicon")
    parser.add_argument("--lexicon", type=Path, help="词典模式的 UTF-8 补充词表，每行一个词")
    parser.add_argument("--group-by", choices=("corpus_role", "period", "topic", "authorship", "venue", "paper"), default="corpus_role")
    parser.add_argument("--terms", type=Path)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--include-low-quality", action="store_true")
    args = parser.parse_args()
    if args.top < 0:
        parser.error("--top 须为非负整数")
    if args.lexicon and args.tokenizer != "lexicon":
        parser.error("--lexicon 仅适用于词典模式")
    try:
        terms = load_terms(args.terms) if args.terms else {}
        words = load_lexicon(args.lexicon) if args.lexicon else set()
        print_json(run_statistics(
            args.catalog, args.processed_dir, args.tokenizer, args.group_by, terms, args.top, args.include_low_quality, words,
        ))
    except (OSError, UnicodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
