import os, time, json, logging, subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

from .colab_launcher import ColabLauncher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stealth_lora.sota")

STEALTH_DATA = Path.home() / ".stealth"
TRAIN_DIR = STEALTH_DATA / "lora_training"
ADAPTER_REGISTRY = STEALTH_DATA / "adapter_registry.json"


class ColabTrainerSOTA:
    def __init__(self, model: str = "7b", hf_token: str = ""):
        self.model = model
        self.hf_token = hf_token
        self.launcher = ColabLauncher(model=self.model, hf_token=self.hf_token)
        TRAIN_DIR.mkdir(parents=True, exist_ok=True)

    def export_data(self) -> tuple[int, Path]:
        count, path = self.launcher.export_for_colab()
        return count, path

    def train_on_colab(self, dataset_path: Optional[Path] = None) -> Path:
        data_path = dataset_path or self.launcher.export_for_colab()
        notebook = self.launcher.generate_notebook(data_path)
        notebook_path = TRAIN_DIR / f"colab_train_{datetime.now().strftime('%Y%m%d_%H%M')}.py"
        notebook_path.write_text(notebook)
        logger.info(f"Colab-Notebook geschrieben → {notebook_path}")
        print(f"\n{'='*60}")
        print(f"🚀 COLAB LORA TRAINING (KOSTENLOS)")
        print(f"{'='*60}")
        print(f"Modell: {self.launcher.model}")
        print(f"Dataset: {data_path}")
        print(f"Notebook: {notebook_path}")
        print(f"\nÖffne Google Colab (https://colab.research.google.com/)")
        print(f"→ Upload {notebook_path.name}")
        print(f"→ Oder kopiere den Code aus: {notebook_path}")
        print(f"\nOder nutze TuneKit (no-code): https://tunekit.app/")
        print(f"{'='*60}\n")
        return notebook_path

    def deploy_adapter(self, adapter_id: str, capability: str = "survey_ui_robustness"):
        data = json.loads(ADAPTER_REGISTRY.read_text()) if ADAPTER_REGISTRY.exists() else {"adapters": [], "active_adapter": None, "total_calls": 0}
        if not any(a["id"] == adapter_id for a in data["adapters"]):
            data["adapters"].append({
                "id": adapter_id, "description": f"Colab-LoRA Mistral {self.model} – kontrastives Lernen",
                "capability": capability, "base_model": self.launcher.model,
                "status": "available", "total_calls": 0,
            })
        data["active_adapter"] = adapter_id
        ADAPTER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        ADAPTER_REGISTRY.write_text(json.dumps(data, indent=2))
        logger.info(f"Adapter deployed: {adapter_id}")

    def run_full_cycle(self) -> Optional[str]:
        count, data_path = self.export_data()
        if count < 5:
            logger.error(f"Nicht genug Beispiele ({count} < 5)")
            return None

        notebook_path = self.train_on_colab(data_path)

        adapter_id = f"colab-lora-mistral-{self.model}-{int(time.time())}"
        print(f"\n📝 Nach dem Training:")
        print(f"   adapter_id = \"{adapter_id}\"")
        print(f"   → Upload zu HuggingFace: delqhi/sin-daemon-lora")
        print(f"   → Dann deploy mit: deploy_adapter(\"{adapter_id}\")")

        return notebook_path


if __name__ == "__main__":
    trainer = ColabTrainerSOTA()
    result = trainer.run_full_cycle()
    print(f"\n{'✅ Notebook erstellt' if result else '❌ Fehler beim Export'}")
