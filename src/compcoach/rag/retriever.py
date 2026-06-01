import json

import chromadb
from chromadb.config import Settings

from compcoach.config import CHROMA_PERSIST_DIR, COURSES_COLLECTION


class CourseRetriever:
    def __init__(self) -> None:
        CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_PERSIST_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_collection(COURSES_COLLECTION)

    def search(
        self,
        query: str,
        n_results: int = 4,
        *,
        domain: str | None = None,
        area: str | None = None,
        dimension: str | None = None,
    ) -> list[dict]:
        where: dict | None = None
        filters = []
        if domain:
            filters.append({"domain": domain})
        if area:
            filters.append({"area": area})
        if dimension:
            filters.append({"dimension": dimension})
        if len(filters) == 1:
            where = filters[0]
        elif len(filters) > 1:
            where = {"$and": filters}

        result = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict] = []
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        seen_slugs: set[str] = set()
        for doc, meta, dist in zip(docs, metas, dists):
            slug = meta.get("slug", "")
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            hits.append(
                {
                    "slug": slug,
                    "title": meta.get("title", ""),
                    "url": meta.get("url", ""),
                    "domain": meta.get("domain", ""),
                    "area": meta.get("area", ""),
                    "dimension": meta.get("dimension", ""),
                    "excerpt": doc,
                    "distance": dist,
                }
            )
        return hits

    def format_for_prompt(self, hits: list[dict]) -> str:
        if not hits:
            return "No matching courses found."
        lines = []
        for i, h in enumerate(hits, 1):
            lines.append(
                f"{i}. **{h['title']}** ({h['domain']}/{h['area']}/{h['dimension']})\n"
                f"   URL: {h['url']}\n"
                f"   Slug: {h['slug']}\n"
                f"   Relevant excerpt: {(h['excerpt'] or '')[:400]}"
            )
        return "\n".join(lines)
