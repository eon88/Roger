"""B01 shared transition graph: histories, server actors and replay conflicts."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage-clone"))
import workflow_engine as w


class SharedTransitionTests(unittest.TestCase):
    def test_property_transition_is_timestamped_and_unchanged_replay_safe(self):
        p={"id":"property-a","lifecycle_status":"onboarding","lifecycle_history":[]}
        self.assertTrue(w.apply_transition(
            p,kind="property",target="ready_to_market",
            actor="authenticated-agent",at="2026-11-10T08:00:00Z",
            state_field="lifecycle_status",history_field="lifecycle_history",
            request_id="idempotent-request-1",reason="Verified advertising documents"))
        self.assertEqual(p["lifecycle_status"],"ready_to_market")
        self.assertEqual(p["lifecycle_history"][0]["by"],"authenticated-agent")
        self.assertEqual(p["lifecycle_history"][0]["reason"],"Verified advertising documents")
        self.assertEqual(len(p["lifecycle_history"]),1)
        self.assertFalse(w.apply_transition(
            p,kind="property",target="ready_to_market",
            actor="authenticated-agent",at="2026-11-10T08:01:00Z",
            state_field="lifecycle_status",history_field="lifecycle_history",
            request_id="idempotent-request-1"))
        self.assertEqual(len(p["lifecycle_history"]),1)
        with self.assertRaises(w.RequestReplayConflict):
            w.apply_transition(
                p,kind="property",target="advertised",
                actor="authenticated-agent",at="2026-11-10T08:02:00Z",
                state_field="lifecycle_status",history_field="lifecycle_history",
                request_id="idempotent-request-1")
        self.assertEqual(p["lifecycle_status"],"ready_to_market")

    def test_cannot_jump_between_property_or_tenancy_lifecycle_states(self):
        for kind,current,target in (
            ("property","onboarding","occupied"),
            ("property","offboarded","advertised"),
            ("tenancy","application","active"),
            ("tenancy","former_tenant","active"),
        ):
            with self.subTest(kind=kind,current=current,target=target):
                with self.assertRaises(w.InvalidTransition):
                    w.validate_transition(kind,current,target)
        self.assertTrue(w.validate_transition("property","onboarding","ready_to_market"))
        self.assertTrue(w.validate_transition("tenancy","application","referencing"))

    def test_tenancy_history_preserves_legal_effective_date_and_replay(self):
        tenant={"id":"tenancy-a","status":"notice_given","history":[]}
        changed=w.apply_transition(
            tenant,kind="tenancy",target="checkout",
            actor="office-1",at="2026-11-10T12:00:00Z",
            effective_date="2026-11-10",request_id="request-checkout-a")
        self.assertTrue(changed)
        self.assertEqual(tenant["history"][-1]["effective_date"],"2026-11-10")
        self.assertFalse(w.apply_transition(
            tenant,kind="tenancy",target="checkout",
            actor="office-1",at="2026-11-10T12:00:10Z",
            request_id="request-checkout-a"))
        self.assertEqual(len(tenant["history"]),1)

    def test_invalid_actor_reason_or_request_id_cannot_change_state(self):
        cases=[
            {"actor":"","request_id":"valid-token"},
            {"actor":"office","reason":"X"*501},
            {"actor":"office","request_id":"bad"},
        ]
        for kwargs in cases:
            record={"status":"application"}
            with self.subTest(kwargs=kwargs),self.assertRaises(w.InvalidTransition):
                w.apply_transition(record,kind="tenancy",target="referencing",
                    at="2026-11-10T12:00:00Z",**kwargs)
            self.assertEqual(record,{"status":"application"})

    def test_common_status_history_for_job_case_approval_and_invoice(self):
        for typ, previous, target, action, role in (
            ("case", "reported", "dispatched", "dispatch_repair", "agent"),
            ("job", "assigned", "in_progress", "start", "trades"),
            ("approval", "pending", "approved", "approve", "landlord"),
            ("invoice", "invoice_submitted", "invoice_approved", "approve_invoice", "agent"),
        ):
            with self.subTest(typ=typ):
                record={"status":target}
                self.assertTrue(w.record_status_change(
                    record,previous,action=action,actor="verified-actor",
                    role=role,at="2026-11-10T10:00:00Z"))
                event=record["workflow_history"][0]
                self.assertEqual(event["from"],previous)
                self.assertEqual(event["to"],target)
                self.assertEqual(event["role"],role)
                self.assertFalse(w.record_status_change(
                    record,target,action=action,actor="verified-actor",
                    role=role,at="2026-11-10T10:00:01Z"))
                self.assertEqual(len(record["workflow_history"]),1)

    def test_status_history_fails_closed_on_unknown_role(self):
        rec={"status":"approved"}
        with self.assertRaises(w.InvalidTransition):
            w.record_status_change(rec,"pending",action="approve",
                                   actor="user",role="visitor",at="2026-11-10")
        self.assertNotIn("workflow_history",rec)

    def test_canonical_and_endpoint_transition_graphs_match(self):
        import canonical_records as cr
        self.assertEqual(set(w.PROPERTY_TRANSITIONS),cr.PROPERTY_STATES)
        self.assertEqual(set(w.TENANCY_TRANSITIONS),cr.TENANCY_STATES)


if __name__=="__main__":
    unittest.main()
