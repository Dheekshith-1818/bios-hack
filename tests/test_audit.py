import gc
import tempfile
import os
from pathlib import Path
from backend.store import Storage

def test_audit_hash_chain_integrity_and_tampering():
    fd, path_str = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path_str)

    try:
        store = Storage(db_path=db_path)

        # 1. Log 3 events
        ev1 = store.append_audit_event("TEST_EVENT_1", "actor-1", "inc-1", "act-1", {"key": "val1"})
        ev2 = store.append_audit_event("TEST_EVENT_2", "actor-2", "inc-1", "act-2", {"key": "val2"})
        ev3 = store.append_audit_event("TEST_EVENT_3", "actor-3", "inc-1", "act-3", {"key": "val3"})

        assert ev1.sequence == 1
        assert ev1.previousHash == "GENESIS"
        assert ev2.sequence == 2
        assert ev2.previousHash == ev1.eventHash
        assert ev3.sequence == 3
        assert ev3.previousHash == ev2.eventHash

        # 2. Verify chain on clean log
        verification = store.verify_audit_chain()
        assert verification["valid"]
        assert verification["total_events"] == 3

        # 3. Simulate tamper: modify payload of event 2 directly in DB
        with store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE audit_events SET payload = '{\"key\": \"tampered_val\"}' WHERE sequence = 2")
            conn.commit()

        # 4. Verification must detect tampering!
        tampered_verif = store.verify_audit_chain()
        assert not tampered_verif["valid"]
        assert tampered_verif["broken_sequence"] == 2
        assert "integrity compromised" in tampered_verif["reason"]

    finally:
        del store
        gc.collect()
        try:
            if db_path.exists():
                db_path.unlink()
        except Exception:
            pass
