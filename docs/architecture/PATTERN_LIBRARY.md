# Project Pattern Library (R5) — Architecture

Date: 2026-08-28
Scope: the first reusable hatch-pattern library — **project-scoped only**. A confirmed `LegendEntry` with a computed R4 `HatchFeatureSet` can be added as a `PatternLibraryEntry`; a future hatch's features can then be compared against that project's library to surface Top-K candidate material suggestions. The library **suggests**; it never assigns a material without explicit user confirmation.

## Project scope (why not office/company/global)

The same 45° hatch means reinforced concrete in one project, existing construction in another, masonry in a third — a hatch pattern never globally implies one material. R5 therefore stores and searches library entries **strictly within the project that created them**; `PatternLibraryEntry.project_id` is the only scope key, and every query (`list_entries`, `find_matches`) filters on it. No planning-office, company, or global library exists in this release.

**Future hierarchy (documented, not implemented):** a later release may add broader scopes with the conceptual lookup order `Project → Planning office → Company → Global MassIQ`, where a narrower scope always wins over a broader one (a project-specific match beats an office-wide one, which beats a company-wide one, which beats the eventual global fallback). R5 does not build any of this — only the project layer exists, and this document exists so a future release doesn't have to rediscover the intended ordering.

## Provenance

Every `PatternLibraryEntry` traces back through a real chain, never an anonymous pattern:

```
Project → Plan → LegendEntry (CONFIRMED, with a confirmed material name)
        → pattern crop (stored via R3's StorageService)
        → HatchFeatureSet (R4, versioned)
        → PatternLibraryEntry (references source_legend_entry_id + hatch_feature_set_id)
```

`PatternLibraryEntry` does **not** duplicate any `HatchFeatureSet` column (no copied angles/spacing/density/etc.) — it holds a foreign key to the authoritative, versioned feature row instead, so a future feature recompute is reflected by re-pointing this reference, never by two disagreeing copies of the same measurement. The original pattern crop image is never touched or copied by R5 — it continues to live only under the source `LegendEntry`, resolved through the existing R3 `StorageService`.

## Domain model

`PatternLibraryEntry` (`backend/app/models/pattern_library_entry.py`):

| Field | Notes |
|---|---|
| `project_id` | scope key, FK `projects.id` CASCADE |
| `source_legend_entry_id` | **unique** FK `legend_entries.id` CASCADE — see Duplicate policy |
| `hatch_feature_set_id` | FK `hatch_feature_sets.id` CASCADE |
| `canonical_material_name` | copied from `LegendEntry.material_name` at add-time |
| `material_code`, `thickness_mm`, `original_label` | copied from the source entry; no Material Catalog (R5 section 8) |
| `confirmation_count` | incremented on every re-add of the same source entry |
| `active` | soft-retirement flag, not exercised by any R5 route yet (no delete/deactivate endpoint) — included now to avoid a second migration the first time a future release needs it |

`PatternMatchDecision` (`backend/app/models/pattern_match_decision.py`) — an **append-only, immutable** log (no `updated_at`, no update path in the service): `project_id`, `candidate_legend_entry_id`, nullable `suggested_library_entry_id` (`ON DELETE SET NULL` — a later library-entry deletion must not erase decision history, only the now-dangling reference), nullable `similarity_at_decision`, `decision` (`accepted` / `rejected` / `manual`), nullable `confirmed_material_name`, `created_at`. Not used to train anything in R5 — it exists purely as a persisted, honest history of what was suggested vs. what the user actually confirmed, for a future release to evaluate matcher quality against.

## Duplicate policy

`source_legend_entry_id` carries a **unique constraint** — at most one `PatternLibraryEntry` can ever exist per source `LegendEntry`, enforced at the database level (not just in the service). Re-adding the same confirmed `LegendEntry` (the user re-confirms material info and adds it again) **updates the existing row in place**: material fields and the `hatch_feature_set_id` reference are refreshed, `confirmation_count` increments, `active` is reset to `True`. This is a deliberate, intentional update — never a silent second, ambiguous entry for the same source pattern.

## Library creation policy (no silent computation)

`PatternLibraryService.add_entry` requires, in order: the `LegendEntry` exists and belongs to the project (via `LegendService.get_entry`'s already-tested ownership chain), is `CONFIRMED`, has a non-blank `material_name`, and has an **already-computed** `HatchFeatureSet`. If no feature set exists, `FeatureSetRequiredError` is raised — R4's own explicit-computation-only policy (`POST .../features`) is never bypassed by adding a pattern to the library; a caller must have already run that step deliberately.

## Similarity engine (`backend/app/hatch/similarity/`)

A deterministic, explainable subsystem, one small module per component (mirrors R4's own `hatch/` package discipline — no 500-line scoring function):

```
angle_similarity.py       -- circular orientation distance, best-pairing for multi-angle patterns
spacing_similarity.py     -- smooth relative-difference, respects R4's ~15% scale deviation
density_similarity.py     -- bounded absolute difference (density is always [0,1])
periodicity_similarity.py -- bounded absolute difference
cross_hatch_similarity.py -- clean binary agreement (1.0/0.0), never fabricated on missing evidence
line_width_similarity.py  -- nullable-aware, excluded (not zeroed) when either side is unmeasured
color_similarity.py       -- CIE76 LAB distance, low weight
combined_similarity.py    -- orchestrates all seven, feature-version gate, weighted renormalization
```

`ComparableFeatures` (`similarity/models.py`) is a small, framework-free dataclass built via `ComparableFeatures.from_features(obj)` — duck-typed against either a persisted `HatchFeatureSet` ORM row or an in-memory `HatchFeatures` dataclass, identical field names, zero coupling to SQLAlchemy.

### Feature-version compatibility (checked first, before any component)

`combined_similarity.compare()` compares `reference.feature_version` against `candidate.feature_version` **before** computing anything else. A mismatch returns `SimilarityResult(comparable=False, reason="feature_version_mismatch")` — no number is fabricated by pretending two different algorithm versions measure the same thing. `PatternLibraryService.find_matches` counts these separately (`incompatible_count`) and excludes them from ranking entirely.

### Angle similarity

Uses `hatch.normalization.circular_angle_distance` directly (never re-derived) — 179° and 1° are 2° apart, not 178°, exactly as in R4. For multi-angle patterns (0, 1, or 2 dominant angles per side), angles are matched by **best pairing**, not by array position: `[45, 135]` vs `[135, 45]` scores as a perfect match. A count mismatch (single-direction vs. cross-hatch) matches the smaller set's angle(s) to their closest counterpart and does **not** itself penalize the count difference — that is `cross_hatch_similarity`'s job, kept deliberately separate. Missing evidence on either side (empty angle list) excludes the component entirely.

### Spacing similarity — respects R4's documented scale-invariance limit

`relative_error = abs(a - b) / max(a, b)`, `similarity = 1 - relative_error`. Calibrated directly against R4's own measured evidence: the worst documented same-pattern deviation (~15% normalized-spacing drift at the 2.0x scale extreme, see `docs/testing/R4_HATCH_FEATURE_BENCHMARK.md`) maps to a similarity of ~0.85 under this formula — still clearly "a match," not penalized as if it were a genuinely different pattern. No exact-equality or tight-threshold comparison is used anywhere.

### Density, periodicity

Both bounded `[0,1]` features, compared via plain bounded absolute difference — no relative-error formula needed since the value range is already fixed. Density is always available (never `None`); periodicity is excluded when either side lacks `periodicity_available`.

### Cross-hatch agreement

Full agreement (both single-direction, or both cross-hatch) scores `1.0`; disagreement scores `0.0` — a real, meaningful penalty, not a token deduction. Either side undetermined (`is_cross_hatch=None`, i.e. no reliable primary angle at all) excludes the component. **Architectural note**: R5 explicitly forbids one boolean field from being able to zero the *overall* similarity. This is guaranteed structurally, not by softening the component score: `combined_similarity` combines components as a **weighted average**, never a product/AND-gate, and `CROSS_HATCH_WEIGHT` (0.10) is well below 1.0 — a 0.0 cross-hatch score can only pull the renormalized overall score down by its own weight share, never to zero, as long as other components carry evidence.

### Line width

Nullable/evidence-gated on both sides independently (mirrors R4's own `MIN_LINE_WIDTH_SAMPLES` gate). If either side has no reliable measurement, the component is **excluded from the denominator**, never substituted with zero — missing evidence and negative evidence are different facts, and R5 preserves that distinction exactly as R4 established it.

### Color

CIE76 (plain Euclidean) distance in the same OpenCV 8-bit LAB space `hatch/color.py` already computes features in. Deliberately the **lowest weight** in the combined score (0.07) — construction-drawing color varies with scanner brightness, grayscale printing, and PDF export differences that have nothing to do with the underlying hatch pattern. `COLOR_MAX_LAB_DISTANCE` (120) was calibrated against actual measured values, not guessed: genuine same-pattern brightness/blur/noise/scale variants measured only 0.5–8.5 LAB units apart; measurably different hatch families (mostly density-driven brightness differences, since the benchmark fixtures are grayscale ink-on-paper) ranged up to ~125 units apart.

## Combined similarity — weights and missing-evidence handling

| Component | Weight | Rationale |
|---|---|---|
| Angle | 0.30 | Highest — the tightest, most reproducible synthetic-family separation in the R4 benchmark |
| Spacing | 0.20 | High — second most reliable structural signal |
| Periodicity | 0.15 | Medium-high — directly useful for catching the R4-documented irregular-line false-positive risk |
| Density | 0.10 | Medium — supporting evidence, must not dominate structural evidence |
| Cross-hatch | 0.10 | Medium — meaningful but bounded by weight, never able to zero the total alone |
| Line width | 0.08 | Low-medium — often unmeasured, evidence-gated |
| Color | 0.07 | Low — most exposed to scan/brightness variation |

These are the **initial, documented weights**, informed by which R4 features showed the tightest synthetic-family separation in the R4 benchmark — not copied from an unrelated example. Verified against the full R5 ranking benchmark as a whole (see the benchmark doc): **no numeric weight adjustment was needed** — the initial weights achieved 100% Top-1/Top-3 retrieval across the entire 54-case synthetic benchmark on the first run. The one real fix this release's benchmark evidence did drive was structural, not a weight retune — see "Evidence coverage" below.

When one or more components are excluded (missing evidence), the denominator is **recalculated over only the available components' weights** (R5 section 19's explicit instruction) — `overall = Σ(weight × score for available components) / Σ(weight for available components)`. A missing optional feature is never treated as zero similarity.

### Evidence coverage — a real finding from the benchmark's negative control

The mandatory negative control (R5 section 33) surfaced a real, non-hypothetical issue: querying the synthetic "dotted noise" non-hatch control against the benchmark library produced a raw similarity of **0.84** against an unrelated genuine hatch family. Not because the patterns actually resembled each other — the dotted control has no reliable angle, spacing, periodicity, or cross-hatch evidence at all (same `MIN_ANGLE_EVIDENCE_PX` gate R4 already established), leaving only density + color (a combined weight of 0.17–0.25 out of the full 1.0 budget) to determine the **entire** renormalized score. Renormalizing over available features (as R5 section 19 explicitly requires) is correct for genuinely partial evidence, but this case is different in kind: almost nothing was actually measured.

The fix is **not** a weight change (that would violate R5 section 34's "don't tune one test at a time," and would just move the same problem elsewhere) — it's a new, explicit piece of quality metadata: `SimilarityResult.evidence_coverage` (the sum of weights of the components that were actually available, out of 1.0). The raw `overall_similarity` number is left exactly as the renormalization formula produces it — never silently altered. Instead, the **qualitative band** (HIGH/MEDIUM/LOW, the only thing R5 says should ever reach a user) is capped: a score would otherwise band HIGH only if `evidence_coverage >= MIN_COVERAGE_FOR_HIGH_BAND` (0.5, i.e. at least half the intended feature weight actually had evidence on both sides); otherwise it is capped at MEDIUM regardless of the raw number. This is exactly the same "quality metadata, never a fabricated confidence score" discipline R4 established with `angle_evidence_strength` and the `*_available` flags, applied to the one degenerate case the benchmark actually found.

## Similarity vs. probability — explicit naming

Every score this system produces is a **SIMILARITY** — a bounded structural/visual resemblance measure — never a probability, never a confidence that a material association is correct. This is enforced in naming everywhere it appears: the field is `overall_similarity` (never `confidence` or `probability`), the API field is `similarity`, and the frontend displays "Pattern similarity: 89%" — never "89% confidence" or "89% probability this is concrete." `angle_evidence_strength` (R4) and `evidence_coverage` (R5) are both explicitly unbounded/quality-metadata fields, documented as such, never presented as `[0,1]` confidence.

## Top-K search

`PatternLibraryService.find_matches(project_id, plan_id, legend_entry_id, top_k=5)`:

1. Requires the querying `LegendEntry`'s `HatchFeatureSet` to already exist (same explicit-computation-only policy as `add_entry`) — raises `FeatureSetRequiredError` otherwise, never computing it silently.
2. Queries `PatternLibraryEntry WHERE project_id = <this project> AND active = true`, excluding the querying entry's own library row if it has one (a 100% self-match is not a useful suggestion).
3. Compares against every candidate via `combined_similarity.compare`; version-incompatible candidates are counted (`incompatible_count`) and excluded from ranking.
4. Sorts **deterministically**: similarity DESC, then `created_at` ASC, then `id` ASC as a final stable tie-break — plain Python scoring over project-scoped SQL rows, no vector search, no external index. At R5's expected library scale (tens to low hundreds of entries per project) this is comfortably fast (see the benchmark doc's performance section) and deliberately not optimized further, per R5's explicit "do not add a vector DB for theoretical future scale" instruction.
5. Returns the top `top_k` (default 5) with component scores, `evidence_coverage`, and enough provenance (`source_plan_id`, `source_legend_entry_id`) for the frontend to fetch a preview image through the existing, already-tested crop-serving route.

### No-match behavior (R5 section 24)

An empty project library returns `candidates: [], reason: "empty_library"` — not an error. If the library has entries but every one is version-incompatible, `reason: "no_comparable_candidates"`. Either way, the original R3 confirm workflow is completely unaffected: a user can always type the material manually and confirm, with or without any library assistance (see R5 section 39 — verified explicitly in the Playwright suite's pre-existing R3/R3.5 scenarios, all of which remain green and untouched).

## API surface

```
POST /api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/library          -- add/update
GET  /api/projects/{project_id}/pattern-library                                                   -- project-scoped list
POST /api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/matches           -- Top-K search
POST /api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/match-decision    -- record a decision
GET  /api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/match-decisions   -- decision history
```

Every domain error maps to a controlled 400/404 (never a raw exception). No local filesystem path is ever present in a response. `source_plan_id` on both the library-listing and matches responses is a transient, computed enrichment (looked up via the source `LegendEntry`, never a real column on `pattern_library_entries`) — it exists purely so the frontend can build a pattern-preview URL through R3's existing crop-serving route.

## Frontend (minimal, optional)

Two small additive components, reusing existing CSS classes:

- `PatternMatchesPanel.jsx` — "Find Matches" button, a list of Top-K candidates (thumbnail, material, "Pattern similarity: NN% (band)"), "Use this" / "Reject" actions. Restores previously-recorded decisions on load (`GET .../match-decisions`) so a reload shows the same accepted/rejected state, not a blank slate.
- `PatternLibraryPanel.jsx` — a simple project-level list (thumbnail, material, confirmation count, created date). No filtering, no bulk editing, no hierarchy UI.

"Use this" prefills the material fields already present in `LegendEntryEditor` (from R3) — it never silently saves or confirms anything; the user still explicitly clicks "Save Correction & Material" and "Confirm Legend Entry," preserving R3's human-in-the-loop confirmation as the sole source of truth.

## Known limitations

- Only one real, non-synthetic construction plan exists in this development environment (see `docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md`'s real-crop section) — R5's real-data validation compares two independently-drawn crops of the *same* real wall, which is genuine evidence but not a cross-plan validation.
- `evidence_coverage`'s 0.5 threshold is itself a documented, not exhaustively tuned, choice — revisit if a future release's real usage surfaces cases it doesn't handle well.
- The library has no deactivate/delete endpoint yet; `active` exists in the schema for a future release to use without a second migration.
