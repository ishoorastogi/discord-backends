"""Lazy, process-wide resume normalization resources.

MiniLM retains its existing lazy cache in vectorization.resume_vectorizer.
Importing this module does not construct a normalizer or load either model.
"""
from functools import lru_cache

from shared.logs.log_config import get_logger

logger = get_logger("resume handler")


@lru_cache(maxsize=1)
def get_normalizer(esco_csv=None, esco_cache_dir=None):
    from normalization.normalize_resume import make_normalizer
    normalizer = make_normalizer(esco_csv, esco_cache_dir)
    if normalizer.extractor is None:
        logger.info("ESCO semantic layer disabled: set ESCO_CSV in internships/src/config.json")
    return normalizer
