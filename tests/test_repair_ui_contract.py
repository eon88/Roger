"""Front-end contract and JavaScript syntax checks for the optional repair interview."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


TENANT = (Path(__file__).resolve().parents[1] / "stage-clone" / "tenant.html")


class RepairInterviewBrowserContractTests(unittest.TestCase):
    def test_interview_is_opt_in_and_does_not_auto_submit(self):
        page = TENANT.read_text(encoding="utf-8")
        self.assertIn('onclick="startRepairInterview()"', page)
        self.assertIn('id="repair-question"', page)
        self.assertIn("post('/api/repair-diagnose'", page)
        self.assertIn("msg.value=repairState.report", page)
        # Submitting an actual repair remains the existing, separate user action.
        self.assertIn("post('/api/tenant/issue'", page)
        self.assertIn('onclick="report()"', page)

    def test_embedded_tenant_javascript_compiles(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js unavailable for a syntax-only check")
        page = TENANT.read_text(encoding="utf-8")
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", page, flags=re.S | re.I)
        self.assertTrue(scripts)
        for script in scripts:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                             suffix=".js", delete=False) as tmp:
                tmp.write(script)
                path = Path(tmp.name)
            try:
                result = subprocess.run([node, "--check", str(path)],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr[:800])
            finally:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
