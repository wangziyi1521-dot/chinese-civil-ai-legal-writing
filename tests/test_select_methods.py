"""Method retrieval invariants using the 51 real cards and isolated synthetic fixtures."""

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "select_methods.py"
SPEC = importlib.util.spec_from_file_location("select_methods", SCRIPT)
RETRIEVAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RETRIEVAL)


def fixture_record(**overrides):
    record = {
        "id": "FIX-1", "title": "合成标题一", "year": 2000,
        "note_file": "cards.md", "note_line": 3,
        "issue_keywords": ["检索争点"], "methods": ["合成方法二"],
        "use_when": "检查合成材料", "boundary": "仅合成测试",
        "normative_context": "历史语境专用词", "original_locator": "页码待核",
        "citation_status": "verified", "source_url": "https://example.invalid/no-fetch",
    }
    record.update(overrides)
    return record


class RealCardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = RETRIEVAL.load_index(ROOT)

    def select(self, query):
        return RETRIEVAL.select_methods(
            self.records, terms=RETRIEVAL.query_terms([query]), skill_root=ROOT,
        )

    def test_all_51_ids_extract_the_complete_exact_card(self):
        self.assertEqual(len(self.records), 51)
        self.assertEqual(len({record["id"] for record in self.records}), 51)
        for record in self.records:
            with self.subTest(identifier=record["id"]):
                result = RETRIEVAL.select_methods(
                    self.records, identifier=record["id"], skill_root=ROOT,
                )["results"][0]
                text = (ROOT / record["note_file"]).read_text(encoding="utf-8")
                headings = list(re.finditer(r"(?m)^##(?:[^\S\r\n]+[^\r\n]*)?$", text))
                exact = [position for position in headings if re.match(
                    rf"^##[^\S\r\n]+{re.escape(record['id'])}(?:[^\S\r\n]+|$)", position.group(),
                )]
                self.assertEqual(len(exact), 1)
                start = exact[0].start()
                end = next((heading.start() for heading in headings if heading.start() > start), len(text))
                self.assertEqual(result["analysis_card"], text[start:end])
                self.assertEqual(result["analysis_card"].splitlines()[0].split()[1], record["id"])
                self.assertEqual(result["resolved_note_line"], record["note_line"])
                self.assertEqual(result["warnings"], [])
                for field in ("normative_context", "original_locator", "citation_status"):
                    self.assertEqual(result[field], record[field])

    def test_partial_performance_and_termination_has_one_match(self):
        payload = self.select("部分履行 解除")
        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual([result["id"] for result in payload["results"]], ["WL-V12-E-01"])
        self.assertEqual(payload["results"][0]["matched_terms"], ["部分履行", "解除"])
        self.assertIn("1995年", payload["results"][0]["normative_context"])
        self.assertIn("页码待核", payload["results"][0]["original_locator"])

    def test_article_468_and_nature_has_one_match(self):
        payload = self.select("第468条 性质")
        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual([result["id"] for result in payload["results"]], ["WL-A25-04"])
        self.assertIn("精确引页待核", payload["results"][0]["original_locator"])

    def test_unrelated_topic_returns_empty_without_substitute(self):
        payload = self.select("海商提单电放")
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["total_matches"], 0)
        self.assertIn("无匹配方法卡；不强配。", RETRIEVAL.render_markdown(payload))

    def test_default_limit_and_explicit_limit(self):
        default = self.select("概念")
        self.assertGreater(default["total_matches"], 2)
        self.assertEqual(default["returned"], 2)
        limited = RETRIEVAL.select_methods(self.records, terms=["概念"], limit=1, skill_root=ROOT)
        self.assertEqual(limited["returned"], 1)
        self.assertEqual(limited["results"][0]["id"], default["results"][0]["id"])

    def test_unknown_id_or_id_prefix_is_not_a_match(self):
        for identifier in ("WL-V12-E-0", "WL-A25", "NOT-FOUND"):
            with self.subTest(identifier=identifier):
                payload = RETRIEVAL.select_methods(self.records, identifier=identifier, skill_root=ROOT)
                self.assertEqual(payload["results"], [])

    def test_cli_accepts_separate_or_quoted_terms_and_outputs_json(self):
        outputs = []
        for values in (["部分履行", "解除"], ["部分履行 解除"]):
            process = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--query", *values, "--json"],
                capture_output=True, text=True, check=True,
            )
            self.assertEqual(process.stderr, "")
            outputs.append(json.loads(process.stdout))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0]["results"][0]["id"], "WL-V12-E-01")
        self.assertIn("不表示精确引页已核", outputs[0]["usage_note"])

    def test_cli_markdown_keeps_context_and_citation_boundaries(self):
        process = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--id", "WL-A25-04"],
            capture_output=True, text=True, check=True,
        )
        for text in ("WL-A25-04", "（2025）", "发表时的规范语境", "精确引页待核", "verified", "不构成现行法依据"):
            self.assertIn(text, process.stdout)

    def test_cli_rejects_empty_query_and_nonpositive_limit(self):
        for arguments in (["--query", "  "], ["--query", "解除", "--limit", "0"]):
            with self.subTest(arguments=arguments):
                process = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), *arguments], capture_output=True, text=True,
                )
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual(process.stdout, "")


class IsolatedCardsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="method-cards-")
        self.addCleanup(temporary.cleanup)
        self.area = Path(temporary.name)
        self.root = self.area / "skill"
        self.root.mkdir()
        self.card = self.root / "cards.md"
        self.card.write_text(
            "# 合成\n\n## FIX-1 合成标题一\n\n第一卡正文。\n### 内部小节\n应完整保留。\n\n"
            "## FIX-10 前缀冲突\n\n第二卡正文，不能并入第一卡。\n", encoding="utf-8",
        )

    def test_stale_line_falls_back_to_full_id_and_warns(self):
        result = RETRIEVAL.read_card(fixture_record(note_line=9), self.root)
        self.assertEqual(result["resolved_note_line"], 3)
        self.assertIn("### 内部小节\n应完整保留。", result["analysis_card"])
        self.assertNotIn("第二卡正文", result["analysis_card"])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("note_line=9 已过期", result["warnings"][0])
        self.assertIn("按完整 ID 回退", result["warnings"][0])

    def test_prefix_collision_and_missing_exact_heading(self):
        result = RETRIEVAL.read_card(fixture_record(id="FIX-10", note_line=3), self.root)
        self.assertTrue(result["analysis_card"].startswith("## FIX-10 "))
        self.assertNotIn("第一卡正文", result["analysis_card"])
        with self.assertRaises(RETRIEVAL.RetrievalError):
            RETRIEVAL.read_card(fixture_record(id="FIX-100"), self.root)

    def test_duplicate_exact_headings_are_rejected(self):
        self.card.write_text("## FIX-1 一\n正文一\n## FIX-1 二\n正文二\n", encoding="utf-8")
        with self.assertRaises(RETRIEVAL.RetrievalError):
            RETRIEVAL.read_card(fixture_record(note_line=1), self.root)

    def test_search_is_and_across_only_the_five_allowed_fields(self):
        record = fixture_record()
        self.assertTrue(RETRIEVAL.matches_query(record, ["标题一", "方法二"]))
        self.assertFalse(RETRIEVAL.matches_query(record, ["标题一", "不存在"]))
        for term in ("历史语境专用词", "页码待核", "verified", "no-fetch", "FIX-1"):
            with self.subTest(term=term):
                self.assertFalse(RETRIEVAL.matches_query(record, [term]))

    def test_absolute_traversal_and_symlink_escape_are_rejected(self):
        outside = self.area / "outside.md"
        outside.write_text("## FIX-1 绝不读取\n越界内容\n", encoding="utf-8")
        (self.root / "escape.md").symlink_to(outside)
        for path in (str(outside), "../outside.md", "escape.md"):
            with self.subTest(path=path):
                with self.assertRaises(RETRIEVAL.RetrievalError):
                    RETRIEVAL.read_card(fixture_record(note_file=path), self.root)

    def test_index_symlink_escape_is_rejected(self):
        external = self.area / "outside.jsonl"
        external.write_text(json.dumps(fixture_record()), encoding="utf-8")
        metadata = self.root / "corpus" / "metadata"
        metadata.mkdir(parents=True)
        (metadata / "issue-index.jsonl").symlink_to(external)
        with self.assertRaises(RETRIEVAL.RetrievalError):
            RETRIEVAL.load_index(self.root)

    def test_source_contents_are_returned_as_data_and_never_executed(self):
        marker = self.root / "MUST-NOT-EXIST"
        executable_text = f"__import__('pathlib').Path({str(marker)!r}).touch()"
        self.card.write_text(f"## FIX-1 合成\n```python\n{executable_text}\n```\n", encoding="utf-8")
        record = fixture_record(note_line=1, source_url=executable_text)
        result = RETRIEVAL.read_card(record, self.root)
        self.assertIn(executable_text, result["analysis_card"])
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
