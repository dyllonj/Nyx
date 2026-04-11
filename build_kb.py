#!/usr/bin/env python3
"""
Build (or rebuild) the RAG knowledge base from files in the knowledge/ directory.

Usage:
    python build_kb.py              # index all files, upsert (safe to re-run)
    python build_kb.py --reset      # wipe collection and re-index from scratch
    python build_kb.py --dry-run    # print what would be indexed, don't write

The script is idempotent: chunk IDs are stable (based on filename + index),
so re-running after editing a knowledge file updates only changed chunks.
"""
import argparse
import json
import os
import re
import sys
import time

import config
from knowledge_base import COLLECTION_NAME, EMBEDDING_MODEL


def serialize_json_object(obj: dict) -> str:
    """Serialize a JSON object as 'key: value, key: value' for embedding."""
    parts = []
    for k, v in obj.items():
        if isinstance(v, list):
            v_str = ", ".join(str(item) for item in v)
        elif isinstance(v, dict):
            v_str = "; ".join(f"{sk}: {sv}" for sk, sv in v.items())
        else:
            v_str = str(v)
        parts.append(f"{k}: {v_str}")
    return ", ".join(parts)


def parse_json_file(path: str) -> list[tuple[str, dict]]:
    """
    Parse a JSON knowledge file into (text, metadata) chunks.
    - Array of objects: each object → one chunk
    - Dict of dicts: each top-level key → one chunk
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    filename = os.path.basename(path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    chunks = []

    if isinstance(data, list):
        for i, obj in enumerate(data):
            if not isinstance(obj, dict):
                continue
            text = serialize_json_object(obj)
            # Use a descriptive title from common key names
            title = str(obj.get("vdot") or obj.get("condition") or obj.get("temp_celsius") or f"item {i}")
            meta = {
                "domain": stem,
                "source_file": filename,
                "chunk_index": i,
                "section_title": title,
                "format": "json_row",
            }
            chunks.append((text, meta))

    elif isinstance(data, dict):
        for i, (key, value) in enumerate(data.items()):
            if isinstance(value, dict):
                text = f"{key}: {serialize_json_object(value)}"
            else:
                text = f"{key}: {value}"
            meta = {
                "domain": stem,
                "source_file": filename,
                "chunk_index": i,
                "section_title": key,
                "format": "json_section",
            }
            chunks.append((text, meta))

    return chunks


def parse_markdown_file(path: str) -> list[tuple[str, dict]]:
    """
    Parse a Markdown knowledge file into (text, metadata) chunks.
    Splits on '## ' section headers. Content before the first header
    is treated as 'Overview'. Long sections (>400 words) are split
    at paragraph breaks with the section title as a prefix.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    filename = os.path.basename(path)

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split on ## headers
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(content))

    sections = []
    if matches:
        # Content before first ## header
        preamble = content[: matches[0].start()].strip()
        if preamble and len(preamble) >= 50:
            sections.append(("Overview", preamble))

        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start:end].strip()
            if body and len(body) >= 50:
                sections.append((title, body))
    else:
        # No headers — treat whole file as one chunk
        sections.append(("Overview", content.strip()))

    chunks = []
    chunk_index = 0

    for title, body in sections:
        words = body.split()
        if len(words) <= 400:
            meta = {
                "domain": stem,
                "source_file": filename,
                "chunk_index": chunk_index,
                "section_title": title,
                "format": "markdown_section",
            }
            chunks.append((body, meta))
            chunk_index += 1
        else:
            # Split long sections at paragraph breaks
            paragraphs = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
            current_parts = []
            current_words = 0
            sub_index = 0

            for para in paragraphs:
                para_words = len(para.split())
                if current_words + para_words > 350 and current_parts:
                    text = f"[{title}]\n" + "\n\n".join(current_parts)
                    meta = {
                        "domain": stem,
                        "source_file": filename,
                        "chunk_index": chunk_index,
                        "section_title": f"{title} (part {sub_index + 1})",
                        "format": "markdown_section",
                    }
                    chunks.append((text, meta))
                    chunk_index += 1
                    sub_index += 1
                    current_parts = [para]
                    current_words = para_words
                else:
                    current_parts.append(para)
                    current_words += para_words

            if current_parts:
                text = f"[{title}]\n" + "\n\n".join(current_parts)
                label = f"{title} (part {sub_index + 1})" if sub_index > 0 else title
                meta = {
                    "domain": stem,
                    "source_file": filename,
                    "chunk_index": chunk_index,
                    "section_title": label,
                    "format": "markdown_section",
                }
                chunks.append((text, meta))
                chunk_index += 1

    return chunks


def build(reset: bool = False, dry_run: bool = False) -> None:
    knowledge_dir = config.KNOWLEDGE_DIR

    if not os.path.isdir(knowledge_dir):
        print(f"Error: knowledge directory '{knowledge_dir}' not found.")
        sys.exit(1)

    # Collect all files
    all_files = sorted(
        os.path.join(knowledge_dir, f)
        for f in os.listdir(knowledge_dir)
        if f.endswith((".json", ".md"))
    )

    if not all_files:
        print(f"No .json or .md files found in '{knowledge_dir}'.")
        return

    # Parse all files into chunks
    all_chunks: list[tuple[str, str, dict]] = []  # (id, text, metadata)
    for path in all_files:
        stem = os.path.splitext(os.path.basename(path))[0]
        ext = os.path.splitext(path)[1]

        if ext == ".json":
            chunks = parse_json_file(path)
        else:
            chunks = parse_markdown_file(path)

        for i, (text, meta) in enumerate(chunks):
            chunk_id = f"{stem}_chunk_{i:04d}"
            all_chunks.append((chunk_id, text, meta))

        print(f"  Parsed  {os.path.basename(path)}: {len(chunks)} chunks")

    print(f"\n  Total: {len(all_chunks)} chunks across {len(all_files)} files")

    if dry_run:
        print("\n[Dry run — no data written]")
        return

    # Embed and upsert
    print("\nLoading embedding model (downloads ~22MB on first run)...")
    t0 = time.time()

    try:
        from fastembed import TextEmbedding
        import chromadb
    except ImportError as e:
        print(f"Error: {e}\nRun: pip install fastembed chromadb")
        sys.exit(1)

    embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL, show_progress_bar=True)

    client = chromadb.PersistentClient(path=config.KNOWLEDGE_DB_PATH)

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"  Deleted existing collection '{COLLECTION_NAME}'")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [c[0] for c in all_chunks]
    texts = [c[1] for c in all_chunks]
    metadatas = [c[2] for c in all_chunks]

    print(f"Embedding {len(texts)} chunks...")
    embeddings = list(embedding_model.embed(texts))
    embeddings_list = [e.tolist() for e in embeddings]

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            documents=texts[i : i + batch_size],
            embeddings=embeddings_list[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )

    elapsed = time.time() - t0
    final_count = collection.count()
    print(f"\nDone. {final_count} chunks in collection '{COLLECTION_NAME}' ({elapsed:.1f}s)")
    print(f"Knowledge base saved to: {config.KNOWLEDGE_DB_PATH}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the running coach knowledge base")
    parser.add_argument("--reset", action="store_true", help="Wipe collection and re-index")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")
    args = parser.parse_args()

    build(reset=args.reset, dry_run=args.dry_run)
