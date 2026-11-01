import sys
import os
import subprocess
from pathlib import Path

def main():
    root_dir = Path(__file__).resolve().parent
    os.chdir(root_dir)

    # Detect portable python in .python if running on Windows and standard python is not configured
    local_py = root_dir / ".python" / "python.exe"
    if local_py.exists() and sys.executable != str(local_py):
        print(f"[CivicGuard] Switching to bundled environment at {local_py}")
        cmd = [str(local_py), "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"]
        sys.exit(subprocess.call(cmd))

    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()

