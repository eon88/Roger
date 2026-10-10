"""Security regression tests for Roger's public file routes."""
import http.client
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import HTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class StaticSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        static = cls.root / "_next" / "static" / "css"
        static.mkdir(parents=True)

        fixtures = {
            "index.html": "PUBLIC PAGE",
            "login.html": "LOGIN PAGE",
            "dash.css": "body{}",
            "_next/static/css/test.css": "body{}",
            "stage.json": "PRIVATE_STAGE_MARKER",
            "users.json": "PRIVATE_USERS_MARKER",
            "serve.py": "PRIVATE_SOURCE_MARKER",
        }
        for name, content in fixtures.items():
            target = cls.root / name
            target.write_text(content)

        cls.root_patch = patch.object(serve, "ROOT", str(cls.root))
        cls.root_patch.start()

        cls.server = HTTPServer(("127.0.0.1", 0), serve.H)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.root_patch.stop()
        cls.temp.cleanup()

    def request(self, path, method="GET"):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_private_files_and_traversal_denied(self):
        paths = [
            "/stage.json",
            "/users.json",
            "/serve.py",
            "/_next/../stage.json",
            "/_next/../users.json",
            "/_next/../serve.py",
            "/_next/%2e%2e/serve.py",
            "/_next/static/../../serve.py",
            "/_next/static/css/../../../stage.json",
            "/_next/static/css/test.py",
        ]
        for path in paths:
            with self.subTest(path=path):
                status, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"PRIVATE_", body)

    def test_public_pages_still_work(self):
        for path in (
            "/", "/login", "/dash.css",
            "/_next/static/css/test.css"
        ):
            with self.subTest(path=path):
                status, _ = self.request(path)
                self.assertEqual(status, 200)

    def test_head_file_access_denied(self):
        for path in ("/serve.py", "/stage.json", "/"):
            with self.subTest(path=path):
                status, _ = self.request(path, "HEAD")
                self.assertEqual(status, 405)

    def test_unknown_file_denied(self):
        status, _ = self.request("/something-not-public.txt")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
