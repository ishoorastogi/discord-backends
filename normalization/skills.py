"""
LAYER 1 of skill normalization: the manually built local dictionary.

The vocabulary lives in skills_vocab.csv (edit it in Excel or any text editor):
    canonical = the one generic name we want a skill to be called
    aliases   = other spellings of it, separated by |
    ambiguous = terms that are also ordinary English words ("go", "r", "rest").
                Fine inside a skills LIST, but IGNORED when searching sentences,
                otherwise "go to market" would count as the Go language.

This file has no AI in it. Two things it can do:
  1. look up a short skill item     ("JS"  -> "javascript")
  2. search a sentence for known terms ("Built REST APIs in Flask" -> ["rest api", "flask"])
"""
import csv
import re
from pathlib import Path

VOCAB_PATH = Path(__file__).with_name("skills_vocab.csv")


def load_vocab(path=VOCAB_PATH):
    """
    Read the CSV. Returns:
      lookup    : {variant -> canonical name}  (every spelling points to the generic name)
      ambiguous : set of variants that must NOT be searched for inside sentences
    """
    lookup, ambiguous = {}, set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {"canonical", "aliases", "ambiguous"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: header row must be 'canonical,aliases,ambiguous'. "
                             f"Missing: {sorted(missing)}. Found: {reader.fieldnames}")
        for row in reader:
            canon = row["canonical"].strip().lower()
            lookup[canon] = canon                      # the generic name maps to itself
            for alias in row["aliases"].split("|"):
                alias = alias.strip().lower()
                if alias:
                    lookup[alias] = canon
            for term in row["ambiguous"].split("|"):
                term = term.strip().lower()
                if term:
                    ambiguous.add(term)
    if not lookup:
        raise ValueError(f"{path} has a header but NO skills in it, so the dictionary layer "
                         "would match nothing. Replace it with the provided skills_vocab.csv.")
    return lookup, ambiguous


def clean_key(text):
    """'  JS ' -> 'js'  (lowercase, single spaces). Used for dictionary lookups."""
    return " ".join(str(text).lower().split())


def build_matcher(lookup, ambiguous):
    """
    ONE regex that finds any known term inside a sentence.
    - Longest terms first, so 'machine learning' wins over shorter overlaps.
    - The lookbehind/lookahead mean "not glued to other letters", so 'java' does NOT
      match inside 'javascript' and 'c' does not match inside 'cat'.
      '+' and '#' are included so 'c++' and 'c#' stay whole.
    """
    terms = sorted((t for t in lookup if t not in ambiguous), key=len, reverse=True)
    pattern = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"(?<![A-Za-z0-9+#])(?:{pattern})(?![A-Za-z0-9+#])", re.IGNORECASE)


def find_terms_in_sentence(text, matcher, lookup):
    """Known skills inside free text -> generic names, in order found, no duplicates."""
    found, seen = [], set()
    for m in matcher.finditer(text or ""):
        canon = lookup[clean_key(m.group(0))]
        if canon not in seen:
            seen.add(canon)
            found.append(canon)
    return found


if __name__ == "__main__":
    lookup, ambiguous = load_vocab()
    matcher = build_matcher(lookup, ambiguous)
    print("Short items:")
    for raw in ["JS", " py ", "Postgres", "Kubernetes"]:
        print(f"  {raw!r:<14} -> {lookup.get(clean_key(raw), '(not in dictionary)')}")
    print("\nSentences:")
    for s in ["Built REST APIs in Flask", "Go to market strategy and the rest of the team"]:
        print(f"  {s!r}\n    -> {find_terms_in_sentence(s, matcher, lookup)}")