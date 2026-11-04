"""Optional local Neo4j topic-graph mirror for Commercial RAG."""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from urllib.parse import urlparse


class Neo4jTopicGraph:
    """Mirror indexed passages, topics, and typed context entities locally."""

    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str,
        connection_timeout_seconds: float = 5.0,
    ) -> None:
        parsed_uri = urlparse(uri)
        hostname = (parsed_uri.hostname or "").casefold()
        try:
            is_loopback = hostname == "localhost" or ipaddress.ip_address(
                hostname
            ).is_loopback
        except ValueError:
            is_loopback = False
        if parsed_uri.scheme not in {"bolt", "neo4j"} or not is_loopback:
            raise ValueError(
                "The Neo4j graph backend only supports a local bolt:// or "
                "neo4j:// endpoint."
            )
        if not username or not password:
            raise ValueError(
                "Neo4j graph backend requires a username and password from "
                "the local environment."
            )
        if not database or len(database) > 63:
            raise ValueError("Neo4j database name is invalid.")

        from neo4j import GraphDatabase

        self._database = database
        self._driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
            connection_timeout=connection_timeout_seconds,
            max_connection_pool_size=10,
        )
        self._driver.verify_connectivity()
        with self._driver.session(database=database) as session:
            session.execute_write(self._ensure_constraints)

    @staticmethod
    def _ensure_constraints(transaction) -> None:
        transaction.run(
            """
            CREATE CONSTRAINT commercial_source_id IF NOT EXISTS
            FOR (source:CommercialSource)
            REQUIRE source.source_id IS UNIQUE
            """
        )
        transaction.run(
            """
            CREATE CONSTRAINT commercial_passage_id IF NOT EXISTS
            FOR (passage:CommercialPassage)
            REQUIRE passage.chunk_id IS UNIQUE
            """
        )
        transaction.run(
            """
            CREATE CONSTRAINT commercial_topic_id IF NOT EXISTS
            FOR (topic:CommercialTopic)
            REQUIRE topic.topic_id IS UNIQUE
            """
        )
        transaction.run(
            """
            CREATE CONSTRAINT commercial_context_entity_id IF NOT EXISTS
            FOR (entity:CommercialContextEntity)
            REQUIRE entity.entity_id IS UNIQUE
            """
        )

    def sync_document(
        self,
        *,
        source_id: str,
        content_sha256: str,
        source_path: str,
        pages: int,
        passages: Sequence[dict[str, object]],
        context_graph: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        """Idempotently mirror one document and its existing SQLite passages."""
        with self._driver.session(database=self._database) as session:
            session.execute_write(
                self._sync_document_transaction,
                source_id,
                content_sha256,
                source_path,
                pages,
                list(passages),
                context_graph or {"entities": [], "relationships": []},
            )

    @staticmethod
    def _sync_document_transaction(
        transaction,
        source_id: str,
        content_sha256: str,
        source_path: str,
        pages: int,
        passages: list[dict[str, object]],
        context_graph: dict[str, list[dict[str, object]]],
    ) -> None:
        transaction.run(
            """
            MATCH (entity:CommercialContextEntity {source_id: $source_id})
            DETACH DELETE entity
            """,
            source_id=source_id,
        )
        transaction.run(
            """
            MATCH (passage:CommercialPassage {source_id: $source_id})
            OPTIONAL MATCH (passage)-[topic_edge:ABOUT_TOPIC]->()
            DELETE topic_edge
            """,
            source_id=source_id,
        )
        transaction.run(
            """
            MATCH (passage:CommercialPassage {source_id: $source_id})
            WHERE NOT passage.chunk_id IN $chunk_ids
            DETACH DELETE passage
            """,
            source_id=source_id,
            chunk_ids=[str(item["chunk_id"]) for item in passages],
        )
        transaction.run(
            """
            MERGE (source:CommercialSource {source_id: $source_id})
            SET source.sha256 = $sha256,
                source.path = $path,
                source.page_count = $page_count
            """,
            source_id=source_id,
            sha256=content_sha256,
            path=source_path,
            page_count=pages,
        )
        transaction.run(
            """
            UNWIND $passages AS row
            MATCH (source:CommercialSource {source_id: $source_id})
            MERGE (passage:CommercialPassage {chunk_id: row.chunk_id})
            SET passage.source_id = $source_id,
                passage.sha256 = row.sha256,
                passage.page_number = row.page_number,
                passage.section = row.section,
                passage.text = row.text,
                passage.extraction_method = row.extraction_method,
                passage.synthetic = row.synthetic
            MERGE (source)-[:HAS_PASSAGE]->(passage)
            WITH passage, row
            UNWIND row.topics AS topic_id
            MERGE (topic:CommercialTopic {topic_id: topic_id})
            MERGE (passage)-[:ABOUT_TOPIC]->(topic)
            """,
            source_id=source_id,
            passages=list(passages),
        )
        transaction.run(
            """
            UNWIND $entities AS row
            MERGE (entity:CommercialContextEntity {entity_id: row.entity_id})
            SET entity.entity_type = row.entity_type,
                entity.label = row.label,
                entity.properties_json = row.properties_json,
                entity.source_id = $source_id,
                entity.page_number = row.page_number,
                entity.section = row.section,
                entity.extraction_confidence = row.extraction_confidence
            """,
            source_id=source_id,
            entities=context_graph["entities"],
        )
        transaction.run(
            """
            UNWIND $relationships AS row
            MATCH (source:CommercialContextEntity {entity_id: row.source_entity_id})
            MATCH (target:CommercialContextEntity {entity_id: row.target_entity_id})
            MERGE (source)-[edge:CG_RELATION {
                relationship: row.relationship,
                source_id: row.source_id,
                page_number: row.page_number
            }]->(target)
            SET edge.section = row.section,
                edge.extraction_confidence = row.extraction_confidence,
                edge.evidence_chunk_id = row.evidence_chunk_id
            """,
            relationships=context_graph["relationships"],
        )

    def search(
        self,
        topic_ids: Sequence[str],
        source_ids: Sequence[str],
        limit: int,
    ) -> list[str]:
        """Return passage IDs for matching topics and configured sources only."""
        if not topic_ids or not source_ids:
            return []
        with self._driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (passage:CommercialPassage)-[:ABOUT_TOPIC]->(
                    topic:CommercialTopic
                )
                WHERE topic.topic_id IN $topic_ids
                  AND passage.source_id IN $source_ids
                RETURN DISTINCT passage.chunk_id AS chunk_id
                ORDER BY chunk_id
                LIMIT $limit
                """,
                topic_ids=list(topic_ids),
                source_ids=list(source_ids),
                limit=limit,
            )
            return [str(record["chunk_id"]) for record in result]

    def search_entities(
        self,
        entity_labels: Sequence[str],
        source_ids: Sequence[str],
        limit: int,
    ) -> list[str]:
        """Find cited passages linked to exact entity labels within source scope."""
        if not entity_labels or not source_ids:
            return []
        with self._driver.session(database=self._database) as session:
            result = session.run(
                """
                MATCH (entity:CommercialContextEntity)
                WHERE entity.label IN $entity_labels
                  AND entity.source_id IN $source_ids
                MATCH (entity)-[:CG_RELATION*0..2]-(passage:CommercialContextEntity)
                WHERE passage.entity_type = 'Passage'
                  AND passage.source_id IN $source_ids
                RETURN DISTINCT passage.entity_id AS passage_id
                ORDER BY passage_id
                LIMIT $limit
                """,
                entity_labels=[label.upper() for label in entity_labels],
                source_ids=list(source_ids),
                limit=limit,
            )
            return [
                str(record["passage_id"]).removeprefix("chunk:")
                for record in result
            ]

    def remove_document(self, source_id: str) -> None:
        """Remove one configured source and its passages from the graph."""
        with self._driver.session(database=self._database) as session:
            session.run(
                """
                MATCH (entity:CommercialContextEntity {source_id: $source_id})
                DETACH DELETE entity
                """,
                source_id=source_id,
            )
            session.run(
                """
                MATCH (source:CommercialSource {source_id: $source_id})
                OPTIONAL MATCH (source)-[:HAS_PASSAGE]->(passage)
                DETACH DELETE source, passage
                """,
                source_id=source_id,
            )

    def close(self) -> None:
        """Close the driver and its local connection pool."""
        self._driver.close()
