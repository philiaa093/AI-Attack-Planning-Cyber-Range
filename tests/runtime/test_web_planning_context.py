"""Focused tests for the bounded web-surface projection used by LLM planning."""
from __future__ import annotations

import unittest

from runtime.planners.web_planning_context import (
    build_web_planning_context,
    completion_blocker,
)

ALL_WEB_ACTIONS = {
    "ACTION-RECON-002", "ACTION-SCAN-001", "ACTION-SCAN-002",
    "ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003",
    "ACTION-LOGIC-001", "ACTION-END-001", "ACTION-END-003",
}


def fact(fact_id: str, fact_type: str, subject: str, value, confidence: float = 0.8) -> dict:
    return {"fact_id": fact_id, "fact_type": fact_type, "subject": subject,
            "value": value, "confidence": confidence}


class WebPlanningContextTests(unittest.TestCase):
    def state(self, facts, endpoints=("/products",), previous=("ACTION-RECON-002", "ACTION-SCAN-001")):
        return {
            "phase": "TESTING",
            "objective_id": "OBJ-001",
            "remaining_budget": {"actions": 7, "requests": 40},
            "previous_actions": list(previous),
            "discovered_endpoints": list(endpoints),
            "observed_facts": list(facts),
        }

    def build(self, facts, endpoints=("/products",), actions=ALL_WEB_ACTIONS, limit=32):
        return build_web_planning_context(self.state(facts, endpoints), list(endpoints),
                                          facts, ["ACTION-RECON-002", "ACTION-SCAN-001"],
                                          set(actions), limit=limit)

    def test_projection_distinguishes_measured_zero_from_missing_or_invalid_counts(self):
        scanner = "ACTION-SCAN-002:fixture"
        status = fact("F1", "ACTION_OUTCOME", scanner, "COMPLETED")
        bounded = fact("F2", "ACTION_OUTCOME", scanner + ":coverage", "BOUNDED")
        for values, expected in (
            ([status], (None, None)),
            ([status, bounded, fact("F3", "ACTION_OUTCOME", scanner + ":unrequested_seeds", 0)],
             ("BOUNDED", 0)),
            ([status, bounded, fact("F3", "ACTION_OUTCOME", scanner + ":unrequested_seeds", "0")],
             ("BOUNDED", None)),
        ):
            with self.subTest(expected=expected):
                row, = self.build(values)["scanner_coverage"]
                self.assertEqual((row["coverage"], row["unrequested_seeds"]), expected)

    def test_overlong_identifiers_are_omitted_without_collapsing_counts(self):
        prefix = "/" + "a" * 511
        first = prefix + "b" * 89
        second = prefix + "c" * 89
        facts = [fact("F1", "PARAMETER", first, "q"), fact("F2", "PARAMETER", second, "q")]
        context = self.build(facts, endpoints=(first, second))

        self.assertTrue(context["truncated"])
        self.assertEqual(context["counts"]["endpoints"], 2)
        self.assertEqual(context["counts"]["get_inputs"], 2)
        self.assertEqual(context["counts"]["unresolved_checks"], 2)
        for key in ("observed_endpoints", "observed_get_inputs", "unresolved_checks"):
            self.assertEqual(context[key], [])

    def test_completion_requires_observed_surface(self):
        for facts in ([], [fact("F1", "TARGET", "lab-ecommerce", "lab-ecommerce")]):
            with self.subTest(facts=facts):
                self.assertEqual(completion_blocker(self.state(facts), ALL_WEB_ACTIONS),
                                 "unresolved_candidate_surface")

    def test_same_counts_different_routes_and_forms_produce_different_projection(self):
        first_facts = [
            fact("F1", "PARAMETER", "/products", "q"),
            fact("F2", "CANDIDATE_FINDING", "/login", "post_form_input_username"),
        ]
        second_facts = [
            fact("F1", "PARAMETER", "/search", "term"),
            fact("F2", "CANDIDATE_FINDING", "/checkout", "post_form_input_coupon"),
        ]
        first = self.build(first_facts)
        second = self.build(second_facts)

        self.assertEqual(first["counts"]["get_inputs"], second["counts"]["get_inputs"])
        self.assertEqual(first["counts"]["post_inputs"], second["counts"]["post_inputs"])
        self.assertNotEqual(first["observed_get_inputs"], second["observed_get_inputs"])
        self.assertNotEqual(first["observed_post_inputs"], second["observed_post_inputs"])

    def test_post_inputs_are_observed_but_not_executable_candidates(self):
        context = self.build([
            fact("F1", "PARAMETER", "/products", "q"),
            fact("F2", "CANDIDATE_FINDING", "/login", "post_form_input_username"),
        ])

        self.assertEqual(context["observed_post_inputs"][0]["parameter_name"], "username")
        self.assertTrue(context["post_inputs_unsupported"])
        self.assertIn("not executable candidates", context["post_inputs_note"])
        self.assertTrue(all(row["accepted_methods"] == ["GET"]
                            for row in context["approved_actions"]
                            if row["semantics"].startswith("Bounded")))
        self.assertEqual([row["parameter_name"] for row in context["unresolved_checks"]], ["q"])
        self.assertEqual([check["action"] for check in
                          context["unresolved_checks"][0]["pending_checks"]],
                         ["ACTION-WEB-001", "ACTION-WEB-002"])
        post_only = [fact("POST", "CANDIDATE_FINDING", "/login", "post_form_input_username")]
        self.assertEqual(completion_blocker(self.state(post_only), ALL_WEB_ACTIONS),
                         "unresolved_candidate_surface")

    def test_control_fields_are_not_projected(self):
        context = self.build([
            fact("F1", "PARAMETER", "/login", "password"),
            fact("F2", "CANDIDATE_FINDING", "/login", "post_form_input_csrf_token"),
        ])

        self.assertEqual(context["observed_get_inputs"], [])
        self.assertEqual(context["observed_post_inputs"], [])
        self.assertEqual(context["counts"]["get_inputs"], 0)

    def test_refused_actions_remain_visible(self):
        context = self.build([
            fact("F1", "ACTION_OUTCOME", "ACTION-WEB-002:/products:q", "REFUSED"),
        ])
        self.assertEqual(context["refused_actions"], ["ACTION-WEB-002:/products:q"])

    def test_scanner_partial_coverage_and_seed_gap_are_visible(self):
        context = self.build([
            fact("F1", "ACTION_OUTCOME", "ACTION-SCAN-002:zap-active", "COMPLETED"),
            fact("F2", "ACTION_OUTCOME", "ACTION-SCAN-002:zap-active:coverage", "PARTIAL"),
            fact("F3", "ACTION_OUTCOME", "ACTION-SCAN-002:zap-active:unrequested_seeds", 3),
        ], actions=ALL_WEB_ACTIONS - {"ACTION-WEB-001", "ACTION-WEB-002",
                                      "ACTION-WEB-003", "ACTION-LOGIC-001"},
            endpoints=())

        self.assertEqual(context["scanner_coverage"][0]["coverage"], "PARTIAL")
        self.assertEqual(context["scanner_coverage"][0]["unrequested_seeds"], 3)
        self.assertEqual(context["incomplete_scans"][0]["tool"], "zap-active")

    def test_completion_blocker_requires_every_eligible_check(self):
        unchecked = self.state([fact("F1", "PARAMETER", "/products", "q")])
        self.assertEqual(completion_blocker(unchecked, ALL_WEB_ACTIONS),
                         "unresolved_candidate_surface")

        sql_only = {"ACTION-WEB-001", "ACTION-END-001", "ACTION-END-003"}
        sql_checked = self.state([
            fact("F1", "PARAMETER", "/products", "q"),
            fact("F2", "ACTION_OUTCOME", "ACTION-WEB-001:/products:q", "NEGATIVE"),
        ])
        self.assertIsNone(completion_blocker(sql_checked, sql_only))
        self.assertEqual(completion_blocker(sql_checked, ALL_WEB_ACTIONS),
                         "unresolved_candidate_surface")

        fully_checked = self.state([
            fact("F1", "PARAMETER", "/products", "q"),
            fact("F2", "ACTION_OUTCOME", "ACTION-WEB-001:/products:q", "NEGATIVE"),
            fact("F3", "ACTION_OUTCOME", "ACTION-WEB-002:/products:q", "VERIFIED_IN_LAB"),
        ])
        self.assertIsNone(completion_blocker(fully_checked, ALL_WEB_ACTIONS))

        inconclusive = self.state([
            fact("F1", "PARAMETER", "/products", "q"),
            fact("F2", "ACTION_OUTCOME", "ACTION-WEB-001:/products:q", "INCONCLUSIVE"),
            fact("F3", "ACTION_OUTCOME", "ACTION-WEB-002:/products:q", "NEGATIVE"),
        ])
        self.assertEqual(completion_blocker(inconclusive, ALL_WEB_ACTIONS),
                         "unresolved_candidate_surface")

        refused = self.state([
            fact("F1", "PARAMETER", "/products", "q"),
            fact("F2", "ACTION_OUTCOME", "ACTION-WEB-001:/products:q", "REFUSED"),
            fact("F3", "ACTION_OUTCOME", "ACTION-WEB-002:/products:q", "NEGATIVE"),
        ])
        self.assertEqual(completion_blocker(refused, ALL_WEB_ACTIONS),
                         "unresolved_candidate_surface")

    def test_completion_blocker_reports_incomplete_scan_coverage(self):
        state = self.state([
            fact("F1", "ACTION_OUTCOME", "ACTION-SCAN-002:nuclei", "COMPLETED"),
            fact("F2", "ACTION_OUTCOME", "ACTION-SCAN-002:nuclei:coverage", "PARTIAL"),
            fact("F3", "ACTION_OUTCOME", "ACTION-SCAN-002:nuclei:unrequested_seeds", 4),
        ], endpoints=())
        self.assertEqual(completion_blocker(state, ALL_WEB_ACTIONS),
                         "unresolved_scan_coverage")

    def test_unsupported_inputs_block_success_without_creating_test_actions(self):
        state = self.state([fact("F1", "PARAMETER", "/products", "q")])
        scan_only = {"ACTION-RECON-002", "ACTION-SCAN-001", "ACTION-SCAN-002",
                     "ACTION-END-001", "ACTION-END-003"}
        self.assertEqual(completion_blocker(state, scan_only), "unresolved_candidate_surface")
        context = build_web_planning_context(
            state, ["/products"], state.get("observed_facts", []), [], scan_only)
        self.assertEqual(context["untestable_inputs"][0]["parameter_name"], "q")

    def test_truncation_is_bounded_and_explicit(self):
        endpoint_rows = [f"/page/{index}" for index in range(40)]
        context = self.build([], endpoints=endpoint_rows, limit=8)

        self.assertTrue(context["truncated"])
        self.assertEqual(context["counts"]["endpoints"], 40)
        self.assertEqual(len(context["observed_endpoints"]), 8)

        post_facts = [fact(f"P{index}", "CANDIDATE_FINDING", f"/form/{index}",
                           f"post_form_input_field{index}") for index in range(12)]
        post_context = self.build(post_facts, endpoints=(), limit=8)
        self.assertTrue(post_context["truncated"])
        self.assertEqual(post_context["counts"]["post_inputs"], 12)
        self.assertEqual(len(post_context["observed_post_inputs"]), 8)


if __name__ == "__main__":
    unittest.main()
