"""Session revocation and cookie security regression tests."""
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "stage-clone")
)
import serve


class SessionSecurityTests(unittest.TestCase):

    def handler(self, token):
        h = serve.H.__new__(serve.H)
        h.path = "/logout"
        h.headers = {"Cookie": f"stage_session={token}"}
        h.sent_headers = []
        h.send_response = lambda code: h.sent_headers.append(
            ("STATUS", code)
        )
        h.send_header = lambda name, value: (
            h.sent_headers.append((name, value))
        )
        h.end_headers = lambda: None
        return h

    def test_logout_revokes_presented_token_only(self):
        users = {
            "sessions": {
                "token-one": {"username": "one"},
                "token-two": {"username": "two"},
            }
        }
        h = self.handler("token-one")

        with patch.object(
            serve, "load_users", return_value=users
        ), patch.object(serve, "save_users") as save:
            h.do_POST_logout({})

            self.assertNotIn("token-one", users["sessions"])
            self.assertIn("token-two", users["sessions"])
            save.assert_called_once()

        self.assertIn(("STATUS", 303), h.sent_headers)

    def test_unknown_token_cannot_revoke_other_sessions(self):
        users = {
            "sessions": {
                "real-token": {"username": "agent"},
            }
        }
        h = self.handler("fake-token")

        with patch.object(
            serve, "load_users", return_value=users
        ), patch.object(serve, "save_users") as save:
            h.do_POST_logout({})
            save.assert_not_called()

        self.assertIn("real-token", users["sessions"])

    def test_cookie_secure_by_default(self):
        with patch.dict(
            os.environ,
            {"ROGER_ENV": "production",
             "ROGER_LAB_HTTP_COOKIES": "0"}
        ):
            cookie = serve.H.session_cookie_header("test-token")

        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/", cookie)

    def test_lab_http_exception_requires_both_flags(self):
        with patch.dict(
            os.environ,
            {"ROGER_ENV": "security-lab",
             "ROGER_LAB_HTTP_COOKIES": "1"}
        ):
            cookie = serve.H.session_cookie_header("test-token")

        self.assertNotIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)

    def test_logout_cookie_expires(self):
        with patch.dict(
            os.environ,
            {"ROGER_ENV": "production"}
        ):
            cookie = serve.H.session_cookie_header(
                "", revoke=True
            )

        self.assertIn("Max-Age=0", cookie)
        self.assertIn("Secure", cookie)


if __name__ == "__main__":
    unittest.main()
