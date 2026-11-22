"""
Answer support: what the server adds around the model so answers are more exact.

Three things, each switchable by an environment variable and each measured on the eval
(see notebooks/kinnow_kaggle_runbook.ipynb, section 7):

  1. Lookup    The most relevant reviewed Q&A notes are shown to the model in front of the question
               (hybrid word + embedding matching by default).
  2. Calculators  For plain calculation questions (gratuity, PF, ESI, new-regime tax, interest) the server
               works out the figure in code and gives it to the model, which then only explains it.
  3. Sources   After the answer, a line such as "Sources: Section 16(2)(aa), Rule 37" taken from the notes
               that were shown, so exact citations are present.

Nothing here can stop a request: every step falls back to the plain question or the plain answer on any
error, and the whole feature is optional (the server runs without the knowledge file).

Environment variables
    KINNOW_LOOKUP      hybrid (default) | bm25 | off      how notes are found
    KINNOW_KB_PATH     knowledge file (default data/knowledge/kb.jsonl, built by scripts/build_kb.py)
    KINNOW_LOOKUP_K    notes per question (default 4; 6 scored lower in testing)
    KINNOW_CALC        1 (default) | 0                    calculators
    KINNOW_SOURCES     1 (default) | 0                    "Sources:" line
"""

import logging
import os
from pathlib import Path

from .calculators import computed_hint
from .retrieval import DEFAULT_KB_PATH, load_retriever, sources_line, with_notes

log = logging.getLogger("kinnow.answer_support")

# A model reply that is a refusal gets no Sources line (the notes were not about the question)
_REFUSAL_MARKERS = ("only help with", "i'm kinnow's erp assistant", "cannot change my role", "outside my scope")


def _flag(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


class AnswerSupport:
    def __init__(self, retriever=None, k: int = 4, calc: bool = True, sources: bool = True):
        self.retriever = retriever
        self.k = k
        self.calc = calc
        self.sources = sources

    def prepare(self, query: str) -> tuple[str, list[dict]]:
        """(the user turn to send to the model, the notes that were found). Plain query on any failure."""
        hits: list[dict] = []
        computed = None
        try:
            if self.retriever is not None:
                hits = self.retriever.search(query, k=self.k)
        except Exception as e:  # never fail a chat because the lookup failed
            log.warning("lookup failed: %s", e)
        try:
            if self.calc:
                computed = computed_hint(query)
        except Exception as e:
            log.warning("calculator failed: %s", e)
        try:
            return with_notes(query, hits, computed), hits
        except Exception as e:
            log.warning("could not build the prompt with notes: %s", e)
            return query, []

    def finish(self, text: str, hits: list[dict]) -> str:
        """The answer with a Sources line added when the notes cite something. Unchanged otherwise."""
        if not self.sources or not hits:
            return text
        low = text.lower()
        if any(m in low for m in _REFUSAL_MARKERS):
            return text
        try:
            line = sources_line(hits)
        except Exception as e:
            log.warning("sources line failed: %s", e)
            return text
        if not line or line in text:
            return text
        return text.rstrip() + "\n" + line

    @classmethod
    def from_env(cls, env=None):
        """Build from the environment. Returns None when every part is switched off or unavailable."""
        env = os.environ if env is None else env
        mode = (env.get("KINNOW_LOOKUP") or "hybrid").strip().lower()
        calc = _flag(env.get("KINNOW_CALC"), True)
        sources = _flag(env.get("KINNOW_SOURCES"), True)
        k = int(env.get("KINNOW_LOOKUP_K") or 4)
        retriever = None
        if mode != "off":
            path = Path(env.get("KINNOW_KB_PATH") or DEFAULT_KB_PATH)
            if not path.exists():
                log.warning("knowledge file %s not found: running without the lookup", path)
            else:
                try:
                    retriever = load_retriever(path, hybrid=(mode == "hybrid"))
                except Exception as e:
                    log.warning("hybrid lookup unavailable (%s): falling back to word matching", e)
                    try:
                        retriever = load_retriever(path)
                    except Exception as e2:
                        log.warning("lookup unavailable: %s", e2)
        if retriever is None and not calc:
            return None
        return cls(retriever=retriever, k=k, calc=calc, sources=sources and retriever is not None)

    def describe(self) -> str:
        kind = type(self.retriever).__name__ if self.retriever is not None else "none"
        return f"lookup={kind} (k={self.k}) calculators={'on' if self.calc else 'off'} sources={'on' if self.sources else 'off'}"
