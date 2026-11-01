from typing import Dict, Any
from backend.schemas import ActionProposal
from backend.recovery.simulator_executor import simulator_executor
from backend.recovery.kubernetes_lab_executor import kubernetes_lab_executor
from backend.config import settings

class UnifiedExecutor:
    def apply_action(self, proposal: ActionProposal, percent: float) -> Dict[str, Any]:
        if settings.MODE == "k8s_lab":
            return kubernetes_lab_executor.apply_action(proposal, percent)
        return simulator_executor.apply_action(proposal, percent)

    def revert_action(self, proposal: ActionProposal) -> Dict[str, Any]:
        if settings.MODE == "k8s_lab":
            return kubernetes_lab_executor.revert_action(proposal)
        return simulator_executor.revert_action(proposal)

unified_executor = UnifiedExecutor()

