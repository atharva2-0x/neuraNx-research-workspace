"""Semantic search with pgvector — supports both local (384-dim) and OpenAI (1536-dim) embeddings.

SQLite: stores JSON embeddings and uses in-memory cosine ranking.
PostgreSQL: uses pgvector's HNSW index with cosine-distance operator.

The embedding dimension is determined by the EMBEDDING_PROVIDER setting:
  - local (default): 384-dim via BAAI/bge-small-en-v1.5
  - openai: 1536-dim via text-embedding-3-small
"""
import json
from sqlalchemy import select, text
from app.db import Session, ChunkRecord, engine
from app.provider import embed, embed_query, embedding_dim
from app.retrieval import cosine


def initialize_pgvector():
    if engine.dialect.name != "postgresql":
        return
    dim = embedding_dim()
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text(
            f"CREATE TABLE IF NOT EXISTS semantic_vectors ("
            f"document_id text NOT NULL, "
            f"chunk_id text NOT NULL, "
            f"embedding vector({dim}) NOT NULL, "
            f"PRIMARY KEY (document_id, chunk_id))"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS semantic_vectors_hnsw "
            "ON semantic_vectors USING hnsw (embedding vector_cosine_ops)"
        ))


def index_document(document_id):
    with Session() as session:
        chunks = session.scalars(
            select(ChunkRecord).where(ChunkRecord.document_id == document_id)
        ).all()
        missing = [c for c in chunks if not c.embedding]
        for i in range(0, len(missing), 32):
            batch = missing[i:i + 32]
            vectors = embed([c.content for c in batch])
            for c, v in zip(batch, vectors):
                c.embedding = v
            session.commit()
        if engine.dialect.name == "postgresql":
            initialize_pgvector()
            with engine.begin() as connection:
                for c in chunks:
                    connection.execute(
                        text(
                            "INSERT INTO semantic_vectors (document_id, chunk_id, embedding) "
                            "VALUES (:document_id, :chunk_id, CAST(:embedding AS vector)) "
                            "ON CONFLICT (document_id, chunk_id) "
                            "DO UPDATE SET embedding = EXCLUDED.embedding"
                        ),
                        {
                            "document_id": document_id,
                            "chunk_id": c.id,
                            "embedding": json.dumps(c.embedding),
                        },
                    )


def search(document_id, question, limit=4):
    with Session() as session:
        rows = session.scalars(
            select(ChunkRecord).where(ChunkRecord.document_id == document_id)
        ).all()
        if not rows:
            return []
        if any(not r.embedding for r in rows):
            index_document(document_id)
            session.expire_all()
            rows = session.scalars(
                select(ChunkRecord).where(ChunkRecord.document_id == document_id)
            ).all()
        query = embed_query(question)
        by_id = {r.id: r for r in rows}
        if engine.dialect.name == "postgresql":
            with engine.connect() as connection:
                ranked = connection.execute(
                    text(
                        "SELECT chunk_id, 1-(embedding <=> CAST(:query AS vector)) AS score "
                        "FROM semantic_vectors WHERE document_id=:document_id "
                        "ORDER BY embedding <=> CAST(:query AS vector) LIMIT :limit"
                    ),
                    {"query": json.dumps(query), "document_id": document_id, "limit": limit},
                ).all()
            scored = [(by_id[cid], float(score)) for cid, score in ranked]
        else:
            scored = sorted(
                [(r, cosine(query, r.embedding)) for r in rows],
                key=lambda p: p[1],
                reverse=True,
            )[:limit]
        return [
            {"id": r.id, "page": r.page, "section": r.section, "content": r.content, "score": score}
            for r, score in scored
        ]
