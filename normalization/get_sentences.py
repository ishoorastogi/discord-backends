import csv
import os
from datasets import load_dataset

OUT = r"C:\Users\ishaa\esco\synthetic_sentences.csv"

ds = load_dataset("TechWolf/Synthetic-ESCO-skill-sentences", split="train")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["sentence", "skill"])
    for row in ds:
        writer.writerow([row["sentence"], row["skill"]])

print(f"Wrote {len(ds)} rows to {OUT}")