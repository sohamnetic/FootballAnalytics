"""Naming players on a match: only the owner, merge/remove, limits."""

import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app import auth, jobs, main, settings, storage, store  # noqa: E402


class PlayerNamesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(settings, "DATA_DIR", Path(self.tmp.name)),
            mock.patch.object(settings, "STORAGE", "local"),
            mock.patch.object(settings, "RUNNER", "external"),
            mock.patch.object(settings, "secret", lambda: "test"),
            mock.patch.object(auth, "secret", lambda: "test"),
        ]
        for p in self.patches:
            p.start()
        storage.get_storage.cache_clear()
        store._rows, auth._users, jobs._worker_state = None, None, None
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.owner = self.signup("owner@x.io")
        self.other = self.signup("other@x.io")
        self.match = "0f0f0f0f-0000-4000-8000-000000000001"
        store.upsert_match({"match_id": self.match, "user_id": auth.parse_token(self.owner)["id"], "status": "completed"})

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for p in self.patches:
            p.stop()
        storage.get_storage.cache_clear()
        store._rows, auth._users, jobs._worker_state = None, None, None
        self.tmp.cleanup()

    def signup(self, email):
        r = self.client.post("/api/auth/signup", json={"email": email, "password": "secret1"})
        return r.json()["token"]

    def put(self, names, token=None):
        return self.client.put(f"/api/matches/{self.match}/player-names", json={"names": names},
                               headers={"Authorization": f"Bearer {token or self.owner}"})

    def test_merge_and_remove(self):
        self.assertEqual(self.put({"7": "  Rahul   Sharma "}).json()["player_names"], {"7": "Rahul Sharma"})
        self.assertEqual(self.put({"9": "Keeper"}).json()["player_names"], {"7": "Rahul Sharma", "9": "Keeper"})
        self.assertEqual(self.put({"7": ""}).json()["player_names"], {"9": "Keeper"})
        detail = self.client.get(f"/api/matches/{self.match}", headers={"Authorization": f"Bearer {self.owner}"})
        self.assertEqual(detail.json()["player_names"], {"9": "Keeper"})

    def test_only_the_owner(self):
        self.assertEqual(self.put({"7": "Rahul"}, token=self.other).status_code, 403)

    def test_limits(self):
        self.assertEqual(self.put({"7": "x" * 41}).status_code, 400)
        self.assertEqual(self.put({"seven": "Rahul"}).status_code, 400)
        self.assertEqual(self.put({str(i): "a" for i in range(101)}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
