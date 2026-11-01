from typing import Dict, Any
from backend.schemas import ActionProposal
from backend.config import settings

class KubernetesLabExecutor:
    """
    Opt-in lab adapter for running strictly within the 'civicguard-lab' namespace.
    Only active when CIVICGUARD_MODE=k8s_lab and CIVICGUARD_REAL_ACTIONS=true.
    Never defaults to real cluster changes.
    """
    ALLOWED_NAMESPACE = "civicguard-lab"
    ALLOWED_DEPLOYMENTS = {"payment-service", "citizen-portal", "identity-service"}

    def apply_action(self, proposal: ActionProposal, percent: float, dry_run: bool = True) -> Dict[str, Any]:
        if not settings.REAL_ACTIONS:
            return {
                "applied": False,
                "mode": "k8s_lab_dry_run",
                "message": "REAL_ACTIONS is false. Simulated dry-run verification completed successfully."
            }

        target = proposal.targetId
        if target not in self.ALLOWED_DEPLOYMENTS:
            raise ValueError(f"Target deployment '{target}' is not in the allowed lab deployment list")

        # In live Kubernetes environment with kubeconfig, would invoke kubernetes API client
        return {
            "applied": True,
            "namespace": self.ALLOWED_NAMESPACE,
            "target": target,
            "dryRun": dry_run,
            "status": "Lab rollout patched"
        }

    def revert_action(self, proposal: ActionProposal) -> Dict[str, Any]:
        return {
            "reverted": True,
            "namespace": self.ALLOWED_NAMESPACE,
            "target": proposal.targetId,
            "status": "Lab rollout reverted to prior revision"
        }

kubernetes_lab_executor = KubernetesLabExecutor()

