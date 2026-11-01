package civicguard.policy

default allow = false
default require_human_approval = false

# Allowable action types
valid_actions := {
    "reroute_canary",
    "rollback_release",
    "scale_up",
    "disable_feature_flag",
    "restart_replica",
    "NO_ACTION"
}

# Critical services requiring stricter gates & approval
critical_services := {
    "payment-service",
    "identity-service"
}

# Protected infrastructure that must NOT be blindly restarted
non_restartable_services := {
    "postgres-db",
    "redis-cache"
}

# Reasons collection
deny_reasons[msg] {
    not valid_actions[input.action_type]
    msg := sprintf("Action type '%v' is not allowlisted", [input.action_type])
}

deny_reasons[msg] {
    input.action_type == "restart_replica"
    non_restartable_services[input.target_id]
    msg := sprintf("Restarting shared stateful node '%v' is prohibited by safety policy", [input.target_id])
}

deny_reasons[msg] {
    input.root_cause_score < input.min_rca_threshold
    msg := sprintf("Root cause ranking strength %v is below minimum threshold %v", [input.root_cause_score, input.min_rca_threshold])
}

deny_reasons[msg] {
    input.evidence_age_seconds > input.max_evidence_ttl
    msg := sprintf("Evidence age %v seconds exceeds TTL limit %v seconds", [input.evidence_age_seconds, input.max_evidence_ttl])
}

deny_reasons[msg] {
    not input.rollback_plan_present
    msg := "Rollback plan is missing or incomplete"
}

deny_reasons[msg] {
    input.predicted_blast_radius > input.max_blast_radius
    msg := sprintf("Predicted blast radius %v exceeds maximum permitted limit %v", [input.predicted_blast_radius, input.max_blast_radius])
}

deny_reasons[msg] {
    input.active_remediations_on_target > 0
    msg := sprintf("Target '%v' already has an ongoing remediation in progress", [input.target_id])
}

deny_reasons[msg] {
    input.mode == "production"
    msg := "Autonomous policy engine is restricted to simulation and civicguard-lab namespace"
}

# Human approval checks
require_human_approval {
    critical_services[input.target_id]
    count(deny_reasons) == 0
}

# Overall decision
allow {
    count(deny_reasons) == 0
    not require_human_approval
}

decision := "ALLOW" {
    allow
} else := "HUMAN_APPROVAL_REQUIRED" {
    require_human_approval
} else := "DENY" {
    not allow
    not require_human_approval
}

