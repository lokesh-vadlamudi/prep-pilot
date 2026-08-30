from __future__ import annotations

import json
import re
import unittest
from dataclasses import FrozenInstanceError, replace

from app.content.inference_course import (
    COURSE,
    SUPPLEMENT_ALIASES,
    CatalogValidationError,
    LabDescriptor,
    SelectionRule,
    SupplementAlias,
    catalog_payload,
    explicit_supplement_aliases,
    normalize_alias_identity,
    supplement_alias_payload,
    validate_catalog,
)
from app.content import inference_course


EXPECTED_MODULE_IDS = tuple(f"IC-{index:02d}" for index in range(17))
EXPECTED_SOURCE_KIND_COUNTS = {
    "section": 14,
    "topic": 91,
    "resource": 16,
    "hands_on": 33,
    "workplace_project": 4,
    "workplace_task": 24,
    "personal_project": 4,
    "paper": 9,
    "hardware": 29,
    "routine": 3,
}
REQUIRED_ARTIFACT_TEMPLATES = {
    "IC-03-ARTIFACT-BENCHMARK-DATA": ("benchmark-data", "csv"),
    "IC-07-ARTIFACT-MODEL-FIT": ("model-fit-worksheet", "markdown"),
    "IC-04-ARTIFACT-FRAMEWORK-MATRIX": ("framework-decision-matrix", "markdown"),
    "IC-05-ARTIFACT-QUANTIZATION-CHART": ("quality-speed-memory-chart", "csv"),
    "IC-08-ARTIFACT-SCALING-REPORT": ("scaling-report", "markdown"),
    "IC-09-ARTIFACT-GATEWAY-ADR": ("gateway-adr", "markdown"),
    "IC-10-ARTIFACT-K8S-ROLLBACK": ("kubernetes-rollback-record", "markdown"),
    "IC-11-ARTIFACT-GRAFANA-CHECKLIST": ("grafana-dashboard-checklist", "markdown"),
    "IC-11-ARTIFACT-COST-MODEL": ("cost-model", "csv"),
    "IC-06-ARTIFACT-EXPERIMENT-MEMO": ("experiment-memo", "markdown"),
    "IC-14-ARTIFACT-WORKPLACE-PROPOSAL": ("workplace-proposal", "markdown"),
    "IC-15-ARTIFACT-CAPSTONE-README": ("capstone-readme", "markdown"),
    "IC-16-ARTIFACT-PAPER-NOTES": ("paper-notes", "markdown"),
}
FORBIDDEN_FIELDS = {"xp", "points", "streak", "score", "grade", "percentage", "sm2"}
WORKPLACE_PROJECT_IDS = ("SRC-WP-01", "SRC-WP-02", "SRC-WP-03", "SRC-WP-04")
PAPER_SOURCE_IDS = tuple(f"SRC-PAPER-{index:02d}" for index in range(1, 10))


class InferenceCourseCatalogTests(unittest.TestCase):
    @staticmethod
    def _supplement_alias(**changes) -> SupplementAlias:
        values = {
            "id": "SUPPLEMENT-ALIAS-KV-CACHE-PREREQUISITE",
            "slug_alias": "prereq kv cache memory basics",
            "title_alias": "kv cache memory basics prerequisite",
            "module_id": "IC-02",
            "lesson_id": "IC-02-LESSON",
            "source_id": "SRC-P1-2-TOPIC-KV-CACHE",
        }
        values.update(changes)
        return SupplementAlias(**values)

    @staticmethod
    def _legacy_identity(**changes):
        values = {
            "id": "LEGACY-IDENTITY-TRANSFORMER-ARCHITECTURE-INTERNALS",
            "slug_prefix": "inference-engineering-",
            "title_alias": "transformer architecture internals",
            "chapter_alias": "transformer architecture internals",
            "sequence": 1000,
            "module_id": "IC-01",
            "lesson_id": "IC-01-LESSON",
            "source_id": "SRC-P1-1-SECTION",
        }
        values.update(changes)
        return inference_course.LegacyIdentity(**values)

    def test_supplement_alias_manifest_is_closed_immutable_and_service_ready(self):
        self.assertIsInstance(SUPPLEMENT_ALIASES, tuple)
        self.assertEqual(COURSE.supplement_aliases, SUPPLEMENT_ALIASES)
        self.assertEqual(SUPPLEMENT_ALIASES, ())
        self.assertEqual(explicit_supplement_aliases("IC-02"), ())

        alias = self._supplement_alias()
        synthetic = replace(COURSE, supplement_aliases=(alias,))
        validate_catalog(synthetic)
        self.assertEqual(alias.slug_alias, normalize_alias_identity(alias.slug_alias))
        self.assertEqual(alias.title_alias, normalize_alias_identity(alias.title_alias))
        with self.assertRaises(FrozenInstanceError):
            alias.module_id = "IC-03"  # type: ignore[misc]

    def test_supplement_alias_validation_rejects_collisions_and_invalid_targets(self):
        alias = self._supplement_alias()
        duplicate = replace(
            alias,
            id="SUPPLEMENT-ALIAS-KV-CACHE-DUPLICATE",
            slug_alias=alias.slug_alias,
        )
        with self.assertRaisesRegex(CatalogValidationError, "duplicate normalized supplement alias"):
            validate_catalog(replace(COURSE, supplement_aliases=(alias, duplicate)))

        canonical_collision = replace(alias, slug_alias="ic 02")
        with self.assertRaisesRegex(CatalogValidationError, "canonical identity"):
            validate_catalog(replace(COURSE, supplement_aliases=(canonical_collision,)))

        unknown = replace(alias, source_id="SRC-UNKNOWN")
        with self.assertRaisesRegex(CatalogValidationError, "unknown target source"):
            validate_catalog(replace(COURSE, supplement_aliases=(unknown,)))

        cross_module = replace(alias, source_id="SRC-P2-1-TOPIC-PAGED-ATTENTION")
        with self.assertRaisesRegex(CatalogValidationError, "source ownership"):
            validate_catalog(replace(COURSE, supplement_aliases=(cross_module,)))

    def test_supplement_alias_validation_rejects_fuzzy_wildcard_chain_and_bad_lesson(self):
        alias = self._supplement_alias()
        invalid_cases = (
            (replace(alias, slug_alias="prereq-*"), "normalized exact"),
            (replace(alias, source_id="SUPPLEMENT-ALIAS-OTHER"), "alias chaining"),
            (replace(alias, lesson_id="IC-03-LESSON"), "lesson identity"),
            (replace(alias, id="SUPPLEMENT-ALIAS-1"), "semantic id"),
        )
        for invalid, message in invalid_cases:
            with self.subTest(message=message), self.assertRaisesRegex(CatalogValidationError, message):
                validate_catalog(replace(COURSE, supplement_aliases=(invalid,)))

    def test_supplement_alias_ids_reject_numeric_or_position_derived_segments(self):
        alias = self._supplement_alias()
        for alias_id in (
            "SUPPLEMENT-ALIAS-IC-02-1",
            "SUPPLEMENT-ALIAS-KV-2-PREREQUISITE",
        ):
            with self.subTest(alias_id=alias_id), self.assertRaisesRegex(
                CatalogValidationError, "semantic id",
            ):
                validate_catalog(replace(COURSE, supplement_aliases=(replace(alias, id=alias_id),)))

    def test_legacy_identity_manifest_is_closed_exact_and_omission_sensitive(self):
        self.assertIsInstance(inference_course.LEGACY_IDENTITIES, tuple)
        self.assertEqual(COURSE.legacy_identities, inference_course.LEGACY_IDENTITIES)
        self.assertEqual(inference_course.LEGACY_IDENTITIES, ())
        self.assertEqual(inference_course.legacy_identities("IC-01"), ())

        identity = self._legacy_identity()
        synthetic = replace(COURSE, legacy_identities=(identity,))
        validate_catalog(synthetic)
        matched = inference_course.legacy_identity_match(
            "IC-01",
            slug="inference-engineering-transformer-internals-0",
            title="Transformer Architecture Internals",
            chapter="Transformer Architecture Internals",
            sequence=1000,
            catalog=synthetic,
        )
        self.assertEqual(matched, identity)
        base = {
            "slug": "inference-engineering-transformer-internals-0",
            "title": "Transformer Architecture Internals",
            "chapter": "Transformer Architecture Internals",
            "sequence": 1000,
        }
        for changes in (
            {"title": "Transformer Architecture"},
            {"chapter": "Transformer Internals"},
            {"sequence": 1001},
            {"slug": "other-book-transformer-internals-0"},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(inference_course.legacy_identity_match(
                    "IC-01", catalog=synthetic, **(base | changes),
                ))

    def test_legacy_identity_validation_and_payload_are_semantic_and_deterministic(self):
        first = self._legacy_identity()
        second = self._legacy_identity(
            id="LEGACY-IDENTITY-LLM-GENERATION-DEEP-DIVE",
            title_alias="llm generation deep dive",
            chapter_alias="llm generation deep dive",
            sequence=1001,
            module_id="IC-02",
            lesson_id="IC-02-LESSON",
            source_id="SRC-P1-2-SECTION",
        )
        self.assertEqual(
            inference_course.legacy_identity_payload((first, second)),
            inference_course.legacy_identity_payload((second, first)),
        )
        invalid_cases = (
            (replace(first, id="LEGACY-IDENTITY-IC-01-1"), "semantic id"),
            (replace(first, title_alias="Transformer Architecture Internals"), "normalized exact"),
            (replace(first, chapter_alias="transformer internals"), "source identity"),
            (replace(first, sequence=-1), "sequence"),
            (replace(first, module_id="IC-02", lesson_id="IC-02-LESSON"), "source ownership"),
        )
        for invalid, message in invalid_cases:
            with self.subTest(message=message), self.assertRaisesRegex(CatalogValidationError, message):
                validate_catalog(replace(COURSE, legacy_identities=(invalid,)))
        duplicate = replace(
            second,
            id="LEGACY-IDENTITY-SECOND-TRANSFORMER-ENTRY",
            title_alias=first.title_alias,
            chapter_alias=first.chapter_alias,
            sequence=first.sequence,
            module_id=first.module_id,
            lesson_id=first.lesson_id,
            source_id=first.source_id,
        )
        with self.assertRaisesRegex(CatalogValidationError, "duplicate normalized legacy identity"):
            validate_catalog(replace(COURSE, legacy_identities=(first, duplicate)))

    def test_supplement_alias_serialization_is_stable_across_reordering(self):
        first = self._supplement_alias()
        second = self._supplement_alias(
            id="SUPPLEMENT-ALIAS-PAGED-ATTENTION-PREREQUISITE",
            slug_alias="prereq paged attention basics",
            title_alias="paged attention prerequisite",
            module_id="IC-03",
            lesson_id="IC-03-LESSON",
            source_id="SRC-P2-1-TOPIC-PAGED-ATTENTION",
        )
        forward = supplement_alias_payload((first, second))
        reverse = supplement_alias_payload((second, first))
        self.assertEqual(forward, reverse)
        self.assertEqual([item["id"] for item in forward], sorted((first.id, second.id)))
        self.assertEqual(
            catalog_payload(replace(COURSE, supplement_aliases=(first, second))),
            catalog_payload(replace(COURSE, supplement_aliases=(second, first))),
        )

    def test_has_stable_ordered_course_and_module_identity(self):
        self.assertEqual(COURSE.key, "inference-engineering")
        self.assertEqual(COURSE.version, "2026.08.29")
        self.assertEqual(COURSE.title, "Inference Flight School: Token to Traffic")
        self.assertEqual(tuple(module.id for module in COURSE.modules), EXPECTED_MODULE_IDS)
        self.assertEqual(tuple(module.order for module in COURSE.modules), tuple(range(17)))

    def test_every_module_exposes_the_complete_mission_loop(self):
        for module in COURSE.modules:
            with self.subTest(module=module.id):
                self.assertTrue(module.callsign)
                self.assertTrue(module.mission_brief)
                self.assertTrue(module.learning_objectives)
                self.assertTrue(module.lesson_outline)
                self.assertTrue(module.lab.title)
                self.assertIn(module.lab.platform, {"dgx", "mac", "both", "optional_cloud"})
                self.assertTrue(module.lab.steps)
                self.assertTrue(module.lab.verification)
                self.assertTrue(module.checkpoint.prompts)
                self.assertTrue(module.checkpoint.pass_condition)
                self.assertTrue(module.oral.opening_prompt)
                self.assertTrue(module.oral.rubric)
                self.assertTrue(module.artifacts)
                self.assertTrue(all(artifact.id and artifact.title for artifact in module.artifacts))
                self.assertTrue(all(len(artifact.id) <= 80 and len(artifact.title) <= 100
                                    for artifact in module.artifacts))
                self.assertTrue(module.debrief_prompt)

    def test_source_manifest_traces_every_approved_source_category(self):
        counts: dict[str, int] = {}
        for source in COURSE.source_manifest:
            counts[source.kind] = counts.get(source.kind, 0) + 1
        self.assertEqual(counts, EXPECTED_SOURCE_KIND_COUNTS)

        mapped = {source_id for module in COURSE.modules for source_id in module.source_ids}
        manifest = {source.id for source in COURSE.source_manifest}
        self.assertEqual(mapped, manifest)
        self.assertEqual(len(manifest), len(COURSE.source_manifest))

        labels = {source.label for source in COURSE.source_manifest}
        for required in (
            "Attention Is All You Need",
            "PagedAttention paper",
            "GPTQ paper",
            "AWQ paper",
            "Speculative Decoding paper",
            "SGLang paper",
            "Self-hosted model serving workplace project",
            "Cross-platform inference comparison personal project",
            "Verify CUDA version and driver compatibility",
            "Use Mac as daily driver for reading, coding, and light experiments",
            "Sunday paper and community review",
        ):
            self.assertIn(required, labels)

        evidence_kinds = {
            "hands_on", "workplace_project", "workplace_task", "personal_project", "paper", "hardware", "routine",
        }
        evidence_sources = {source.id for source in COURSE.source_manifest if source.kind in evidence_kinds}
        artifact_sources = {
            source_id
            for module in COURSE.modules
            for artifact in module.artifacts
            for source_id in artifact.source_ids
        }
        self.assertEqual(artifact_sources, evidence_sources)

    def test_all_workplace_checklist_tasks_have_distinct_stable_mappings(self):
        expected = {
            "SRC-WP-01-TASK-AUDIT-USAGE", "SRC-WP-01-TASK-DEPLOY-OPEN-MODEL",
            "SRC-WP-01-TASK-COMPARE-QUALITY", "SRC-WP-01-TASK-COMPARE-COST",
            "SRC-WP-01-TASK-ROUTE-BY-COMPLEXITY", "SRC-WP-01-TASK-DOCUMENT-OUTCOMES",
            "SRC-WP-02-TASK-BUILD-PROXY", "SRC-WP-02-TASK-LOG-REQUESTS",
            "SRC-WP-02-TASK-BUILD-DASHBOARD", "SRC-WP-02-TASK-ENFORCE-QUOTAS",
            "SRC-WP-02-TASK-ADD-SEMANTIC-CACHE", "SRC-WP-02-TASK-ADD-SMART-ROUTING",
            "SRC-WP-03-TASK-SETUP-VECTOR-STORE", "SRC-WP-03-TASK-BUILD-RETRIEVAL",
            "SRC-WP-03-TASK-SERVE-LOCAL-MODEL", "SRC-WP-03-TASK-BUILD-END-TO-END",
            "SRC-WP-03-TASK-OPTIMIZE-PIPELINE", "SRC-WP-03-TASK-EVALUATE-RAG",
            "SRC-WP-04-TASK-PROFILE-BASELINE", "SRC-WP-04-TASK-APPLY-QUANTIZATION",
            "SRC-WP-04-TASK-TUNE-BATCHING", "SRC-WP-04-TASK-ADD-PROMPT-CACHING",
            "SRC-WP-04-TASK-OPTIMIZE-KV-CACHE", "SRC-WP-04-TASK-DOCUMENT-DELTAS",
        }
        actual = {source.id for source in COURSE.source_manifest if source.kind == "workplace_task"}
        self.assertEqual(actual, expected)
        module = next(item for item in COURSE.modules if item.id == "IC-14")
        self.assertTrue(expected <= set(module.source_ids))
        self.assertTrue(expected <= set(module.artifacts[0].source_ids))

    def test_section_source_ids_are_semantic_and_not_position_derived(self):
        positional = re.compile(r"-(?:TOPIC|RESOURCE|HANDS)-\d+$")
        derived = [source.id for source in COURSE.source_manifest if positional.search(source.id)]
        self.assertEqual(derived, [])
        for required in (
            "SRC-P1-1-TOPIC-TOKENIZATION",
            "SRC-P1-1-RESOURCE-TRANSFORMER-PAPER",
            "SRC-P1-1-HANDS-MINIMAL-TRANSFORMER",
            "SRC-P5-3-TOPIC-SERVICE-METRICS",
        ):
            self.assertIn(required, {source.id for source in COURSE.source_manifest})

    def test_frontier_recon_has_required_selection_bounds(self):
        frontier = next(module for module in COURSE.modules if module.id == "IC-12")
        self.assertIsNotNone(frontier.selection_rule)
        self.assertEqual(frontier.selection_rule.minimum, 2)
        self.assertEqual(frontier.selection_rule.maximum, 3)
        self.assertEqual(len(frontier.selection_rule.options), 8)

    def test_validation_rejects_missing_or_invalid_frontier_selection_bounds(self):
        frontier = COURSE.modules[12]
        missing = replace(COURSE, modules=(*COURSE.modules[:12], replace(frontier, selection_rule=None), *COURSE.modules[13:]))
        with self.assertRaisesRegex(CatalogValidationError, "selection rule"):
            validate_catalog(missing)

        invalid_rule = SelectionRule(minimum=4, maximum=3, options=tuple(frontier.source_ids[:8]))
        invalid = replace(
            COURSE,
            modules=(*COURSE.modules[:12], replace(frontier, selection_rule=invalid_rule), *COURSE.modules[13:]),
        )
        with self.assertRaisesRegex(CatalogValidationError, "selection bounds"):
            validate_catalog(invalid)

    def test_dependencies_are_earlier_and_catalog_validates(self):
        by_id = {module.id: module for module in COURSE.modules}
        for module in COURSE.modules:
            for dependency in module.prerequisites:
                self.assertIn(dependency, by_id)
                self.assertLess(by_id[dependency].order, module.order)
        validate_catalog(COURSE)

    def test_ids_are_unique_and_namespaced(self):
        ids = []
        for module in COURSE.modules:
            ids.extend([module.checkpoint.id, module.oral.id])
            ids.extend(artifact.id for artifact in module.artifacts)
            self.assertTrue(module.checkpoint.id.startswith(f"{module.id}-"))
            self.assertTrue(module.oral.id.startswith(f"{module.id}-"))
            self.assertTrue(all(artifact.id.startswith(f"{module.id}-") for artifact in module.artifacts))
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_approved_artifact_templates_have_stable_independent_descriptors(self):
        artifacts = {artifact.id: artifact for module in COURSE.modules for artifact in module.artifacts}
        self.assertTrue(REQUIRED_ARTIFACT_TEMPLATES.keys() <= artifacts.keys())
        for artifact_id, (template_key, output_format) in REQUIRED_ARTIFACT_TEMPLATES.items():
            with self.subTest(artifact=artifact_id):
                artifact = artifacts[artifact_id]
                self.assertEqual(artifact.template_key, template_key)
                self.assertEqual(artifact.output_format, output_format)
                self.assertTrue(artifact.template_fields)
                self.assertTrue(artifact.verification_rubric)

        grafana = artifacts["IC-11-ARTIFACT-GRAFANA-CHECKLIST"]
        cost = artifacts["IC-11-ARTIFACT-COST-MODEL"]
        self.assertNotEqual(grafana.id, cost.id)
        self.assertIn("SRC-P5-3-HANDS-GRAFANA-DASHBOARD", grafana.source_ids)
        self.assertIn("SRC-P5-3-HANDS-COST-CALCULATION", cost.source_ids)

    def test_ic14_completion_contract_scopes_all_projects_and_ties_selection(self):
        artifact = COURSE.modules[14].artifacts[0]
        rule = artifact.completion_rule
        self.assertEqual(rule.id, "COMPLETION-WORKPLACE-PROJECT-SELECTION")
        self.assertEqual(tuple(entry.source_id for entry in rule.entries), WORKPLACE_PROJECT_IDS)
        self.assertEqual(
            tuple(entry.label for entry in rule.entries),
            tuple(next(source.label for source in COURSE.source_manifest if source.id == source_id)
                  for source_id in WORKPLACE_PROJECT_IDS),
        )
        payload = {
            "project_scopes": [
                {"project_id": source_id, "scope": f"Scope for {source_id}"}
                for source_id in reversed(WORKPLACE_PROJECT_IDS)
            ],
            "chosen_project_id": "SRC-WP-03",
            "selected_proposal": {
                "project_id": "SRC-WP-03",
                "evidence": "The private-document boundary makes this the safest useful pilot.",
            },
        }
        canonical = inference_course.canonical_completion_payload(artifact, payload)
        self.assertEqual(
            tuple(entry["project_id"] for entry in canonical["project_scopes"]),
            WORKPLACE_PROJECT_IDS,
        )
        self.assertEqual(canonical["selected_proposal"]["project_id"], canonical["chosen_project_id"])

    def test_ic14_completion_contract_rejects_omissions_duplicates_unknowns_and_mismatch(self):
        artifact = COURSE.modules[14].artifacts[0]
        scopes = [
            {"project_id": source_id, "scope": f"Bounded scope for {source_id}"}
            for source_id in WORKPLACE_PROJECT_IDS
        ]
        base = {
            "project_scopes": scopes,
            "chosen_project_id": "SRC-WP-02",
            "selected_proposal": {"project_id": "SRC-WP-02", "evidence": "Measured gateway need."},
        }
        invalid_payloads = (
            {**base, "project_scopes": scopes[:-1]},
            {**base, "project_scopes": [*scopes[:-1], scopes[0]]},
            {**base, "project_scopes": [*scopes[:-1], {"project_id": "SRC-PAPER-01", "scope": "x"}]},
            {**base, "chosen_project_id": "SRC-WP-99"},
            {**base, "selected_proposal": {"project_id": "SRC-WP-03", "evidence": "mismatch"}},
            {**base, "project_scopes": [{**scopes[0], "scope": " "}, *scopes[1:]]},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(CatalogValidationError):
                inference_course.canonical_completion_payload(artifact, payload)

    def test_ic16_completion_contract_requires_one_bounded_note_per_ordered_paper(self):
        artifact = COURSE.modules[16].artifacts[0]
        rule = artifact.completion_rule
        self.assertEqual(rule.id, "COMPLETION-ORDERED-PAPER-NOTES")
        self.assertEqual(tuple(entry.source_id for entry in rule.entries), PAPER_SOURCE_IDS)
        payload = {
            "paper_notes": [
                {"paper_id": source_id, "note": f"Mechanism and lab connection for {source_id}."}
                for source_id in reversed(PAPER_SOURCE_IDS)
            ]
        }
        canonical = inference_course.canonical_completion_payload(artifact, payload)
        self.assertEqual(tuple(entry["paper_id"] for entry in canonical["paper_notes"]), PAPER_SOURCE_IDS)
        self.assertEqual(len(canonical["paper_notes"]), 9)

    def test_ic16_completion_contract_rejects_omission_duplicate_unknown_and_oversize(self):
        artifact = COURSE.modules[16].artifacts[0]
        notes = [
            {"paper_id": source_id, "note": f"Note for {source_id}."}
            for source_id in PAPER_SOURCE_IDS
        ]
        invalid_collections = (
            notes[:-1],
            [*notes[:-1], notes[0]],
            [*notes[:-1], {"paper_id": "SRC-PAPER-99", "note": "unknown"}],
            [{**notes[0], "note": " "}, *notes[1:]],
            [{**notes[0], "note": "x" * 2001}, *notes[1:]],
        )
        for paper_notes in invalid_collections:
            with self.subTest(paper_notes=paper_notes), self.assertRaises(CatalogValidationError):
                inference_course.canonical_completion_payload(artifact, {"paper_notes": paper_notes})

    def test_completion_contract_validation_rejects_source_and_shape_drift(self):
        artifact = COURSE.modules[14].artifacts[0]
        rule = artifact.completion_rule
        invalid_rules = (
            replace(rule, entries=rule.entries[:-1]),
            replace(rule, entries=(*rule.entries[:-1], rule.entries[0])),
            replace(rule, entries=(*rule.entries[:-1], replace(rule.entries[-1], source_id="SRC-PAPER-01"))),
            replace(rule, chosen_id_field="project_scopes"),
        )
        for invalid_rule in invalid_rules:
            changed_artifact = replace(artifact, completion_rule=invalid_rule)
            changed_module = replace(COURSE.modules[14], artifacts=(changed_artifact,))
            changed = replace(COURSE, modules=(*COURSE.modules[:14], changed_module, *COURSE.modules[15:]))
            with self.subTest(rule=invalid_rule), self.assertRaises(CatalogValidationError):
                validate_catalog(changed)

    def test_completion_payload_rejects_malformed_structural_types(self):
        plain_artifact = COURSE.modules[0].artifacts[0]
        workplace = COURSE.modules[14].artifacts[0]
        papers = COURSE.modules[16].artifacts[0]
        workplace_scopes = [
            {"project_id": source_id, "scope": f"Scope for {source_id}"}
            for source_id in WORKPLACE_PROJECT_IDS
        ]
        workplace_base = {
            "project_scopes": workplace_scopes,
            "chosen_project_id": "SRC-WP-01",
            "selected_proposal": {"project_id": "SRC-WP-01", "evidence": "Measured need."},
        }
        paper_notes = [
            {"paper_id": source_id, "note": f"Note for {source_id}."}
            for source_id in PAPER_SOURCE_IDS
        ]
        cases = (
            (plain_artifact, {}),
            (papers, []),
            (papers, {}),
            (papers, {"paper_notes": "not-a-list"}),
            (papers, {"paper_notes": [*paper_notes[:-1], "not-an-entry"]}),
            (papers, {"paper_notes": [*paper_notes[:-1], {**paper_notes[-1], "extra": "x"}]}),
            (papers, {"paper_notes": [{**paper_notes[0], "paper_id": 1}, *paper_notes[1:]]}),
            (papers, {"paper_notes": [{**paper_notes[0], "note": 1}, *paper_notes[1:]]}),
            (papers, {"paper_notes": [{**paper_notes[0], "note": "bad\x00note"}, *paper_notes[1:]]}),
            (workplace, {**workplace_base, "chosen_project_id": 1}),
            (workplace, {**workplace_base, "selected_proposal": []}),
            (workplace, {**workplace_base, "selected_proposal": {"project_id": "SRC-WP-01"}}),
        )
        for artifact, payload in cases:
            with self.subTest(artifact=artifact.id, payload=payload), self.assertRaises(CatalogValidationError):
                inference_course.canonical_completion_payload(artifact, payload)

    def test_validation_rejects_duplicate_or_unsupported_template_metadata(self):
        first, second = COURSE.modules[:2]
        duplicate_key = replace(second.artifacts[0], template_key=first.artifacts[0].template_key)
        duplicate = replace(
            COURSE,
            modules=(first, replace(second, artifacts=(duplicate_key,)), *COURSE.modules[2:]),
        )
        with self.assertRaisesRegex(CatalogValidationError, "template keys"):
            validate_catalog(duplicate)

        unsupported = replace(first.artifacts[0], output_format="binary")
        invalid = replace(COURSE, modules=(replace(first, artifacts=(unsupported,)), *COURSE.modules[1:]))
        with self.assertRaisesRegex(CatalogValidationError, "output format"):
            validate_catalog(invalid)

    def test_payload_is_deterministic_json_safe_and_has_no_score_fields(self):
        first = catalog_payload(COURSE)
        second = catalog_payload(COURSE)
        self.assertEqual(first, second)
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )

        def assert_safe(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    normalized = key.lower().replace("_", "")
                    self.assertNotIn(normalized, FORBIDDEN_FIELDS)
                    assert_safe(child)
            elif isinstance(value, list):
                for child in value:
                    assert_safe(child)

        assert_safe(first)

    def test_catalog_is_deeply_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            COURSE.version = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            COURSE.modules[0].title = "changed"  # type: ignore[misc]
        self.assertIsInstance(COURSE.modules, tuple)
        self.assertIsInstance(COURSE.modules[0].lab.steps, tuple)

    def test_validation_rejects_duplicate_module_identity(self):
        duplicate = replace(COURSE, modules=COURSE.modules + (COURSE.modules[0],))
        with self.assertRaisesRegex(CatalogValidationError, "module ids"):
            validate_catalog(duplicate)

    def test_validation_rejects_missing_or_out_of_order_modules(self):
        missing = replace(COURSE, modules=COURSE.modules[:-1])
        with self.assertRaisesRegex(CatalogValidationError, "IC-00 through IC-16"):
            validate_catalog(missing)
        swapped = replace(COURSE, modules=(COURSE.modules[1], COURSE.modules[0], *COURSE.modules[2:]))
        with self.assertRaisesRegex(CatalogValidationError, "ordered"):
            validate_catalog(swapped)

    def test_validation_rejects_dangling_and_cyclic_dependencies(self):
        dangling_module = replace(COURSE.modules[1], prerequisites=("IC-99",))
        dangling = replace(COURSE, modules=(COURSE.modules[0], dangling_module, *COURSE.modules[2:]))
        with self.assertRaisesRegex(CatalogValidationError, "unknown prerequisite"):
            validate_catalog(dangling)

        cyclic_first = replace(COURSE.modules[0], prerequisites=("IC-01",))
        cyclic = replace(COURSE, modules=(cyclic_first, *COURSE.modules[1:]))
        with self.assertRaisesRegex(CatalogValidationError, "dependency cycle"):
            validate_catalog(cyclic)

    def test_validation_rejects_unknown_platform_and_incomplete_descriptors(self):
        bad_lab = replace(COURSE.modules[0].lab, platform="browser")
        bad_platform = replace(COURSE, modules=(replace(COURSE.modules[0], lab=bad_lab), *COURSE.modules[1:]))
        with self.assertRaisesRegex(CatalogValidationError, "lab platform"):
            validate_catalog(bad_platform)

        empty_lab = LabDescriptor(title="", platform="both", steps=(), verification="", safety=())
        incomplete = replace(COURSE, modules=(replace(COURSE.modules[0], lab=empty_lab), *COURSE.modules[1:]))
        with self.assertRaisesRegex(CatalogValidationError, "mission loop"):
            validate_catalog(incomplete)

    def test_validation_rejects_source_gaps_duplicates_and_unknown_tags(self):
        gap = replace(COURSE, source_manifest=COURSE.source_manifest[:-1])
        with self.assertRaisesRegex(CatalogValidationError, "unknown source ids"):
            validate_catalog(gap)

        duplicate_source = replace(COURSE, source_manifest=COURSE.source_manifest + (COURSE.source_manifest[0],))
        with self.assertRaisesRegex(CatalogValidationError, "source ids"):
            validate_catalog(duplicate_source)

        extra_source = COURSE.source_manifest[0]
        unreferenced = replace(
            COURSE,
            source_manifest=COURSE.source_manifest + (replace(extra_source, id="SRC-UNMAPPED"),),
        )
        with self.assertRaisesRegex(CatalogValidationError, "unmapped source ids"):
            validate_catalog(unreferenced)

    def test_validation_rejects_gamification_copy(self):
        gamified = replace(COURSE.modules[0], mission_brief="Build an XP leaderboard.")
        invalid = replace(COURSE, modules=(gamified, *COURSE.modules[1:]))
        with self.assertRaisesRegex(CatalogValidationError, "learner-facing gamification"):
            validate_catalog(invalid)

    def test_validation_rejects_gamification_in_course_title(self):
        invalid = replace(COURSE, title="Inference XP Flight Course")
        with self.assertRaisesRegex(CatalogValidationError, "learner-facing gamification"):
            validate_catalog(invalid)

    def test_validation_rejects_gamification_in_source_labels(self):
        bad_source = replace(COURSE.source_manifest[0], label="Earn points for this section")
        invalid = replace(COURSE, source_manifest=(bad_source, *COURSE.source_manifest[1:]))
        with self.assertRaisesRegex(CatalogValidationError, "source label"):
            validate_catalog(invalid)

    def test_validation_rejects_cross_module_artifact_source_swaps(self):
        first, second = COURSE.modules[:2]
        first_artifact = replace(
            first.artifacts[0],
            source_ids=(second.artifacts[0].source_ids[0], *first.artifacts[0].source_ids[1:]),
        )
        second_artifact = replace(
            second.artifacts[0],
            source_ids=(first.artifacts[0].source_ids[0], *second.artifacts[0].source_ids[1:]),
        )
        invalid = replace(
            COURSE,
            modules=(
                replace(first, artifacts=(first_artifact,)),
                replace(second, artifacts=(second_artifact,)),
                *COURSE.modules[2:],
            ),
        )
        with self.assertRaisesRegex(CatalogValidationError, "artifact source ownership"):
            validate_catalog(invalid)

    def test_import_does_not_seed_or_mutate_runtime_state(self):
        self.assertNotIn("sqlmodel", globals())
        self.assertFalse(hasattr(COURSE, "seed"))
        self.assertFalse(hasattr(COURSE, "activate"))


if __name__ == "__main__":
    unittest.main()
