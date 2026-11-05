"""Resume JSON -> same shape, but every skill is an official ESCO name. Unrecognised words are dropped."""
import re
import esco_skills
from skill_normalizer import SkillNormalizer


def clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    text = re.sub(r"[•●▪◦*#`]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def dedupe(items):
    seen, out = set(), []
    for i in items:
        if i and i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out


def flatten_skills(skills):
    if isinstance(skills, dict):                      # {"languages": [...], "libraries": [...]}
        return [x for group in skills.values() for x in (group or [])]
    return list(skills or [])


def make_normalizer():
    extractor = esco_skills.EscoSkillExtractor() if esco_skills.ESCO_CSV_PATH else None
    return SkillNormalizer(extractor=extractor)


def _to_esco_names(dictionary_names, extractor):
    """
    Swap 'javascript' -> 'JavaScript' ONLY when the names match exactly (ignoring a trailing
    '(...)'). No AI here: AI turned 'react' into 'react to events in time-critical environments'.
    Names ESCO doesn't have (flask, react) keep their dictionary name.
    """
    names = list(dict.fromkeys(dictionary_names))
    if extractor is None:
        return {n: n for n in names}
    if not hasattr(extractor, "_by_name"):                      # build the lookup once
        by_name = {}
        for s in extractor.skills:
            base = re.sub(r"\s*\(.*\)\s*$", "", s["label"]).lower()   # 'Python (computer programming)' -> 'python'
            by_name.setdefault(base, s["label"])
        for s in extractor.skills:
            by_name[s["label"].lower()] = s["label"]            # exact full-label matches win
        extractor._by_name = by_name
    return {n: extractor._by_name.get(n.lower(), n) for n in names}

def skills_from(normalizer, items, sentences):
    """Short skill items + full sentences -> list of ESCO skill names (unmatched words dropped)."""
    found = normalizer.normalize_items([clean(i) for i in items])
    found += normalizer.find_in_sentences([clean(s) for s in sentences])
    kept = [r for r in found if r.source != "unmatched"]          # <- this is the filler-word cleanup
    to_esco = _to_esco_names([r.name for r in kept if r.source == "dictionary"], normalizer.extractor)
    return dedupe([to_esco[r.name] if r.source == "dictionary" else r.name for r in kept])


def normalize_resume(resume, normalizer):
    out = {}
    for key in ("major", "grad_year"):                            # kept for the later hard filter
        if resume.get(key) is not None:
            out[key] = resume[key]

    out["skills"] = skills_from(normalizer, flatten_skills(resume.get("skills")), [])

    out["education"] = [
        {"degree": clean(e.get("degree")), "field": clean(e.get("field"))}
        for e in resume.get("education") or [] if clean(e.get("degree")) or clean(e.get("field"))
    ]

    out["experience"] = [
        {"title": clean(e.get("title")),
         "skills": skills_from(normalizer, e.get("technologies") or e.get("skills") or [],
                               e.get("bullets") or [])}
        for e in resume.get("experience") or []
    ]

    out["projects"] = [
        {"name": clean(p.get("name")),
         "skills": skills_from(normalizer, p.get("technologies") or p.get("skills") or [],
                               [p.get("description")] + (p.get("bullets") or []))}
        for p in resume.get("projects") or []
    ]
    return out