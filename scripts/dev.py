"""Run the API and durable worker together; stop both if either exits."""
import signal
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.db import initialize


def main():
    initialize()
    children=[]
    def stop(signum=None,frame=None):
        for child in children:
            if child.poll() is None:child.terminate()
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    try:
        children.append(subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8012'],cwd=ROOT))
        children.append(subprocess.Popen([sys.executable,'-m','backend.worker'],cwd=ROOT))
        print('DoAide API + local job worker: http://127.0.0.1:8012',flush=True)
        while all(child.poll() is None for child in children):time.sleep(.5)
    finally:
        stop()
        for child in children:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':main()
