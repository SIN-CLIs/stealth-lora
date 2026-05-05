"""Colab LoRA Launcher — Kostenloses Fine-Tuning via Google Colab mit mistral-finetune."""
import json, sys, base64, webbrowser
from pathlib import Path
from typing import Optional

COLAB_URL = "https://colab.research.google.com/github/mistralai/mistral-finetune/blob/main/examples/mistral_7b/1_train.ipynb"
TUNEKIT_URL = "https://tunekit.app/"
LOCAL_COLAB_SCRIPT = Path(__file__).parent / "colab_train_template.py"

MISTRAL_MODELS = {
    "7b": "mistralai/Mistral-7B-v0.3",
    "8x7b": "mistralai/Mixtral-8x7B-v0.1",
    "nemo": "mistralai/Mistral-Nemo-Base-2407",
}


class ColabLauncher:
    def __init__(self, model: str = "7b", hf_token: str = ""):
        self.model = MISTRAL_MODELS.get(model, MISTRAL_MODELS["7b"])
        self.hf_token = hf_token
        self._data_path = Path.home() / ".stealth" / "lora_training"

    def export_for_colab(self, output_path: Path = None) -> tuple[int, Path]:
        out = output_path or (self._data_path / "train_paired.jsonl")
        from .data_exporter import ContrastiveDataExporter
        exporter = ContrastiveDataExporter(min_examples=5)
        count, path = exporter.export()
        print(f"✅ {count} Beispiele exportiert → {path}")
        return count, path

    def generate_notebook(self, dataset_path: Path) -> str:
        template = LOCAL_COLAB_SCRIPT.read_text() if LOCAL_COLAB_SCRIPT.exists() else ""
        if not template:
            template = self._fallback_notebook()
        return template.replace("{DATASET_PATH}", str(dataset_path)).replace(
            "{HF_MODEL}", self.model).replace("{HF_TOKEN}", self.hf_token)

    def open_colab(self, dataset_path: Optional[Path] = None):
        data_path = dataset_path or self.export_for_colab()
        print(f"\n📋 Öffne diesen Link und lade {data_path.name} hoch:")
        print(f"   {TUNEKIT_URL}")
        print(f"\n🔧 Oder Colab: {COLAB_URL}")
        print(f"\n💡 Modell: {self.model}")
        print(f"📁 Dataset: {data_path}")
        print(f"\nFühre dann aus:")
        print(f"  pip install mistral-finetune huggingface_hub")
        print(f"  python -m mistral_finetune --data {data_path} --model {self.model}")
        print(f"  → Adapter wird gespeichert als: ./checkpoints/adapter.safetensors")
        print(f"\n🔄 Danach Upload zu HuggingFace Hub:")
        print(f"  huggingface-cli upload delqhi/sin-daemon-lora ./checkpoints --repo-type model")

    def _fallback_notebook(self) -> str:
        return '''# SIN-daemon LoRA Training (kostenlos auf Colab T4)
# pip install mistral-finetune datasets huggingface_hub

import json
from mistral_finetune import LoRATrainer, TrainingConfig
from datasets import Dataset

# Lade Trainingsdaten
with open("{DATASET_PATH}") as f:
    data = [json.loads(l) for l in f]

# Konvertiere zu Mistral-Finetune Format
messages = []
for d in data:
    messages.append({"messages": d["messages"]})

dataset = Dataset.from_list(messages)

# Trainiere LoRA
config = TrainingConfig(
    model_id="{HF_MODEL}",
    lora_rank=16,
    learning_rate=5e-5,
    epochs=2,
    batch_size=4,
    gradient_accumulation_steps=4,
    output_dir="./checkpoints",
)

trainer = LoRATrainer(config)
trainer.train(dataset)

print("✅ Training abgeschlossen! Adapter in ./checkpoints/")
print("Upload mit: huggingface-cli upload USER/sin-daemon-lora ./checkpoints")
'''


if __name__ == "__main__":
    launcher = ColabLauncher()
    launcher.open_colab()
