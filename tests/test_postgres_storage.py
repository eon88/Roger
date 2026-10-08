"""Tests for the optional PostgreSQL snapshot backend."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-clone"))
import serve


class FakeCursor:
    def fetchone(self):
        return ({"cases": []},)


class FakeConnection:
    def __init__(self):
        self.queries = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, query, params=None):
        self.queries.append((query, params))
        return FakeCursor()


class PostgresStorageTests(unittest.TestCase):
    def test_postgres_backend_reads_snapshot_and_syncs_entity_projections(self):
        connection = FakeConnection()
        with patch.dict("os.environ", {"ROGER_STORAGE_BACKEND": "postgres", "DATABASE_URL": "postgresql://test"}):
            with patch.object(serve, "postgres_connection", return_value=connection):
                self.assertEqual(serve.load_stage(), {"cases": []})
                serve.save_stage({
                    "properties": [{"id": "home-1"}],
                    "tenancies": [{"id": "tenancy-1", "property_id": "home-1"}],
                })
        queries = [query for query, _ in connection.queries]
        self.assertTrue(any("roger_stage_snapshot" in q for q in queries))
        self.assertTrue(any("INSERT INTO roger_properties" in q for q in queries))
        self.assertTrue(any("INSERT INTO roger_tenancies" in q for q in queries))
        self.assertTrue(any("TRUNCATE TABLE roger_jobs" in q for q in queries))

    def test_postgres_backend_requires_database_url(self):
        with patch.dict("os.environ", {"ROGER_STORAGE_BACKEND": "postgres"}, clear=True):
            with self.assertRaises(RuntimeError):
                serve.postgres_connection()


if __name__ == "__main__":
    unittest.main()
