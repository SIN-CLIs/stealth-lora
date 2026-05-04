import json
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

KEY_FILE = Path.home() / ".stealth" / "api_keys.json"


class KeyPoolManager:
    def __init__(self, key_file: Path = KEY_FILE):
        self.key_file = key_file
        self.lock = threading.RLock()
        self._current_key = None
        self._load()

    def _load(self):
        if not self.key_file.exists():
            self.keys = []
            return
        with open(self.key_file) as f:
            data = json.load(f)
        self.keys = [k for k in data.get("keys", []) if not k.get("exhausted", False)
                     and k.get("value") and k.get("status") != "empty"]
        self.keys.sort(key=lambda k: k.get("failures", 0))

    def _save(self):
        with open(self.key_file) as f:
            data = json.load(f)
        data["keys"] = [
            {**k, "exhausted": k.get("exhausted", False), "status": k.get("status", "active")}
            for k in data.get("keys", [])
        ]
        with open(self.key_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_active_key(self) -> Optional[str]:
        with self.lock:
            self._load()
            if not self.keys:
                return None
            key = self.keys[0]["value"]
            self._current_key = key
            return key

    def report_failure(self, key_value: str):
        with self.lock:
            data = json.load(open(self.key_file))
            for k in data["keys"]:
                if k.get("value") == key_value:
                    k["failures"] = k.get("failures", 0) + 1
                    if k["failures"] >= 10:
                        k["exhausted"] = True
                        k["status"] = "exhausted"
                        print(f"Key erschöpft: {key_value[:12]}...")
                    break
            with open(self.key_file, "w") as f:
                json.dump(data, f, indent=2)
            self._load()

    def rotate(self):
        with self.lock:
            self._load()
            if len(self.keys) > 1:
                self.keys = self.keys[1:] + [self.keys[0]]
                self._current_key = self.keys[0]["value"]
            elif self.keys:
                self._current_key = self.keys[0]["value"]

    def add_key(self, key_id: str, key_value: str):
        with self.lock:
            with open(self.key_file) as f:
                data = json.load(f)
            for k in data["keys"]:
                if k.get("status") == "empty" or k.get("value") == "":
                    k["id"] = key_id
                    k["value"] = key_value
                    k["added"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    k["status"] = "active"
                    k["failures"] = 0
                    k["exhausted"] = False
                    break
            with open(self.key_file, "w") as f:
                json.dump(data, f, indent=2)
            self._load()

    def list_keys(self):
        with self.lock:
            if not self.key_file.exists():
                return []
            with open(self.key_file) as f:
                data = json.load(f)
            return [
                {"id": k["id"], "status": k["status"],
                 "failures": k.get("failures", 0),
                 "added": k.get("added"),
                 "exhausted": k.get("exhausted", False),
                 "note": k.get("note", "")}
                for k in data.get("keys", [])
            ]


manager = KeyPoolManager()