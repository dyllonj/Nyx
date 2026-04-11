"""
RAG knowledge base for the AI running coach.

Wraps fastembed (ONNX, no PyTorch) and ChromaDB (SQLite-backed).
Public API: init() and retrieve() — both safe to call even if the
knowledge base hasn't been built yet (retrieve() returns "" gracefully).
"""
import logging
from typing import Optional

import config
from logging_utils import get_logger, log_event

COLLECTION_NAME = "running_knowledge"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # 22MB ONNX, 384-dim, CPU-fast

_embedding_model = None
_collection = None
logger = get_logger("knowledge_base")


def init() -> None:
    """
    Lazy-initialize the embedding model and ChromaDB collection.
    Idempotent — safe to call multiple times.
    Fails silently with a warning if chroma_db/ doesn't exist yet.
    """
    global _embedding_model, _collection

    if _embedding_model is not None and _collection is not None:
        return

    try:
        from fastembed import TextEmbedding
        import chromadb

        _embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL, show_progress_bar=False)

        client = chromadb.PersistentClient(path=config.KNOWLEDGE_DB_PATH)
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        count = _collection.count()
        if count == 0:
            log_event(
                logger,
                logging.WARNING,
                "knowledge_base.empty",
                hint="Run `python build_kb.py` to index knowledge files.",
            )
    except ImportError as e:
        log_event(
            logger,
            logging.WARNING,
            "knowledge_base.unavailable",
            error=str(e),
            hint="Run `pip install fastembed chromadb`.",
        )
    except Exception as e:
        log_event(logger, logging.WARNING, "knowledge_base.init_warning", error=str(e))


def retrieve(
    query: str,
    k: int = config.KNOWLEDGE_RETRIEVAL_K,
    threshold: float = config.KNOWLEDGE_SIMILARITY_THRESHOLD,
) -> str:
    """
    Embed query and return top-K chunks above cosine similarity threshold,
    formatted for injection into a Claude system block.

    Returns empty string if not initialized, no results above threshold,
    or any exception. Never raises.
    """
    if _embedding_model is None or _collection is None:
        return ""

    if not query or not query.strip():
        return ""

    try:
        # fastembed.embed() returns a generator of numpy arrays
        query_embedding = list(_embedding_model.embed([query]))[0].tolist()

        results = _collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, _collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance = 1 - cosine_similarity
            # So: dist < (1 - threshold) means similarity > threshold
            if dist < (1.0 - threshold):
                domain = meta.get("domain", "general")
                section = meta.get("section_title", "")
                if section and section != "Overview":
                    label = f"[Source: {domain} | Section: {section}]"
                else:
                    label = f"[Source: {domain}]"
                chunks.append(f"{label}\n{doc.strip()}")

        return "\n\n".join(chunks)

    except Exception as e:
        log_event(logger, logging.WARNING, "knowledge_base.retrieve_warning", error=str(e))
        return ""
