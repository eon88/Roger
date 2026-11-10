"""B01 central transition, role and non-status finance event contract."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import workflow_engine as w


class DomainTransitionContract(unittest.TestCase):
    def test_every_declared_job_action_has_role_and_state_definition(self):
        self.assertEqual(set(w.JOB_ACTION_ROLES), set(w.JOB_ACTION_STATES))
        for action, roles in w.JOB_ACTION_ROLES.items():
            origin, targets = w.JOB_ACTION_STATES[action]
            self.assertTrue(origin and targets)
            for role in roles:
                for state in origin:
                    for destination in targets:
                        with self.subTest(action=action, role=role, state=state,
                                          destination=destination):
                            self.assertTrue(w.validate_domain_action(
                                "job", action=action, previous=state,
                                target=destination, role=role))

    def test_unauthorised_roles_and_skip_transitions_are_rejected(self):
        for kwargs in (
            dict(kind="job", action="record_payment", previous="invoice_approved",
                 target="paid", role="trades"),
            dict(kind="job", action="start", previous="triaged",
                 target="in_progress", role="trades"),
            dict(kind="job", action="complete", previous="assigned",
                 target="paid", role="trades"),
            dict(kind="job", action="approve_quote", previous="quote_requested",
                 target="assigned", role="agent"),
            dict(kind="job", action="record_payment", previous="invoice_submitted",
                 target="paid", role="agent"),
            dict(kind="approval", action="approve", previous="approved",
                 target="approved", role="landlord"),
            dict(kind="approval", action="approve", previous="pending",
                 target="approved", role="agent", approval_type="prework_quote"),
            dict(kind="landlord_job", action="approve",
                 previous="invoice_submitted", target="invoice_approved",
                 role="landlord", approval_type="invoice"),
            dict(kind="unknown", action="approve", previous="pending",
                 target="approved", role="agent"),
        ):
            with self.subTest(**kwargs), self.assertRaises(w.InvalidTransition):
                w.validate_domain_action(**kwargs)

    def test_quote_and_invoice_approval_require_correct_job_states(self):
        valid = (
            ("prework_quote", "approve", "awaiting_prework_approval", "assigned"),
            ("prework_quote", "reject", "awaiting_prework_approval", "quote_requested"),
            ("variation_quote", "approve", "in_progress", "in_progress"),
            ("variation_quote", "reject", "assigned", "assigned"),
            ("invoice", "approve", "awaiting_approval", "invoice_approved"),
            ("invoice", "reject", "awaiting_approval", "rejected"),
        )
        for typ, action, before, after in valid:
            with self.subTest(kind=typ, action=action):
                self.assertTrue(w.validate_domain_action(
                    "landlord_job", action=action, previous=before,
                    target=after, role="landlord", approval_type=typ))

    def test_several_partial_payments_record_events_even_when_status_is_same(self):
        job = {"status": "partially_paid"}
        for idx in range(2):
            self.assertTrue(w.record_status_change(
                job, "partially_paid", action="record_payment", role="agent",
                actor="office", at=f"2026-11-10T12:00:0{idx}Z",
                include_noop=True))
        self.assertEqual(len(job["workflow_history"]), 2)
        self.assertEqual(
            [event["to"] for event in job["workflow_history"]],
            ["partially_paid", "partially_paid"])
        self.assertFalse(w.record_status_change(
            job, "partially_paid", action="record_payment", role="agent",
            actor="office", at="2026-11-10T12:00:30Z"))


if __name__ == "__main__":
    unittest.main()
