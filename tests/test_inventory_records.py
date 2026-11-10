"""End-to-end API-level property inventories: evidence scoping and immutable issue."""
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
import copy
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"stage-clone"))
import serve
import inventory_record


class InventoryTests(TestCase):
    def setUp(self):
        self.stage={
            "properties":[{"id":"flat-1","title":"A","tenant_party_id":"tenant-a","landlord_party_id":"landlord-1"},
                          {"id":"flat-2","title":"B","tenant_party_id":"tenant-b"}],
            "parties":[
                {"id":"tenant-a","roles":["tenant"],"status":"active","account_id":"acc-a"},
                {"id":"tenant-b","roles":["tenant"],"status":"active","account_id":"acc-b"},
                {"id":"landlord-1","roles":["landlord"],"status":"active","account_id":"acc-landlord"}],
            "tenancies":[
                {"id":"tenancy-a","property_id":"flat-1","tenant_party_ids":["tenant-a"],"status":"active"},
                {"id":"tenancy-b","property_id":"flat-2","tenant_party_ids":["tenant-b"],"status":"active"}],
            "documents":[
                {"id":"doc-public","property_id":"flat-1","tenancy_id":"tenancy-a",
                 "status":"verified","access_roles":["agent","tenant"]},
                {"id":"doc-private","property_id":"flat-1","tenancy_id":"tenancy-a",
                 "status":"verified","access_roles":["agent"]},
                {"id":"doc-other","property_id":"flat-2","tenancy_id":"tenancy-b",
                 "status":"verified","access_roles":["agent","tenant"]}],
            "inventories":[],"audit_log":[]
        }
        self.handler=serve.H.__new__(serve.H)
        self.handler.user={"role":"agent","username":"agent","account_id":"acc-agent"}
        self.last=[]
        self.handler._json=lambda data,code=200:self.last.append((data,code))
        a=patch.object(serve,"load_stage",return_value=self.stage)
        b=patch.object(serve,"save_stage")
        c=patch.object(serve,"now",return_value="2026-11-08T11:00:00Z")
        a.start(); b.start(); c.start()
        for x in (a,b,c): self.addCleanup(x.stop)

    def call(self, action, expected=200, **data):
        self.handler.handle_inventory_action({"action":action,**data})
        obj, code=self.last[-1]
        self.assertEqual(code,expected,obj)
        return obj

    def test_issue_photo_meter_keys_and_tenant_dispute(self):
        created=self.call("create",tenancy_id="tenancy-a",
                          kind="check_in",inspection_date="2026-11-08",
                          summary="Moving in")["inventory"]
        ref=created["id"]
        self.call("room",inventory_id=ref,room="Kitchen",condition="Clean, undamaged",
                  document_ids=["doc-public","doc-private"])
        self.call("meter",inventory_id=ref,meter="electricity",reading="003267",serial="XYZ")
        self.call("keys",inventory_id=ref,description="Front entrance",count=2)
        self.call("issue",inventory_id=ref)
        self.call("room",400,inventory_id=ref,room="Kitchen",condition="Damaged",
                  document_ids=[])
        self.assertEqual(self.stage["inventories"][0]["meter_readings"]["electricity"]["reading"],"003267")
        public=inventory_record.scoped_inventory(self.stage["inventories"][0],
                                                  "tenant",self.stage["documents"])
        self.assertEqual(public["rooms"][0]["document_ids"],["doc-public"])
        self.assertNotIn("created_by",public)
        self.assertNotIn("revisions",public)
        self.handler.user={"role":"tenant","account_id":"acc-a","username":"tenant"}
        self.call("acknowledge",inventory_id=ref,accepted=False,comment="Scratch near window")
        self.assertEqual(self.stage["inventories"][0]["status"],"disputed")
        self.call("acknowledge",400,inventory_id=ref,accepted=True,comment="Now accepted")
        self.assertEqual(self.stage["audit_log"][-1]["action"],"inventory_tenant_response")

    def test_foreign_tenant_cannot_touch_inventory(self):
        ref=self.call("create",tenancy_id="tenancy-a",kind="mid_term",
                      inspection_date="2026-11-08")["inventory"]["id"]
        self.call("room",inventory_id=ref,room="Bedroom",condition="Good",document_ids=[])
        self.call("issue",inventory_id=ref)
        self.handler.user={"role":"tenant","account_id":"acc-b","username":"unrelated"}
        self.call("acknowledge",403,inventory_id=ref,accepted=True,comment="")
        self.assertEqual(self.stage["inventories"][0]["status"],"issued")
        self.call("room",403,inventory_id=ref,room="Bedroom",condition="Bad",document_ids=[])

    def test_documents_cannot_cross_properties(self):
        ref=self.call("create",tenancy_id="tenancy-a",kind="check_in",
                      inspection_date="2026-11-08")["inventory"]["id"]
        self.call("room",400,inventory_id=ref,room="Kitchen",condition="Good",
                  document_ids=["doc-other"])
        self.assertEqual(len(self.stage["inventories"][0]["rooms"]),0)

    def test_requires_room_and_immutable_when_issued(self):
        ref=self.call("create",tenancy_id="tenancy-a",kind="check_out",
                      inspection_date="2026-11-08")["inventory"]["id"]
        self.call("issue",400,inventory_id=ref)
        self.call("room",inventory_id=ref,room="Sitting room",condition="Good",document_ids=[])
        self.call("issue",inventory_id=ref)
        self.call("issue",400,inventory_id=ref)
        self.call("meter",400,inventory_id=ref,meter="water",reading="123")

    def test_draft_is_invisible_to_tenant(self):
        x=self.call("create",tenancy_id="tenancy-a",kind="check_in",
                    inspection_date="2026-11-08")["inventory"]
        self.assertIsNone(inventory_record.scoped_inventory(x,"tenant",self.stage["documents"]))


if __name__=="__main__":
    main()
