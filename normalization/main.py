"""Run:  python main.py                       (uses sample_input/backend1.json)
        python main.py some_resume.json"""
import json
import sys
from pathlib import Path

from normalize_resume import make_normalizer, normalize_resume

HERE = Path(__file__).parent


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "sample_input" / "backend1.json"
    resume = json.loads(src.read_text(encoding="utf-8-sig"))

    normalizer = make_normalizer()
    print("ESCO layer:", "ON" if normalizer.extractor else "OFF (set ESCO_CSV_PATH in esco_skills.py)")
    result = normalize_resume(resume, normalizer)

    out = HERE / "output" / f"{src.stem}.normalized.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\nINPUT skills :", resume.get("skills"))
    print("OUTPUT       :", json.dumps(result, indent=2))
    print(f"\nSaved to {out}\n\nREPORT\n{normalizer.report()}")


if __name__ == "__main__":
    main()