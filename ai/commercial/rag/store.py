"""Persistent local SQLite BM25, vector, and topic-graph indexes."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from ai.commercial.context_graph.extraction import extract_passage_graph
from ai.commercial.rag.chunking import CHUNKER_VERSION, DocumentChunk
from ai.commercial.rag.embeddings import EmbeddingProvider, pack_vector, unpack_vector
from ai.commercial.rag.query_planner import QUERY_TOPICS

SCHEMA_VERSION = 1
RRF_K = 60


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _topics_for_chunk(chunk: DocumentChunk) -> list[str]:
    text = _normalized(f"{chunk.section or ''} {chunk.text}")
    topics: list[str] = []
    for topic, aliases, _ in QUERY_TOPICS:
        if any(_normalized(alias) in text for alias in aliases):
            topics.append(topic)
    return topics


class LocalRAGIndex:
    """Transactional on-disk index for documents, chunks, vectors, and graph."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=10,
            isolation_level="IMMEDIATE",
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS documents (
                    source_id TEXT PRIMARY KEY,
                    content_sha256 TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
                    page_count INTEGER NOT NULL CHECK (page_count >= 0),
                    extraction_methods TEXT NOT NULL,
                    ingestion_issues TEXT NOT NULL,
                    chunker_version INTEGER NOT NULL DEFAULT 0,
                    indexed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES documents(source_id)
                        ON DELETE CASCADE,
                    document_sha256 TEXT NOT NULL,
                    page_number INTEGER NOT NULL CHECK (page_number > 0),
                    section TEXT,
                    text TEXT NOT NULL,
                    extraction_method TEXT NOT NULL,
                    synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
                    embedding_model TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    topics_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_by_source
                    ON chunks(source_id);
                CREATE INDEX IF NOT EXISTS chunks_by_embedding
                    ON chunks(embedding_model);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    text,
                    tokenize = 'unicode61 remove_diacritics 2'
                );
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    label TEXT NOT NULL,
                    properties_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_edges (
                    source_node TEXT NOT NULL REFERENCES graph_nodes(node_id)
                        ON DELETE CASCADE,
                    target_node TEXT NOT NULL REFERENCES graph_nodes(node_id)
                        ON DELETE CASCADE,
                    relationship TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    page_number INTEGER,
                    section TEXT,
                    extraction_confidence REAL
                        CHECK (extraction_confidence IS NULL
                            OR extraction_confidence BETWEEN 0 AND 1),
                    evidence_chunk_id TEXT,
                    PRIMARY KEY (source_node, target_node, relationship)
                );
                CREATE INDEX IF NOT EXISTS graph_edges_by_target
                    ON graph_edges(target_node, relationship);
                CREATE INDEX IF NOT EXISTS graph_edges_by_source
                    ON graph_edges(source_node, relationship);
                """
            )
            document_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(documents)"
                ).fetchall()
            }
            if "chunker_version" not in document_columns:
                connection.execute(
                    """
                    ALTER TABLE documents
                    ADD COLUMN chunker_version INTEGER NOT NULL DEFAULT 0
                    """
                )
            graph_edge_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(graph_edges)"
                ).fetchall()
            }
            if "evidence_chunk_id" not in graph_edge_columns:
                connection.execute(
                    "ALTER TABLE graph_edges ADD COLUMN evidence_chunk_id TEXT"
                )
            current = connection.execute(
                "SELECT value FROM index_metadata WHERE key = 'schema_version'"
            ).fetchone()
            if current is not None and int(current["value"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    "Unsupported local RAG index schema version. "
                    "Back up and rebuild the index with the current version."
                )
            connection.execute(
                f"""
                INSERT OR REPLACE INTO index_metadata (key, value)
                VALUES ('schema_version', ?)
                """,
                (str(SCHEMA_VERSION),),
            )
            connection.commit()
        finally:
            connection.close()

    def document_hash(self, source_id: str) -> str | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT content_sha256 FROM documents WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            return str(row["content_sha256"]) if row else None
        finally:
            connection.close()

    def is_current(
        self,
        source_id: str,
        content_sha256: str,
        embedding_model: str,
        *,
        retry_ocr: bool = False,
    ) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT d.content_sha256, d.extraction_methods,
                       d.chunker_version,
                       (SELECT COUNT(*) FROM chunks c
                        WHERE c.source_id = d.source_id) AS chunk_count,
                       (SELECT COUNT(*) FROM chunks c
                        WHERE c.source_id = d.source_id
                          AND c.embedding_model = ?) AS model_count
                FROM documents d WHERE d.source_id = ?
                """,
                (embedding_model, source_id),
            ).fetchone()
            extraction_methods = (
                json.loads(row["extraction_methods"])
                if row is not None
                else []
            )
            return bool(
                row
                and row["content_sha256"] == content_sha256
                and row["chunker_version"] == CHUNKER_VERSION
                and row["chunk_count"] == row["model_count"]
                and not (retry_ocr and "unavailable" in extraction_methods)
            )
        finally:
            connection.close()

    def remove_document(self, source_id: str) -> None:
        """Remove one no-longer-configured source and all of its index entries."""
        connection = self._connect()
        try:
            self._delete_source_context_entities(connection, source_id)
            connection.execute(
                """
                DELETE FROM graph_nodes
                WHERE node_id IN (
                    SELECT 'chunk:' || chunk_id
                    FROM chunks WHERE source_id = ?
                )
                """,
                (source_id,),
            )
            connection.execute(
                "DELETE FROM graph_nodes WHERE node_id = ?",
                (f"document:{source_id}",),
            )
            connection.execute(
                "DELETE FROM chunks_fts WHERE chunk_id IN "
                "(SELECT chunk_id FROM chunks WHERE source_id = ?)",
                (source_id,),
            )
            connection.execute(
                "DELETE FROM documents WHERE source_id = ?",
                (source_id,),
            )
            connection.execute(
                """
                DELETE FROM graph_nodes
                WHERE node_type = 'GuidelineTopic'
                  AND NOT EXISTS (
                      SELECT 1 FROM graph_edges
                      WHERE graph_edges.source_node = graph_nodes.node_id
                         OR graph_edges.target_node = graph_nodes.node_id
                  )
                """
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _delete_source_context_entities(
        connection: sqlite3.Connection,
        source_id: str,
    ) -> None:
        connection.execute(
            """
            DELETE FROM graph_nodes
            WHERE node_id IN (
                SELECT source_node FROM graph_edges
                WHERE source_id = ? AND source_node LIKE 'entity:%'
                UNION
                SELECT target_node FROM graph_edges
                WHERE source_id = ? AND target_node LIKE 'entity:%'
            )
            """,
            (source_id, source_id),
        )

    def index_document(
        self,
        *,
        source_id: str,
        source_path: Path,
        content_sha256: str,
        size_bytes: int,
        page_count: int,
        extraction_methods: Sequence[str],
        ingestion_issues: Sequence[str],
        chunks: Sequence[DocumentChunk],
        embedder: EmbeddingProvider,
    ) -> int:
        """Replace one source atomically, retaining provenance in graph edges."""
        indexed_at = datetime.now(timezone.utc).isoformat()
        passage_graphs = {
            chunk.chunk_id: extract_passage_graph(chunk)
            for chunk in chunks
        }
        connection = self._connect()
        try:
            self._delete_source_context_entities(connection, source_id)
            connection.execute(
                """
                DELETE FROM graph_nodes
                WHERE node_id IN (
                    SELECT 'chunk:' || chunk_id
                    FROM chunks WHERE source_id = ?
                )
                """,
                (source_id,),
            )
            connection.execute(
                "DELETE FROM graph_nodes WHERE node_id = ?",
                (f"document:{source_id}",),
            )
            connection.execute(
                "DELETE FROM chunks_fts WHERE chunk_id IN "
                "(SELECT chunk_id FROM chunks WHERE source_id = ?)",
                (source_id,),
            )
            connection.execute(
                "DELETE FROM documents WHERE source_id = ?",
                (source_id,),
            )
            connection.execute(
                """
                INSERT INTO documents (
                    source_id, content_sha256, source_path, size_bytes,
                    page_count, extraction_methods, ingestion_issues,
                    chunker_version, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    content_sha256,
                    str(source_path),
                    size_bytes,
                    page_count,
                    json.dumps(sorted(set(extraction_methods))),
                    json.dumps(list(ingestion_issues)),
                    CHUNKER_VERSION,
                    indexed_at,
                ),
            )
            document_node = f"document:{source_id}"
            connection.execute(
                """
                INSERT INTO graph_nodes (
                    node_id, node_type, label, properties_json
                ) VALUES (?, 'SourceDocument', ?, ?)
                """,
                (
                    document_node,
                    source_id,
                    json.dumps(
                        {
                            "sha256": content_sha256,
                            "size_bytes": size_bytes,
                            "page_count": page_count,
                            "indexed_at": indexed_at,
                        },
                        sort_keys=True,
                    ),
                ),
            )

            for chunk in chunks:
                embedding = pack_vector(embedder.embed(chunk.text))
                topics = _topics_for_chunk(chunk)
                connection.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, source_id, document_sha256, page_number,
                        section, text, extraction_method, synthetic,
                        embedding_model, embedding, topics_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        source_id,
                        chunk.document_sha256,
                        chunk.page_number,
                        chunk.section,
                        chunk.text,
                        chunk.extraction_method,
                        int(chunk.synthetic),
                        embedder.model_id,
                        embedding,
                        json.dumps(topics),
                    ),
                )
                connection.execute(
                    "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
                    (chunk.chunk_id, chunk.text),
                )

                chunk_node = f"chunk:{chunk.chunk_id}"
                connection.execute(
                    """
                    INSERT INTO graph_nodes (
                        node_id, node_type, label, properties_json
                    ) VALUES (?, 'Passage', ?, ?)
                    """,
                    (
                        chunk_node,
                        f"{source_id} page {chunk.page_number}",
                        json.dumps(
                            {
                                "chunk_id": chunk.chunk_id,
                                "page_number": chunk.page_number,
                                "section": chunk.section,
                                "extraction_method": chunk.extraction_method,
                                "synthetic": chunk.synthetic,
                            },
                            sort_keys=True,
                        ),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO graph_edges (
                        source_node, target_node, relationship, source_id,
                        page_number, section, extraction_confidence
                    ) VALUES (?, ?, 'HAS_PASSAGE', ?, ?, ?, 1.0)
                    """,
                    (
                        document_node,
                        chunk_node,
                        source_id,
                        chunk.page_number,
                        chunk.section,
                    ),
                )

                for topic in topics:
                    topic_node = f"topic:{topic}"
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO graph_nodes (
                            node_id, node_type, label, properties_json
                        ) VALUES (?, 'GuidelineTopic', ?, '{}')
                        """,
                        (topic_node, topic.replace("_", " ")),
                    )
                    connection.execute(
                        """
                        INSERT INTO graph_edges (
                            source_node, target_node, relationship, source_id,
                            page_number, section, extraction_confidence
                        ) VALUES (?, ?, 'ABOUT_TOPIC', ?, ?, ?, NULL)
                        """,
                        (
                            chunk_node,
                            topic_node,
                            source_id,
                            chunk.page_number,
                            chunk.section,
                        ),
                    )

                passage_graph = passage_graphs[chunk.chunk_id]
                for entity in passage_graph.entities:
                    connection.execute(
                        """
                        INSERT INTO graph_nodes (
                            node_id, node_type, label, properties_json
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(node_id) DO UPDATE SET
                            label = CASE
                                WHEN length(excluded.properties_json)
                                     > length(graph_nodes.properties_json)
                                THEN excluded.label
                                ELSE graph_nodes.label
                            END,
                            properties_json = CASE
                                WHEN length(excluded.properties_json)
                                     > length(graph_nodes.properties_json)
                                THEN excluded.properties_json
                                ELSE graph_nodes.properties_json
                            END
                        """,
                        (
                            entity.entity_id,
                            entity.entity_type,
                            entity.label,
                            json.dumps(entity.properties, sort_keys=True),
                        ),
                    )
                for edge in passage_graph.relationships:
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO graph_edges (
                            source_node, target_node, relationship, source_id,
                            page_number, section, extraction_confidence,
                            evidence_chunk_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            edge.source_entity_id,
                            edge.target_entity_id,
                            edge.relationship,
                            edge.source_id,
                            edge.page_number,
                            edge.section,
                            edge.extraction_confidence,
                            edge.evidence_chunk_id,
                        ),
                    )
            connection.commit()
            return len(chunks)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def lexical_search(
        self,
        terms: Sequence[str],
        limit: int,
        source_ids: Sequence[str],
    ) -> list[str]:
        safe_terms = [
            term.replace('"', "").strip()
            for term in terms
            if term.strip() and len(term) <= 128
        ]
        if not safe_terms or not source_ids:
            return []
        match_expression = " OR ".join(f'"{term}"' for term in safe_terms)
        source_placeholders = ",".join("?" for _ in source_ids)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT chunks_fts.chunk_id
                FROM chunks_fts
                JOIN chunks ON chunks.chunk_id = chunks_fts.chunk_id
                WHERE chunks_fts MATCH ?
                  AND chunks.source_id IN ({source_placeholders})
                ORDER BY bm25(chunks_fts), chunks_fts.chunk_id
                LIMIT ?
                """,
                (match_expression, *source_ids, limit),
            ).fetchall()
            return [str(row["chunk_id"]) for row in rows]
        finally:
            connection.close()

    def vector_search(
        self,
        vector: Sequence[float],
        model_id: str,
        limit: int,
        source_ids: Sequence[str],
    ) -> list[tuple[str, float]]:
        query_norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not query_norm or not source_ids:
            return []
        source_placeholders = ",".join("?" for _ in source_ids)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT chunk_id, embedding FROM chunks
                WHERE embedding_model = ?
                  AND source_id IN ({source_placeholders})
                """,
                (model_id, *source_ids),
            ).fetchall()
            scores = []
            for row in rows:
                stored = unpack_vector(row["embedding"])
                if len(stored) != len(vector):
                    continue
                score = sum(
                    left * right
                    for left, right in zip(vector, stored)
                ) / query_norm
                scores.append((score, str(row["chunk_id"])))
            scores.sort(key=lambda item: (-item[0], item[1]))
            return [
                (chunk_id, score)
                for score, chunk_id in scores[:limit]
            ]
        finally:
            connection.close()

    def graph_search(
        self,
        topic_ids: Sequence[str],
        limit: int,
        source_ids: Sequence[str],
    ) -> list[str]:
        safe_topic_ids = [
            f"topic:{topic}" for topic in topic_ids if len(topic) <= 100
        ]
        if not safe_topic_ids or not source_ids:
            return []
        placeholders = ",".join("?" for _ in safe_topic_ids)
        source_placeholders = ",".join("?" for _ in source_ids)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT DISTINCT passage.node_id
                FROM graph_nodes AS topic
                JOIN graph_edges AS topic_edge
                  ON topic_edge.target_node = topic.node_id
                 AND topic_edge.relationship = 'ABOUT_TOPIC'
                JOIN graph_nodes AS passage
                  ON passage.node_id = topic_edge.source_node
                 AND passage.node_type = 'Passage'
                WHERE topic.node_id IN ({placeholders})
                  AND topic_edge.source_id IN ({source_placeholders})
                ORDER BY passage.node_id
                LIMIT ?
                """,
                (*safe_topic_ids, *source_ids, limit),
            ).fetchall()
            return [
                str(row["node_id"]).removeprefix("chunk:")
                for row in rows
            ]
        finally:
            connection.close()

    def context_graph_search(
        self,
        asset_ids: Sequence[str],
        limit: int,
        source_ids: Sequence[str],
    ) -> list[str]:
        """Retrieve provenance passages for matched assets and adjacent entities."""
        safe_asset_ids = list(
            dict.fromkeys(
                asset_id.upper()
                for asset_id in asset_ids[:20]
                if len(asset_id) <= 32
            )
        )
        if not safe_asset_ids or not source_ids:
            return []

        asset_placeholders = ",".join("?" for _ in safe_asset_ids)
        source_placeholders = ",".join("?" for _ in source_ids)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                WITH matched_entities AS (
                    SELECT node_id
                    FROM graph_nodes
                    WHERE node_type = 'Machine'
                      AND json_extract(properties_json, '$.asset_id')
                          IN ({asset_placeholders})
                ),
                related_entities AS (
                    SELECT node_id FROM matched_entities
                    UNION
                    SELECT edge.source_node
                    FROM graph_edges AS edge
                    JOIN matched_entities AS matched
                      ON edge.target_node = matched.node_id
                    WHERE edge.source_id IN ({source_placeholders})
                      AND edge.relationship IN (
                          'DEPENDS_ON', 'FEEDS', 'RESTRICTED_BY'
                      )
                    UNION
                    SELECT edge.target_node
                    FROM graph_edges AS edge
                    JOIN matched_entities AS matched
                      ON edge.source_node = matched.node_id
                    WHERE edge.source_id IN ({source_placeholders})
                      AND edge.relationship IN (
                          'DEPENDS_ON', 'FEEDS', 'RESTRICTED_BY'
                      )
                )
                SELECT support.target_node AS passage_node,
                       MIN(CASE
                           WHEN support.source_node IN (
                               SELECT node_id FROM matched_entities
                           ) THEN 0 ELSE 1
                       END) AS graph_distance,
                       MIN(support.page_number) AS page_number
                FROM graph_edges AS support
                JOIN related_entities AS related
                  ON support.source_node = related.node_id
                WHERE support.relationship = 'SUPPORTED_BY'
                  AND support.source_id IN ({source_placeholders})
                  AND support.target_node LIKE 'chunk:%'
                GROUP BY support.target_node
                ORDER BY graph_distance, page_number, passage_node
                LIMIT ?
                """,
                (
                    *safe_asset_ids,
                    *source_ids,
                    *source_ids,
                    *source_ids,
                    limit,
                ),
            ).fetchall()
            return [
                str(row["passage_node"]).removeprefix("chunk:")
                for row in rows
            ]
        finally:
            connection.close()

    def get_chunks(
        self,
        chunk_ids: Sequence[str],
        source_ids: Sequence[str],
    ) -> list[sqlite3.Row]:
        if not chunk_ids or not source_ids:
            return []
        connection = self._connect()
        try:
            placeholders = ",".join("?" for _ in chunk_ids)
            source_placeholders = ",".join("?" for _ in source_ids)
            rows = connection.execute(
                f"""
                SELECT chunk_id, source_id, document_sha256, page_number,
                       section, text, extraction_method, synthetic,
                       embedding_model, topics_json
                FROM chunks
                WHERE chunk_id IN ({placeholders})
                  AND source_id IN ({source_placeholders})
                """,
                (*chunk_ids, *source_ids),
            ).fetchall()
            return list(rows)
        finally:
            connection.close()

    def indexed_documents(self) -> list[dict[str, object]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT source_id, content_sha256, source_path, size_bytes,
                       page_count, extraction_methods, ingestion_issues, indexed_at
                FROM documents
                ORDER BY source_id
                """
            ).fetchall()
            return [
                {
                    "source_id": row["source_id"],
                    "sha256": row["content_sha256"],
                    "path": row["source_path"],
                    "size_bytes": row["size_bytes"],
                    "page_count": row["page_count"],
                    "extraction_methods": json.loads(row["extraction_methods"]),
                    "ingestion_issues": json.loads(row["ingestion_issues"]),
                    "indexed_at": row["indexed_at"],
                }
                for row in rows
            ]
        finally:
            connection.close()

    def chunks_for_document(self, source_id: str) -> list[dict[str, object]]:
        """Return bounded-provenance chunk records for an optional graph mirror."""
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT chunk_id, document_sha256, page_number, section, text,
                       extraction_method, synthetic, topics_json
                FROM chunks
                WHERE source_id = ?
                ORDER BY page_number, chunk_id
                """,
                (source_id,),
            ).fetchall()
            return [
                {
                    "chunk_id": row["chunk_id"],
                    "sha256": row["document_sha256"],
                    "page_number": row["page_number"],
                    "section": row["section"],
                    "text": row["text"],
                    "extraction_method": row["extraction_method"],
                    "synthetic": bool(row["synthetic"]),
                    "topics": json.loads(row["topics_json"]),
                }
                for row in rows
            ]
        finally:
            connection.close()

    def context_graph_for_document(self, source_id: str) -> dict[str, list[dict[str, object]]]:
        """Return typed context entities and their provenance-bearing edges."""
        connection = self._connect()
        try:
            nodes = connection.execute(
                """
                SELECT node_id, node_type, label, properties_json
                FROM graph_nodes
                WHERE node_id IN (
                    SELECT source_node FROM graph_edges WHERE source_id = ?
                    UNION
                    SELECT target_node FROM graph_edges WHERE source_id = ?
                )
                  AND node_type != 'GuidelineTopic'
                ORDER BY node_id
                """,
                (source_id, source_id),
            ).fetchall()
            edges = connection.execute(
                """
                SELECT source_node, target_node, relationship, source_id,
                       page_number, section, extraction_confidence,
                       evidence_chunk_id
                FROM graph_edges
                WHERE source_id = ?
                ORDER BY source_node, target_node, relationship
                """,
                (source_id,),
            ).fetchall()
            edge_metadata: dict[str, dict[str, object]] = {}
            for edge in edges:
                metadata = {
                    "page_number": edge["page_number"],
                    "section": edge["section"],
                    "extraction_confidence": edge["extraction_confidence"],
                }
                edge_metadata.setdefault(str(edge["source_node"]), metadata)
                edge_metadata.setdefault(str(edge["target_node"]), metadata)
            return {
                "entities": [
                    {
                        "entity_id": row["node_id"],
                        "entity_type": row["node_type"],
                        "label": row["label"],
                        "properties_json": row["properties_json"],
                        **edge_metadata.get(str(row["node_id"]), {}),
                    }
                    for row in nodes
                ],
                "relationships": [
                    {
                        "source_entity_id": row["source_node"],
                        "target_entity_id": row["target_node"],
                        "relationship": row["relationship"],
                        "source_id": row["source_id"],
                        "page_number": row["page_number"],
                        "section": row["section"],
                        "extraction_confidence": row["extraction_confidence"],
                        "evidence_chunk_id": row["evidence_chunk_id"],
                    }
                    for row in edges
                ],
            }
        finally:
            connection.close()

    def index_counts(self) -> dict[str, int]:
        connection = self._connect()
        try:
            return {
                table: int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                )
                for table in (
                    "documents",
                    "chunks",
                    "graph_nodes",
                    "graph_edges",
                )
            }
        finally:
            connection.close()

    def reciprocal_rank_fusion(
        self,
        ranked_lists: Sequence[Sequence[str]],
        limit: int,
    ) -> list[str]:
        scores: dict[str, float] = {}
        for ranked in ranked_lists:
            for rank, chunk_id in enumerate(ranked, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                    1 / (RRF_K + rank)
                )
        return [
            chunk_id
            for chunk_id, _ in sorted(
                scores.items(),
                key=lambda item: (-item[1], item[0]),
            )[:limit]
        ]
