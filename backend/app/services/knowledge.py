from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from app.core.models import KnowledgeCitation, KnowledgeSource


class KnowledgeService:
    """Transparent offline retrieval over versioned Markdown knowledge documents."""

    TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}")

    def __init__(self, docs_dir: Path):
        self.docs_dir = docs_dir
        self._manifest = self._load_manifest()
        self._sections = self._load_sections()

    def _load_manifest(self) -> dict[str, dict[str, str]]:
        path = self.docs_dir.parent / "sources.json"
        if not path.exists():
            return {}
        return {item["document_id"]: item for item in json.loads(path.read_text(encoding="utf-8"))}

    def _load_sections(self) -> list[dict[str, str]]:
        sections: list[dict[str, str]] = []
        for path in sorted(self.docs_dir.glob("*.md")):
            current_heading = "概述"
            buffer: list[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("## "):
                    if buffer:
                        sections.append(self._record(path, current_heading, buffer))
                    current_heading = line[3:].strip()
                    buffer = []
                elif not line.startswith("# ") and line.strip():
                    buffer.append(line.strip())
            if buffer:
                sections.append(self._record(path, current_heading, buffer))
        return sections

    @staticmethod
    def _record(path: Path, heading: str, lines: list[str]) -> dict[str, str]:
        content = " ".join(lines)
        return {"document_id": path.stem, "section": heading, "content": content}

    @staticmethod
    def _tokens(text: str) -> list[str]:
        lowered = text.lower()
        ascii_tokens = re.findall(r"[a-z_][a-z0-9_]+", lowered)
        chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
        chinese = []
        for run in chinese_runs:
            chinese.extend(run[index:index + 2] for index in range(max(1, len(run) - 1)))
        return ascii_tokens + chinese

    def search(self, query: str, limit: int = 5) -> list[KnowledgeCitation]:
        tokens = self._tokens(query)
        document_frequencies = Counter()
        section_tokens = []
        for section in self._sections:
            counts = Counter(self._tokens(f"{section['section']} {section['content']}"))
            section_tokens.append(counts)
            document_frequencies.update(counts.keys())
        scored: list[tuple[float, dict[str, str]]] = []
        n = max(1, len(self._sections))
        for section, counts in zip(self._sections, section_tokens):
            length = max(1, sum(counts.values()))
            score = 0.0
            for token in tokens:
                tf = counts[token]
                if tf:
                    idf = math.log(1 + (n - document_frequencies[token] + 0.5) / (document_frequencies[token] + 0.5))
                    score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * length / 180))
            haystack = f"{section['section']} {section['content']}".lower()
            for marker in ("流失", "客单价", "618", "连续", "sql", "文案", "合规", "触达", "数据库", "字段"):
                if marker in query.lower() and marker in haystack:
                    score += 4
            if score:
                scored.append((score, section))
        if not scored:
            scored = [(1, section) for section in self._sections[:limit]]
        scored.sort(key=lambda item: (-item[0], item[1]["document_id"], item[1]["section"]))
        return [
            KnowledgeCitation(
                document_id=section["document_id"],
                section=section["section"],
                summary=section["content"][:220],
                source_id=self._manifest.get(section["document_id"], {}).get("source_id", section["document_id"]),
                publisher=self._manifest.get(section["document_id"], {}).get("publisher", "项目内部"),
                url=self._manifest.get(section["document_id"], {}).get("url"),
                trust_level=self._manifest.get(section["document_id"], {}).get("trust_level", "internal"),
                retrieval_score=round(score, 4),
            )
            for score, section in scored[:limit]
        ]

    @property
    def sources(self) -> list[KnowledgeSource]:
        result = []
        for document_id, item in sorted(self._manifest.items()):
            path = self.docs_dir / f"{document_id}.md"
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"
            result.append(KnowledgeSource(
                source_id=item.get("source_id", document_id), title=item["title"],
                publisher=item.get("publisher", "项目内部"), url=item.get("url"),
                published_at=item.get("published_at"), retrieved_at=item["retrieved_at"],
                trust_level=item.get("trust_level", "internal"), content_hash=content_hash,
            ))
        return result

    @property
    def document_count(self) -> int:
        return len({section["document_id"] for section in self._sections})
