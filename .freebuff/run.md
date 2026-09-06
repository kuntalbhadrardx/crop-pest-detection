# Preview run doc — Crop Pest & Disease Detection API (FastAPI)

Python is NOT installed on the Windows host; the only interpreter is inside the
WSL distro `Ubuntu-26.04` (Python 3.14.4). All setup/run commands therefore go
through `wsl -d Ubuntu-26.04`.

## Reproduce the artifacts

A fresh checkout needs one artifact: the Linux virtual environment `.venv`
(with the light deps so the API can boot — ultralytics/PyTorch are optional and
imported lazily).

1. From the project root on Windows, in Git Bash (or WSL directly):
   ```bash
   wsl -d Ubuntu-26.04 bash -lc 'cd "/mnt/c/Users/kunta/OneDrive/Documents/crop pest detection" && python3 -m venv .venv'
   ```
2. Install dependencies. Minimum for the API to boot:
   ```bash
   wsl -d Ubuntu-26.04 bash -lc 'cd "/mnt/c/Users/kunta/OneDrive/Documents/crop pest detection" && ./.venv/bin/python -m pip install -r requirements-dev.txt'
   ```
   Full ML stack (ultralytics + PyTorch, ~1–2 GB) for real inference:
   ```bash
   wsl -d Ubuntu-26.04 bash -lc 'cd "/mnt/c/Users/kunta/OneDrive/Documents/crop pest detection" && ./.venv/bin/python -m pip install -r requirements.txt'
   ```
3. No `.env` is needed — code defaults match `.env.example`. Trained weights are
   absent (`models/custom.pt`), so the app auto-downloads the `yolov8n.pt`
   fallback on first start and reports `fallback_in_use: true` in `/api/health`
   (generic COCO classes until a real pest model is trained and placed at
   `models/custom.pt`).

## Run the server (detached)

`uvicorn` must run inside WSL and is reachable from Windows via WSL2 localhost
forwarding on port 8000. From the project root on Windows:

```bash
powershell -NoProfile -Command "\$p = Start-Process -FilePath 'C:\Windows\System32\wsl.exe' -ArgumentList '-d','Ubuntu-26.04','--','./.venv/bin/python','-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -RedirectStandardOutput '<log>' -RedirectStandardError '<log>.err' -WindowStyle Hidden -PassThru; Write-Output \$p.Id"
```

- The WSL process inherits the Windows working directory (project root), which
  WSL translates to `/mnt/c/Users/kunta/OneDrive/Documents/crop pest detection`
  — so `./.venv/bin/python` resolves and `python -m uvicorn` finds `app`.
- Check it is alive: `powershell -NoProfile -Command "Get-Process -Id <pid>"`.
- Verify it answers: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/docs`
  (expect 200).
- Preview URL: `http://127.0.0.1:8000/` (upload UI — canvas boxes drawn client-side
  from `/api/detect` bbox data) or `/docs` (Swagger UI).
- Root `/` now serves `static/index.html` via a `StaticFiles` mount registered
  after the API routers, so `/api/*`, `/docs` and `/openapi.json` keep priority.
- Stop it: `wsl -d Ubuntu-26.04 -- pkill -f uvicorn` (or kill the Windows pid).
