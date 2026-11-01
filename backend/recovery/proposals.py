import time
import uuid
from typing import Optional, Dict, Any
from backend.schemas import ActionProposal, RootCauseCandidate

class ProposalEngine:
    def generate_proposal(self, incident_id: str, top_candidate: RootCauseCandidate) -> ActionProposal:
        s_id = top_candidate.serviceId

        if "redis-replica" in s_id or s_id == "redis-cache":
            # Cache replica degradation: reroute canary to healthy replica B
            target = "redis-replica-a" if "a" in s_id else "redis-cache"
            return ActionProposal(
                id=str(uuid.uuid4()),
                incidentId=incident_id,
                actionType="reroute_canary",
                targetId=target,
                resourceSelector={"service": "redis-cache", "active_replica": target},
                changeParameters={
                    "source_replica": "redis-replica-a",
                    "destination_replica": "redis-replica-b",
                    "canary_percent": 10.0,
                    "max_canary_percent": 100.0
                },
                expectedBenefit="Isolates slow/partitioned cache replica and routes traffic to warm replica-b",
                potentialHarm="Increased connection load on replica-b (mitigated by 10% canary start)",
                reversibility="FULLY_REVERSIBLE",
                undoDescription="Restore 100% traffic allocation to replica-a",
                priorRevisionConfig={"traffic_allocation": {"redis-replica-a": 100.0, "redis-replica-b": 0.0}},
                canaryConstraints={"initial_percent": 10.0, "step_increments": [10.0, 25.0, 50.0, 100.0]},
                expiry=time.time() + 180.0
            )

        elif s_id == "payment-service":
            # Deployment regression on payment-service
            return ActionProposal(
                id=str(uuid.uuid4()),
                incidentId=incident_id,
                actionType="rollback_release",
                targetId="payment-service",
                resourceSelector={"app": "payment-service", "deployment": "payment-v2"},
                changeParameters={"target_revision": "v1.4.2", "current_revision": "v2.0.0-rc1"},
                expectedBenefit="Reverts bad binary revision to proven baseline v1.4.2",
                potentialHarm="Temporarily loses v2 feature enhancements during rollback window",
                reversibility="FULLY_REVERSIBLE",
                undoDescription="Re-deploy revision v2.0.0-rc1 if rollback unneeded",
                priorRevisionConfig={"image": "registry.civicguard.gov/payment-service:v2.0.0-rc1"},
                canaryConstraints={"initial_percent": 10.0, "step_increments": [10.0, 25.0, 50.0, 100.0]},
                expiry=time.time() + 180.0
            )

        elif s_id in ("identity-service", "eligibility-service", "benefits-engine"):
            # Stateless scaling proposal
            return ActionProposal(
                id=str(uuid.uuid4()),
                incidentId=incident_id,
                actionType="scale_up",
                targetId=s_id,
                resourceSelector={"app": s_id},
                changeParameters={"replica_delta": 2, "max_replicas": 6},
                expectedBenefit="Expands horizontal worker capacity to relieve queue latency",
                potentialHarm="Slight increase in database connection pool saturation",
                reversibility="FULLY_REVERSIBLE",
                undoDescription="Scale down replicas by delta 2 back to original count",
                priorRevisionConfig={"replicas": 2},
                canaryConstraints={"initial_percent": 10.0, "step_increments": [10.0, 25.0, 50.0, 100.0]},
                expiry=time.time() + 180.0
            )

        else:
            return ActionProposal(
                id=str(uuid.uuid4()),
                incidentId=incident_id,
                actionType="NO_ACTION",
                targetId=s_id,
                resourceSelector={"service": s_id},
                changeParameters={},
                expectedBenefit="No safe automated action identified; escalate to on-call SRE",
                potentialHarm="None",
                reversibility="N/A",
                undoDescription="N/A",
                priorRevisionConfig={},
                canaryConstraints={},
                expiry=time.time() + 180.0
            )

proposal_engine = ProposalEngine()

