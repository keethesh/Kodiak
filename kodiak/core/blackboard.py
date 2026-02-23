"""
Blackboard service: append-only events + projected canonical facts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import UUID

from loguru import logger

from kodiak.core.blackboard_schema import (
    CONFIDENCE_RANK,
    ENTITY_TYPES,
    TOOL_TO_EVENT,
    confidence_max,
    normalize_entity_key,
    normalize_entity_type,
    normalize_event_type,
    role_scoped_entity_types,
)
from kodiak.core.config import settings
from kodiak.database import crud
from kodiak.database.models import (
    BlackboardEdge,
    BlackboardEvent,
    BlackboardFact,
    ConfidenceLevel,
    VerificationQueue,
    VerificationQueueStatus,
    VerificationStatus,
)


class BlackboardService:
    """
    Shared scan blackboard built on SQL tables.
    """

    async def publish_event(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        agent_id: str,
        event_type: str,
        entity_type: str,
        entity_key: str,
        payload: Dict[str, Any],
        confidence: str = "medium",
        status: str = "observed",
    ) -> Dict[str, Any]:
        if not settings.blackboard_enabled or not session or not project_id or not scan_id:
            return {}

        normalized_event_type = normalize_event_type(event_type)
        normalized_entity_type = normalize_entity_type(entity_type)
        normalized_entity_key = normalize_entity_key(entity_key, default_prefix=normalized_entity_type)
        normalized_confidence = self._normalize_confidence(confidence)
        normalized_status = str(status or "observed").strip().lower()
        normalized_payload = payload if isinstance(payload, dict) else {}

        event = BlackboardEvent(
            project_id=project_id,
            scan_id=scan_id,
            agent_id=str(agent_id or "unknown"),
            event_type=normalized_event_type,
            entity_type=normalized_entity_type,
            entity_key=normalized_entity_key,
            payload=normalized_payload,
            confidence=normalized_confidence,
            status=normalized_status,
        )

        try:
            created_event = await crud.blackboard_event.create(session, event)
        except Exception as e:
            text = str(e).lower()
            if "no such table" in text and "blackboard" in text:
                try:
                    from kodiak.database.engine import init_db

                    await init_db()
                    created_event = await crud.blackboard_event.create(session, event)
                except Exception as retry_error:
                    logger.warning(f"Failed to publish blackboard event after init_db retry: {retry_error}")
                    return {}
            else:
                logger.warning(f"Failed to publish blackboard event: {e}")
                return {}

        fact = None
        edge = None
        if normalized_entity_type == "attack_path_edge" or normalized_event_type == "attack_path_edge":
            edge = await self._upsert_edge_from_payload(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                payload=normalized_payload,
                confidence=str(normalized_confidence),
                last_event_id=created_event.id,
            )
        else:
            fact = await self._upsert_fact_from_event(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                event=created_event,
            )

        return {
            "event_id": str(created_event.id),
            "entity_type": created_event.entity_type,
            "entity_key": created_event.entity_key,
            "fact_id": str(fact.id) if fact else None,
            "edge_id": str(edge.id) if edge else None,
        }

    async def publish_tool_result(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        agent_id: str,
        tool_name: str,
        target: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
        fingerprint: str,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not settings.blackboard_enabled:
            return []

        items = self._derive_events_for_tool(
            tool_name=tool_name,
            target=target,
            args=args,
            result=result,
            fingerprint=fingerprint,
            execution_context=execution_context or {},
        )
        published: List[Dict[str, Any]] = []
        for item in items:
            response = await self.publish_event(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                agent_id=agent_id,
                event_type=item["event_type"],
                entity_type=item["entity_type"],
                entity_key=item["entity_key"],
                payload=item["payload"],
                confidence=item.get("confidence", "medium"),
                status=item.get("status", "observed"),
            )
            if response:
                published.append(response)
        return published

    async def publish_fact(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        agent_id: str,
        entity_type: str,
        entity_key: str,
        payload: Dict[str, Any],
        confidence: str = "medium",
        status: str = "observed",
    ) -> Dict[str, Any]:
        normalized_entity_type = normalize_entity_type(entity_type)
        validated_payload = self._validate_manual_payload(normalized_entity_type, payload)
        event_type = self._event_type_for_manual_fact(normalized_entity_type, status)
        response = await self.publish_event(
            session=session,
            project_id=project_id,
            scan_id=scan_id,
            agent_id=agent_id,
            event_type=event_type,
            entity_type=normalized_entity_type,
            entity_key=entity_key,
            payload=validated_payload,
            confidence=confidence,
            status=status,
        )
        if response and str(status or "").lower() == "verified":
            await self._resolve_pending_verification(
                session=session,
                scan_id=scan_id,
                entity_type=normalized_entity_type,
                entity_key=normalize_entity_key(entity_key, default_prefix=normalized_entity_type),
            )
        return response

    async def publish_edge(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        agent_id: str,
        src_type: str,
        src_key: str,
        relation: str,
        dst_type: str,
        dst_key: str,
        confidence: str = "medium",
        status: str = "observed",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = dict(payload or {})
        body.update(
            {
                "src_type": normalize_entity_type(src_type),
                "src_key": normalize_entity_key(src_key, default_prefix=normalize_entity_type(src_type)),
                "relation": self._trim_text(relation, 60),
                "dst_type": normalize_entity_type(dst_type),
                "dst_key": normalize_entity_key(dst_key, default_prefix=normalize_entity_type(dst_type)),
            }
        )
        body = self._validate_manual_payload("attack_path_edge", body)
        return await self.publish_event(
            session=session,
            project_id=project_id,
            scan_id=scan_id,
            agent_id=agent_id,
            event_type="attack_path_edge",
            entity_type="attack_path_edge",
            entity_key=f"edge:{body['src_key']}:{body['relation']}:{body['dst_key']}",
            payload=body,
            confidence=confidence,
            status=status,
        )

    async def query_facts(
        self,
        session: Any,
        scan_id: UUID,
        role: str,
        entity_type: Optional[str] = None,
        keyword: Optional[str] = None,
        target: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        if not settings.blackboard_enabled:
            return []
        scoped = role_scoped_entity_types(role)
        normalized_type = normalize_entity_type(entity_type) if entity_type else None
        entity_filters = [normalized_type] if normalized_type else scoped
        try:
            facts = await crud.blackboard_fact.list_by_scan(
                session=session,
                scan_id=scan_id,
                limit=max(50, int(limit) * 6),
                entity_types=entity_filters,
            )
        except Exception as e:
            text = str(e).lower()
            if "no such table" in text and "blackboard" in text:
                from kodiak.database.engine import init_db

                await init_db()
                facts = await crud.blackboard_fact.list_by_scan(
                    session=session,
                    scan_id=scan_id,
                    limit=max(50, int(limit) * 6),
                    entity_types=entity_filters,
                )
            else:
                raise
        sorted_facts = self._sort_facts(facts)
        needle = self._query_needle(keyword=keyword, target=target)
        rows: List[Dict[str, Any]] = []
        for fact in sorted_facts:
            canonical = fact.canonical or {}
            if needle:
                blob = f"{fact.entity_key} {json.dumps(canonical, sort_keys=True, default=str)}".lower()
                if needle not in blob:
                    continue
            rows.append(
                {
                    "entity_type": fact.entity_type,
                    "entity_key": fact.entity_key,
                    "confidence": str(fact.confidence or "medium").lower(),
                    "verification_status": str(fact.verification_status or "unverified").lower(),
                    "canonical": canonical,
                    "updated_at": fact.updated_at.isoformat() if getattr(fact, "updated_at", None) else None,
                }
            )
            if len(rows) >= max(1, int(limit)):
                break
        return rows

    async def query_edges(
        self,
        session: Any,
        scan_id: UUID,
        entity_key: Optional[str] = None,
        relation: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        if not settings.blackboard_enabled:
            return []
        rows: List[Dict[str, Any]] = []
        rel_needle = str(relation or "").strip().lower()
        key_needle = str(entity_key or "").strip().lower()
        try:
            edges = await crud.blackboard_edge.list_by_scan(session=session, scan_id=scan_id, limit=max(60, limit * 4))
        except Exception as e:
            text = str(e).lower()
            if "no such table" in text and "blackboard" in text:
                from kodiak.database.engine import init_db

                await init_db()
                edges = await crud.blackboard_edge.list_by_scan(
                    session=session,
                    scan_id=scan_id,
                    limit=max(60, limit * 4),
                )
            else:
                raise
        for edge in edges:
            if rel_needle and rel_needle not in str(edge.relation or "").lower():
                continue
            if key_needle:
                src = f"{edge.src_type}:{edge.src_key}".lower()
                dst = f"{edge.dst_type}:{edge.dst_key}".lower()
                if key_needle not in src and key_needle not in dst:
                    continue
            rows.append(
                {
                    "src_type": edge.src_type,
                    "src_key": edge.src_key,
                    "relation": edge.relation,
                    "dst_type": edge.dst_type,
                    "dst_key": edge.dst_key,
                    "confidence": str(edge.confidence or "medium").lower(),
                    "updated_at": edge.updated_at.isoformat() if getattr(edge, "updated_at", None) else None,
                }
            )
            if len(rows) >= max(1, int(limit)):
                break
        return rows

    async def query_events(
        self,
        session: Any,
        scan_id: UUID,
        entity_type: Optional[str] = None,
        entity_key: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        if not settings.blackboard_enabled:
            return []
        try:
            if entity_type and entity_key:
                events = await crud.blackboard_event.list_by_entity(
                    session=session,
                    scan_id=scan_id,
                    entity_type=normalize_entity_type(entity_type),
                    entity_key=normalize_entity_key(entity_key, default_prefix=normalize_entity_type(entity_type)),
                    limit=max(20, int(limit)),
                )
            else:
                events = await crud.blackboard_event.list_by_scan(
                    session=session,
                    scan_id=scan_id,
                    limit=max(40, int(limit) * 2),
                )
        except Exception as e:
            text = str(e).lower()
            if "no such table" in text and "blackboard" in text:
                from kodiak.database.engine import init_db

                await init_db()
                if entity_type and entity_key:
                    events = await crud.blackboard_event.list_by_entity(
                        session=session,
                        scan_id=scan_id,
                        entity_type=normalize_entity_type(entity_type),
                        entity_key=normalize_entity_key(entity_key, default_prefix=normalize_entity_type(entity_type)),
                        limit=max(20, int(limit)),
                    )
                else:
                    events = await crud.blackboard_event.list_by_scan(
                        session=session,
                        scan_id=scan_id,
                        limit=max(40, int(limit) * 2),
                    )
            else:
                raise
        rows: List[Dict[str, Any]] = []
        for event in events[: max(1, int(limit))]:
            if entity_type and not entity_key and event.entity_type != normalize_entity_type(entity_type):
                continue
            rows.append(
                {
                    "agent_id": event.agent_id,
                    "event_type": event.event_type,
                    "entity_type": event.entity_type,
                    "entity_key": event.entity_key,
                    "status": event.status,
                    "confidence": str(event.confidence or "medium").lower(),
                    "payload": event.payload or {},
                    "created_at": event.created_at.isoformat() if getattr(event, "created_at", None) else None,
                }
            )
        return rows

    async def query_verification_queue(
        self,
        session: Any,
        scan_id: UUID,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        if not settings.blackboard_enabled:
            return []
        try:
            items = await crud.verification_queue.list_pending_by_scan(
                session=session,
                scan_id=scan_id,
                limit=max(20, int(limit) * 3),
            )
        except Exception as e:
            text = str(e).lower()
            if "no such table" in text and ("verificationqueue" in text or "blackboard" in text):
                from kodiak.database.engine import init_db

                await init_db()
                items = await crud.verification_queue.list_pending_by_scan(
                    session=session,
                    scan_id=scan_id,
                    limit=max(20, int(limit) * 3),
                )
            else:
                raise
        rows: List[Dict[str, Any]] = []
        for item in items[: max(1, int(limit))]:
            rows.append(
                {
                    "id": str(item.id),
                    "entity_type": item.entity_type,
                    "entity_key": item.entity_key,
                    "reason": item.reason,
                    "requested_by_agent": item.requested_by_agent,
                    "status": str(item.status),
                    "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
                }
            )
        return rows

    async def resolve_verification_item(
        self,
        session: Any,
        item_id: UUID,
        status: str = "resolved",
    ) -> Optional[Dict[str, Any]]:
        normalized = str(status or "resolved").strip().lower()
        resolved_status = (
            VerificationQueueStatus.IGNORED if normalized == "ignored" else VerificationQueueStatus.RESOLVED
        )
        item = await crud.verification_queue.resolve(session=session, item_id=item_id, status=resolved_status)
        if not item:
            return None
        return {
            "id": str(item.id),
            "status": str(item.status),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }

    async def build_prompt_context(
        self,
        session: Any,
        scan_id: UUID,
        role: str,
        target: Optional[str] = None,
        limit: int = 10,
        max_chars: int = 2000,
    ) -> str:
        if not settings.blackboard_enabled or not session or not scan_id:
            return ""

        scoped_entity_types = role_scoped_entity_types(role)
        safe_limit = max(1, min(50, int(limit)))
        try:
            facts = await crud.blackboard_fact.list_by_scan(
                session=session,
                scan_id=scan_id,
                limit=max(80, safe_limit * 4),
                entity_types=scoped_entity_types,
            )
            edges = await crud.blackboard_edge.list_by_scan(
                session=session,
                scan_id=scan_id,
                limit=max(40, safe_limit * 2),
            )
            pending = await crud.verification_queue.list_pending_by_scan(
                session=session,
                scan_id=scan_id,
                limit=20,
            )
        except Exception as e:
            text = str(e).lower()
            if "no such table" in text and ("blackboard" in text or "verificationqueue" in text):
                try:
                    from kodiak.database.engine import init_db

                    await init_db()
                    facts = await crud.blackboard_fact.list_by_scan(
                        session=session,
                        scan_id=scan_id,
                        limit=max(80, safe_limit * 4),
                        entity_types=scoped_entity_types,
                    )
                    edges = await crud.blackboard_edge.list_by_scan(
                        session=session,
                        scan_id=scan_id,
                        limit=max(40, safe_limit * 2),
                    )
                    pending = await crud.verification_queue.list_pending_by_scan(
                        session=session,
                        scan_id=scan_id,
                        limit=20,
                    )
                except Exception as retry_error:
                    logger.warning(f"Failed to build blackboard context for scan {scan_id} after init_db retry: {retry_error}")
                    return ""
            else:
                logger.warning(f"Failed to build blackboard context for scan {scan_id}: {e}")
                return ""

        prioritized_facts = self._sort_facts(self._prioritize_facts(facts, target=target))
        execution_ledger = [fact for fact in prioritized_facts if fact.entity_type == "task"]
        canonical_facts = [fact for fact in prioritized_facts if fact.entity_type != "task"]
        lines: List[str] = ["BLACKBOARD FACTS (shared canonical state):"]

        for fact in canonical_facts[:safe_limit]:
            confidence = str(fact.confidence or "medium").lower()
            verification = str(fact.verification_status or "unverified").lower()
            summary = self._summarize_payload(fact.canonical or {})
            lines.append(
                f"- [{verification}|{confidence}] {fact.entity_type} {fact.entity_key} obs={summary}"
            )

        if execution_ledger:
            lines.append("PEER STRATEGIES & EXECUTION OUTCOMES:")
            for fact in execution_ledger[: min(5, safe_limit)]:
                payload = fact.canonical or {}
                status = str(payload.get("status") or "unknown").lower()
                tool = str(payload.get("tool") or "tool")
                target_label = str(payload.get("target") or "-")
                strategy = self._trim_text(str(payload.get("strategy") or ""), 110)
                outcome = self._trim_text(str(payload.get("outcome") or ""), 80)
                next_step = self._trim_text(str(payload.get("next_step") or ""), 95)
                line = f"- [{status}] {tool} target={target_label}"
                if strategy:
                    line += f" why={strategy}"
                if outcome:
                    line += f" outcome={outcome}"
                if next_step:
                    line += f" next={next_step}"
                lines.append(line)

        if any(et == "attack_path_edge" for et in scoped_entity_types) or role in {"attacker", "analyst", "reporter", "verifier"}:
            if edges:
                lines.append("BLACKBOARD EDGES (attack-path graph):")
                for edge in edges[: min(5, safe_limit)]:
                    confidence = str(edge.confidence or "medium").lower()
                    lines.append(
                        f"- [{confidence}] {edge.src_type}:{edge.src_key} -[{edge.relation}]-> {edge.dst_type}:{edge.dst_key}"
                    )

        if pending:
            lines.append("PENDING VERIFICATION:")
            for item in pending[: min(5, safe_limit)]:
                reason = self._trim_text(item.reason, 120)
                lines.append(f"- {item.entity_type} {item.entity_key} reason={reason}")
        return self._truncate_context("\n".join(lines), max_chars=max_chars)

    async def _upsert_fact_from_event(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        event: BlackboardEvent,
    ) -> Optional[BlackboardFact]:
        existing = await crud.blackboard_fact.get_by_entity(
            session=session,
            scan_id=scan_id,
            entity_type=event.entity_type,
            entity_key=event.entity_key,
        )

        payload = event.payload or {}
        confidence = self._normalize_confidence(str(event.confidence))

        if not existing:
            verification_status = VerificationStatus.UNVERIFIED
            if str(event.status).lower() == "verified":
                verification_status = VerificationStatus.VERIFIED
            fact = BlackboardFact(
                project_id=project_id,
                scan_id=scan_id,
                entity_type=event.entity_type,
                entity_key=event.entity_key,
                canonical=payload,
                confidence=confidence,
                verification_status=verification_status,
                last_event_id=event.id,
                updated_at=datetime.now(timezone.utc),
            )
            return await crud.blackboard_fact.create(session, fact)

        current_signature = self._payload_signature(existing.canonical or {})
        incoming_signature = self._payload_signature(payload)
        current_conf = str(existing.confidence or "medium").lower()
        incoming_conf = str(confidence).lower()

        existing.confidence = self._normalize_confidence(confidence_max(current_conf, incoming_conf))
        existing.last_event_id = event.id
        existing.updated_at = datetime.now(timezone.utc)

        if current_signature != incoming_signature:
            existing.verification_status = VerificationStatus.CONFLICTED
            if CONFIDENCE_RANK.get(incoming_conf, 2) >= CONFIDENCE_RANK.get(current_conf, 2):
                existing.canonical = payload
            await self._enqueue_verification_if_needed(
                session=session,
                project_id=project_id,
                scan_id=scan_id,
                entity_type=existing.entity_type,
                entity_key=existing.entity_key,
                reason=(
                    "Conflicting observations detected for canonical fact "
                    f"(event={event.event_type}, agent={event.agent_id})."
                ),
                requested_by_agent=event.agent_id,
            )
        else:
            if str(event.status).lower() == "verified":
                existing.verification_status = VerificationStatus.VERIFIED
                await self._resolve_pending_verification(
                    session=session,
                    scan_id=scan_id,
                    entity_type=existing.entity_type,
                    entity_key=existing.entity_key,
                )

        return await crud.blackboard_fact.save(session, existing)

    async def _upsert_edge_from_payload(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        payload: Dict[str, Any],
        confidence: str,
        last_event_id: UUID,
    ) -> Optional[BlackboardEdge]:
        src_type = normalize_entity_type(str(payload.get("src_type") or "host"))
        src_key = normalize_entity_key(str(payload.get("src_key") or ""), default_prefix=src_type)
        relation = self._trim_text(str(payload.get("relation") or "RELATED_TO"), 60)
        dst_type = normalize_entity_type(str(payload.get("dst_type") or "host"))
        dst_key = normalize_entity_key(str(payload.get("dst_key") or ""), default_prefix=dst_type)
        conf = self._normalize_confidence(confidence)

        existing = await crud.blackboard_edge.get_by_relation(
            session=session,
            scan_id=scan_id,
            src_type=src_type,
            src_key=src_key,
            relation=relation,
            dst_type=dst_type,
            dst_key=dst_key,
        )
        if not existing:
            edge = BlackboardEdge(
                project_id=project_id,
                scan_id=scan_id,
                src_type=src_type,
                src_key=src_key,
                relation=relation,
                dst_type=dst_type,
                dst_key=dst_key,
                confidence=conf,
                last_event_id=last_event_id,
                updated_at=datetime.now(timezone.utc),
            )
            return await crud.blackboard_edge.create(session, edge)

        existing.confidence = self._normalize_confidence(
            confidence_max(str(existing.confidence or "medium"), str(conf))
        )
        existing.last_event_id = last_event_id
        existing.updated_at = datetime.now(timezone.utc)
        return await crud.blackboard_edge.save(session, existing)

    async def _enqueue_verification_if_needed(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        entity_type: str,
        entity_key: str,
        reason: str,
        requested_by_agent: str,
    ) -> Optional[VerificationQueue]:
        existing = await crud.verification_queue.find_pending(
            session=session,
            scan_id=scan_id,
            entity_type=entity_type,
            entity_key=entity_key,
        )
        if existing:
            return existing

        item = VerificationQueue(
            project_id=project_id,
            scan_id=scan_id,
            entity_type=entity_type,
            entity_key=entity_key,
            reason=self._trim_text(reason, 280),
            requested_by_agent=str(requested_by_agent or "unknown"),
            status=VerificationQueueStatus.PENDING,
        )
        return await crud.verification_queue.create(session, item)

    async def _resolve_pending_verification(
        self,
        session: Any,
        scan_id: UUID,
        entity_type: str,
        entity_key: str,
    ) -> None:
        pending = await crud.verification_queue.find_pending(
            session=session,
            scan_id=scan_id,
            entity_type=entity_type,
            entity_key=entity_key,
        )
        if pending:
            await crud.verification_queue.resolve(
                session=session,
                item_id=pending.id,
                status=VerificationQueueStatus.RESOLVED,
            )

    def _derive_events_for_tool(
        self,
        tool_name: str,
        target: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
        fingerprint: str,
        execution_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        name = str(tool_name or "").strip().lower()
        output_data = result.get("data") if isinstance(result.get("data"), dict) else {}
        events: List[Dict[str, Any]] = []
        default_mapping = TOOL_TO_EVENT.get(name, ("tool_execution", "task"))
        default_event_type, default_entity_type = default_mapping
        success = bool(result.get("success"))
        execution_status = str(execution_context.get("status") or ("success" if success else "failure")).lower()
        strategy = self._trim_text(str(execution_context.get("strategy") or ""), 180)
        outcome = self._trim_text(str(execution_context.get("outcome") or ""), 120)
        next_step = self._trim_text(str(execution_context.get("next_step") or ""), 160)
        error_text = self._trim_text(str(result.get("error") or ""), 220)
        output_excerpt = self._trim_text(str(result.get("output") or ""), 220)

        def append_event(
            event_type: str,
            entity_type: str,
            entity_key: str,
            payload: Dict[str, Any],
            confidence: str = "medium",
            status: str = "observed",
        ) -> None:
            events.append(
                {
                    "event_type": event_type,
                    "entity_type": entity_type,
                    "entity_key": entity_key,
                    "payload": payload,
                    "confidence": confidence,
                    "status": status,
                }
            )

        host = self._extract_host(target)
        if host and success:
            append_event(
                event_type="host_discovered",
                entity_type="host",
                entity_key=f"host:{host}",
                payload={"target": target, "source_tool": name, "fingerprint": fingerprint},
                confidence="medium",
            )

        if name == "nmap":
            parsed = output_data.get("parsed", {})
            for item in (parsed.get("open_ports") or [])[:25]:
                port = item.get("port")
                proto = str(item.get("protocol") or "tcp").lower()
                service = item.get("service")
                append_event(
                    event_type="service_fingerprinted",
                    entity_type="service",
                    entity_key=f"service:{host}:{port}/{proto}",
                    payload={
                        "host": host,
                        "port": port,
                        "protocol": proto,
                        "service": service,
                        "version": item.get("version"),
                        "source_tool": name,
                    },
                    confidence="high" if service else "medium",
                )

        elif name in {"httpx", "ffuf", "katana"}:
            rows = output_data.get("results")
            if not isinstance(rows, list):
                rows = output_data.get("urls") if isinstance(output_data.get("urls"), list) else []
            for row in rows[:60]:
                if isinstance(row, str):
                    url = row
                    status_code = None
                    title = None
                else:
                    url = row.get("url")
                    status_code = row.get("status") or row.get("status_code")
                    title = row.get("title")
                if not url:
                    continue
                append_event(
                    event_type="endpoint_discovered",
                    entity_type="endpoint",
                    entity_key=f"endpoint:{str(url).lower()}",
                    payload={
                        "url": url,
                        "status_code": status_code,
                        "title": title,
                        "source_tool": name,
                    },
                    confidence="medium",
                )

        elif name == "whatweb":
            for row in (output_data.get("results") or [])[:30]:
                target_url = row.get("target")
                if target_url:
                    append_event(
                        event_type="endpoint_discovered",
                        entity_type="endpoint",
                        entity_key=f"endpoint:{str(target_url).lower()}",
                        payload={
                            "url": target_url,
                            "status_code": row.get("http_status"),
                            "source_tool": name,
                        },
                        confidence="medium",
                    )
                techs = row.get("technologies") or []
                for tech in techs[:20]:
                    tech_name = str(tech.get("name") or "").strip()
                    if not tech_name:
                        continue
                    key_host = self._extract_host(target_url or target) or "unknown"
                    append_event(
                        event_type="service_fingerprinted",
                        entity_type="tech",
                        entity_key=f"tech:{key_host}:{tech_name.lower()}",
                        payload={
                            "target": target_url or target,
                            "technology": tech_name,
                            "version": tech.get("version"),
                            "string": tech.get("string"),
                            "source_tool": name,
                        },
                        confidence="high",
                    )

        elif name == "nuclei":
            for finding in (output_data.get("findings") or [])[:60]:
                matched = str(finding.get("matched_at") or target).strip()
                template_id = str(finding.get("template_id") or finding.get("template-id") or "unknown")
                cve_id = str(finding.get("cve_id") or "").strip()
                identifier = cve_id or template_id
                severity = str(finding.get("severity") or "info").lower()
                confidence = "high" if severity in {"critical", "high"} else "medium"
                append_event(
                    event_type="vulnerability_found",
                    entity_type="vulnerability",
                    entity_key=f"vulnerability:{identifier.lower()}@{matched.lower()}",
                    payload={
                        "target": matched,
                        "template_id": template_id,
                        "cve_id": cve_id or None,
                        "name": finding.get("name"),
                        "severity": severity,
                        "risk_level": finding.get("risk_level"),
                        "source_tool": name,
                    },
                    confidence=confidence,
                )

        elif name == "sqlmap":
            url = str(output_data.get("url") or target)
            for vuln in (output_data.get("vulnerabilities") or [])[:40]:
                param = str(vuln.get("parameter") or "unknown").strip()
                append_event(
                    event_type="vulnerability_validated",
                    entity_type="vulnerability",
                    entity_key=f"vulnerability:sqli@{url.lower()}#{param.lower()}",
                    payload={
                        "target": url,
                        "parameter": param,
                        "type": vuln.get("type"),
                        "severity": str(vuln.get("severity") or "high").lower(),
                        "title": vuln.get("title"),
                        "payload": vuln.get("payload"),
                        "source_tool": name,
                    },
                    confidence="high",
                    status="verified",
                )

        elif name == "searchsploit":
            for exploit in (output_data.get("exploits") or [])[:40]:
                exploit_id = str(exploit.get("id") or "unknown").strip()
                append_event(
                    event_type="vulnerability_found",
                    entity_type="vulnerability",
                    entity_key=f"vulnerability:edb-{exploit_id.lower()}",
                    payload={
                        "exploit_id": exploit_id,
                        "title": exploit.get("title"),
                        "platform": exploit.get("platform"),
                        "type": exploit.get("type"),
                        "path": exploit.get("path"),
                        "source_tool": name,
                    },
                    confidence="medium",
                )

        if not events and success:
            append_event(
                event_type=default_event_type,
                entity_type=default_entity_type,
                entity_key=f"{default_entity_type}:{name}:{fingerprint}",
                payload={
                    "tool": name,
                    "target": target,
                    "success": bool(result.get("success")),
                    "error": result.get("error"),
                    "source_tool": name,
                },
                confidence="low",
            )

        append_event(
            event_type="tool_execution",
            entity_type="task",
            entity_key=f"task:{name}:{fingerprint}",
            payload={
                "tool": name,
                "target": target,
                "status": execution_status,
                "success": success,
                "strategy": strategy,
                "outcome": outcome,
                "next_step": next_step,
                "error": error_text,
                "output_excerpt": output_excerpt,
                "args": self._summarize_args(args),
                "fingerprint": fingerprint,
            },
            confidence="medium" if success else "low",
            status=execution_status,
        )
        return events

    def _event_type_for_manual_fact(self, entity_type: str, status: str) -> str:
        verified = str(status or "").strip().lower() == "verified"
        if entity_type == "host":
            return "host_discovered"
        if entity_type in {"service", "tech"}:
            return "service_fingerprinted"
        if entity_type == "endpoint":
            return "endpoint_discovered"
        if entity_type == "credential":
            return "credential_validated" if verified else "credential_found"
        if entity_type == "vulnerability":
            return "vulnerability_validated" if verified else "vulnerability_found"
        return "tool_execution"

    def _validate_manual_payload(self, entity_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Unsupported entity_type '{entity_type}'")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        source = str(payload.get("source_tool") or payload.get("source") or "").strip()
        if not source:
            raise ValueError("payload must include source_tool (or source)")
        encoded = json.dumps(payload, sort_keys=True, default=str)
        if len(encoded) > 4096:
            raise ValueError("payload too large (max 4096 chars serialized)")
        return payload

    def _prioritize_facts(self, facts: List[BlackboardFact], target: Optional[str]) -> List[BlackboardFact]:
        if not target:
            return facts
        needle = str(target).lower()
        high = []
        low = []
        for fact in facts:
            blob = f"{fact.entity_key} {json.dumps(fact.canonical or {}, sort_keys=True, default=str)}".lower()
            if needle in blob:
                high.append(fact)
            else:
                low.append(fact)
        return high + low

    def _sort_facts(self, facts: List[BlackboardFact]) -> List[BlackboardFact]:
        def score(fact: BlackboardFact) -> Tuple[int, int, float]:
            verification = str(getattr(fact, "verification_status", "unverified")).lower()
            verification_score = 2 if verification == "verified" else (1 if verification == "unverified" else 0)
            confidence_score = CONFIDENCE_RANK.get(str(getattr(fact, "confidence", "medium")).lower(), 2)
            updated = getattr(fact, "updated_at", None)
            if hasattr(updated, "timestamp"):
                recency = updated.timestamp()
            elif isinstance(updated, (int, float)):
                recency = float(updated)
            else:
                recency = 0.0
            return verification_score, confidence_score, recency

        return sorted(facts, key=score, reverse=True)

    def _query_needle(self, keyword: Optional[str], target: Optional[str]) -> str:
        for value in (keyword, target):
            token = str(value or "").strip().lower()
            if token:
                return token
        return ""

    def _truncate_context(self, text: str, max_chars: int) -> str:
        if max_chars <= 0:
            return text
        if len(text) <= max_chars:
            return text
        clipped = text[: max(0, max_chars - 3)]
        if "\n" in clipped:
            clipped = clipped.rsplit("\n", 1)[0]
        return clipped + "..."

    def _extract_host(self, value: Optional[str]) -> str:
        if not value:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = parsed.netloc or parsed.path
        host = host.split("/")[0].strip().lower()
        return host

    def _payload_signature(self, payload: Dict[str, Any]) -> str:
        try:
            return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        except Exception:
            return str(payload)

    def _normalize_confidence(self, confidence: str) -> ConfidenceLevel:
        normalized = str(confidence or "medium").lower().strip()
        if normalized == "low":
            return ConfidenceLevel.LOW
        if normalized == "high":
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM

    def _summarize_payload(self, payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict) or not payload:
            return "-"
        preferred_keys = (
            "tool",
            "status",
            "outcome",
            "url",
            "target",
            "status_code",
            "severity",
            "technology",
            "service",
            "port",
            "parameter",
            "name",
            "title",
            "exploit_id",
            "relation",
        )
        parts: List[str] = []
        for key in preferred_keys:
            if key in payload and payload[key] not in (None, "", [], {}):
                parts.append(f"{key}={payload[key]}")
            if len(parts) >= 3:
                break
        if not parts:
            for key, value in payload.items():
                if isinstance(value, (str, int, float, bool)):
                    parts.append(f"{key}={value}")
                if len(parts) >= 3:
                    break
        return self._trim_text(", ".join(parts) if parts else "-", 150)

    def _summarize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(args, dict):
            return {}
        summary: Dict[str, Any] = {}
        for key in ("target", "url", "domain", "query", "tags", "severity", "wordlist", "method"):
            value = args.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, str):
                summary[key] = self._trim_text(value, 140)
            else:
                summary[key] = value
            if len(summary) >= 6:
                break
        if not summary:
            summary["keys"] = sorted([str(k) for k in list(args.keys())[:8]])
        return summary

    def _trim_text(self, text: Optional[str], limit: int = 180) -> str:
        cleaned = " ".join((text or "").split()).strip()
        if len(cleaned) > limit:
            return cleaned[: limit - 3] + "..."
        return cleaned
