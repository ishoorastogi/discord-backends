"""Measures how often ConTeXT picks the RIGHT ESCO skill, at different min_score cutoffs.
Run:  python tune_threshold.py"""
import csv
import random

import esco_skills

SENTENCES_CSV = r"C:\Users\ishaa\esco\synthetic_sentences.csv"
SAMPLE = 500                        # 500 sentences is enough for a quick test

random.seed(0)                      # same sample every run
with open(SENTENCES_CSV, newline="", encoding="utf-8-sig") as f:
    rows = random.sample(list(csv.DictReader(f)), SAMPLE)
texts = [r["sentence"] for r in rows]
gold = [r["skill"].strip().lower() for r in rows]

extractor = esco_skills.EscoSkillExtractor()
# min_score=-1 means "always return the best match", so we can apply cutoffs ourselves below
best = [m[0] for m in extractor.extract(texts, top_k=1, min_score=-1)]

print(f"{'cutoff':<8}{'kept':<8}{'precision':<11}(precision = of kept matches, how many were right)")
for cutoff in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
    kept = [(m, g) for m, g in zip(best, gold) if m.score >= cutoff]
    right = sum(m.label.strip().lower() == g for m, g in kept)
    precision = right / len(kept) if kept else 0
    print(f"{cutoff:<8}{len(kept) / SAMPLE:<8.0%}{precision:<11.0%}")