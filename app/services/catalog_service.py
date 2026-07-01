from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.utils.text import normalize_text, tokenize


TECHNICAL_HINTS = {
    "ai",
    "api",
    "architecture",
    "backend",
    "coding",
    "data",
    "database",
    "developer",
    "development",
    "designer",
    "engineer",
    "engineering",
    "java",
    "machine",
    "ml",
    "model",
    "programming",
    "python",
    "software",
    "system",
    "sql",
    "technical",
}

TECHNICAL_ROLE_HINTS = {
    "ai",
    "developer",
    "designer",
    "engineer",
    "engineering",
    "machine",
    "ml",
    "software",
    "system",
}

PERSONALITY_HINTS = {
    "behavior",
    "collaboration",
    "communication",
    "personality",
    "stakeholder",
    "team",
    "teamwork",
    "workstyle",
}

COGNITIVE_HINTS = {
    "ability",
    "analysis",
    "analytical",
    "aptitude",
    "cognitive",
    "critical",
    "numerical",
    "problem",
    "reasoning",
}

SENIORITY_GROUPS = {
    "entry": {"entry", "junior", "graduate", "fresher", "intern"},
    "mid": {"mid", "intermediate"},
    "senior": {"senior", "lead", "manager", "director", "principal"},
}


@dataclass(frozen=True)
class CatalogItem:
    name: str
    url: str
    test_type: str
    description: str = ""
    categories: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    job_levels: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    @property
    def search_blob(self) -> str:
        parts = [
            self.name,
            self.description,
            " ".join(self.categories),
            " ".join(self.skills),
            " ".join(self.job_levels),
            self.test_type,
        ]
        return normalize_text(" ".join(part for part in parts if part))


class CatalogService:
    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = Path(catalog_path)
        self._items = self._load_items()

    def _load_items(self) -> list[CatalogItem]:
        if not self.catalog_path.exists():
            return []

        raw_items = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        items: list[CatalogItem] = []
        for raw_item in raw_items:
            items.append(
                CatalogItem(
                    name=raw_item["name"],
                    url=raw_item["url"],
                    test_type=raw_item["test_type"],
                    description=raw_item.get("description", ""),
                    categories=raw_item.get("categories", []),
                    skills=raw_item.get("skills", []),
                    job_levels=raw_item.get("job_levels", []),
                    aliases=raw_item.get("aliases", []),
                )
            )
        return items

    def all_items(self) -> list[CatalogItem]:
        return list(self._items)

    def find_named_items(self, text: str) -> list[CatalogItem]:
        normalized = normalize_text(text)
        query_tokens = set(tokenize(text))
        matches = []
        for item in self._items:
            candidates = {normalize_text(item.name), *(normalize_text(alias) for alias in item.aliases)}
            alias_tokens = set()
            for candidate in candidates:
                alias_tokens.update(tokenize(candidate))

            has_full_match = any(candidate and candidate in normalized for candidate in candidates)
            has_token_match = bool(query_tokens & alias_tokens)
            if has_full_match or has_token_match:
                matches.append(item)
        return matches

    def search(self, query: str, limit: int = 5) -> list[CatalogItem]:
        query_tokens = set(tokenize(query))
        profile = self._build_query_profile(query_tokens)
        scored_items: list[tuple[float, CatalogItem]] = []

        for item in self._items:
            score = self._score_item(item=item, query=query, query_tokens=query_tokens, profile=profile)
            if score > 0:
                scored_items.append((score, item))

        scored_items.sort(key=lambda pair: (-pair[0], pair[1].name))
        if not scored_items:
            return []

        top_score = scored_items[0][0]
        minimum_score = max(3.0, top_score - 7.0)
        filtered = [(score, item) for score, item in scored_items if score >= minimum_score]
        diversified = self._diversify_results(filtered=filtered, profile=profile, limit=limit)
        return diversified[:limit]

    def _score_item(
        self,
        item: CatalogItem,
        query: str,
        query_tokens: set[str],
        profile: dict[str, object],
    ) -> float:
        item_tokens = set(tokenize(item.search_blob))
        name_tokens = set(tokenize(item.name))
        category_tokens = set(tokenize(" ".join(item.categories)))
        skill_tokens = set(tokenize(" ".join(item.skills)))
        job_level_tokens = set(tokenize(" ".join(item.job_levels)))

        score = 0.0
        score += 3.0 * len(query_tokens & skill_tokens)
        score += 2.5 * len(query_tokens & name_tokens)
        score += 2.0 * len(query_tokens & category_tokens)
        score += 1.5 * len(query_tokens & job_level_tokens)
        score += 1.0 * len(query_tokens & item_tokens)

        if normalize_text(item.name) in normalize_text(query):
            score += 4.0

        preferred_seniority = profile["preferred_seniority"]
        if isinstance(preferred_seniority, str):
            score += self._seniority_score(preferred_seniority, job_level_tokens)

        query_is_technical = bool(profile["technical"])
        query_is_personality = bool(profile["personality"])
        query_is_cognitive = bool(profile["cognitive"])
        query_has_technical_role = bool(profile["technical_role"])

        item_is_technical = self._item_matches_domain(item, TECHNICAL_HINTS)
        item_is_personality = self._item_matches_domain(item, PERSONALITY_HINTS) or item.test_type == "P"
        item_is_cognitive = self._item_matches_domain(item, COGNITIVE_HINTS) or item.test_type == "C"

        if query_is_technical:
            score += 2.5 if item_is_technical else -1.0
        if query_has_technical_role:
            if item.test_type == "K":
                score += 2.5
            elif item.test_type == "C":
                score += 1.0
        if query_is_personality:
            score += 1.5 if item_is_personality else -0.5
        if query_is_cognitive:
            score += 2.0 if item_is_cognitive else -0.5

        return score

    def _diversify_results(
        self,
        filtered: list[tuple[float, CatalogItem]],
        profile: dict[str, object],
        limit: int,
    ) -> list[CatalogItem]:
        selected: list[CatalogItem] = []
        selected_names: set[str] = set()

        if bool(profile["technical"]):
            self._append_best_match(
                selected,
                selected_names,
                filtered,
                lambda item: self._item_matches_domain(item, TECHNICAL_HINTS),
            )
        if bool(profile["personality"]):
            self._append_best_match(
                selected,
                selected_names,
                filtered,
                lambda item: self._item_matches_domain(item, PERSONALITY_HINTS) or item.test_type == "P",
            )
        if bool(profile["cognitive"]):
            self._append_best_match(
                selected,
                selected_names,
                filtered,
                lambda item: self._item_matches_domain(item, COGNITIVE_HINTS) or item.test_type == "C",
            )

        for _, item in filtered:
            if item.name not in selected_names:
                selected.append(item)
                selected_names.add(item.name)
            if len(selected) >= limit:
                break

        return selected

    def _append_best_match(
        self,
        selected: list[CatalogItem],
        selected_names: set[str],
        filtered: list[tuple[float, CatalogItem]],
        predicate,
    ) -> None:
        for _, item in filtered:
            if predicate(item) and item.name not in selected_names:
                selected.append(item)
                selected_names.add(item.name)
                return

    def _build_query_profile(self, query_tokens: set[str]) -> dict[str, object]:
        preferred_seniority = None
        for label, aliases in SENIORITY_GROUPS.items():
            if query_tokens & aliases:
                preferred_seniority = label
                break

        return {
            "preferred_seniority": preferred_seniority,
            "technical": bool(query_tokens & TECHNICAL_HINTS),
            "technical_role": bool(query_tokens & TECHNICAL_ROLE_HINTS),
            "personality": bool(query_tokens & PERSONALITY_HINTS),
            "cognitive": bool(query_tokens & COGNITIVE_HINTS),
        }

    def _seniority_score(self, preferred_seniority: str, job_level_tokens: set[str]) -> float:
        preferred_aliases = SENIORITY_GROUPS[preferred_seniority]
        if job_level_tokens & preferred_aliases:
            return 3.0

        if preferred_seniority == "mid" and job_level_tokens & SENIORITY_GROUPS["entry"]:
            return -2.5
        if preferred_seniority == "senior" and job_level_tokens & (
            SENIORITY_GROUPS["entry"] | SENIORITY_GROUPS["mid"]
        ):
            return -3.0
        if preferred_seniority == "entry" and job_level_tokens & SENIORITY_GROUPS["senior"]:
            return -1.0
        return 0.0

    def _item_matches_domain(self, item: CatalogItem, hint_tokens: set[str]) -> bool:
        item_tokens = set(tokenize(item.search_blob))
        return bool(item_tokens & hint_tokens)
