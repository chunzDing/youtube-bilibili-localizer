from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
TITLE_PREFIX_NOISE_RE = re.compile(
    r"^[\[\(【]\s*(中文字幕|中英字幕|中字|中文翻译|中文配音|Chinese subtitles?)\s*[\]\)】]\s*",
    flags=re.IGNORECASE,
)
ASCII_WORD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\s.+:/_-]*[A-Za-z0-9]$")
MULTISPACE_RE = re.compile(r"\s+")
PLACEHOLDER_RE = re.compile(r"__YBL_TERM_(\d+)__")
ASCII_PUNCT_TRANSLATIONS = str.maketrans(
    {
        ",": "，",
        ".": "。",
        "?": "？",
        "!": "！",
        ":": "：",
        ";": "；",
    }
)


@dataclass(frozen=True)
class GlossaryTerm:
    source: str
    target: str
    protect: bool = False
    aliases: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GlossaryTerm":
        source = str(payload.get("source") or "").strip()
        target = str(payload.get("target") or "").strip()
        if not source or not target:
            raise ValueError("Glossary terms must include non-empty source and target fields")
        aliases = tuple(str(item).strip() for item in payload.get("aliases", []) if str(item).strip())
        protect = bool(payload.get("protect", False))
        return cls(source=source, target=target, protect=protect, aliases=aliases)

    def iter_source_forms(self) -> tuple[str, ...]:
        values = [self.source]
        values.extend(self.aliases)
        deduped: list[str] = []
        seen: set[str] = set()
        for item in values:
            lowered = item.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(item)
        return tuple(deduped)


@dataclass(frozen=True)
class LoadedGlossary:
    terms: tuple[GlossaryTerm, ...]
    source_path: str = ""

    def protect_text(self, text: str) -> tuple[str, dict[str, str]]:
        if not text:
            return "", {}

        protected = text
        replacements: dict[str, str] = {}
        counter = 0
        for term in sorted(self.terms, key=lambda item: len(item.source), reverse=True):
            if not term.protect:
                continue

            for candidate in term.iter_source_forms():
                pattern = make_term_pattern(candidate)

                def replace_match(_match: re.Match[str]) -> str:
                    nonlocal counter
                    placeholder = f"__YBL_TERM_{counter}__"
                    counter += 1
                    replacements[placeholder] = term.target
                    return placeholder

                protected = pattern.sub(replace_match, protected)
        return protected, replacements

    def normalize_translation(self, text: str, placeholders: dict[str, str] | None = None) -> str:
        normalized = text or ""
        if placeholders:
            for placeholder, target in placeholders.items():
                normalized = normalized.replace(placeholder, target)

        for match in PLACEHOLDER_RE.findall(normalized):
            normalized = normalized.replace(f"__YBL_TERM_{match}__", "")

        for term in sorted(self.terms, key=lambda item: len(item.source), reverse=True):
            replacement_values = list(term.iter_source_forms())
            if term.target.casefold() not in {value.casefold() for value in replacement_values}:
                replacement_values.append(term.target)
            for candidate in replacement_values:
                normalized = make_term_pattern(candidate).sub(term.target, normalized)

        return clean_chinese_text(normalized)


def normalize_language_code(language: str | None) -> str | None:
    if not language:
        return None
    return language.strip().lower().replace("_", "-").split("-", 1)[0] or None


def default_glossary_path(skill_root: Path) -> Path:
    return skill_root / "references" / "glossary.zh.json"


def load_glossary(path: Path | None) -> LoadedGlossary:
    if path is None:
        return LoadedGlossary(terms=())
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_terms = payload.get("terms", payload if isinstance(payload, list) else [])
    if not isinstance(raw_terms, list):
        raise ValueError("Glossary file must contain a 'terms' list or a top-level list")
    terms = tuple(GlossaryTerm.from_dict(item) for item in raw_terms)
    return LoadedGlossary(terms=terms, source_path=str(path))


def normalize_source_text(text: str) -> str:
    return MULTISPACE_RE.sub(" ", text or "").strip()


def clean_title_text(title: str) -> str:
    normalized = TITLE_PREFIX_NOISE_RE.sub("", title or "")
    normalized = clean_chinese_text(normalized)
    return normalized or "视频"


def clean_chinese_text(text: str) -> str:
    normalized = MULTISPACE_RE.sub(" ", text or "").strip()
    if not normalized:
        return ""

    normalized = re.sub(r"\s+([，。！？：；、,.!?:;])", r"\1", normalized)
    normalized = re.sub(r"([（【“‘(])\s+", r"\1", normalized)
    normalized = re.sub(r"\s+([）】”’)])", r"\1", normalized)
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", normalized)
    normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[A-Za-z0-9])", " ", normalized)
    normalized = re.sub(r"(?<=[A-Za-z0-9])\s+(?=[\u4e00-\u9fff])", " ", normalized)

    if CHINESE_CHAR_RE.search(normalized):
        normalized = normalized.translate(ASCII_PUNCT_TRANSLATIONS)
        normalized = re.sub(r"(?<=[\u4e00-\u9fff])\s*'\s*(?=[A-Za-z])", "'", normalized)

    normalized = normalized.replace("AI平台", "AI 平台")
    normalized = normalized.replace("AI代理", "AI 智能体")
    normalized = normalized.replace("Ai ", "AI ")
    normalized = normalized.replace("Sas", "SaaS")

    return MULTISPACE_RE.sub(" ", normalized).strip()


def make_term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if ASCII_WORD_RE.fullmatch(term):
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", flags=re.IGNORECASE)
    return re.compile(escaped, flags=re.IGNORECASE)
