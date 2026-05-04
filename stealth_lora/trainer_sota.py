import os, time, json, logging
from pathlib import Path
from typing import Optional
import httpx

from ..key_rotator.manager import KeyPoolManager

FW_API_BASE = "https://api.fireworks.ai"
FW_INFERENCE_BASE = "https://api.fireworks.ai/inference/v1"
BASE_MODEL = "accounts/fireworks/models/minimax-m2p7"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stealth_lora.sota")


class FireworksTrainerSOTA:
    def __init__(self, base_model: str = BASE_MODEL):
        self.base_model = base_model
        self.pool = KeyPoolManager()
        self.account_id = self._discover_account_id()

    def _key(self) -> str:
        key = self.pool.get_active_key()
        if not key:
            raise RuntimeError("Kein API-Key im Pool verfügbar")
        return key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}

    def _http(self, method: str, url: str, **kwargs) -> httpx.Response:
        key = self._key()
        with httpx.Client(timeout=60) as client:
            r = client.request(method, url, headers={"Authorization": f"Bearer {key}"}, **kwargs)
        if r.status_code == 429:
            self.pool.report_failure(key)
            logger.warning(f"Rate-Limit auf Key {key[:12]}... Rotating...")
            self.pool.rotate()
            return self._http(method, url, **kwargs)
        return r

    def _discover_account_id(self) -> str:
        r = httpx.get(f"{FW_API_BASE}/v1/accounts",
                      headers={"Authorization": f"Bearer {self._key()}"}, timeout=15)
        r.raise_for_status()
        accounts = r.json().get("accounts", [])
        if not accounts:
            raise RuntimeError("Kein Fireworks-Account gefunden")
        name = accounts[0].get("name", "")
        account_id = name.replace("accounts/", "")
        logger.info(f"Account: {account_id}")
        return account_id

    def _account_url(self, path: str) -> str:
        return f"{FW_API_BASE}/v1/accounts/{self.account_id}/{path}"

    def create_dataset(self, dataset_id: str, example_count: int) -> bool:
        url = self._account_url("datasets")
        payload = {"datasetId": dataset_id, "dataset": {"userUploaded": {}, "exampleCount": str(example_count)}}
        r = self._http("POST", url, json=payload)
        if r.status_code not in (200, 201):
            logger.error(f"Dataset-Erstellung fehlgeschlagen: {r.text}")
            return False
        logger.info(f"Dataset-Record erstellt: {dataset_id}")
        return True

    def upload_dataset_file(self, dataset_id: str, dataset_path: Path) -> bool:
        url = self._account_url(f"datasets/{dataset_id}:upload")
        for attempt in range(3):
            try:
                key = self._key()
                with open(dataset_path, "rb") as f:
                    r = httpx.post(url, headers={"Authorization": f"Bearer {key}"},
                                   files={"file": (dataset_path.name, f, "application/jsonl")}, timeout=120)
                if r.status_code == 429:
                    self.pool.report_failure(key)
                    self.pool.rotate()
                    time.sleep(5)
                    continue
                if r.status_code in (200, 201):
                    logger.info(f"Upload OK: {dataset_path.name}")
                    return True
                logger.warning(f"Upload attempt {attempt+1}/3 ({r.status_code}): {r.text[:200]}")
                time.sleep(5)
            except Exception as e:
                logger.warning(f"Upload attempt {attempt+1}/3 Exception: {e}")
                time.sleep(5)
        return False

    def validate_dataset(self, dataset_id: str) -> bool:
        url = self._account_url(f"datasets/{dataset_id}:validateUpload")
        r = self._http("POST", url)
        return r.status_code in (200, 201)

    def create_ft_job(self, dataset_id: str) -> Optional[str]:
        output_id = f"sin-daemon-lora-{int(time.time())}"
        url = self._account_url("supervisedFineTuningJobs")
        payload = {
            "displayName": output_id, "baseModel": self.base_model, "dataset": dataset_id,
            "outputModel": output_id, "epochs": 2, "learningRate": 5e-5,
            "loraRank": 16, "batchSize": 16, "gradientAccumulationSteps": 4,
        }
        r = self._http("POST", url, json=payload)
        if r.status_code not in (200, 201):
            logger.error(f"Job-Erstellung fehlgeschlagen: {r.text}")
            return None
        result = r.json()
        job_name = result.get("name", output_id)
        logger.info(f"Fine-Tuning Job erstellt: {job_name}")
        return job_name

    def poll_ft_job(self, job_name: str, max_seconds: int = 600) -> Optional[str]:
        url = self._account_url(f"supervisedFineTuningJobs/{job_name}")
        end = time.time() + max_seconds
        while time.time() < end:
            try:
                r = self._http("GET", url)
                status = r.json()
                state = status.get("state", "STATE_UNSPECIFIED")
                if state == "JOB_STATE_COMPLETED":
                    model = status.get("outputModel", "")
                    logger.info(f"Training erfolgreich: {model}")
                    return model
                if state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED"):
                    logger.error(f"Training fehlgeschlagen: {status.get('errorMessage', state)}")
                    return None
                logger.info(f"Status: {state} – warten...")
                time.sleep(20)
            except Exception as e:
                logger.warning(f"Polling-Fehler: {e}")
                time.sleep(15)
        logger.error("Timeout beim Training")
        return None

    def evaluate(self, adapter_model_id: str, prompts: list[str]) -> float:
        if not prompts:
            return 1.0
        url = f"{FW_INFERENCE_BASE}/chat/completions"
        hits = 0
        for prompt in prompts:
            try:
                r = self._http("POST", url, json={
                    "model": adapter_model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 128,
                })
                answer = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                if any(kw in answer.lower() for kw in ["ax-tree", "weiter", "klicken", "workaround", "element"]):
                    hits += 1
                logger.info(f"Eval: {prompt[:40]} → {answer[:50]}")
            except Exception as e:
                logger.warning(f"Eval-Fehler: {e}")
        return hits / len(prompts)

    def deploy(self, adapter_id: str, capability: str = "survey_ui_robustness"):
        reg_path = Path.home() / ".stealth" / "adapter_registry.json"
        data = json.loads(reg_path.read_text()) if reg_path.exists() else {"adapters": [], "active_adapter": None, "total_calls": 0}
        if not any(a["id"] == adapter_id for a in data["adapters"]):
            data["adapters"].append({
                "id": adapter_id, "description": "SOTA LoRA – kontrastives Lernen",
                "capability": capability, "base_model": self.base_model,
                "status": "available", "total_calls": 0,
            })
        data["active_adapter"] = adapter_id
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps(data, indent=2))
        logger.info(f"Adapter deployed: {adapter_id}")

    def run_full_cycle(self) -> Optional[str]:
        from .data_exporter import ContrastiveDataExporter
        exporter = ContrastiveDataExporter(min_examples=10)
        count, path = exporter.export()
        if count == 0:
            logger.error(f"Nicht genug Beispiele ({count} < 10)")
            return None

        dataset_id = f"sin-daemon-{int(time.time())}"
        if not self.create_dataset(dataset_id, count):
            return None
        if not self.upload_dataset_file(dataset_id, path):
            return None
        self.validate_dataset(dataset_id)

        job_name = self.create_ft_job(dataset_id)
        if not job_name:
            return None

        adapter_model = self.poll_ft_job(job_name)
        if not adapter_model:
            return None

        score = self.evaluate(adapter_model, [
            "Ziel: Weiter-Button klicken. Element nicht über data-testid gefunden.",
            "Dropdown Land auswählen. aria-label nicht expandierbar.",
        ])
        logger.info(f"Eval-Score: {score:.2f}")
        if score < 0.5:
            logger.warning("Qualität zu niedrig – kein Deployment")
            return None

        self.deploy(adapter_model)
        return adapter_model


if __name__ == "__main__":
    trainer = FireworksTrainerSOTA()
    result = trainer.run_full_cycle()
    print(f"{'✅ Adapter: ' + result if result else '❌ Training fehlgeschlagen'}")