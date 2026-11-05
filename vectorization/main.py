"""Run:  python main.py                       (uses sample_input/backend1.normalized.json)
        python main.py some_file.normalized.json"""
import json
import sys
from pathlib import Path

import numpy as np

from resume_vectorizer import build_section_texts, vectorize_resume

HERE = Path(__file__).parent


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "sample_input" / "backend1.normalized.json"
    resume = json.loads(src.read_text(encoding="utf-8-sig"))

    print("TEXT sent to MiniLM:")
    for section, texts in build_section_texts(resume).items():
        print(f"  [{section}] {texts}")

    vecs = vectorize_resume(resume)
    print("\nVECTORS (first 4 numbers of each):")
    for section, v in vecs.items():
        print(f"  {section:<11} length={len(v)} norm={np.linalg.norm(v):.3f} {np.round(v[:4], 3)}")

    out = HERE / "output" / f"{src.stem.replace('.normalized', '')}.vectors.npz"
    out.parent.mkdir(exist_ok=True)
    np.savez(out, **vecs)                      # one named array per section
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()