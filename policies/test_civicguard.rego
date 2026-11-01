package civicguard.policy_test

import data.civicguard.policy

test_allow_valid_canary {
    input := {
        "action_type": "reroute_canary",
        "target_id": "redis-replica-a",
        "root_cause_score": 85.0,
        "min_rca_threshold": 70.0,
        "evidence_age_seconds": 12.0,
        "max_evidence_ttl": 60.0,
        "rollback_plan_present": true,
        "predicted_blast_radius": 2,
        "max_blast_radius": 5,
        "active_remediations_on_target": 0,
        "mode": "simulation"
    }
    policy.allow with input as input
    policy.decision with input as input == "ALLOW"
}

test_deny_unsupported_action {
    input := {
        "action_type": "arbitrary_shell_command",
        "target_id": "redis-replica-a",
        "root_cause_score": 90.0,
        "min_rca_threshold": 70.0,
        "evidence_age_seconds": 5.0,
        "max_evidence_ttl": 60.0,
        "rollback_plan_present": true,
        "predicted_blast_radius": 1,
        "max_blast_radius": 5,
        "active_remediations_on_target": 0,
        "mode": "simulation"
    }
    not policy.allow with input as input
    policy.decision with input as input == "DENY"
}

test_deny_restart_on_stateful_node {
    input := {
        "action_type": "restart_replica",
        "target_id": "redis-cache",
        "root_cause_score": 95.0,
        "min_rca_threshold": 70.0,
        "evidence_age_seconds": 5.0,
        "max_evidence_ttl": 60.0,
        "rollback_plan_present": true,
        "predicted_blast_radius": 1,
        "max_blast_radius": 5,
        "active_remediations_on_target": 0,
        "mode": "simulation"
    }
    not policy.allow with input as input
    policy.decision with input as input == "DENY"
}

test_human_approval_for_payment_service {
    input := {
        "action_type": "rollback_release",
        "target_id": "payment-service",
        "root_cause_score": 92.0,
        "min_rca_threshold": 70.0,
        "evidence_age_seconds": 15.0,
        "max_evidence_ttl": 60.0,
        "rollback_plan_present": true,
        "predicted_blast_radius": 1,
        "max_blast_radius": 5,
        "active_remediations_on_target": 0,
        "mode": "simulation"
    }
    policy.decision with input as input == "HUMAN_APPROVAL_REQUIRED"
}

