"""Synthetic acceptance tests for Roger's opt-in repair interview."""
import base64
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import repair_diagnosis as diag
import serve


class RepairDiagnosticTests(unittest.TestCase):
    def test_ten_representative_maintenance_scenarios(self):
        cases = [
            ("A pipe is leaking under the kitchen sink", "plumbing", False),
            ("The boiler stopped giving us hot water", "heating", False),
            ("Sparks are coming from a socket", "electric", True),
            ("The front door lock is jammed", "locksmith", False),
            ("Black mould has spread on the bedroom wall", "damp", False),
            ("The hallway ceiling plaster is cracked", "general", False),
            ("I smell gas in the kitchen", "gas", True),
            ("Water is flooding the kitchen floor", "plumbing", True),
            ("Light flickers but there is no burning smell or sparks", "electric", False),
            ("The carbon monoxide alarm is going off", "general", True),
        ]
        with patch.dict(os.environ, {"ROGER_REPAIR_TEXT_MODEL": "", "ROGER_REPAIR_VISION_MODEL": ""}):
            for description, expected_trade, expected_danger in cases:
                with self.subTest(description=description):
                    result = diag.diagnose(description)
                    self.assertEqual(result["suggested_trade"], expected_trade)
                    self.assertEqual(bool(result["safety_flags"]), expected_danger)
                    self.assertEqual(result["engine"], "rules")
                    self.assertEqual(result["complete"], expected_danger)
                    self.assertTrue(result["next_step"])
                    self.assertTrue(result["report"])

    def test_guided_interview_builds_report_then_stops(self):
        with patch.dict(os.environ, {"ROGER_REPAIR_TEXT_MODEL": "", "ROGER_REPAIR_VISION_MODEL": ""}):
            issue = "The bathroom sink is dripping"
            history = []
            for count in range(3):
                output = diag.diagnose(issue, history)
                self.assertEqual(output["complete"], False)
                self.assertTrue(output["question"])
                history.append({"question": output["question"], "answer": "My observation " + str(count)})
            finished = diag.diagnose(issue, history)
            self.assertTrue(finished["complete"])
            self.assertEqual(finished["question"], "")
            self.assertEqual(finished["answers_count"], 3)
            self.assertIn("My observation 2", finished["report"])

    def test_history_limits_and_photo_type_checks(self):
        with self.assertRaises(ValueError):
            diag.diagnose("", [])
        with self.assertRaises(ValueError):
            diag.diagnose("Leaking pipe", [{"question": "Where?", "answer": ""}])
        with self.assertRaises(ValueError):
            diag.diagnose("Leaking pipe", [{}] * 4)
        with self.assertRaises(ValueError):
            diag.diagnose("Leaking pipe", image_b64="!!!!!", mime="image/jpeg")
        fake_png = base64.b64encode(b"not a real photo").decode()
        with self.assertRaises(ValueError):
            diag.diagnose("Leaking pipe", image_b64=fake_png, mime="image/png")

    def test_photo_without_vision_is_explicitly_not_analysed(self):
        picture = base64.b64encode(b"\xff\xd8\xffsample").decode()
        with patch.dict(os.environ, {"ROGER_REPAIR_TEXT_MODEL": "", "ROGER_REPAIR_VISION_MODEL": ""}):
            response = diag.diagnose("The tap is dripping", image_b64=picture, mime="image/jpeg")
        self.assertTrue(response["image_supplied"])
        self.assertFalse(response["photo_analyzed"])
        self.assertEqual(response["photo_observation"], "")

    def test_local_vision_model_can_propose_a_question_and_photo_observation(self):
        picture = base64.b64encode(b"\xff\xd8\xffsample").decode()
        response_body = json.dumps({"message": {"content": json.dumps({
            "question": "Can you see active dripping beneath the joint?",
            "likely_cause": "Joint or fitting might be loose",
            "photo_observation": "Water visible near a pipe",
        })}}).encode()
        seen = {}
        def fake_urlopen(req, timeout=0):
            seen["request"] = json.loads(req.data)
            return io.BytesIO(response_body)
        with patch.dict(os.environ, {"ROGER_REPAIR_TEXT_MODEL": "",
                                     "ROGER_REPAIR_VISION_MODEL": "llava-test"}):
            with patch.object(diag.urllib.request, "urlopen", side_effect=fake_urlopen):
                result = diag.diagnose("Leak near a sink", image_b64=picture, mime="image/jpeg")
        self.assertEqual(result["engine"], "local-ollama")
        self.assertTrue(result["photo_analyzed"])
        self.assertIn("Water visible", result["report"])
        self.assertTrue(seen["request"]["messages"][-1]["images"])
        self.assertEqual(seen["request"]["model"], "llava-test")

    def test_ai_cannot_ask_tenant_to_fix_the_fault(self):
        # Real Qwen smoke initially asked what actions could fix a leak.
        with patch.object(diag, "_ollama_suggestion", return_value=(
            {"question": "What actions can be taken to fix the leaking pipe?",
             "likely_cause": "Possible loose connection"}, False
        )):
            result = diag.diagnose("Water leaking under kitchen sink")
        self.assertTrue(result["question"].startswith("Where is the water"))
        self.assertNotIn("fix", result["question"].lower())
        self.assertFalse(diag.safe_interview_question("How can I repair the socket?"))
        self.assertTrue(diag.safe_interview_question("When did you notice the issue?"))

    def test_ai_failures_fall_back_without_hiding_emergency(self):
        with patch.dict(os.environ, {"ROGER_REPAIR_TEXT_MODEL": "small-model",
                                     "ROGER_REPAIR_VISION_MODEL": ""}):
            with patch.object(diag.urllib.request, "urlopen", side_effect=OSError("unavailable")):
                result = diag.diagnose("Kitchen pipe leak")
            urgent = diag.diagnose("I smell gas in the kitchen")
        self.assertEqual(result["engine"], "rules")
        self.assertTrue(urgent["safety_flags"])
        self.assertEqual(urgent["urgency"], "emergency-review")

    def test_remote_ollama_requires_explicit_opt_in(self):
        with patch.dict(os.environ, {"ROGER_REPAIR_TEXT_MODEL": "model",
                                     "ROGER_REPAIR_VISION_MODEL": "",
                                     "ROGER_OLLAMA_BASE_URL": "https://third-party.example",
                                     "ROGER_REPAIR_ALLOW_REMOTE_MODEL": "0"}):
            with patch.object(diag.urllib.request, "urlopen") as net:
                result = diag.diagnose("Kitchen pipe leak")
        self.assertEqual(result["engine"], "rules")
        net.assert_not_called()


class RepairDiagnosticAccessTests(unittest.TestCase):
    def setUp(self):
        self.h = serve.H.__new__(serve.H)
        self.h.user = {"role": "tenant", "account_id": "tenant-account"}
        self.h.account_party_ids = lambda stage, user, role: {"tenant-1"}
        self.h._json = lambda payload, code=200: (payload, code)
        self.stage = {"properties": [
            {"id": "home-1", "tenant_party_id": "tenant-1"},
            {"id": "home-2", "tenant_party_id": "tenant-2"},
        ]}
        patcher = patch.object(serve, "load_stage", return_value=self.stage)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_wrong_property_is_denied_before_model_use(self):
        with patch.object(diag, "diagnose") as model:
            body, code = self.h.handle_repair_diagnosis({
                "property_id": "home-2", "description": "Leak",
            })
        self.assertEqual(code, 403)
        self.assertEqual(body["error"], "not your property")
        model.assert_not_called()

    def test_tenant_can_interview_for_their_linked_property(self):
        with patch.dict(os.environ, {"ROGER_REPAIR_TEXT_MODEL": "", "ROGER_REPAIR_VISION_MODEL": ""}):
            body, code = self.h.handle_repair_diagnosis({
                "property_id": "home-1", "description": "Water leaking from the sink",
            })
        self.assertEqual(code, 200)
        self.assertIn("question", body)
        self.assertNotIn("case_id", body)  # no job or case created

    def test_invalid_input_is_rejected_without_persistence(self):
        body, code = self.h.handle_repair_diagnosis({
            "property_id": "home-1", "description": "",
        })
        self.assertEqual(code, 400)
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()
