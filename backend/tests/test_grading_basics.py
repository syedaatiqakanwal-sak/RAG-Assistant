"""Unit tests for grading helpers that do not require embedding models or Ollama."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.chunking import (
    chunk_curriculum_text,
    extract_core_topics,
    extract_learning_outcomes,
    has_detectable_structure,
    split_into_sections,
)
from app.core.classification import classify_syllabus_status, to_percent, aggregate_similarity
from app.core.config import settings
from app.core.correction_log import append_correction, list_corrections
from app.core.curriculum import parse_curriculum_path
from app.core.correction_log import append_correction, list_corrections
from app.core.hashing import normalize_submission_text, submission_cache_hash
from app.core.json_util import parse_json_object


SAMPLE_SYLLABUS = """# Unit 401 Programming

## Learning Outcomes

LO1: Analyse a simple problem and produce a structured design.
LO2: Implement a working solution in a high-level language.

## Core Topics

- Variables and data types
- Selection and iteration
- Functions

## Unit 401: Assessment

Students submit a short program covering the outcomes above.
"""


class ClassificationTests(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(classify_syllabus_status(70, 70, 50), "IN_SYLLABUS")
        self.assertEqual(classify_syllabus_status(69.9, 70, 50), "PARTIALLY_RELATED")
        self.assertEqual(classify_syllabus_status(50, 70, 50), "PARTIALLY_RELATED")
        self.assertEqual(classify_syllabus_status(49.9, 70, 50), "OUT_OF_SYLLABUS")

    def test_percent_and_aggregate(self):
        self.assertEqual(to_percent(0.734), 73.4)
        self.assertEqual(aggregate_similarity([0.8, 0.6]), 0.7)
        self.assertEqual(aggregate_similarity([]), 0.0)


class ChunkingTests(unittest.TestCase):
    def test_detects_structure_and_keeps_lo_intact(self):
        self.assertTrue(has_detectable_structure(SAMPLE_SYLLABUS))
        sections = split_into_sections(SAMPLE_SYLLABUS)
        self.assertGreaterEqual(len(sections), 3)
        chunks = chunk_curriculum_text(SAMPLE_SYLLABUS, chunk_size=400, chunk_overlap=40)
        joined = "\n".join(chunks)
        self.assertIn("LO1:", joined)
        self.assertIn("LO2:", joined)
        for chunk in chunks:
            if "LO1:" in chunk:
                self.assertIn("structured design", chunk)

    def test_plain_notes_fall_back(self):
        plain = "This is a lecture transcript without headings. " * 20
        self.assertFalse(has_detectable_structure(plain))
        chunks = chunk_curriculum_text(plain, chunk_size=120, chunk_overlap=20)
        self.assertGreaterEqual(len(chunks), 2)

    def test_extractors(self):
        outcomes = extract_learning_outcomes(SAMPLE_SYLLABUS)
        self.assertEqual(len(outcomes), 2)
        topics = extract_core_topics(SAMPLE_SYLLABUS)
        self.assertTrue(any("Variables" in t for t in topics))


class PathParsingTests(unittest.TestCase):
    def test_hierarchical_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "Level4" / "U401_Programming" / "Syllabus" / "spec.md"
            path.parent.mkdir(parents=True)
            path.write_text("x", encoding="utf-8")
            parsed = parse_curriculum_path(path, root)
            self.assertEqual(parsed["level"], "Level4")
            self.assertEqual(parsed["unit_id"], "U401")
            self.assertEqual(parsed["unit_name"], "Programming")
            self.assertEqual(parsed["doc_type"], "syllabus")


class HashCacheTests(unittest.TestCase):
    def test_near_identical_normalisation(self):
        a = "Hello   World\n\nTEST"
        b = "hello world test"
        self.assertEqual(normalize_submission_text(a), "hello world test")
        self.assertEqual(submission_cache_hash(a), submission_cache_hash(b))


class JsonParseTests(unittest.TestCase):
    def test_fenced_and_raw(self):
        raw = '```json\n{"rationale": "ok", "draft_feedback": "hi"}\n```'
        self.assertEqual(parse_json_object(raw)["rationale"], "ok")
        self.assertEqual(parse_json_object('{"a": 1}')["a"], 1)


class CorrectionLogTests(unittest.TestCase):
    def test_append_and_filter(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        original = settings.CORRECTION_LOG_PATH
        settings.CORRECTION_LOG_PATH = Path(tmp.name) / "correction_log.jsonl"
        self.addCleanup(lambda: setattr(settings, "CORRECTION_LOG_PATH", original))

        append_correction({
            "submission_id": "a1",
            "system_verdict": "IN_SYLLABUS",
            "system_score": 82,
            "corrected_verdict": "PARTIALLY_RELATED",
            "corrected_score": 60,
            "correction_reason": "topic mismatch",
        })
        append_correction({
            "submission_id": "a2",
            "system_verdict": "OUT_OF_SYLLABUS",
            "system_score": 10,
            "corrected_verdict": "IN_SYLLABUS",
            "corrected_score": 75,
            "correction_reason": "wrong unit indexed",
        })
        all_rows = list_corrections(limit=10)
        self.assertEqual(len(all_rows), 2)
        only_a1 = list_corrections(assignment_id="a1")
        self.assertEqual(len(only_a1), 1)
        self.assertEqual(only_a1[0]["corrected_verdict"], "PARTIALLY_RELATED")


if __name__ == "__main__":
    unittest.main()
