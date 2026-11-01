import sqlite3
import json
import hashlib
import hmac
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
from backend.config import settings
from backend.schemas import AuditEvent, Incident, TopologySnapshot

class Storage:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.SQLITE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                sequence INTEGER PRIMARY KEY,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                incident_id TEXT,
                action_id TEXT,
                payload TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                symptoms TEXT NOT NULL,
                start_ts REAL NOT NULL,
                detected_at REAL,
                confirmed_at REAL,
                identified_at REAL,
                recovered_at REAL,
                probable_root_causes TEXT,
                scope TEXT,
                severity TEXT,
                evidence_refs TEXT,
                proof TEXT,
                active_action TEXT,
                canary_observation TEXT
            );
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS topology_snapshots (
                version INTEGER PRIMARY KEY,
                timestamp REAL NOT NULL,
                nodes TEXT NOT NULL,
                edges TEXT NOT NULL
            );
            """)
            conn.commit()

    def compute_hash(self, seq: int, ts: float, event_type: str, actor: str, payload_str: str, prev_hash: str) -> str:
        data = f"{seq}|{ts:.4f}|{event_type}|{actor}|{payload_str}|{prev_hash}"
        return hmac.new(settings.AUDIT_SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()

    def append_audit_event(self, event_type: str, actor: str, incident_id: Optional[str], action_id: Optional[str], payload: Dict[str, Any]) -> AuditEvent:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sequence, event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                next_seq = row["sequence"] + 1
                prev_hash = row["event_hash"]
            else:
                next_seq = 1
                prev_hash = "GENESIS"

            ts = time.time()
            payload_str = json.dumps(payload, sort_keys=True)
            ev_hash = self.compute_hash(next_seq, ts, event_type, actor, payload_str, prev_hash)

            cursor.execute("""
            INSERT INTO audit_events (sequence, timestamp, event_type, actor, incident_id, action_id, payload, previous_hash, event_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (next_seq, ts, event_type, actor, incident_id, action_id, payload_str, prev_hash, ev_hash))
            conn.commit()

            return AuditEvent(
                sequence=next_seq,
                timestamp=ts,
                eventType=event_type,
                actor=actor,
                incidentId=incident_id,
                actionId=action_id,
                payload=payload,
                previousHash=prev_hash,
                eventHash=ev_hash
            )

    def verify_audit_chain(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_events ORDER BY sequence ASC")
            rows = cursor.fetchall()
            
            if not rows:
                return {"valid": True, "total_events": 0, "message": "Audit log is empty"}

            prev_hash = "GENESIS"
            for row in rows:
                seq = row["sequence"]
                ts = row["timestamp"]
                ev_type = row["event_type"]
                actor = row["actor"]
                payload_str = row["payload"]
                recorded_prev = row["previous_hash"]
                recorded_hash = row["event_hash"]

                if recorded_prev != prev_hash:
                    return {
                        "valid": False,
                        "broken_sequence": seq,
                        "reason": f"Previous hash mismatch at sequence {seq}: expected {prev_hash}, found {recorded_prev}"
                    }

                expected_hash = self.compute_hash(seq, ts, ev_type, actor, payload_str, recorded_prev)
                if expected_hash != recorded_hash:
                    return {
                        "valid": False,
                        "broken_sequence": seq,
                        "reason": f"Event hash mismatch at sequence {seq}: integrity compromised"
                    }
                prev_hash = recorded_hash

            return {"valid": True, "total_events": len(rows), "latest_hash": prev_hash}

    def get_audit_events(self, limit: int = 100) -> List[AuditEvent]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_events ORDER BY sequence DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            events = []
            for r in rows:
                events.append(AuditEvent(
                    sequence=r["sequence"],
                    timestamp=r["timestamp"],
                    eventType=r["event_type"],
                    actor=r["actor"],
                    incidentId=r["incident_id"],
                    actionId=r["action_id"],
                    payload=json.loads(r["payload"]),
                    previousHash=r["previous_hash"],
                    eventHash=r["event_hash"]
                ))
            return events

    def save_incident(self, inc: Incident):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO incidents (
                id, status, symptoms, start_ts, detected_at, confirmed_at, identified_at, recovered_at,
                probable_root_causes, scope, severity, evidence_refs, proof, active_action, canary_observation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inc.id,
                inc.status,
                json.dumps(inc.symptoms),
                inc.startTs,
                inc.detectedAt,
                inc.confirmedAt,
                inc.identifiedAt,
                inc.recoveredAt,
                json.dumps([c.model_dump() for c in inc.probableRootCauses]),
                json.dumps(inc.scope),
                inc.severity,
                json.dumps(inc.evidenceRefs),
                json.dumps(inc.currentProof.model_dump()) if inc.currentProof else None,
                json.dumps(inc.activeAction.model_dump()) if inc.activeAction else None,
                json.dumps(inc.canaryObservation.model_dump()) if inc.canaryObservation else None
            ))
            conn.commit()

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def get_all_incidents(self) -> List[Incident]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM incidents ORDER BY start_ts DESC")
            rows = cursor.fetchall()
            return [self._row_to_incident(r) for r in rows]

    def _row_to_incident(self, r: sqlite3.Row) -> Incident:
        from backend.schemas import RootCauseCandidate, RemediationProof, ActionProposal, CanaryObservation
        return Incident(
            id=r["id"],
            status=r["status"],
            symptoms=json.loads(r["symptoms"]),
            startTs=r["start_ts"],
            detectedAt=r["detected_at"],
            confirmedAt=r["confirmed_at"],
            identifiedAt=r["identified_at"],
            recoveredAt=r["recovered_at"],
            probableRootCauses=[RootCauseCandidate(**c) for c in json.loads(r["probable_root_causes"] or "[]")],
            scope=json.loads(r["scope"] or "[]"),
            severity=r["severity"] or "MEDIUM",
            evidenceRefs=json.loads(r["evidence_refs"] or "[]"),
            currentProof=RemediationProof(**json.loads(r["proof"])) if r["proof"] else None,
            activeAction=ActionProposal(**json.loads(r["active_action"])) if r["active_action"] else None,
            canaryObservation=CanaryObservation(**json.loads(r["canary_observation"])) if r["canary_observation"] else None
        )

    def save_topology_snapshot(self, snapshot: TopologySnapshot):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO topology_snapshots (version, timestamp, nodes, edges)
            VALUES (?, ?, ?, ?)
            """, (
                snapshot.version,
                snapshot.timestamp,
                json.dumps([n.model_dump() for n in snapshot.nodes]),
                json.dumps([e.model_dump() for e in snapshot.edges])
            ))
            conn.commit()

    def get_latest_topology_snapshot(self) -> Optional[TopologySnapshot]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM topology_snapshots ORDER BY version DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            from backend.schemas import GraphNode, GraphEdge
            return TopologySnapshot(
                version=row["version"],
                timestamp=row["timestamp"],
                nodes=[GraphNode(**n) for n in json.loads(row["nodes"])],
                edges=[GraphEdge(**e) for e in json.loads(row["edges"])]
            )

    def clear(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM audit_events")
            cursor.execute("DELETE FROM incidents")
            cursor.execute("DELETE FROM topology_snapshots")
            conn.commit()

    def close(self):
        # Explicit garbage collection of connection references
        import gc
        gc.collect()

store = Storage()
