import csv
import os
from datasets import load_dataset

OUT = r"C:\Users\ishaa\esco\skills_en.csv"      # same path esco_skills.py already uses

corpus = load_dataset("TechWolf/Skill-normalisation-ESCO-graded", "corpus", split="corpus")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["conceptUri", "preferredLabel"])       # column names esco_skills.py looks for
    for row in corpus:
        writer.writerow([row["_id"], row["title"]])

print(f"Wrote {len(corpus)} skills to {OUT}")