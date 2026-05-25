# KYKT Vision Client

React + TypeScript workbench client for the local KYKT desktop app. The desktop shell uses Tauri 2 and can supervise the local FastAPI backend.

## Run

Web dev entry:

```powershell
powershell -ExecutionPolicy Bypass -File E:\kykt\Coding\4.06\vision_ui\start_client_rebuild.ps1
```

Desktop dev entry:

```powershell
powershell -ExecutionPolicy Bypass -File E:\kykt\Coding\4.06\vision_ui\start_desktop_client.ps1
```

The web entry opens Vite on:

```text
http://127.0.0.1:5173
```

The desktop entry starts:

- FastAPI backend on `127.0.0.1:8765`
- Vite dev server through Tauri
- Tauri 2 desktop shell

Release app / installers:

```text
E:\kykt\release\kykt_vision_client\kykt_vision_client.exe
E:\kykt\release\kykt_vision_client\KYKT Vision Client_0.1.0_x64-setup.exe
E:\kykt\release\kykt_vision_client\KYKT Vision Client_0.1.0_x64_en-US.msi
E:\kykt\Coding\4.06\vision_ui\client\src-tauri\target\release\kykt_vision_client.exe
E:\kykt\Coding\4.06\vision_ui\client\src-tauri\target\release\bundle\nsis\KYKT Vision Client_0.1.0_x64-setup.exe
E:\kykt\Coding\4.06\vision_ui\client\src-tauri\target\release\bundle\msi\KYKT Vision Client_0.1.0_x64_en-US.msi
```

The release executable checks `127.0.0.1:8765` on startup. If the backend is not already running, it locates the `vision_ui` project root and starts `.venv\Scripts\python.exe -m uvicorn app:app --port 8765` in the background. The backend log is written to:

```text
E:\kykt\Coding\4.06\vision_ui\local_jobs\_desktop\backend.log
```

If the project root moves, set `KYKT_BACKEND_ROOT` to the `vision_ui` directory before launching the app.

## Current scope

- Workbench Light desktop UI aligned with `DESIGN.md`
- Overview command center
- Create workspace with runnable-vs-catalog model distinction
- Jobs split-pane inspector with filters, batch actions, and keyboard navigation
- Sample Matrix compare workspace with report export and locate-job handoff
- System deployment console with readiness matrix and next-action cards
- Advisor as an auxiliary draft path
- Job bundle export from the selected Jobs inspector task
- Tauri-managed local backend process for the release executable
- Desktop/backend status reporting showing whether FastAPI was reused or started by Tauri

## Keyboard flow in Jobs

- `/` focuses the jobs search box
- `J` / `K` moves the current selection in the filtered list
- `↑` / `↓` in the search box also steps the current selection

## Next

- Continue splitting `src/App.tsx` into smaller workspace-sized components, hooks, and helper modules
- Inspect Fast3R job `20260425-113002` and Spann3R job `20260425-113227`, then choose better comparison samples
- Continue tightening report/evaluation/Advisor contracts
- Decide whether to fully bundle Python/.venv for portable release builds
