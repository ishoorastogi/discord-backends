"""
SKILL NORMALIZATION = turn messy skill text into ONE shared vocabulary.

Two layers, in this order:

  LAYER 1  dictionary (skills.py + skills_vocab.csv)
           Exact, trusted, instant. "JS" -> "javascript".

  LAYER 2  ConTeXT + ESCO (esco_skills.py)
           Only for what layer 1 did not recognise.
           1) every ESCO skill name was turned into a vector by ConTeXT (done once, cached)
           2) the leftover resume text is turned into a vector by the same model
           3) cosine similarity picks the closest ESCO skill(s); weak matches are dropped
           4) we keep ONLY THE NAME of the match. The resume vectors are discarded right here.

  Whatever neither layer recognises is kept AS WRITTEN and marked "unmatched",
  so nothing silently disappears and you can see what to add to the dictionary.

Two entry points, because skills show up in two shapes:
  normalize_items(["JS", "Kubernetes"])        short items listed as skills
  find_in_sentences(["Built REST APIs ..."])   skills hiding inside sentences
"""
from collections import Counter, namedtuple

from skills import build_matcher, clean_key, find_terms_in_sentence, load_vocab
# source is one of: "dictionary", "esco", "unmatched"
NormalizedSkill = namedtuple("NormalizedSkill", ["original", "name", "source", "score", "uri"])


class SkillNormalizer:
    """
    lookup / ambiguous : the dictionary (loaded from skills_vocab.csv if not given)
    extractor          : an EscoSkillExtractor, or None to run layer 1 only (no models needed)
    sentence_top_k     : how many ESCO matches one SENTENCE may keep (a sentence can mention several skills)
    """

    def __init__(self, lookup=None, ambiguous=None, extractor=None, sentence_top_k=1):
        if lookup is None:
            lookup, ambiguous = load_vocab()
        self.lookup = lookup
        self.ambiguous = ambiguous or set()
        self.matcher = build_matcher(self.lookup, self.ambiguous)
        self.extractor = extractor
        self.sentence_top_k = sentence_top_k
        self.log = []                                   # every decision, for report()

    # ------------------------------------------------------------ short items
    def normalize_items(self, items):
        """
        ["JS", "Kube", "Cooking"] -> one NormalizedSkill per non-empty item, same order.
        A listed item is ONE skill, so layer 2 keeps only its single best match.
        """
        items = [str(i).strip() for i in items if str(i).strip()]
        results = [None] * len(items)

        # Layer 1: dictionary
        leftovers = []
        for i, item in enumerate(items):
            canon = self.lookup.get(clean_key(item))
            if canon:
                results[i] = NormalizedSkill(item, canon, "dictionary", 1.0, None)
            else:
                leftovers.append(i)

        # Layer 2: ConTeXT + ESCO, ONE batch for everything layer 1 missed
        if leftovers and self.extractor is not None:
            matches = self.extractor.extract([items[i] for i in leftovers], top_k=1)
            for i, found in zip(leftovers, matches):
                if found:
                    m = found[0]
                    results[i] = NormalizedSkill(items[i], m.label, "esco", m.score, m.uri)

        # Nothing recognised it: keep as written (lowercased), flagged
        for i, item in enumerate(items):
            if results[i] is None:
                results[i] = NormalizedSkill(item, item.lower(), "unmatched", 0.0, None)

        self.log.extend(results)
        return results

    # ------------------------------------------------------------ sentences
    def find_in_sentences(self, sentences):
        """
        ["Built REST APIs in Flask"] -> a flat list of NormalizedSkill.
        Layer 1 searches each sentence for dictionary terms. Layer 2 then asks ConTeXT
        which ESCO skills the sentence is about. Sentences with no skill produce nothing.
        """
        sentences = [s.strip() for s in sentences if s and s.strip()]
        results = []

        for s in sentences:                                         # Layer 1
            for canon in find_terms_in_sentence(s, self.matcher, self.lookup):
                results.append(NormalizedSkill(s, canon, "dictionary", 1.0, None))

        if sentences and self.extractor is not None:                # Layer 2
            for s, found in zip(sentences, self.extractor.extract(sentences, top_k=self.sentence_top_k)):
                for m in found:
                    results.append(NormalizedSkill(s, m.label, "esco", m.score, m.uri))

        self.log.extend(results)
        return results

    # ------------------------------------------------------------ helpers
    @staticmethod
    def names(results):
        """Just the skill names, no duplicates (ignoring upper/lower case), in order."""
        seen, out = set(), []
        for r in results:
            if r.name.lower() not in seen:
                seen.add(r.name.lower())
                out.append(r.name)
        return out

    def report(self):
        """Plain-English summary. The 'unmatched' list is your to-do list for the dictionary."""
        if not self.log:
            return "Nothing normalized yet."
        counts = Counter(r.source for r in self.log)
        lines = [f"  dictionary: {counts['dictionary']}   esco: {counts['esco']}   unmatched: {counts['unmatched']}"]
        for r in self.log:
            if r.source == "esco":
                lines.append(f"  ESCO       {r.original[:45]!r:<49} -> {r.name} ({r.score})")
        for name in sorted({r.name for r in self.log if r.source == "unmatched"}):
            lines.append(f"  UNMATCHED  {name!r}   (add to skills_vocab.csv?)")
        return "\n".join(lines)


def dictionary_names_missing_from_esco(lookup, esco_skills):
    """
    The dictionary's generic names and ESCO's official names are two naming systems.
    This lists dictionary names that do not appear (ignoring case) among ESCO's names.
    ESCO often adds a qualifier, e.g. 'Python (computer programming)', so some of these
    are just spelling differences. Read the list and decide which names to align.
    """
    esco = {s["label"].lower() for s in esco_skills}
    return sorted({c for c in set(lookup.values()) if c not in esco})


if __name__ == "__main__":
    import normalization.esco_skills as esco_skills

    extractor = esco_skills.EscoSkillExtractor() if esco_skills.ESCO_CSV_PATH else None
    print("Layer 1 (dictionary): ON")
    print("Layer 2 (ConTeXT + ESCO):", "ON" if extractor else "OFF (set ESCO_CSV_PATH in esco_skills.py)", "\n")

    norm = SkillNormalizer(extractor=extractor)
    print("SHORT ITEMS")
    for r in norm.normalize_items(["JS", "Postgres", "Tensor Flow", "Kubernetes", "pastry"]):
        print(f"  {r.original!r:<14} -> {r.name!r:<32} via {r.source} ({r.score})")

    print("\nSENTENCES")
    for s in ["Built REST APIs in Flask serving 10k requests per day",
              "Go to market strategy and the rest of the team"]:
        found = norm.find_in_sentences([s])
        print(f"  {s!r}\n    -> {[(r.name, r.source) for r in found] or 'nothing found'}")

    print("\nREPORT")
    print(norm.report())

    if extractor:
        print("\nDictionary names not found verbatim in ESCO:")
        print(" ", dictionary_names_missing_from_esco(norm.lookup, extractor.skills))