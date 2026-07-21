import os
import tempfile
import unittest
from datetime import datetime, timedelta


_data_dir = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _data_dir.name

from app import db  # noqa: E402


class PurgeExpiredResultsTest(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.DbConnection() as conn:
            conn.execute("DELETE FROM results")
            conn.execute("DELETE FROM jobs")
            old = (datetime.now() - timedelta(hours=100)).isoformat()
            conn.execute(
                "INSERT INTO jobs (id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("expired-job", "completed", old, old),
            )
            conn.execute(
                "INSERT INTO results (job_id, filename, created_at) VALUES (?, ?, ?)",
                ("expired-job", "invoice.png", old),
            )

    def test_purge_removes_results_before_jobs(self):
        self.assertEqual(db.purge_expired_results(72), 1)

        with db.DbConnection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM results").fetchone()[0], 0)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
