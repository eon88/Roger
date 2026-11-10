"""B01 canonical identities, cross-record integrity and non-destructive upgrade."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"stage-clone"))
sys.path.insert(0,str(ROOT/"tests"/"fixtures"))
import canonical_records as cr
import serve
from v1_two_agency_data import build


class CanonicalTests(unittest.TestCase):
    def setUp(self):
        self.stage=build("oaklettings")
        self.stage["property_units"]=[]
        self.stage["ownership_interests"]=[]

    def test_legacy_upgrader_returns_copy_preserving_every_legacy_field(self):
        old=copy.deepcopy(self.stage)
        new,report=cr.propose_upgrade(self.stage)
        self.assertEqual(self.stage,old)
        self.assertEqual(new["model_metadata"]["version"],1)
        self.assertEqual(new["properties"],old["properties"])
        self.assertEqual(new["tenancies"],old["tenancies"])
        self.assertEqual(new["documents"],old["documents"])
        self.assertEqual(new["rent_ledger_entries"],old["rent_ledger_entries"])
        self.assertEqual(report["counts"]["properties"],2)
        self.assertEqual(cr.propose_upgrade(new)[0],new)
        self.assertEqual(cr.validate_for_save(new)["warnings"],[])

    def test_new_units_require_real_property_and_no_duplicate_ids(self):
        p=self.stage["properties"][0]["id"]
        u=cr.new_unit(self.stage,p,"unit-ground","Ground-floor flat","oaklettings")
        self.stage["property_units"].append(u)
        self.assertTrue(cr.validate_for_save(self.stage))
        with self.assertRaisesRegex(cr.RecordIntegrityError,"duplicate ID"):
            cr.new_unit(self.stage,p,"unit-ground","Different flat","oaklettings")
        with self.assertRaisesRegex(cr.RecordIntegrityError,"missing properties"):
            cr.new_unit(self.stage,"foreign-property","unit-foreign","Fake","oaklettings")

    def test_joint_owners_cannot_exceed_allocation(self):
        p=self.stage["properties"][0]["id"]
        owner1=self.stage["parties"][0]["id"]
        owner2="ci-oaklettings-party-landlord-2"
        self.stage["parties"].append({
            "id":owner2,"roles":["landlord"],"status":"active",
            "agency_id":"oaklettings","model_version":1,
        })
        a=cr.new_ownership(self.stage,"owner-interest-1",p,owner1,6000,
                           "2026-11-01",agency_id="oaklettings")
        self.stage["ownership_interests"].append(a)
        b=cr.new_ownership(self.stage,"owner-interest-2",p,owner2,4000,
                           "2026-11-01",agency_id="oaklettings")
        self.stage["ownership_interests"].append(b)
        self.assertEqual(sum(x["share_basis_points"] for x in
                             self.stage["ownership_interests"]),10000)
        with self.assertRaisesRegex(cr.RecordIntegrityError,"exceed 100"):
            cr.new_ownership(self.stage,"interest-3",p,owner2,1,
                             "2026-11-01",agency_id="oaklettings")
        with self.assertRaisesRegex(cr.RecordIntegrityError,"landlord Party"):
            cr.new_ownership(self.stage,"interest-4",p,self.stage["parties"][1]["id"],
                             1000,"2026-11-01",agency_id="oaklettings")

    def test_v1_tenancy_rejects_wrong_roles_and_foreign_units(self):
        t=copy.deepcopy(self.stage["tenancies"][0])
        t["model_version"]=1
        self.stage["tenancies"][0]=t
        self.assertEqual(cr.validate_for_save(self.stage)["warnings"],[])
        t["tenant_party_ids"]=[self.stage["parties"][0]["id"]]
        with self.assertRaisesRegex(cr.RecordIntegrityError,"wrong-role"):
            cr.validate_for_save(self.stage)
        t["tenant_party_ids"]=[self.stage["parties"][1]["id"]]
        t["unit_id"]="not-in-property"
        with self.assertRaisesRegex(cr.RecordIntegrityError,"missing property_units"):
            cr.validate_for_save(self.stage)

    def test_inventory_and_deposit_must_match_tenancy_property(self):
        rec=self.stage["deposit_records"][0]
        rec["model_version"]=1
        rec["property_id"]=self.stage["properties"][1]["id"]
        with self.assertRaisesRegex(cr.RecordIntegrityError,"does not match tenancy"):
            cr.validate_for_save(self.stage)
        rec["property_id"]=self.stage["properties"][0]["id"]
        self.assertTrue(cr.validate_for_save(self.stage))

    def test_document_cannot_refer_to_unrelated_tenancy(self):
        doc=self.stage["documents"][0]
        doc["model_version"]=1
        doc["tenancy_id"]=self.stage["tenancies"][1]["id"]
        with self.assertRaisesRegex(cr.RecordIntegrityError,"Document belongs to unrelated tenancies"):
            cr.validate_for_save(self.stage)

    def test_legacy_missing_references_are_reported_not_guessed_or_deleted(self):
        old=copy.deepcopy(self.stage)
        self.stage["documents"][0]["tenancy_id"]="unknown-legacy"
        result=cr.inspect(self.stage)
        self.assertTrue(any(w["field"]=="tenancy_id" for w in result["warnings"]))
        self.assertEqual(cr.propose_upgrade(self.stage)[0]["documents"][0]["tenancy_id"],
                         "unknown-legacy")
        self.assertEqual(self.stage["properties"],old["properties"])

    def test_bad_duplicate_ids_fail_even_on_legacy_snapshot(self):
        self.stage["properties"].append(copy.deepcopy(self.stage["properties"][0]))
        with self.assertRaisesRegex(cr.RecordIntegrityError,"duplicate ID"):
            cr.validate_for_save(self.stage)
        with self.assertRaisesRegex(cr.RecordIntegrityError,"duplicate ID"):
            cr.propose_upgrade(self.stage)

    def test_invalid_future_schema_not_downgraded(self):
        self.stage["model_metadata"]={"version":9000}
        with self.assertRaisesRegex(cr.RecordIntegrityError,"future"):
            cr.propose_upgrade(self.stage)

    def test_file_snapshot_rejects_new_duplicate_before_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            f=Path(directory)/"stage.json"
            before=copy.deepcopy(self.stage)
            f.write_text(json.dumps(before))
            bad=copy.deepcopy(before)
            bad["properties"].append(copy.deepcopy(bad["properties"][0]))
            with patch.object(serve,"STAGE_FILE",str(f)),\
                 patch.dict(os.environ,{"ROGER_STORAGE_BACKEND":"file",
                                        "ROGER_SAAS_MODE":"0"}):
                with self.assertRaises(cr.RecordIntegrityError):
                    serve.save_stage(bad)
            self.assertEqual(json.loads(f.read_text()),before)

    def test_strict_record_never_imports_foreign_owner(self):
        row=cr.new_unit(self.stage,self.stage["properties"][0]["id"],
                        "unit-a","Upstairs","oaklettings")
        row["agency_id"]="birchlettings"
        self.stage["property_units"].append(row)
        with self.assertRaises(cr.RecordIntegrityError):
            cr.validate_for_save(self.stage)


if __name__=="__main__":
    unittest.main()
