#!/usr/bin/env python3
"""Query the verified civil/AI candidate ledger without inferring missing facts."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BODY_LEVELS = {"publisher_pdf", "fulltext_html", "body_without_notes"}
LEVELS = BODY_LEVELS | {"abstract", "metadata_only", "unavailable"}
ROLES = {"wang_style", "doctrinal_methods", "ai_tort_debates"}


def read_records(root=ROOT):
    path = root / "corpus/metadata/civil-ai-candidates.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def analysis_path(record, root=ROOT):
    value = record.get("analysis_file")
    if not value:
        return None
    path = (root / value).resolve()
    boundary = (root / "corpus/analyses").resolve()
    if not path.is_relative_to(boundary) or path.suffix != ".md":
        raise ValueError("analysis_file is outside corpus/analyses")
    return path


def validate(records, root=ROOT):
    errors, seen = [], set()
    for r in records:
        n = r.get("candidate_number")
        if not isinstance(n, int) or isinstance(n, bool) or n < 1 or n in seen:
            errors.append(f"invalid or duplicate candidate number: {n}")
        seen.add(n)
        c = r.get("canonical_citation", {})
        for key in ("authors", "title", "journal", "year", "issue"):
            if not c.get(key):
                errors.append(f"C{n}: missing {key}")
        if not isinstance(c.get("authors"), list) or not all(isinstance(a, str) and a for a in c.get("authors", [])):
            errors.append(f"C{n}: authors must be a nonempty list of names")
        if not isinstance(r.get("full_body_read"), bool):
            errors.append(f"C{n}: full_body_read must be boolean")
        if r.get("access_level") not in LEVELS:
            errors.append(f"C{n}: unknown access_level")
        if r.get("verification_status") not in {"verified", "partial", "unresolved", "corrected"}:
            errors.append(f"C{n}: unknown verification_status")
        if not r.get("sources") or any(not s.get("url", "").startswith(("https://", "http://")) for s in r.get("sources", [])):
            errors.append(f"C{n}: missing source URL")
        if not set(r.get("library_roles", [])).issubset(ROLES):
            errors.append(f"C{n}: unknown library role")
        if "wang_style" in r.get("library_roles", []) and c.get("authors") != ["王利明"]:
            errors.append(f"C{n}: non-solo Wang item in personal style library")
        try:
            p = analysis_path(r, root)
            if p and not p.is_file():
                errors.append(f"C{n}: missing analysis file")
            if r.get("full_body_read") and (r.get("access_level") not in BODY_LEVELS or not p or not p.is_file()):
                errors.append(f"C{n}: full-body claim unsupported")
            if r.get("access_level") not in BODY_LEVELS and p:
                errors.append(f"C{n}: partial text presented as full analysis")
        except ValueError as e:
            errors.append(f"C{n}: {e}")
    return errors


def select(records, ids=None, author=None, role=None, text=None, full_body=False):
    selected = []
    for r in records:
        c = r["canonical_citation"]
        if ids and r["candidate_number"] not in ids:
            continue
        if author and author not in c["authors"]:
            continue
        if role and role not in r["library_roles"]:
            continue
        if text and text.casefold() not in json.dumps(c, ensure_ascii=False).casefold():
            continue
        if full_body and not r.get("full_body_read"):
            continue
        selected.append(r)
    return selected


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", type=int, action="append", dest="ids")
    ap.add_argument("--author")
    ap.add_argument("--role", choices=sorted(ROLES))
    ap.add_argument("--text")
    ap.add_argument("--full-body", action="store_true")
    ap.add_argument("--show-analysis", action="store_true")
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    records = read_records()
    errors = validate(records)
    if args.validate:
        print(json.dumps({"records": len(records), "statuses": dict(Counter(r["verification_status"] for r in records)), "access_levels": dict(Counter(r["access_level"] for r in records)), "full_body_read": sum(bool(r.get("full_body_read")) for r in records), "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    if errors:
        print("Invalid ledger: " + "; ".join(errors), file=sys.stderr)
        return 1
    matches = select(records, args.ids, args.author, args.role, args.text, args.full_body)
    if args.show_analysis:
        for r in matches:
            print(f"\n## C{r['candidate_number']:02d} | {r['access_level']} | {r['verification_status']}")
            p = analysis_path(r)
            print(p.read_text(encoding="utf-8") if p else "No full-body analysis; inspect coverage and remaining_gaps in the ledger.")
    else:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
