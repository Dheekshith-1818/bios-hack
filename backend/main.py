import os
import time
import json
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import settings
from backend.schemas import (
    MetricEvent, TraceSpan, LogEvent, Envelope, Incident, ActionProposal
)
from backend.graph.live_graph import live_graph
from backend.telemetry.aggregate import telemetry_aggregator
from backend.telemetry.ingest import telemetry_ingest
from backend.incidents.lifecycle import incident_lifecycle
from backend.incidents.audit import audit_service
from backend.simulator.engine import sim_engine
from backend.clock import sim_clock
from backend.evaluation.scoring import benchmark_evaluator

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()

# Forward simulation ticks to websockets
def on_sim_tick(tick_data: Dict[str, Any]):
    asyncio.create_task(manager.broadcast({
        "type": "telemetry_update",
        "data": tick_data,
        "graph_version": live_graph.graph.version,
        "active_incidents": len(incident_lifecycle.active_incidents)
    }))

@asynccontextmanager
async def lifespan(app: FastAPI):
    sim_engine.register_broadcast_callback(on_sim_tick)
    if os.getenv("TESTING") != "true":
        await sim_engine.start()
    yield
    if os.getenv("TESTING") != "true":
        await sim_engine.stop()

app = FastAPI(
    title="CivicGuard Autopilot",
    description="Proof-Carrying Self-Healing Digital Public Infrastructure Control Plane",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Root: Serve single frontend/index.html ----------------

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = settings.FRONTEND_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>CivicGuard Autopilot</h1><p>Frontend file <code>frontend/index.html</code> is loading...</p>",
            status_code=200
        )
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content)

# ---------------- Authentication & Role Management ----------------

DEMO_USERS = {
    "sre_lead": {
        "password": "civicguard2026",
        "role": "operator",
        "displayName": "SRE Operations Lead",
        "avatar": "🛡️"
    },
    "auditor": {
        "password": "audit2026",
        "role": "viewer",
        "displayName": "Public Infrastructure Auditor",
        "avatar": "🔍"
    }
}

ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    user = DEMO_USERS.get(req.username)
    if user and user["password"] == req.password:
        import uuid
        token = f"cg-token-{uuid.uuid4()}"
        session_data = {
            "username": req.username,
            "role": user["role"],
            "displayName": user["displayName"],
            "avatar": user["avatar"],
            "token": token
        }
        ACTIVE_SESSIONS[token] = session_data
        audit_service.log_event(
            event_type="OPERATOR_AUTHENTICATED",
            actor=req.username,
            payload={"role": user["role"], "displayName": user["displayName"]}
        )
        return {"success": True, "user": session_data}
    
    # Generic fallback login for testing or quick access
    if req.username and req.password:
        role = "operator" if "operator" in req.username.lower() or "sre" in req.username.lower() else "viewer"
        import uuid
        token = f"cg-token-{uuid.uuid4()}"
        session_data = {
            "username": req.username,
            "role": role,
            "displayName": req.username.capitalize(),
            "avatar": "👤",
            "token": token
        }
        ACTIVE_SESSIONS[token] = session_data
        return {"success": True, "user": session_data}

    raise HTTPException(status_code=401, detail="Invalid username or password")

@app.get("/api/auth/me")
async def get_current_user(token: Optional[str] = Query(default=None)):
    if token and token in ACTIVE_SESSIONS:
        return {"authenticated": True, "user": ACTIVE_SESSIONS[token]}
    return {"authenticated": False, "user": None}

@app.post("/api/auth/logout")
async def logout(token: Optional[str] = Query(default=None)):
    if token and token in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS.pop(token)
    return {"success": True}

# ---------------- Core API Routes ----------------

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "CivicGuard Autopilot",
        "version": "1.0.0",
        "mode": settings.MODE,
        "real_actions_allowed": settings.REAL_ACTIONS,
        "clock_speed": sim_clock.speed,
        "is_paused": sim_clock.is_paused,
        "time": time.time()
    }

@app.get("/api/config/public")
async def get_public_config():
    return {
        "env": settings.ENV,
        "mode": settings.MODE,
        "realActions": settings.REAL_ACTIONS,
        "canarySampleWindows": settings.CANARY_SAMPLE_WINDOWS,
        "maxBlastRadius": settings.MAX_BLAST_RADIUS,
        "rcaConfidenceThreshold": settings.RCA_CONFIDENCE_THRESHOLD,
        "evidenceTtlSeconds": settings.EVIDENCE_TTL_SECONDS
    }

@app.get("/api/state")
async def get_full_state():
    return {
        "serverTime": sim_clock.now(),
        "mode": settings.MODE,
        "realActions": settings.REAL_ACTIONS,
        "activeScenario": sim_engine.scenarios.active_scenario_name,
        "judgeMode": sim_engine.judge_mode_active,
        "judgeStep": sim_engine.judge_mode_step,
        "clockSpeed": sim_clock.speed,
        "isPaused": sim_clock.is_paused,
        "graph": live_graph.get_snapshot().model_dump(),
        "activeIncidents": [inc.model_dump() for inc in incident_lifecycle.active_incidents.values()],
        "summaries": telemetry_aggregator.get_all_summaries(),
        "evaluation": benchmark_evaluator.compute_summary()
    }

@app.get("/api/graph")
async def get_graph():
    return live_graph.get_snapshot()

@app.get("/api/telemetry/services/{service_id}")
async def get_service_telemetry(service_id: str):
    summary = telemetry_aggregator.get_service_summary(service_id)
    logs = telemetry_aggregator.get_recent_logs(service_id, limit=20)
    spans = telemetry_aggregator.get_recent_spans(service_id, limit=20)
    return {
        "serviceId": service_id,
        "summary": summary,
        "logs": [l.model_dump() for l in logs],
        "spans": [s.model_dump() for s in spans]
    }

@app.get("/api/telemetry/traces")
async def get_traces(service_id: Optional[str] = None, limit: int = Query(default=50, ge=1, le=200)):
    spans = telemetry_aggregator.get_recent_spans(service_id, limit=limit)
    return [s.model_dump() for s in spans]

@app.get("/api/telemetry/logs")
async def get_logs(service_id: Optional[str] = None, limit: int = Query(default=50, ge=1, le=200)):
    logs = telemetry_aggregator.get_recent_logs(service_id, limit=limit)
    return [l.model_dump() for l in logs]

@app.post("/api/telemetry/metrics")
async def ingest_metric(metric: MetricEvent):
    telemetry_ingest.ingest_metric(metric)
    return {"status": "ok", "metricId": metric.id}

@app.post("/api/telemetry/spans")
async def ingest_span(span: TraceSpan):
    telemetry_ingest.ingest_span(span)
    return {"status": "ok", "spanId": span.spanId}

@app.post("/api/telemetry/logs")
async def ingest_log(log: LogEvent):
    telemetry_ingest.ingest_log(log)
    return {"status": "ok", "logId": log.id}

# ---------------- Incidents & Diagnosis ----------------

@app.get("/api/incidents")
async def get_incidents():
    return [inc.model_dump() for inc in incident_lifecycle.incident_history]

@app.get("/api/incidents/{incident_id}")
async def get_incident_detail(incident_id: str):
    inc = incident_lifecycle.active_incidents.get(incident_id)
    if not inc:
        from backend.store import store
        inc = store.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    return inc.model_dump()

@app.get("/api/incidents/{incident_id}/rca")
async def get_incident_rca(incident_id: str):
    inc = incident_lifecycle.active_incidents.get(incident_id)
    if not inc or not inc.probableRootCauses:
        raise HTTPException(status_code=404, detail=f"RCA not available for incident '{incident_id}'")
    return [c.model_dump() for c in inc.probableRootCauses]

@app.get("/api/incidents/{incident_id}/cascade")
async def get_incident_cascade(incident_id: str):
    inc = incident_lifecycle.active_incidents.get(incident_id)
    if not inc or not inc.currentProof:
        raise HTTPException(status_code=404, detail=f"Cascade prediction not available for incident '{incident_id}'")
    return inc.currentProof.cascadePrediction.model_dump()

@app.get("/api/incidents/{incident_id}/proof")
async def get_incident_proof(incident_id: str):
    inc = incident_lifecycle.active_incidents.get(incident_id)
    if not inc or not inc.currentProof:
        raise HTTPException(status_code=404, detail=f"Remediation proof not found for incident '{incident_id}'")
    return inc.currentProof.model_dump()

# ---------------- Remediations & Policy ----------------

@app.post("/api/remediations/{incident_id}/propose")
async def propose_remediation(incident_id: str):
    inc = incident_lifecycle.active_incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")
    onset = {s: inc.startTs for s in inc.scope}
    proof = incident_lifecycle.diagnose_and_propose(incident_id, onset)
    if not proof:
        raise HTTPException(status_code=400, detail="Unable to generate proof: insufficient diagnostic data")
    return proof.model_dump()

class ApprovalRequest(BaseModel):
    operatorId: str = "sre-operator"

@app.post("/api/remediations/{incident_id}/approve")
async def approve_remediation(incident_id: str, req: ApprovalRequest):
    res = incident_lifecycle.approve_action(incident_id, operator_id=req.operatorId)
    if not res.get("success"):
        raise HTTPException(status_code=403, detail=res)
    return res

class RollbackRequest(BaseModel):
    reason: str = "Manual operator override"

@app.post("/api/remediations/{incident_id}/rollback")
async def trigger_rollback(incident_id: str, req: RollbackRequest):
    res = incident_lifecycle.trigger_rollback(incident_id, reason=req.reason)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res)
    return res

# ---------------- Simulations & Judge Controls ----------------

@app.post("/api/simulations/{scenario_id}/start")
async def start_scenario(scenario_id: str):
    try:
        res = sim_engine.scenarios.start_scenario(scenario_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/simulations/reset")
async def reset_simulation():
    sim_engine.reset()
    live_graph.reset()
    return {"status": "reset_complete"}

@app.post("/api/simulations/judge-mode/start")
async def start_judge_mode():
    sim_engine.start_judge_mode()
    return {"status": "judge_mode_started", "speed": sim_clock.speed}

@app.post("/api/simulations/pause")
async def pause_simulation():
    sim_clock.pause()
    return {"is_paused": True}

@app.post("/api/simulations/resume")
async def resume_simulation():
    sim_clock.resume()
    return {"is_paused": False}

class SpeedRequest(BaseModel):
    speed: float

@app.post("/api/simulations/speed")
async def set_speed(req: SpeedRequest):
    if req.speed <= 0 or req.speed > 10.0:
        raise HTTPException(status_code=400, detail="Speed must be between 0.1 and 10.0")
    sim_clock.set_speed(req.speed)
    return {"speed": req.speed}

# ---------------- Audit Ledger ----------------

@app.get("/api/audit")
async def get_audit_trail(limit: int = Query(default=100, ge=1, le=500)):
    events = audit_service.get_events(limit=limit)
    return [e.model_dump() for e in events]

@app.get("/api/audit/verify")
async def verify_audit_trail():
    return audit_service.verify_ledger()

@app.get("/api/audit/export")
async def export_audit_trail():
    events = audit_service.get_events(limit=500)
    return Response(
        content=json.dumps([e.model_dump() for e in events], indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=civicguard-audit-ledger.json"}
    )

# ---------------- Evaluation Benchmark ----------------

@app.get("/api/evaluation/latest")
async def get_evaluation_summary():
    return benchmark_evaluator.compute_summary()

@app.get("/api/evaluation/export")
async def export_evaluation(format: str = Query(default="csv", pattern="^(csv|json)$")):
    if format == "json":
        summary = benchmark_evaluator.compute_summary()
        return Response(
            content=json.dumps(summary, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=civicguard-evaluation.json"}
        )
    else:
        csv_content = benchmark_evaluator.export_csv()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=civicguard-evaluation.csv"}
        )

# ---------------- WebSocket ----------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # Send immediate state snapshot on connect
    try:
        await websocket.send_json({
            "type": "state_snapshot",
            "serverTime": sim_clock.now(),
            "graph": live_graph.get_snapshot().model_dump(),
            "activeIncidents": [inc.model_dump() for inc in incident_lifecycle.active_incidents.values()]
        })
        while True:
            data = await websocket.receive_text()
            # Client ping/pong or message
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong", "time": time.time()})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
