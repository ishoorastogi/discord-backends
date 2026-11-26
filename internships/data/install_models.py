"""Cache the models required by the backend's configured resume pipeline."""

import argparse
import filecmp
from importlib import import_module
import json
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import NamedTemporaryFile

from internships.src import config


ESCO_FILENAME = "skills_en.csv"


def cache_model(model_id: str, load_model, *, offline: bool) -> bool:
    try:
        load_model(model_id, device="cpu", local_files_only=offline)
    except Exception as error:
        print(f"Could not load {model_id}: {error}", file=sys.stderr)
        print(f"Model download and instructions: https://huggingface.co/{model_id}", file=sys.stderr)
        return False
    print(f"Model ready: {model_id}", flush=True)
    return True


def replace_config(path: Path, contents: str) -> None:
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        shutil.copymode(path, temporary)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_esco_csv(path: Path, load_skills) -> Path:
    target = path.with_name(ESCO_FILENAME)
    source = path
    if not source.is_file():
        if target.is_file():
            source = target
        elif source == target:
            copies = [candidate for candidate in path.parent.glob("skills_en (*).csv") if candidate.is_file()]
            if len(copies) > 1:
                raise ValueError(f"Multiple ESCO downloads found in {path.parent}. Set ESCO_CSV to the one to use.")
            if copies:
                source = copies[0]

    if not load_skills(source):
        raise ValueError("the skills CSV is empty")
    if source != target:
        if target.exists():
            if not filecmp.cmp(source, target, shallow=False):
                raise FileExistsError(f"{target} already contains a different dataset")
        else:
            with source.open("rb") as original, NamedTemporaryFile(dir=target.parent) as staged:
                shutil.copyfileobj(original, staged)
                staged.flush()
                os.link(staged.name, target)
            print(f"Prepared ESCO skills file: {target}", flush=True)

    if target != path:
        config_path = Path(config.__file__).resolve().with_name("config.json")
        values = json.loads(config_path.read_text(encoding="utf-8"))
        values["ESCO_CSV"] = str(Path(values["ESCO_CSV"].strip()).with_name(ESCO_FILENAME))
        replace_config(config_path, json.dumps(values, indent=2, ensure_ascii=False) + "\n")
    return target


def enable_offline_defaults() -> None:
    if config.HF_HUB_OFFLINE and config.TRANSFORMERS_OFFLINE:
        return
    path = Path(config.__file__).resolve()
    source = path.read_text(encoding="utf-8")
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        assignment = rf"^({name}[ \t]*=[ \t]*)(?:True|False)(?=[ \t]*(?:#|$))"
        source, count = re.subn(assignment, r"\g<1>True", source, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"Expected one boolean assignment for {name} in {path}")
    replace_config(path, source)


def main(*, offline: bool) -> int:
    config.load_environment()
    config.configure_ml_environment(offline=offline)
    try:
        from sentence_transformers import SentenceTransformer
    except (ImportError, OSError) as error:
        print(f"Could not load Sentence Transformers: {error}", file=sys.stderr)
        print("PyTorch platform packages: https://pytorch.org/get-started/locally/", file=sys.stderr)
        return 1

    vectorizer = import_module("internships.int-res-shared.vectorization.resume_vectorizer")
    ready = cache_model(f"sentence-transformers/{vectorizer.MODEL_NAME}", SentenceTransformer, offline=offline)

    try:
        settings = config.load_settings()
    except ValueError as error:
        print(f"Check internships/src/config.json: {error}", file=sys.stderr)
        return 1

    if settings.esco_csv is not None:
        esco = import_module("internships.int-res-shared.normalization.esco_skills")
        if not cache_model(esco.CONTEXT_MODEL_NAME, SentenceTransformer, offline=offline):
            ready = False
        if offline:
            try:
                path = prepare_esco_csv(settings.esco_csv, esco.load_esco_skills)
                print(f"ESCO skills file ready: {path}", flush=True)
            except (OSError, ValueError) as error:
                print(f"Could not prepare the ESCO skills CSV at {settings.esco_csv}: {error}", file=sys.stderr)
                print("Get the English skills CSV from https://esco.ec.europa.eu/en/use-esco/download",
                      file=sys.stderr)
                print(f"Point ESCO_CSV in internships/src/config.json to {ESCO_FILENAME}.", file=sys.stderr)
                ready = False

    if offline and ready:
        try:
            enable_offline_defaults()
        except (OSError, ValueError) as error:
            print(f"Could not enable offline defaults in internships/src/config.py: {error}", file=sys.stderr)
            return 1
        print("Offline model setup verified. The backend will start in offline mode.", flush=True)

    return 0 if ready else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-offline", action="store_true", help="Verify cached models and ESCO data offline.")
    sys.exit(main(offline=parser.parse_args().verify_offline))
