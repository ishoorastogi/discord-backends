"""Normalized resume JSON -> one unit-length vector per section (MiniLM)."""
import re
import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"


class EmptyResumeError(Exception):
    """Resume has no usable text at all."""


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def dedupe(items):
    seen, out = set(), []
    for i in items:
        if i and i.lower() not in seen:
            seen.add(i.lower())
            out.append(i)
    return out


def build_section_texts(resume):
    """Normalized dict -> {section: [texts]}. Empty sections are dropped (never a zero vector)."""
    exp = resume.get("experience") or []
    proj = resume.get("projects") or []

    # skills section = top-level skills + skills found inside each job/project
    all_skills = dedupe(list(resume.get("skills") or [])
                        + [s for e in exp + proj for s in (e.get("skills") or [])])
    skills_text = "Skills: " + ", ".join(all_skills) if all_skills else ""

    titles = [clean(e.get("title")) for e in exp if clean(e.get("title"))]
    titles_text = "; ".join(titles)

    def entry_text(label, entry):
        parts = [clean(label)]
        if entry.get("skills"):
            parts.append("Skills: " + ", ".join(entry["skills"]))
        return ". ".join(p for p in parts if p)

    experience_texts = [t for t in (entry_text(e.get("title"), e) for e in exp) if t]
    project_texts = [t for t in (entry_text(p.get("name"), p) for p in proj) if t]

    education_texts = []
    for ed in resume.get("education") or []:
        d, f = clean(ed.get("degree")), clean(ed.get("field"))
        text = f"{d} in {f}" if d and f else (d or f)
        if text:
            education_texts.append(text)

    # overall: most important first, because models cut off the END of long text
    overall = " ".join(t for t in [skills_text, titles_text, " ".join(experience_texts),
                                   " ".join(project_texts), " ".join(education_texts)] if t)

    sections = {"skills": [skills_text], "titles": [titles_text], "experience": experience_texts,
                "projects": project_texts, "education": education_texts, "overall": [overall]}
    return {k: [t for t in v if t] for k, v in sections.items() if any(v)}


_model = None   # loaded once, reused


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def to_unit_length(vec):
    """Scale a vector to length 1, so cosine similarity == dot product."""
    return (vec / np.linalg.norm(vec)).astype(np.float32)


def embed_texts(texts):
    """List of strings -> one unit-length vector per string (one batch call)."""
    return np.asarray(get_model().encode(texts, normalize_embeddings=True), dtype=np.float32)


def vectorize_resume(resume):
    """Normalized resume dict -> {section: 384-number unit vector}."""
    section_texts = build_section_texts(resume)
    if not section_texts:
        raise EmptyResumeError("Resume has no usable text.")
    result = {}
    for name, texts in section_texts.items():
        vecs = embed_texts(texts)
        # several entries (e.g. 3 jobs) -> average into ONE vector, then re-normalize
        result[name] = vecs[0] if len(vecs) == 1 else to_unit_length(vecs.mean(axis=0))
    return result