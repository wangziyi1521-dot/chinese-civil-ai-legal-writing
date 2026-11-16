"""Executable tests. All papers, transcript content and URLs below are synthetic fixtures."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TRANSCRIPT = """合成记录一
王利明
摘要：然而这段摘要用于验证排除。
关键词：人格权

一、引言
人格权保护需要厘清请求权。然而，个人资料保护属于另一个问题。

二、论证
因此，应先明确个人信息；再讨论人格利益。

一方面，法律关系具有边界。另一方面，条件可能变化。

三、结语
由此可见，应解释规则的适用范围。

注释
因此此处是脚注。

参考文献
因此此处是参考文献。
"""


def fixture(identifier="FIXTURE-1", **fields):
    record = {
        "id": identifier,
        "title": "合成记录一",
        "authors": ["王利明"],
        "year": 2020,
        "venue": "虚构期刊",
        "type": "journal_article",
        "period": "recent",
        "topics": ["合成主题"],
        "source_url": "https://example.invalid/fake-issue",
        "retrieved_on": "2026-11-09",
        "author_status": "confirmed",
        "author_evidence": "合成署名，仅用于程序测试",
        "fulltext_status": "available",
        "extraction_quality": "high",
        "analysis_status": "pending",
        "citation_status": "unverified",
        "rights_note": "人工合成文本，仅用于测试",
    }
    record.update(fields)
    return record


class CorpusToolsTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="claw-test-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.catalog = self.root / "fixture.jsonl"
        self.processed = self.root / "private"
        self.source = self.root / "fixture.txt"
        self.source.write_text(TRANSCRIPT, encoding="utf-8")
        self.set_catalog(fixture())

    def set_catalog(self, *records):
        self.catalog.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")

    def execute(self, script, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / script), str(self.catalog), *(str(item) for item in arguments)],
            encoding="utf-8", capture_output=True, check=False,
        )

    def ingest(self, identifier="FIXTURE-1", source=None, quality="high", options=()):
        return self.execute(
            "corpus_analysis.py", identifier, source or self.source,
            "--processed-dir", self.processed, "--quality", quality,
            "--quality-note", "比对合成文本与原始输入的段落及文字顺序", *options,
        )

    def as_json(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_duplicate_candidates_resolved_by_explicit_lineage(self):
        self.set_catalog(fixture(), fixture("FIXTURE-2", title="合成记录一（转载）"))
        report = self.as_json(self.execute("corpus_validation.py"))
        self.assertEqual(report["duplicate_candidates"][0]["ids"], ["FIXTURE-1", "FIXTURE-2"])
        self.set_catalog(fixture(), fixture("FIXTURE-2", title="合成记录一（转载）", version_of="FIXTURE-1"))
        report = self.as_json(self.execute("corpus_validation.py"))
        self.assertFalse(report["duplicate_candidates"])
        self.assertEqual(report["summary"]["confirmed_target_journal_works_by_explicit_lineage"], 1)

    def test_author_evidence_required_and_near_name_rejected(self):
        self.set_catalog(fixture(authors=["王利民"], author_evidence=None))
        result = self.execute("corpus_validation.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("精确署名", result.stdout)
        self.assertIn("author_evidence", result.stdout)

    def test_invalid_deep_claim_and_year_stratum_rejected(self):
        self.set_catalog(fixture(fulltext_status="unavailable", extraction_quality="not_assessed", analysis_status="deep", year=2004))
        result = self.execute("corpus_validation.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("period 与 year 不一致", result.stdout)
        self.assertIn("须有完整可读全文", result.stdout)

    def test_version_cycles_rejected(self):
        self.set_catalog(fixture(version_of="FIXTURE-2"), fixture("FIXTURE-2", version_of="FIXTURE-1"))
        result = self.execute("corpus_validation.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("存在循环", result.stdout)

    def test_ingest_preserves_order_and_guards_overwrite(self):
        receipt = self.as_json(self.ingest())
        index_path = Path(receipt["path"])
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["source_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())
        blocks = index["blocks"]
        self.assertEqual([b["region"] for b in blocks[:4]], ["title", "front_matter", "abstract", "keywords"])
        self.assertEqual([b["region"] for b in blocks if b["heading"]], ["introduction", "body", "conclusion", "footnotes", "references"])
        self.assertIsNone(blocks[0]["page"])
        self.assertEqual(index_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.ingest().returncode, 1)
        self.as_json(self.ingest(options=("--replace",)))

    def test_preview_recovers_unheaded_introduction_and_leaves_no_index(self):
        self.source.write_text(
            "摘 要：摘要分两行\n第二行仍是摘要。\n\n"
            "因此，这是没有标题的引言。\n\n一、成立条件\n应逐项检验。",
            encoding="utf-8",
        )
        receipt = self.as_json(self.execute("corpus_analysis.py", "FIXTURE-1", self.source, "--preview"))
        self.assertFalse(self.processed.exists())
        self.assertNotIn("path", receipt)
        self.assertEqual([block["region"] for block in receipt["preview"]], ["abstract", "body", "body", "body"])
        self.assertEqual(receipt["preview"][1]["start"], "因此，这是没有标题的引言。")
        self.as_json(self.ingest())
        report = self.as_json(self.execute("style_statistics.py", "--processed-dir", self.processed))
        connectors = {row["value"]: row["count"] for row in report["groups"][0]["connector_matches"]}
        self.assertEqual(connectors["因此"], 1)

    def test_standalone_abstract_label_and_wrapped_keywords(self):
        self.source.write_text(
            "摘要\n\n这是标记后的摘要。\n\n关键词：人格权；\n"
            "个人信息；诉讼\n本段正文紧接关键词，并以句号结束。",
            encoding="utf-8",
        )
        receipt = self.as_json(self.ingest())
        blocks = json.loads(Path(receipt["path"]).read_text(encoding="utf-8"))["blocks"]
        self.assertEqual([block["region"] for block in blocks], ["abstract", "abstract", "keywords", "body"])
        self.assertIn("个人信息；诉讼", blocks[2]["text"])
        self.assertNotIn("本段正文", blocks[2]["text"])

    def test_numbered_citation_footnote_does_not_contaminate_page_body(self):
        self.source.write_text(
            "一、引言\n这是正文。\n① 参见合成来源。\n"
            "脚注续行，属于同一段。\n\n同页脚注之后的正文。"
            "\f（二）展开\n跨页后的正文。",
            encoding="utf-8",
        )
        receipt = self.as_json(self.ingest())
        blocks = json.loads(Path(receipt["path"]).read_text(encoding="utf-8"))["blocks"]
        self.assertEqual([block["region"] for block in blocks],
                         ["introduction", "introduction", "footnotes", "introduction", "body", "body"])
        self.assertIn("脚注续行", blocks[2]["text"])
        self.assertEqual(blocks[-1]["page"], 2)

    def test_circled_footnotes_above_twenty_preserve_next_page_body(self):
        markers = "㉑㉖㉗㉘㉙㉟㊱㊿"
        self.source.write_text(
            "一、引言\n第一页正文。\n"
            + "\n".join(f"{marker} 参见合成来源。" for marker in markers)
            + "\n脚注续行。\f第二页恢复正文。",
            encoding="utf-8",
        )
        receipt = self.as_json(self.ingest())
        blocks = json.loads(Path(receipt["path"]).read_text(encoding="utf-8"))["blocks"]
        self.assertEqual([block["region"] for block in blocks],
                         ["introduction", "introduction"] + ["footnotes"] * len(markers) + ["introduction"])
        self.assertEqual([block["text"][0] for block in blocks[2:-1]], list(markers))
        self.assertTrue(all(block["page"] == 1 for block in blocks[:-1]))
        self.assertIn("脚注续行", blocks[-2]["text"])
        self.assertEqual((blocks[-1]["page"], blocks[-1]["text"]), (2, "第二页恢复正文。"))

    def test_printed_page_map_rejects_impossible_or_ambiguous_mappings(self):
        mapping = self.root / "printed-pages.json"
        mapping.write_text('[[1, 9]]', encoding="utf-8")
        result = self.ingest(options=("--printed-pages", mapping))
        self.assertEqual(result.returncode, 1)
        self.assertIn("含分页符", result.stderr)
        self.source.write_text("一、引言\n正文。\f二、结语\n结束。", encoding="utf-8")
        for bad in ([[3, 9]], [[1, 9], [1, 10]], [[1, 9], [2, "9"]], [[True, 9]]):
            with self.subTest(bad=bad):
                mapping.write_text(json.dumps(bad), encoding="utf-8")
                result = self.ingest(options=("--printed-pages", mapping))
                self.assertEqual(result.returncode, 1)
                self.assertIn("刊页", result.stderr)
                self.assertFalse(self.processed.exists())
        mapping.write_text('[[2, "附录 3"]]', encoding="utf-8")
        receipt = self.as_json(self.ingest(options=("--printed-pages", mapping)))
        self.assertEqual(receipt["physical_page_count"], 2)
        report = self.as_json(self.execute("style_statistics.py", "--processed-dir", self.processed))
        headings = report["samples"][0]["headings"]
        self.assertEqual([(h["page"], h["printed_page"]) for h in headings], [(1, None), (2, "附录 3")])

    def test_rights_and_quality_note_required(self):
        self.set_catalog(fixture(rights_note=None))
        result = self.ingest()
        self.assertEqual(result.returncode, 1)
        self.assertIn("使用限制", result.stderr)
        result = self.execute(
            "corpus_analysis.py", "FIXTURE-1", self.source, "--processed-dir", self.processed,
            "--rights-note", "合成测试", "--quality", "high",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("--quality-note", result.stderr)

    def test_stats_exclude_nonbody_and_locate_term_variants(self):
        self.as_json(self.ingest())
        terms = self.root / "terms.json"
        terms.write_text('{"个人信息": ["个人资料"]}', encoding="utf-8")
        report = self.as_json(self.execute(
            "style_statistics.py", "--processed-dir", self.processed,
            "--terms", terms, "--group-by", "paper", "--top", "300",
        ))
        group = report["groups"][0]
        connectors = {row["value"]: row["count"] for row in group["connector_matches"]}
        self.assertEqual(connectors["然而"], 1)
        self.assertEqual(connectors["因此"], 1)
        self.assertIn("人格权", {row["value"] for row in group["top_token_units"]})
        self.assertEqual(group["sentence_length"]["count"], 6)
        self.assertEqual(group["paragraph_length"]["count"], 4)
        self.assertEqual({row["form"] for row in report["term_matches"]}, {"个人信息", "个人资料"})
        self.assertTrue(all(row["block_counts"] for row in report["term_matches"]))

    def test_stats_exclude_low_quality_and_detect_tampering(self):
        receipt = self.as_json(self.ingest(quality="low"))
        report = self.as_json(self.execute("style_statistics.py", "--processed-dir", self.processed))
        self.assertEqual(report["status"], "no_eligible_local_texts")
        self.assertEqual(report["excluded"][0]["reason"], "not_reviewed_high_or_medium")
        report = self.as_json(self.execute("style_statistics.py", "--processed-dir", self.processed, "--include-low-quality"))
        self.assertEqual(report["groups"][0]["papers"], 1)
        index_path = Path(receipt["path"])
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["blocks"][0]["text"] = "未经重新入库的修改"
        index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        result = self.execute("style_statistics.py", "--processed-dir", self.processed)
        self.assertEqual(result.returncode, 1)
        self.assertIn("文本块校验失败", result.stderr)

    def test_stats_keep_roles_separate_and_omit_reprints(self):
        self.set_catalog(
            fixture(),
            fixture("FIXTURE-2", title="合成记录一（转载）", version_of="FIXTURE-1"),
            fixture("CONTROL-1", corpus_role="comparison", authors=["示例作者"], title="合成对照"),
        )
        for identifier in ("FIXTURE-1", "FIXTURE-2", "CONTROL-1"):
            self.as_json(self.ingest(identifier))
        report = self.as_json(self.execute("style_statistics.py", "--processed-dir", self.processed, "--group-by", "period"))
        self.assertEqual({group["corpus_role"]: group["paper_ids"] for group in report["groups"]}, {
            "comparison": ["CONTROL-1"], "target": ["FIXTURE-1"],
        })
        self.assertEqual(report["excluded"], [{"id": "FIXTURE-2", "reason": "alternative_version", "kept": "FIXTURE-1"}])

    def test_pdf_ingest_on_available_backend(self):
        try:
            from reportlab.pdfgen.canvas import Canvas
        except ImportError:
            self.skipTest("PDF fixture generation needs reportlab")
        pdf = self.root / "generated-synthetic.pdf"
        document = Canvas(str(pdf))
        document.drawString(72, 700, "This is a fabricated legal example.")
        document.showPage()
        document.drawString(72, 700, "Second page of the example.")
        document.save()
        mapping = self.root / "printed-pages.json"
        mapping.write_text('[[1, 12], [2, "S3"]]', encoding="utf-8")
        receipt = self.as_json(self.ingest(source=pdf, options=("--printed-pages", mapping)))
        index = json.loads(Path(receipt["path"]).read_text(encoding="utf-8"))
        self.assertEqual([block["page"] for block in index["blocks"]], [1, 2])
        self.assertEqual([block["printed_page"] for block in index["blocks"]], ["12", "S3"])
        self.assertIn(index["extractor"], {"pdftotext-layout", "pypdf"})
        self.assertEqual(index["source_sha256"], hashlib.sha256(pdf.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
