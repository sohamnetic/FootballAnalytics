"""When the API starts a Kaggle notebook, and what happens to jobs whose
worker disappears. Kaggle itself is replaced by a fake launch()."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app import jobs, settings, storage, store


class CloudJobsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(settings, "DATA_DIR", Path(self.tmp.name)),
            mock.patch.object(settings, "STORAGE", "local"),
            mock.patch.object(settings, "RUNNER", "kaggle"),
            mock.patch.object(settings, "secret", lambda: "test"),
        ]
        for p in self.patches:
            p.start()
        storage.get_storage.cache_clear()
        store._rows = None
        jobs._worker_state = None
        self.launches = []
        self.launch = mock.patch("app.kaggle_launcher.launch", side_effect=self.launches.append)
        self.launch.start()

    def tearDown(self):
        self.launch.stop()
        for p in self.patches:
            p.stop()
        storage.get_storage.cache_clear()
        store._rows = None
        jobs._worker_state = None
        self.tmp.cleanup()

    def add_match(self, match_id="m1"):
        key = store.upload_key(match_id, ".mp4")
        path = storage.get_storage().path(key)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"video")
        store.upsert_match({"match_id": match_id, "video_key": key, "status": "uploaded", "bytes": 5})
        store.upsert_match({"match_id": match_id, "status": "queued", "attempts": 0, "queued_at": time.time()})
        return match_id

    def test_starts_one_notebook_while_it_boots(self):
        self.add_match("m1")
        jobs.kick()
        self.add_match("m2")
        jobs.kick()
        self.assertEqual(len(self.launches), 1)

    def test_running_worker_is_not_doubled_and_exit_allows_restart(self):
        self.add_match("m1")
        jobs.kick()
        job = jobs.claim("w1")
        self.assertEqual(job["match_id"], "m1")
        self.add_match("m2")
        jobs.kick()
        self.assertEqual(len(self.launches), 1)
        jobs.worker_exit("w1", "idle")
        jobs.kick()
        self.assertEqual(len(self.launches), 2)

    def test_silent_worker_gets_requeued_then_failed(self):
        self.add_match("m1")
        jobs.claim("w1")
        store.upsert_match({"match_id": "m1", "heartbeat_at": time.time() - settings.WORKER_STALE_S - 5})
        jobs.watchdog()
        self.assertEqual(store.get_match("m1")["status"], "queued")
        jobs.claim("w2")
        store.upsert_match({"match_id": "m1", "heartbeat_at": time.time() - settings.WORKER_STALE_S - 5})
        jobs.watchdog()
        self.assertEqual(store.get_match("m1")["status"], "failed")

    def test_no_gpu_waits_an_hour(self):
        self.add_match("m1")
        jobs.kick()
        jobs.worker_exit("w1", "no_gpu")
        jobs.kick()
        self.assertEqual(len(self.launches), 1)
        self.assertIn("GPU hours", store.get_match("m1")["message"])

    def test_failed_push_is_retried_later(self):
        self.launch.stop()
        with mock.patch("app.kaggle_launcher.launch", side_effect=RuntimeError("401")):
            self.add_match("m1")
            jobs.kick()
        self.launch.start()
        jobs.kick()
        self.assertEqual(self.launches, [])
        jobs._worker_state["last_push"] = time.time() - jobs.PUSH_RETRY_S - 1
        jobs.kick()
        self.assertEqual(len(self.launches), 1)

    def test_other_workers_cannot_touch_a_job(self):
        self.add_match("m1")
        jobs.claim("w1")
        self.assertFalse(jobs.heartbeat("m1", "intruder", "Tracking players", 30))
        self.assertTrue(jobs.heartbeat("m1", "w1", "Tracking players", 30))
        self.assertEqual(store.get_match("m1")["progress"], 30)

    def test_notebook_script_has_config(self):
        from app import kaggle_launcher

        with mock.patch.multiple(settings, KAGGLE_USERNAME="me", WORKER_TOKEN="tok",
                                 PUBLIC_API_URL="https://api.example", GIT_REF="abc123"):
            with tempfile.TemporaryDirectory() as tmp:
                folder = kaggle_launcher.build_notebook(Path(tmp), "run1")
                meta = json.loads((folder / "kernel-metadata.json").read_text())
                script = (folder / "worker_boot.py").read_text()
        self.assertEqual(meta["id"], "me/fa-analysis-worker")
        self.assertTrue(meta["enable_gpu"] and meta["enable_internet"] and meta["is_private"])
        self.assertIn('"ref": "abc123"', script)
        self.assertIn('"FA_WORKER_TOKEN": "tok"', script)
        compile(script, "worker_boot.py", "exec")


if __name__ == "__main__":
    unittest.main()
