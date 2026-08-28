"""R5's mandatory synthetic ranking benchmark (sections 31-33): extends
R4's own synthetic hatch families/variants (`tests/hatch_fixtures.py`) into
a retrieval benchmark for the similarity engine, entirely offline and
deterministic -- no GPU, no external API, no customer data.

Deliberately built directly on the pure `combined_similarity.compare()`
function and R4's own `HatchFeatureExtractor`, not the database-backed
`PatternLibraryService` -- this is a property of the similarity ALGORITHM
(does it rank the right family highest?), independent of persistence, so
testing it at this layer is both faster and a more precise regression
signal than routing everything through Postgres.

See docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md for the full measured
results (Top-1/Top-3 rates, the negative-control finding, and the
resulting evidence_coverage/MIN_COVERAGE_FOR_HIGH_BAND fix) this file's
thresholds are calibrated against.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.hatch.feature_extractor import HatchFeatureExtractor
from app.hatch.similarity.combined_similarity import compare
from app.hatch.similarity.config import HIGH_SIMILARITY_THRESHOLD, MIN_COVERAGE_FOR_HIGH_BAND
from app.hatch.similarity.models import ComparableFeatures
from app.schemas.pattern_library import similarity_band
from tests import hatch_fixtures as hfx

_EXTRACTOR = HatchFeatureExtractor()

# The 6 "genuine hatch" families -- G (dotted noise) and H (irregular
# lines) are deliberately excluded from the ranking library itself (they
# are non-hatch/irregular CONTROLS, not families a real library search is
# expected to retrieve), and used instead as negative-control queries below.
RANKABLE_FAMILIES = {
    "A": hfx.family_a_parallel_45,
    "B": hfx.family_b_parallel_90,
    "C": hfx.family_c_parallel_wide_spacing,
    "D": hfx.family_d_cross_hatch_45_135,
    "E": hfx.family_e_dense_cross_hatch,
    "F": hfx.family_f_sparse_cross_hatch,
}

VARIANTS = {
    "blur": lambda img: hfx.variant_blur(img),
    "noise": lambda img: hfx.variant_noise(img),
    "brightness": lambda img: hfx.variant_brightness(img),
    "scale_0.75": lambda img: hfx.variant_scale(img, 0.75),
    "scale_1.5": lambda img: hfx.variant_scale(img, 1.5),
    "rotate_2": lambda img: hfx.variant_rotate(img, 2),
    "crop_offset": lambda img: hfx.variant_crop_offset(img),
    "line_interruption": lambda img: hfx.variant_line_interruption(img),
    "overlay": lambda img: hfx.variant_overlay_crossing_line(img),
}


def _features(image) -> ComparableFeatures:
    return ComparableFeatures.from_features(_EXTRACTOR.extract(image))


def _build_library() -> dict[str, ComparableFeatures]:
    return {name: _features(builder()) for name, builder in RANKABLE_FAMILIES.items()}


def _rank_against_library(query: ComparableFeatures, library: dict[str, ComparableFeatures]) -> list[tuple[str, float]]:
    scored = []
    for name, candidate in library.items():
        result = compare(query, candidate)
        if result.comparable:
            scored.append((name, result.overall_similarity))
    scored.sort(key=lambda pair: -pair[1])
    return scored


class RankingBenchmarkTests(unittest.TestCase):
    """R5 section 32 -- mandatory: Top-1 and Top-3 retrieval across
    multiple families and perturbations. These are retrieval metrics, not
    ML accuracy claims (R5 explicitly says R4's explainable features are
    sufficient, not a trained classifier)."""

    @classmethod
    def setUpClass(cls):
        cls.library = _build_library()

    def _run_full_benchmark(self):
        """Returns (total, top1_hits, top3_hits, failures) across every
        (family, variant) query case."""
        total = top1_hits = top3_hits = 0
        failures = []
        for family_name, builder in RANKABLE_FAMILIES.items():
            base_image = builder()
            for variant_name, variant_fn in VARIANTS.items():
                query = _features(variant_fn(base_image))
                ranked = _rank_against_library(query, self.library)
                ranked_names = [name for name, _ in ranked]
                rank = ranked_names.index(family_name) + 1 if family_name in ranked_names else None

                total += 1
                if rank == 1:
                    top1_hits += 1
                if rank is not None and rank <= 3:
                    top3_hits += 1
                else:
                    failures.append((family_name, variant_name, ranked[:3]))
        return total, top1_hits, top3_hits, failures

    def test_top_1_retrieval_meets_the_measured_benchmark_rate(self):
        total, top1_hits, _, failures = self._run_full_benchmark()
        rate = top1_hits / total
        # Measured 100% (54/54) at authoring time (see benchmark doc) --
        # asserting a 90% floor rather than the exact measured rate so a
        # single incidental future tie/rounding change doesn't fail CI,
        # while still catching any real regression in ranking quality.
        self.assertGreaterEqual(rate, 0.9, f"Top-1 rate {rate:.1%}, failures: {failures}")

    def test_top_3_retrieval_meets_the_measured_benchmark_rate(self):
        total, _, top3_hits, failures = self._run_full_benchmark()
        rate = top3_hits / total
        self.assertGreaterEqual(rate, 0.95, f"Top-3 rate {rate:.1%}, failures: {failures}")

    def test_every_family_individually_retrieves_itself_at_rank_one_for_its_own_blur_variant(self):
        """A more targeted per-family check, independent of the aggregate
        rate above -- proves no single family is silently propping up the
        aggregate while another consistently fails."""
        for family_name, builder in RANKABLE_FAMILIES.items():
            with self.subTest(family=family_name):
                query = _features(hfx.variant_blur(builder()))
                ranked = _rank_against_library(query, self.library)
                self.assertEqual(ranked[0][0], family_name)


class NegativeControlTests(unittest.TestCase):
    """R5 section 33 -- mandatory: querying a non-hatch/irregular control
    must not produce a misleadingly near-perfect similarity against a
    genuine hatch family."""

    @classmethod
    def setUpClass(cls):
        cls.library = _build_library()

    def test_dotted_noise_control_does_not_score_near_perfect(self):
        query = _features(hfx.family_g_dotted_noise())
        ranked = _rank_against_library(query, self.library)
        best_score = ranked[0][1]
        self.assertLess(best_score, 0.95, f"dotted-noise control scored suspiciously high: {ranked}")

    def test_irregular_lines_control_does_not_score_near_perfect(self):
        query = _features(hfx.family_h_irregular_lines())
        ranked = _rank_against_library(query, self.library)
        best_score = ranked[0][1]
        self.assertLess(best_score, 0.95, f"irregular-lines control scored suspiciously high: {ranked}")

    def test_negative_control_high_raw_scores_are_never_banded_high(self):
        """The actual R5 finding this benchmark surfaced: G's raw
        similarity against some genuine families crosses the numeric HIGH
        threshold (a coverage artifact -- see
        similarity/config.py::MIN_COVERAGE_FOR_HIGH_BAND's own docstring),
        so the qualitative band -- what a user would actually see -- must
        cap it, even though the raw number alone does not."""
        query = _features(hfx.family_g_dotted_noise())
        found_a_high_raw_score = False
        for name, candidate in self.library.items():
            result = compare(query, candidate)
            if not result.comparable:
                continue
            if result.overall_similarity >= HIGH_SIMILARITY_THRESHOLD:
                found_a_high_raw_score = True
                band = similarity_band(result.overall_similarity, result.evidence_coverage)
                self.assertNotEqual(
                    band, "high",
                    f"dotted-noise vs {name}: raw={result.overall_similarity:.3f} "
                    f"coverage={result.evidence_coverage:.3f} must not band as high",
                )
                self.assertLess(result.evidence_coverage, MIN_COVERAGE_FOR_HIGH_BAND)
        # Document, don't assume: this test is only meaningful if the
        # scenario it guards against actually occurs for this fixture set.
        self.assertTrue(found_a_high_raw_score, "expected at least one high-raw-score case to exercise the cap")


if __name__ == "__main__":
    unittest.main()
