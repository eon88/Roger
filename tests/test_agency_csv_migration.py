"""Migration fixture tests: no silent merges, no live updates, no portal grants."""
from pathlib import Path
from unittest import TestCase,main
import importlib.util
import contextlib
import copy
import json
import os
import tempfile
import io
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "agency_import", ROOT/"ops"/"migration"/"agency_import.py")
importer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

PEOPLE="""external_id,display_name,role,email,phone
landlord-1,Sample Landlord,landlord,sample-owner@example.invalid,07000000001
tenant-1,Sample Tenant,tenant,sample-tenant@example.invalid,07000000002
"""
PROPERTIES="""external_id,title,area,landlord_external_id,address,postcode
prop-1,Sample Flat,Leeds,landlord-1,17 Sample Street,LS1 1AA
"""
TENANCIES="""external_id,property_external_id,tenant_external_id,landlord_external_id,start_date,rent_amount_pence,rent_frequency,deposit_amount_pence
lease-1,prop-1,tenant-1,landlord-1,2026-10-01,120000,monthly,120000
"""


class MigrationTests(TestCase):
    def setUp(self):
        self.stage={"agency_id":"fakeagency","parties":[],"properties":[],"tenancies":[]}
    def test_preview_no_side_effects_and_references_preserved(self):
        old=copy.deepcopy(self.stage)
        state,report=importer.plan(self.stage,PEOPLE,PROPERTIES,TENANCIES)
        self.assertEqual(self.stage,old)
        self.assertEqual(report["created"],{"people":2,"properties":1,"tenancies":1})
        self.assertEqual(state["properties"][0]["landlord_party_id"],state["parties"][0]["id"])
        self.assertEqual(state["tenancies"][0]["property_id"],state["properties"][0]["id"])
        self.assertEqual(state["tenancies"][0]["tenant_party_ids"],[state["parties"][1]["id"]])
        self.assertEqual(state["tenancies"][0]["tenancy_type"],"assured_periodic")
        self.assertEqual(state["tenancies"][0]["status"],"application")
        self.assertIsNone(state["parties"][0]["account_id"])
        self.assertEqual(state["properties"][0]["lifecycle_status"],"onboarding")

    def test_rerun_is_idempotent(self):
        result,initial=importer.plan(self.stage,PEOPLE,PROPERTIES,TENANCIES)
        later,second=importer.plan(result,PEOPLE,PROPERTIES,TENANCIES)
        self.assertEqual(second["total_created"],0)
        self.assertEqual(second["already_present"],{"people":2,"properties":1,"tenancies":1})
        self.assertEqual(result,later)

    def test_reject_mislinked_landlord_and_bad_csv(self):
        with self.assertRaises(importer.MigrationError):
            importer.plan(self.stage,PEOPLE,PROPERTIES,
                          TENANCIES.replace("lease-1,prop-1,tenant-1,landlord-1",
                                            "lease-1,prop-1,tenant-1,landlord-other"))
        with self.assertRaises(importer.MigrationError):
            importer.plan(self.stage,PEOPLE,PROPERTIES,
                          TENANCIES.replace("120000,monthly,120000","120000,annually,120000"))
        with self.assertRaises(importer.MigrationError):
            importer.plan(self.stage,PEOPLE+"tenant-1,Duplicate Tenant,tenant,x@y.invalid,123\n",
                          PROPERTIES,TENANCIES)
        with self.assertRaises(importer.MigrationError):
            importer.plan(self.stage,PEOPLE,
                          PROPERTIES.replace("landlord-1,17","tenant-1,17"),
                          TENANCIES)

    def test_dry_run_does_not_mutate_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d); file=folder/"stage.json"
            file.write_text(json.dumps(self.stage),encoding="utf-8")
            for name,content in (("people",PEOPLE),("properties",PROPERTIES),("tenancies",TENANCIES)):
                (folder/(name+".csv")).write_text(content,encoding="utf-8")
            args=["--data-dir",str(folder),
                  "--people",str(folder/"people.csv"),
                  "--properties",str(folder/"properties.csv"),
                  "--tenancies",str(folder/"tenancies.csv")]
            before=file.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                importer.main(args)
            self.assertEqual(before,file.read_bytes())
            self.assertFalse((folder/"backups").exists())
            with self.assertRaises(SystemExit):
                importer.main(args+["--apply","--confirm","OFFLINE-IMPORT"])
            self.assertEqual(before,file.read_bytes())

    def test_explicit_offline_apply_creates_restorable_backup(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d); file=folder/"stage.json"
            original=json.dumps(self.stage).encode()
            file.write_bytes(original)
            for name,content in (("people",PEOPLE),("properties",PROPERTIES),("tenancies",TENANCIES)):
                (folder/(name+".csv")).write_text(content,encoding="utf-8")
            args=["--data-dir",str(folder),
                  "--people",str(folder/"people.csv"),
                  "--properties",str(folder/"properties.csv"),
                  "--tenancies",str(folder/"tenancies.csv"),
                  "--apply","--confirm","OFFLINE-IMPORT"]
            with patch.dict(os.environ,{"ROGER_MIGRATION_OFFLINE":"1","ROGER_ENV":"test"}):
                with contextlib.redirect_stdout(io.StringIO()):
                    importer.main(args)
            backups=list((folder/"backups").glob("before-agency-import-*.json"))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_bytes(),original)
            self.assertEqual(len(json.loads(file.read_text())["tenancies"]),1)


if __name__=="__main__":
    main()
