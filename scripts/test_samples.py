"""Run isolated repository tests, then cross-repository integration checks."""
from pathlib import Path
import os
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
for repo in sorted((ROOT/'sample-repositories').glob('commerce-*')):
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=repo,env={**os.environ,'PYTHONPATH':str(repo/'src')},check=True)
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,check=True)
