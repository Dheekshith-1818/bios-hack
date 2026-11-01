import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    ENV: str = os.getenv("CIVICGUARD_ENV", "development")
    HOST: str = os.getenv("CIVICGUARD_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("CIVICGUARD_PORT", "8000"))
    MODE: str = os.getenv("CIVICGUARD_MODE", "simulation")  # "simulation" or "k8s_lab"
    REAL_ACTIONS: bool = os.getenv("CIVICGUARD_REAL_ACTIONS", "false").lower() in ("true", "1")
    AUDIT_SECRET: str = os.getenv("CIVICGUARD_AUDIT_SECRET", "civicguard-integrity-secret-local-change-me")
    
    DATA_DIR: Path = Path(os.getenv("CIVICGUARD_DATA_DIR", str(BASE_DIR / "data")))
    SQLITE_PATH: Path = Path(os.getenv("CIVICGUARD_SQLITE_PATH", str(BASE_DIR / "data" / "civicguard.db")))
    
    # Noise gate & Detection thresholds
    WINDOW_SIZE_SECONDS: float = 5.0
    CONSECUTIVE_ANOMALY_WINDOWS: int = 2
    MAD_EPSILON: float = 1e-4
    Z_SCORE_THRESHOLD: float = 3.0
    CUSUM_THRESHOLD: float = 4.0
    CLEAN_WINDOWS_HYSTERESIS: int = 3
    
    # Root Cause & Cascading
    RCA_CONFIDENCE_THRESHOLD: float = 70.0
    MAX_BLAST_RADIUS: int = 4
    EVIDENCE_TTL_SECONDS: float = 120.0
    
    # Canary parameters
    CANARY_SAMPLE_WINDOWS: int = 3
    CANARY_MAX_REGRESSION_TOLERANCE: float = 0.005 # 0.5% max drop in availability / payment success
    CANARY_LATENCY_MAX_INCREASE: float = 0.10 # 10% max p95 latency increase
    
    # Frontend directory
    FRONTEND_DIR: Path = BASE_DIR / "frontend"

settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
