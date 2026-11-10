"""B02 inventory: all POST dispatches need explicit roles or public classification.

The manifest fails when a new mutation is added without a role policy; GET
routes are separately checked for authentication/ownership guards.
"""
import ast
from pathlib import Path
import inspect
import sys
import textwrap
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class EndpointSecurityInventory(unittest.TestCase):
    def test_every_mutation_handler_has_explicit_public_or_role_policy(self):
        source = textwrap.dedent(inspect.getsource(serve.H.do_POST))
        parsed = ast.parse(source)
        dispatch = next(
            node.value for node in ast.walk(parsed)
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "handlers"
                for target in node.targets))
        names = {n.value for n in dispatch.keys}
        self.assertTrue(all(path.startswith("/") for path in names))
        self.assertEqual(len(names), len(dispatch.keys), "duplicate POST routes")
        self.assertEqual(set(serve.H.ROLE_API) | set(serve.H.PUBLIC_POST), names)
        self.assertFalse(set(serve.H.ROLE_API) & set(serve.H.PUBLIC_POST))
        for path, roles in serve.H.ROLE_API.items():
            with self.subTest(path=path):
                self.assertTrue(roles)
                self.assertTrue(roles.issubset({"agent", "tenant", "landlord", "trades"}))

    def test_finance_and_privileged_staff_routes_are_least_privilege(self):
        roles = serve.H.ROLE_API
        for route in (
            "/api/rent-ledger-action", "/api/bank-reconciliation-action",
            "/api/landlord-statement-action", "/api/security/staff/invite",
            "/api/security/staff/suspend", "/api/invitation",
            "/api/management-agreement-action",
        ):
            self.assertEqual(roles[route], {"agent"})
        self.assertEqual(roles["/api/landlord-action"], {"landlord"})
        self.assertEqual(roles["/api/job-action"], {"trades", "agent"})
        self.assertEqual(roles["/api/document"], {"agent"})
        self.assertEqual(roles["/api/document-action"], {"agent"})

    def unauthenticated_get(self, path):
        h = serve.H.__new__(serve.H)
        h.path = path
        h.sent = []
        h.session_user = lambda: None
        h.send_response = lambda code: h.sent.append(("status", code))
        h.send_header = lambda k,v: None
        h.end_headers = lambda: None
        h.send_error = lambda code, *args: h.sent.append(("error", code))
        h._json = lambda body, code=200: h.sent.append(("json", code))
        h.serve_file = lambda *args, **kwargs: h.sent.append(("leaked", True))
        h.require = lambda roles=None: h.sent.append(("auth_required", roles)) or None
        h._do_GET_with_agency_boundary()
        return h.sent

    def test_every_private_get_requires_authentication_before_reading(self):
        protected = [
            "/change-password", "/security", "/api/stage", "/agent",
            "/tenant", "/landlord", "/trades", "/api/deposits",
            "/api/inventories", "/api/tenancy-policy", "/api/agent/briefing",
            "/api/trades-pool", "/api/compliance", "/api/landlord-statements",
            "/api/rent-ledger", "/api/landlord/rent-ledger",
            "/api/appointments", "/api/tasks", "/api/office-settings",
            "/api/newsletter-subscriptions", "/api/notifications",
            "/api/documents", "/api/document/doc-1",
            "/api/document/doc-1/file",
        ]
        for path in protected:
            with self.subTest(path=path):
                result = self.unauthenticated_get(path)
                self.assertTrue(any(item[0] == "auth_required" for item in result), result)
                self.assertFalse(any(item[0] == "leaked" for item in result))

    def test_invite_tokens_in_url_do_not_enter_access_logs(self):
        result = self.unauthenticated_get("/api/invitation/validate/private-token")
        self.assertEqual(result, [("error", 404)])
        source = inspect.getsource(serve.H._do_GET_with_agency_boundary)
        self.assertNotIn('return self._json(self.validate_invitation_token(', source)
        self.assertIn("/api/invite/validate", serve.H.PUBLIC_POST)

    def test_non_agent_portals_offer_security_settings(self):
        root = Path(__file__).resolve().parents[1] / "stage-clone"
        for role in ("agent", "landlord", "tenant", "trades"):
            with self.subTest(role=role):
                html = (root / (role + ".html")).read_text()
                self.assertIn('href="/security"', html)
        self.assertIn('id="totp"', (root / "login.html").read_text())

    def test_no_private_downloads_or_source_files_under_static_allowlist(self):
        self.assertFalse(serve.H.is_public(serve.H.__new__(serve.H), "/files/abc"))
        self.assertFalse(serve.H.is_public(serve.H.__new__(serve.H), "/users.json"))
        self.assertFalse(serve.H.is_public(serve.H.__new__(serve.H), "/security"))
        self.assertNotIn("/api/stage", serve.H.PUBLIC_GET)


if __name__ == "__main__":
    unittest.main()
