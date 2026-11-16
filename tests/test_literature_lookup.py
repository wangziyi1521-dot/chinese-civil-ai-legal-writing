import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("literature_lookup", ROOT / "scripts/literature_lookup.py")
lookup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lookup)


class EvidenceQueries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = lookup.read_records()

    def test_real_catalog_and_analyses_are_consistent(self):
        self.assertEqual(lookup.validate(self.rows), [])
        self.assertTrue(set(range(1, 19)).issubset({r["candidate_number"] for r in self.rows}))

    def test_full_body_excludes_abstract_and_excerpt(self):
        rows = lookup.select(self.rows, full_body=True)
        self.assertEqual({r["candidate_number"] for r in rows if r["candidate_number"] <= 18}, {1, 3, 4, 5, 7, 8, 10, 11, 12, 17})
        self.assertFalse(lookup.select(self.rows, ids=[15], full_body=True))

    def test_exact_number_never_matches_10_to_18(self):
        self.assertEqual([r["candidate_number"] for r in lookup.select(self.rows, ids=[1])], [1])

    def test_coauthor_correction_is_searchable(self):
        self.assertEqual([r["candidate_number"] for r in lookup.select(self.rows, author="徐涵渊")], [12])

    def test_style_role_never_merges_scholars(self):
        self.assertEqual({r["candidate_number"] for r in lookup.select(self.rows, role="wang_style") if r["candidate_number"] <= 18}, {1, 3, 4})
        self.assertFalse(lookup.select(self.rows, author="程啸", role="wang_style"))

    def test_duplicate_and_false_full_text_claim_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows.append(copy.deepcopy(rows[0]))
        self.assertTrue(any("duplicate" in e for e in lookup.validate(rows)))
        rows = copy.deepcopy(self.rows)
        rows[14]["full_body_read"] = True
        self.assertTrue(any("unsupported" in e for e in lookup.validate(rows)))

    def test_analysis_path_cannot_escape_skill_analysis_directory(self):
        row = copy.deepcopy(self.rows[0])
        row["analysis_file"] = "../../state/user-request.txt"
        with self.assertRaises(ValueError):
            lookup.analysis_path(row)

    def test_wrong_author_cannot_enter_wang_style(self):
        rows = copy.deepcopy(self.rows)
        rows[4]["library_roles"].append("wang_style")
        self.assertTrue(any("non-solo Wang" in e for e in lookup.validate(rows)))


if __name__ == "__main__":
    unittest.main()
