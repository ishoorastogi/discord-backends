"""
Skill extraction with the ConTeXT model + the ESCO skill list.

THE IDEA IN ONE PICTURE
    ESCO file: ~13,900 official skill names  --(ConTeXT model)-->  13,900 vectors   (done ONCE, saved to disk)
    A resume sentence                        --(ConTeXT model)-->  1 vector
    Compare the sentence vector with all 13,900 skill vectors; the closest ones are
    the skills that sentence talks about.

ConTeXT is a "sentence-transformers" model, the SAME kind of thing as MiniLM:
text goes in, a list of numbers comes out. It was just trained on job-market text,
so its notion of "close" is tuned for skills.

SETUP (one time)
  1. Download the ESCO dataset (CSV, English) from the ESCO website's download page.
  2. Find the skills file (named something like skills_en.csv) and put its path in ESCO_CSV_PATH below.
  3. python -m pip install sentence-transformers numpy
"""
import csv
import hashlib
from collections import namedtuple
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- config (all in one place)
CONTEXT_MODEL_NAME = "TechWolf/ConTeXT-Skill-Extraction-base"

# Path to the ESCO skills CSV. LEFT BLANK ON PURPOSE. Example later:
#   ESCO_CSV_PATH = r"C:\Users\ishaa\esco\skills_en.csv"
import os
# Put your real path in the second argument. An ESCO_CSV environment variable overrides it.
ESCO_CSV_PATH = os.environ.get("ESCO_CSV", r"C:\Users\ishaa\esco\skills_en.csv")

CACHE_DIR = str(Path(__file__).with_name(".skill_cache"))   # always next to this file, wherever you run from      # where the 13,900 skill vectors are saved after the first run

# STARTING GUESS, not a tested value. Tune it with:  python esco_skills.py
DEFAULT_MIN_SCORE = 0.50

SkillMatch = namedtuple("SkillMatch", ["label", "uri", "score"])


# ---------------------------------------------------------------- reading ESCO
def load_esco_skills(csv_path, label_col="preferredLabel", uri_col="conceptUri"):
    """
    Read the ESCO skills CSV -> list of {"label": ..., "uri": ...}.
    The column names are what I EXPECT the file to contain. If yours differ,
    the error below prints the real ones; just change label_col / uri_col.
    ('utf-8-sig' also copes with an invisible BOM character at the start of a file.)
    """
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for needed in (label_col, uri_col):
            if needed not in columns:
                raise ValueError(f"Column {needed!r} not found in {csv_path}. "
                                 f"Columns in this file are: {columns}")
        return [{"label": row[label_col].strip(), "uri": row[uri_col].strip()}
                for row in reader if row[label_col].strip()]


# ---------------------------------------------------------------- the extractor
class EscoSkillExtractor:
    """
    extract(texts) -> for each text, the ESCO skills it most resembles.

    skills    : list of {"label", "uri"}. If None, read from csv_path.
    embed_fn  : function list[str] -> 2D array of UNIT-LENGTH vectors.
                If None, the real ConTeXT model is loaded (lazily, once).
                Tests pass a fake here, so they run without downloading anything.
    cache_dir : folder for the saved skill vectors (None = don't save).
    """

    def __init__(self, csv_path=None, skills=None, embed_fn=None,
                 model_name=CONTEXT_MODEL_NAME, cache_dir=CACHE_DIR,
                 min_score=DEFAULT_MIN_SCORE):
        self.skills = skills if skills is not None else load_esco_skills(csv_path or ESCO_CSV_PATH)
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.min_score = min_score
        self._embed_fn = embed_fn
        self._model = None
        self._vecs = None               # the 13,900 skill vectors, built lazily
        self.log = []                   # what matched what, for you to read: see report()

    # ---- embedding
    def _embed(self, texts):
        if self._embed_fn is not None:
            return np.asarray(self._embed_fn(texts), dtype=np.float32)
        if self._model is None:                       # load the model ONCE
            from sentence_transformers import SentenceTransformer
            # If loading fails, check the model card; you may need: SentenceTransformer(self.model_name, trust_remote_code=True)
            self._model = SentenceTransformer(self.model_name)
        return np.asarray(
            self._model.encode(texts, normalize_embeddings=True, batch_size=64,
                               show_progress_bar=len(texts) > 500),
            dtype=np.float32)

    def _skill_vectors(self):
        """Vectors for every ESCO skill. Slow the first time (minutes on a CPU), instant afterwards."""
        if self._vecs is not None:
            return self._vecs
        labels = [s["label"] for s in self.skills]
        cache_file = None
        if self.cache_dir:
            # The file name contains a fingerprint of (model + skill list). If either changes,
            # the fingerprint changes, so we never reuse stale vectors by accident.
            key = hashlib.sha256((self.model_name + "\n" + "\n".join(labels)).encode()).hexdigest()[:16]
            cache_file = Path(self.cache_dir) / f"esco_vectors_{key}.npy"
            if cache_file.exists():
                self._vecs = np.load(cache_file)
                return self._vecs
        self._vecs = self._embed(labels)
        if cache_file is not None:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache_file, self._vecs)
        return self._vecs

    # ---- main function
    def extract(self, texts, top_k=3, min_score=None):
        """
        For each text, return up to top_k SkillMatch(label, uri, score), best first,
        keeping only scores >= min_score. A text with no good match gets an empty list.
        Scores are cosine similarity (dot product of unit vectors): 1.0 = identical meaning.
        """
        min_score = self.min_score if min_score is None else min_score
        texts = [t for t in texts]
        if not texts:
            return []
        text_vecs = self._embed(texts)                     # (n_texts, dim)
        scores = text_vecs @ self._skill_vectors().T       # (n_texts, n_skills): ALL comparisons at once

        results = []
        for text, row in zip(texts, scores):
            best = np.argsort(-row)[:top_k]
            matches = [SkillMatch(self.skills[i]["label"], self.skills[i]["uri"], round(float(row[i]), 3))
                       for i in best if row[i] >= min_score]
            results.append(matches)
            self.log.append({"text": text, "matches": matches})
        return results

    def explain(self, text, top=5):
        """Top candidates for one text, with NO threshold. Use this to pick min_score."""
        row = self._embed([text])[0] @ self._skill_vectors().T
        return [(self.skills[i]["label"], round(float(row[i]), 3)) for i in np.argsort(-row)[:top]]

    def report(self, max_lines=40):
        """Readable summary of what each text matched."""
        if not self.log:
            return "Nothing extracted yet."
        lines = []
        for entry in self.log[:max_lines]:
            found = ", ".join(f"{m.label} ({m.score})" for m in entry["matches"]) or "NO MATCH"
            lines.append(f"  {entry['text'][:60]!r:<64} -> {found}")
        return "\n".join(lines)


# ---------------------------------------------------------------- tuning demo
if __name__ == "__main__":
    if not ESCO_CSV_PATH:
        raise SystemExit("Set ESCO_CSV_PATH at the top of esco_skills.py first.")
    extractor = EscoSkillExtractor()
    print(f"Loaded {len(extractor.skills)} ESCO skills. "
          "The first run embeds them all (a few minutes); later runs reuse the saved file.\n")
    for phrase in ["JS", "Postgre SQL", "TensorFlow", "Kubernetes",
                   "Built REST APIs in Flask serving 10k requests per day",
                   "Baked 200 croissants daily"]:
        print(phrase)
        for label, score in extractor.explain(phrase):
            print(f"    {score:<6} {label}")
    print("\nRead the scores: where do RIGHT matches stop and WRONG ones start? "
          "That boundary is your min_score.")