"""B02: document bytes and identity must not escape metadata/download controls."""
import base64
import inspect
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class AttachmentAndPayloadTests(unittest.TestCase):
    def handler(self):
        h = serve.H.__new__(serve.H)
        h.sent = []
        h.wfile = io.BytesIO()
        h.send_response = lambda code: h.sent.append(("status", code))
        h.send_header = lambda name, value: h.sent.append((name, value))
        h.end_headers = lambda: None
        return h

    def test_download_is_attachment_only_no_mime_execution_or_header_injection(self):
        h = self.handler()
        payload = b'<script>fetch("/api/stage")</script>'
        fake = {
            "id": "doc-1", "file_name": 'a"\r\nX-Evil: enabled.html',
            "content_type": "text/html", "data_b64": base64.b64encode(payload).decode(),
        }
        h.serve_document_file(fake)
        headers = dict(h.sent)
        self.assertEqual(headers["status"], 200)
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Content-Security-Policy"], "sandbox")
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        self.assertNotIn("\r", headers["Content-Disposition"])
        self.assertNotIn("\n", headers["Content-Disposition"])
        self.assertNotIn('"X-Evil:', headers["Content-Disposition"])
        self.assertEqual(h.wfile.getvalue(), payload)

    def test_document_metadata_does_not_reveal_storage_or_internal_notes(self):
        h = self.handler()
        result = h.safe_document({
            "id": "doc-1", "file_name": "agreement.pdf", "document_type": "tenancy_agreement",
            "storage_key": "private-file-key", "data_b64": "c2VjcmV0",
            "internal_notes": "PRIVATE-STORAGE-REVIEW",
            "uploaded_by_account_id": "private-upload-account",
            "access_roles": ["agent", "tenant"],
        })
        self.assertEqual(result["file_name"], "agreement.pdf")
        self.assertEqual(result["id"], "doc-1")
        self.assertTrue(result["has_file"])
        self.assertNotIn("storage_key", result)
        self.assertNotIn("data_b64", result)
        self.assertNotIn("internal_notes", result)
        self.assertNotIn("uploaded_by_account_id", result)

    def test_json_api_is_noncacheable_and_referrer_safe(self):
        h = self.handler()
        h._json({"authenticated": False}, 401)
        headers = dict(h.sent)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_remote_mail_errors_do_not_echo_exception_secrets(self):
        source = inspect.getsource(serve.H.handle_email_sync) + inspect.getsource(
            serve.H.handle_email_reply)
        self.assertNotIn('"mailbox sync failed: " + str(exc)', source)
        self.assertNotIn('"email provider could not accept this message: " + str(exc)', source)

    def test_credentials_not_logged_by_server_requests(self):
        self.assertIn("pass", inspect.getsource(serve.H.log_message))
        self.assertNotIn("print(", inspect.getsource(serve.H.do_POST_login))


if __name__ == "__main__":
    unittest.main()
