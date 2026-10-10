import io
import sys
import unittest
from email.message import Message
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class RequestBodyLimitsTests(unittest.TestCase):

    def make_handler(self, path="/api/not-real", body=b"{}",
                     length=None, extra=None, omit_length=False):
        h = serve.H.__new__(serve.H)
        h.path = path
        h.headers = Message()
        h.headers.add_header(
            "Origin", "https://agency.lifecompass.shop"
        )

        if not omit_length:
            h.headers.add_header(
                "Content-Length",
                str(len(body) if length is None else length)
            )

        for key, value in (extra or []):
            h.headers.add_header(key, value)

        h.rfile = io.BytesIO(body)
        h.close_connection = False
        h.require = lambda roles=None: {
            "role": "agent",
            "display_name": "Test Agent",
        }
        h.responses = []
        h._json = lambda data, code=200: h.responses.append(code)
        h.handle_document = lambda data: h._json({"ok": True})
        h.handle_tenant_issue = lambda data: h._json({"ok": True})
        return h

    def run_request(self, handler, expected):
        handler.do_POST()
        self.assertEqual(handler.responses[-1], expected)

    def test_small_request_allowed(self):
        self.run_request(self.make_handler(), 404)

    def test_ordinary_api_body_too_large(self):
        h = self.make_handler(length=262145)
        self.run_request(h, 413)
        self.assertTrue(h.close_connection)

    def test_missing_content_length_rejected(self):
        h = self.make_handler(omit_length=True)
        self.run_request(h, 411)

    def test_invalid_content_length_rejected(self):
        h = self.make_handler(length="-1")
        self.run_request(h, 400)

    def test_duplicate_content_length_rejected(self):
        h = self.make_handler(extra=[
            ("Content-Length", "2")
        ])
        self.run_request(h, 400)

    def test_chunked_encoding_rejected(self):
        h = self.make_handler(extra=[
            ("Transfer-Encoding", "chunked")
        ])
        self.run_request(h, 400)

    def test_invalid_utf8_rejected(self):
        h = self.make_handler(body=b"\xff")
        self.run_request(h, 400)

    def test_json_array_rejected(self):
        h = self.make_handler(body=b"[]")
        self.run_request(h, 400)

    def test_document_upload_has_higher_limit(self):
        body = b'{"padding":"' + b"x" * (1024 * 1024) + b'"}'
        h = self.make_handler("/api/document", body=body)
        self.run_request(h, 200)

    def test_document_over_eight_megabytes_rejected(self):
        h = self.make_handler(
            "/api/document",
            length=8 * 1024 * 1024 + 1
        )
        self.run_request(h, 413)

    def test_tenant_attachment_request_has_higher_limit(self):
        body = b'{"padding":"' + b"x" * (1024 * 1024) + b'"}'
        h = self.make_handler("/api/tenant/issue", body=body)
        self.run_request(h, 200)

    def test_tenant_request_over_32_megabytes_rejected(self):
        h = self.make_handler(
            "/api/tenant/issue",
            length=32 * 1024 * 1024 + 1
        )
        self.run_request(h, 413)

    def test_login_body_limit(self):
        h = self.make_handler("/login", length=8193)
        self.run_request(h, 413)


if __name__ == "__main__":
    unittest.main()
