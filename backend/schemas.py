from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import time
import uuid

# Base envelopes
class Envelope(BaseModel):
    schemaVersion: str = "1.0.0"
    sequence: int = 0
    serverTime: float = Field(default_factory=lambda: time.time())
    mode: str = "simulation"
    payload: Any

class MetricEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=lambda: time.time())
    serviceId: str
    name: str
    value: float
    unit: str
    labels: Dict[str, str] = Field(default_factory=dict)
    source: str = "simulator"

class TraceSpan(BaseModel):
    traceId: str
    spanId: str
    parentSpanId: Optional[str] = None
    startTs: float
    endTs: float
    duration_ms: float = 0.0
    serviceId: str
    peerServiceId: Optional[str] = None
    operation: str
    status: str = "OK"  # "OK" or "ERROR"
    attributes: Dict[str, Any] = Field(default_factory=dict)

class LogEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=lambda: time.time())
    serviceId: str
    severity: str = "INFO"  # INFO, WARN, ERROR, CRITICAL
    eventType: str
    message: str
    traceId: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class GraphNode(BaseModel):
    id: str
    labels: Dict[str, str] = Field(default_factory=dict)
    evidenceCount: int = 0
    lastSeen: float = Field(default_factory=lambda: time.time())
    healthStatus: str = "HEALTHY"  # HEALTHY, OBSERVING, ANOMALOUS, ROOT_CAUSE, RECOVERING
    normalizedMetrics: Dict[str, float] = Field(default_factory=dict)
    recentChanges: List[str] = Field(default_factory=list)
    stale: bool = False

class GraphEdge(BaseModel):
    id: str
    caller: str
    callee: str
    callCount: int = 0
    lastSeen: float = Field(default_factory=lambda: time.time())
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    errorRate: float = 0.0
    confidence: float = 1.0
    stale: bool = False

class TopologySnapshot(BaseModel):
    version: int
    timestamp: float
    nodes: List[GraphNode]
    edges: List[GraphEdge]

class SubscoreBreakdown(BaseModel):
    temporal_precedence: float = 0.0
    anomaly_magnitude: float = 0.0
    downstream_impact: float = 0.0
    trace_path_evidence: float = 0.0
    structured_log_evidence: float = 0.0
    topology_explanation: float = 0.0

class RootCauseCandidate(BaseModel):
    serviceId: str
    score: float # 0 - 100
    subscoreBreakdown: SubscoreBreakdown
    supportingEvidenceRefs: List[str] = Field(default_factory=list)
    contradictoryEvidenceRefs: List[str] = Field(default_factory=list)
    explanation: str

class CascadeNodeImpact(BaseModel):
    serviceId: str
    propagationRisk: float
    expectedLatencyIncreasePct: float
    expectedErrorRate: float
    pathFromRoot: List[str]

class CascadePrediction(BaseModel):
    startingNode: str
    predictedImpact: Dict[str, CascadeNodeImpact] = Field(default_factory=dict)
    dependencyPaths: List[List[str]] = Field(default_factory=list)
    overallPropagationRisk: float = 0.0
    modelAssumptions: str = "Deterministic reverse-dependency multi-hop propagation with traffic-weighted decay"
    generatedAt: float = Field(default_factory=lambda: time.time())

class ActionProposal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incidentId: str
    actionType: str  # reroute_canary, rollback_release, scale_up, disable_feature_flag, restart_replica, NO_ACTION
    targetId: str
    resourceSelector: Dict[str, str] = Field(default_factory=dict)
    changeParameters: Dict[str, Any] = Field(default_factory=dict)
    expectedBenefit: str = "Restore service health and bounded performance"
    potentialHarm: str = "Transient load or dependency shift bounded by canary"
    reversibility: str = "FULLY_REVERSIBLE"
    undoDescription: str = "Revert to prior configuration state"
    priorRevisionConfig: Dict[str, Any] = Field(default_factory=dict)
    canaryConstraints: Dict[str, Any] = Field(default_factory=dict)
    expiry: float = 0.0

class PolicyDecision(BaseModel):
    decision: str  # ALLOW, DENY, HUMAN_APPROVAL_REQUIRED
    reasons: List[str] = Field(default_factory=list)
    policyVersion: str = "1.0.0"
    missingPrerequisites: List[str] = Field(default_factory=list)

class CanaryObservation(BaseModel):
    actionId: str
    percent: float # 10, 25, 50, 100
    windowsObserved: int
    controlMetrics: Dict[str, float]
    treatmentMetrics: Dict[str, float]
    thresholds: Dict[str, float]
    guardrailPass: bool
    safetyStatus: str  # SAFE_TO_CANARY, CANARY_EVALUATING, ROLLED_BACK, PROMOTING, RECOVERED, ESCALATED

class RemediationProof(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    incidentId: str
    evidenceRefs: List[str]
    rootCauseCandidates: List[RootCauseCandidate]
    graphVersion: int
    cascadePrediction: CascadePrediction
    policyVersion: str
    policyDecision: PolicyDecision
    permittedScope: str
    actionProposal: ActionProposal
    guardrailThresholds: Dict[str, float]
    baselineMetrics: Dict[str, float]
    canaryStartTs: Optional[float] = None
    canaryEndTs: Optional[float] = None
    rollbackPlan: Dict[str, Any]
    ttlSeconds: float = 120.0
    createdAt: float = Field(default_factory=lambda: time.time())
    operator: str = "civicguard-autonomous-agent"
    contentHash: str = ""
    explanation: str = ""

class Incident(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "OBSERVING"  # OBSERVING, SUSPECTED, CONFIRMED, DIAGNOSING, PROPOSED, POLICY_CHECKED, CANARY_RUNNING, CANARY_PASSED, PROMOTING, RECOVERED, SUPPRESSED, POLICY_DENIED, CANARY_FAILED, ROLLING_BACK, ROLLED_BACK, ESCALATED
    symptoms: List[str] = Field(default_factory=list)
    startTs: float = Field(default_factory=lambda: time.time())
    detectedAt: Optional[float] = None
    confirmedAt: Optional[float] = None
    identifiedAt: Optional[float] = None
    recoveredAt: Optional[float] = None
    probableRootCauses: List[RootCauseCandidate] = Field(default_factory=list)
    scope: List[str] = Field(default_factory=list)
    severity: str = "MEDIUM" # LOW, MEDIUM, HIGH, CRITICAL
    evidenceRefs: List[str] = Field(default_factory=list)
    currentProof: Optional[RemediationProof] = None
    activeAction: Optional[ActionProposal] = None
    canaryObservation: Optional[CanaryObservation] = None

class AuditEvent(BaseModel):
    sequence: int
    timestamp: float = Field(default_factory=lambda: time.time())
    eventType: str
    actor: str = "system"
    incidentId: Optional[str] = None
    actionId: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    previousHash: str = "GENESIS"
    eventHash: str = ""
