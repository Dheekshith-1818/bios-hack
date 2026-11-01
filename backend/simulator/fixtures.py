from typing import Dict, Any, List

SERVICES = [
    "citizen-portal",
    "identity-service",
    "eligibility-service",
    "benefits-engine",
    "payment-service",
    "notification-service",
    "redis-replica-a",
    "redis-replica-b",
    "postgres-db"
]

# Simulator's internal caller -> callee dependency flow
HIDDEN_TOPOLOGY = [
    ("citizen-portal", "identity-service"),
    ("citizen-portal", "eligibility-service"),
    ("identity-service", "redis-replica-a"),
    ("eligibility-service", "benefits-engine"),
    ("eligibility-service", "postgres-db"),
    ("benefits-engine", "payment-service"),
    ("benefits-engine", "postgres-db"),
    ("payment-service", "notification-service")
]

BASE_LATENCIES_MS = {
    "citizen-portal": (30.0, 5.0),
    "identity-service": (40.0, 8.0),
    "eligibility-service": (60.0, 10.0),
    "benefits-engine": (50.0, 8.0),
    "payment-service": (70.0, 12.0),
    "notification-service": (25.0, 4.0),
    "redis-replica-a": (5.0, 1.0),
    "redis-replica-b": (5.0, 1.0),
    "postgres-db": (15.0, 3.0)
}

