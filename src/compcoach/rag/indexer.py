import json

import chromadb
from chromadb.config import Settings

from compcoach.config import (
    CHROMA_PERSIST_DIR,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COURSES_COLLECTION,
    COURSES_PATH,
)
from compcoach.rag.chunking import chunk_text


def load_courses() -> list[dict]:
    with open(COURSES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _client() -> chromadb.PersistentClient:
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(CHROMA_PERSIST_DIR),
        settings=Settings(anonymized_telemetry=False),
    )


def build_course_index(*, reset: bool = True) -> int:
    """
    Chunk course summaries, embed with Chroma's default model, and index metadata.
    Returns number of chunks indexed.
    """
    courses = load_courses()
    client = _client()

    if reset:
        try:
            client.delete_collection(COURSES_COLLECTION)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COURSES_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for course in courses:
        summary = course.get("summary", "")
        title = course.get("title", "")
        body = f"{title}\n\n{summary}" if title else summary
        chunks = chunk_text(body, CHUNK_SIZE, CHUNK_OVERLAP) or [body]

        for i, chunk in enumerate(chunks):
            chunk_id = f"{course['slug']}__{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append(
                {
                    "slug": course["slug"],
                    "title": course["title"],
                    "url": course.get("url", ""),
                    "domain": course.get("domain", ""),
                    "area": course.get("area", ""),
                    "dimension": course.get("dimension", ""),
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                }
            )

    # Chroma has batch limits; insert in batches
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i : i + batch_size],
            documents=documents[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )

    return len(ids)


if __name__ == "__main__":
    n = build_course_index()
    print(f"Indexed {n} course summary chunks into {CHROMA_PERSIST_DIR}")
