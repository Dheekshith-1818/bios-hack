import numpy as np
from collections import deque
from typing import Dict, Any, Optional
from backend.config import settings

class RobustMetricBaseline:
    def __init__(self, metric_name: str, window_size: int = 40, epsilon: float = 1e-4):
        self.metric_name = metric_name
        self.window_size = window_size
        self.epsilon = epsilon
        self.history = deque(maxlen=window_size)
        self.ewma = None
        self.alpha = 0.2
        self.cusum_pos = 0.0
        self.drift_count = 0
        self.paused = False

    def update(self, val: float):
        if self.paused:
            return

        self.history.append(val)
        if self.ewma is None:
            self.ewma = val
        else:
            self.ewma = self.alpha * val + (1.0 - self.alpha) * self.ewma

        # Check for gentle baseline drift
        if len(self.history) >= 15:
            med = float(np.median(self.history))
            if abs(self.ewma - med) > (med * 0.35 + self.epsilon):
                self.drift_count += 1

    def compute_robust_z(self, val: float) -> float:
        if len(self.history) < 5:
            # Insufficient samples for statistical baseline
            return 0.0

        hist = np.array(self.history)
        med = float(np.median(hist))
        mad = float(np.median(np.abs(hist - med)))
        denom = max(1.4826 * mad, self.epsilon)
        z = (val - med) / denom

        # Update one-sided CUSUM for positive anomalies (rising latency/error/CPU)
        k = 0.5  # reference slack
        self.cusum_pos = max(0.0, self.cusum_pos + z - k)

        return z

    @property
    def median(self) -> float:
        return float(np.median(self.history)) if self.history else 0.0

    @property
    def sample_count(self) -> int:
        return len(self.history)

class ServiceBaselineManager:
    def __init__(self):
        # service_id -> metric_name -> RobustMetricBaseline
        self.baselines: Dict[str, Dict[str, RobustMetricBaseline]] = {}

    def get_or_create(self, service_id: str, metric_name: str) -> RobustMetricBaseline:
        if service_id not in self.baselines:
            self.baselines[service_id] = {}
        if metric_name not in self.baselines[service_id]:
            self.baselines[service_id][metric_name] = RobustMetricBaseline(metric_name)
        return self.baselines[service_id][metric_name]

    def pause_service(self, service_id: str):
        if service_id in self.baselines:
            for b in self.baselines[service_id].values():
                b.paused = True

    def resume_service(self, service_id: str):
        if service_id in self.baselines:
            for b in self.baselines[service_id].values():
                b.paused = False

    def reset(self):
        self.baselines.clear()

service_baselines = ServiceBaselineManager()

