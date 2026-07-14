# -*- coding: utf-8 -*-
"""Boot-smoke the freshly built backend sidecar exe: start it, hit /api/health, kill it."""
import subprocess, time, os, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "3r-backend.exe")
PORT = "8799"
env = dict(os.environ)
env["BACKEND_HOST"] = "127.0.0.1"
env["BACKEND_PORT"] = PORT

logf = open(os.path.join(ROOT, "tmp", "smoke_backend.log"), "w", encoding="utf-8", errors="ignore")
print(f"launching {EXE} on port {PORT} ...")
p = subprocess.Popen([EXE], env=env, cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)

ok = False
last = None
for i in range(45):
    time.sleep(1)
    if p.poll() is not None:
        print(f"!! process exited early with code {p.returncode} (see tmp/smoke_backend.log)")
        break
    for path in ["/api/health", "/"]:
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=2)
            body = r.read(300).decode("utf-8", "ignore")
            print(f"HTTP {r.getcode()} {path}  body[:120]={body[:120]!r}")
            if r.getcode() == 200 and path == "/api/health":
                ok = True
        except Exception as e:
            last = f"{path}: {e}"
    if ok:
        break

print("LAST_ERR:", last)
print("SMOKE:", "PASS" if ok else "FAIL")

subprocess.run(["taskkill", "/IM", "3r-backend.exe", "/F"], capture_output=True)
logf.close()
