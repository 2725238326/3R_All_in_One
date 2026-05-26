use serde::Serialize;
use std::{
    env,
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 8765;
const BACKEND_WAIT_SECS: u64 = 20;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

struct BackendProcess(Mutex<Option<Child>>);

struct BackendStatusState(Mutex<BackendStatus>);

#[derive(Clone, Serialize)]
struct BackendStatus {
    running: bool,
    managed_by_tauri: bool,
    message: String,
    backend_root: Option<String>,
    log_path: Option<String>,
}

const SIDECAR_NAME: &str = "3r-backend";

#[tauri::command]
fn app_ready_message() -> &'static str {
    "3R All-in-One desktop shell is ready."
}

#[tauri::command]
fn backend_status(state: tauri::State<'_, BackendStatusState>) -> BackendStatus {
    let mut status = state
        .0
        .lock()
        .map(|status| status.clone())
        .unwrap_or_else(|_| BackendStatus {
            running: false,
            managed_by_tauri: false,
            message: "backend status lock is poisoned".to_string(),
            backend_root: None,
            log_path: None,
        });

    if backend_api_is_healthy() {
        status.running = true;
        if status.message.is_empty() || status.message.contains("did not become ready") {
            status.message = if status.managed_by_tauri {
                "FastAPI backend is healthy and managed by the desktop client.".to_string()
            } else {
                "FastAPI backend is healthy on 127.0.0.1:8765.".to_string()
            };
        }
    } else {
        status.running = false;
        if let Some(pid) = find_listener_pid(BACKEND_PORT) {
            status.message = format!(
                "端口 8765 被 PID {pid} 占用，但本地后端 API 没有正常响应。建议点击“重启本地服务”。"
            );
        } else {
            status.message = "本地后端当前未监听 127.0.0.1:8765。".to_string();
        }
    }

    status
}

#[tauri::command]
fn ensure_backend_now(app: tauri::AppHandle) -> BackendStatus {
    let status = ensure_backend(&app);
    set_backend_status(&app, status.clone());
    status
}

#[tauri::command]
fn restart_backend(app: tauri::AppHandle) -> BackendStatus {
    if let Some(state) = app.try_state::<BackendProcess>() {
        stop_backend(&state);
    }

    if let Some(pid) = find_listener_pid(BACKEND_PORT) {
        let _ = kill_process(pid);
        thread::sleep(Duration::from_millis(600));
    }

    let status = ensure_backend(&app);
    set_backend_status(&app, status.clone());
    status
}

pub fn run() {
    let context = tauri::generate_context!();
    let app = tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .manage(BackendStatusState(Mutex::new(BackendStatus {
            running: false,
            managed_by_tauri: false,
            message: "backend has not been checked yet".to_string(),
            backend_root: None,
            log_path: None,
        })))
        .setup(|app| {
            set_backend_status(
                &app.handle(),
                BackendStatus {
                    running: false,
                    managed_by_tauri: false,
                    message: "Checking local backend availability...".to_string(),
                    backend_root: None,
                    log_path: None,
                },
            );

            let app_handle = app.handle().clone();
            thread::spawn(move || {
                set_backend_status(
                    &app_handle,
                    BackendStatus {
                        running: false,
                        managed_by_tauri: false,
                        message: "Starting or reusing the local FastAPI backend...".to_string(),
                        backend_root: None,
                        log_path: None,
                    },
                );
                let status = ensure_backend(&app_handle);
                set_backend_status(&app_handle, status);
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            app_ready_message,
            backend_status,
            ensure_backend_now,
            restart_backend
        ])
        .build(context)
        .expect("failed to build KYKT Vision Client");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
            let state = app_handle.state::<BackendProcess>();
            stop_backend(&state);
        }
    });
}

fn set_backend_status(app: &tauri::AppHandle, status: BackendStatus) {
    if let Some(state) = app.try_state::<BackendStatusState>() {
        if let Ok(mut guard) = state.0.lock() {
            *guard = status;
        }
    }
}

fn ensure_backend(app: &tauri::AppHandle) -> BackendStatus {
    if backend_api_is_healthy() {
        return BackendStatus {
            running: true,
            managed_by_tauri: false,
            message: "FastAPI backend is already healthy on 127.0.0.1:8765.".to_string(),
            backend_root: None,
            log_path: None,
        };
    }

    if backend_is_listening() {
        let listener_hint = find_listener_pid(BACKEND_PORT)
            .map(|pid| format!("当前占用进程 PID={pid}。"))
            .unwrap_or_else(|| "当前占用进程未知。".to_string());
        return BackendStatus {
            running: false,
            managed_by_tauri: false,
            message: format!(
                "127.0.0.1:8765 已被其他进程占用，但后端 API 没有正常响应。{listener_hint} 请点击“重启本地服务”接管它。"
            ),
            backend_root: None,
            log_path: None,
        };
    }

    // Try sidecar exe first (PyInstaller --onefile bundle)
    if let Some(sidecar_path) = find_sidecar_exe(app) {
        match spawn_sidecar(&sidecar_path) {
            Ok((child, log_path)) => {
                if let Some(state) = app.try_state::<BackendProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        *guard = Some(child);
                    }
                }

                if wait_for_backend() {
                    return BackendStatus {
                        running: true,
                        managed_by_tauri: true,
                        message: "Backend started from bundled sidecar executable.".to_string(),
                        backend_root: Some(sidecar_path.display().to_string()),
                        log_path: Some(log_path.display().to_string()),
                    };
                }
                // Sidecar started but not healthy - continue to try Python fallback
            }
            Err(_) => {
                // Sidecar failed to spawn - continue to try Python fallback
            }
        }
    }

    // Fallback to Python + uvicorn
    let backend_root = match find_backend_root(app) {
        Ok(path) => path,
        Err(message) => {
            return BackendStatus {
                running: false,
                managed_by_tauri: false,
                message: format!("No sidecar found and {}", message),
                backend_root: None,
                log_path: None,
            }
        }
    };

    match spawn_backend_python(&backend_root) {
        Ok((child, log_path)) => {
            if let Some(state) = app.try_state::<BackendProcess>() {
                if let Ok(mut guard) = state.0.lock() {
                    *guard = Some(child);
                }
            }

            if wait_for_backend() {
                BackendStatus {
                    running: true,
                    managed_by_tauri: true,
                    message: "FastAPI backend was started by the desktop client.".to_string(),
                    backend_root: Some(backend_root.display().to_string()),
                    log_path: Some(log_path.display().to_string()),
                }
            } else {
                BackendStatus {
                    running: false,
                    managed_by_tauri: true,
                    message: "Backend process started, but port 8765 did not become ready in time.".to_string(),
                    backend_root: Some(backend_root.display().to_string()),
                    log_path: Some(log_path.display().to_string()),
                }
            }
        }
        Err(message) => BackendStatus {
            running: false,
            managed_by_tauri: false,
            message,
            backend_root: Some(backend_root.display().to_string()),
            log_path: None,
        },
    }
}

fn backend_is_listening() -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], BACKEND_PORT));
    TcpStream::connect_timeout(&addr, Duration::from_millis(250)).is_ok()
}

fn backend_api_is_healthy() -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], BACKEND_PORT));
    let mut stream = match TcpStream::connect_timeout(&addr, Duration::from_millis(400)) {
        Ok(stream) => stream,
        Err(_) => return false,
    };

    let _ = stream.set_read_timeout(Some(Duration::from_millis(1200)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(1200)));

    if stream
        .write_all(
            b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
        )
        .is_err()
    {
        return false;
    }

    let mut buffer = [0u8; 256];
    match stream.read(&mut buffer) {
        Ok(size) if size > 0 => {
            let response = String::from_utf8_lossy(&buffer[..size]);
            response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")
        }
        _ => false,
    }
}

fn wait_for_backend() -> bool {
    let deadline = Instant::now() + Duration::from_secs(BACKEND_WAIT_SECS);
    while Instant::now() < deadline {
        if backend_is_listening() {
            return true;
        }
        thread::sleep(Duration::from_millis(350));
    }
    false
}

fn find_backend_root(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if let Ok(root) = env::var("KYKT_BACKEND_ROOT") {
        let path = PathBuf::from(root);
        if is_backend_root(&path) {
            return Ok(path);
        }
    }

    let manifest_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(client_dir) = manifest_root.parent() {
        if let Some(project_root) = client_dir.parent() {
            if is_backend_root(project_root) {
                return Ok(project_root.to_path_buf());
            }
        }
    }

    if let Ok(exe) = env::current_exe() {
        for ancestor in exe.ancestors() {
            if is_backend_root(ancestor) {
                return Ok(ancestor.to_path_buf());
            }
            // Also accept a sibling `backend/` folder next to the exe so a
            // portable bundle can ship `kykt_vision_client.exe` + `backend/`.
            let sibling = ancestor.join("backend");
            if is_backend_root(&sibling) {
                return Ok(sibling);
            }
        }
    }

    if let Ok(resource_dir) = app.path().resource_dir() {
        for candidate in [resource_dir.join("backend"), resource_dir] {
            if is_backend_root(&candidate) {
                return Ok(candidate);
            }
        }
    }

    Err(
        "Could not locate the FastAPI backend. Set KYKT_BACKEND_ROOT to the \
         vision_ui directory (the folder that contains app.py and job_store.py)."
            .to_string(),
    )
}

fn is_backend_root(path: &Path) -> bool {
    // Relaxed in 0.3.x: only require the FastAPI entry-point sources. The
    // Python interpreter is resolved separately by find_backend_python so a
    // portable bundle can ship without a project-local venv.
    path.join("app.py").exists() && path.join("job_store.py").exists()
}

/// Look for the bundled sidecar executable (PyInstaller --onefile build).
/// Returns the path if found, None otherwise.
fn find_sidecar_exe(app: &tauri::AppHandle) -> Option<PathBuf> {
    // 1. Check resource directory (Tauri bundle location)
    if let Ok(resource_dir) = app.path().resource_dir() {
        #[cfg(windows)]
        let exe_name = format!("{SIDECAR_NAME}-x86_64-pc-windows-msvc.exe");
        #[cfg(not(windows))]
        let exe_name = SIDECAR_NAME.to_string();

        let sidecar_path = resource_dir.join("binaries").join(&exe_name);
        if sidecar_path.exists() {
            return Some(sidecar_path);
        }

        // Also try without target triple
        let simple_path = resource_dir.join("binaries").join(format!("{SIDECAR_NAME}.exe"));
        if simple_path.exists() {
            return Some(simple_path);
        }
    }

    // 2. Check next to the executable (portable deployment)
    if let Ok(exe) = env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            #[cfg(windows)]
            let candidates = [
                format!("{SIDECAR_NAME}-x86_64-pc-windows-msvc.exe"),
                format!("{SIDECAR_NAME}.exe"),
            ];
            #[cfg(not(windows))]
            let candidates = [SIDECAR_NAME.to_string()];

            for name in &candidates {
                let path = exe_dir.join(name);
                if path.exists() {
                    return Some(path);
                }
            }
        }
    }

    // 3. Development: check in dist/ folder relative to project
    let manifest_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(project_root) = manifest_root.parent().and_then(|p| p.parent()) {
        let dev_path = project_root.join("dist").join(format!("{SIDECAR_NAME}.exe"));
        if dev_path.exists() {
            return Some(dev_path);
        }
    }

    None
}

fn find_backend_python(backend_root: &Path) -> Result<PathBuf, String> {
    if let Ok(explicit) = env::var("KYKT_BACKEND_PYTHON") {
        let path = PathBuf::from(explicit);
        if path.exists() {
            return Ok(path);
        }
        return Err(format!(
            "KYKT_BACKEND_PYTHON points to a missing file: {}",
            path.display()
        ));
    }

    // 1. Project-local virtualenv (preferred for developer workflow).
    let venv_python = backend_root
        .join(".venv")
        .join("Scripts")
        .join("python.exe");
    if venv_python.exists() {
        return Ok(venv_python);
    }

    // 2. Backend-relative portable Python (a bundle could ship `python/python.exe`).
    let portable = backend_root.join("python").join("python.exe");
    if portable.exists() {
        return Ok(portable);
    }

    // 3. Sibling `python/python.exe` next to the exe (root of a portable bundle).
    if let Ok(exe) = env::current_exe() {
        for ancestor in exe.ancestors() {
            let candidate = ancestor.join("python").join("python.exe");
            if candidate.exists() {
                return Ok(candidate);
            }
        }
    }

    // 4. Fall back to system PATH `python.exe`. This requires the user to have
    //    installed the requirements; a portable bundle should avoid this path.
    let mut where_cmd = Command::new("where");
    where_cmd.arg("python.exe");
    #[cfg(windows)]
    where_cmd.creation_flags(CREATE_NO_WINDOW);
    if let Ok(output) = where_cmd.output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout);
            if let Some(line) = text.lines().next() {
                let trimmed = line.trim();
                if !trimmed.is_empty() {
                    return Ok(PathBuf::from(trimmed));
                }
            }
        }
    }

    Err(format!(
        "Could not locate a Python interpreter for the FastAPI backend. \
         Looked for {0}\\.venv\\Scripts\\python.exe and {0}\\python\\python.exe. \
         Set KYKT_BACKEND_PYTHON to a python.exe that has the requirements installed.",
        backend_root.display()
    ))
}

fn spawn_sidecar(sidecar_path: &Path) -> Result<(Child, PathBuf), String> {
    let log_dir = if let Ok(exe) = env::current_exe() {
        exe.parent()
            .map(|p| p.join("logs"))
            .unwrap_or_else(|| PathBuf::from("logs"))
    } else {
        PathBuf::from("logs")
    };
    fs::create_dir_all(&log_dir)
        .map_err(|err| format!("Failed to create sidecar log directory: {err}"))?;
    let log_path = log_dir.join("backend.log");

    let mut log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|err| format!("Failed to open sidecar log: {err}"))?;
    writeln!(
        log_file,
        "\n=== 3R All-in-One sidecar start ({}) ===",
        sidecar_path.display()
    )
    .map_err(|err| format!("Failed to write sidecar log: {err}"))?;

    let stdout = Stdio::from(
        log_file
            .try_clone()
            .map_err(|err| format!("Failed to clone sidecar log handle: {err}"))?,
    );
    let stderr = Stdio::from(log_file);

    let mut command = Command::new(sidecar_path);
    command
        .env("BACKEND_HOST", BACKEND_HOST)
        .env("BACKEND_PORT", BACKEND_PORT.to_string())
        .stdout(stdout)
        .stderr(stderr);

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map(|child| (child, log_path))
        .map_err(|err| format!("Failed to start sidecar backend: {err}"))
}

fn spawn_backend_python(backend_root: &Path) -> Result<(Child, PathBuf), String> {
    let python = find_backend_python(backend_root)?;
    if !python.exists() {
        return Err(format!("Python interpreter not found: {}", python.display()));
    }

    let log_dir = backend_root.join("local_jobs").join("_desktop");
    fs::create_dir_all(&log_dir)
        .map_err(|err| format!("Failed to create backend log directory: {err}"))?;
    let log_path = log_dir.join("backend.log");
    let mut log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|err| format!("Failed to open backend log: {err}"))?;
    writeln!(
        log_file,
        "\n=== KYKT desktop backend start ({}) ===",
        python.display()
    )
    .map_err(|err| format!("Failed to write backend log: {err}"))?;

    let stdout = Stdio::from(
        log_file
            .try_clone()
            .map_err(|err| format!("Failed to clone backend log handle: {err}"))?,
    );
    let stderr = Stdio::from(log_file);

    let mut command = Command::new(python);
    command
        .current_dir(backend_root)
        .env("PYTHONUTF8", "1")
        .args([
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            BACKEND_HOST,
            "--port",
            &BACKEND_PORT.to_string(),
        ])
        .stdout(stdout)
        .stderr(stderr);

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map(|child| (child, log_path))
        .map_err(|err| format!("Failed to start FastAPI backend: {err}"))
}

fn stop_backend(state: &BackendProcess) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn find_listener_pid(port: u16) -> Option<u32> {
    let mut cmd = Command::new("netstat");
    cmd.args(["-ano", "-p", "tcp"])
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    let output = cmd.output().ok()?;

    let needle = format!("127.0.0.1:{port}");
    let text = String::from_utf8_lossy(&output.stdout);
    for line in text.lines() {
        if !(line.contains("LISTENING") && line.contains(&needle)) {
            continue;
        }
        let pid = line.split_whitespace().last()?.parse::<u32>().ok()?;
        return Some(pid);
    }
    None
}

fn kill_process(pid: u32) -> bool {
    let mut cmd = Command::new("taskkill");
    cmd.args(["/PID", &pid.to_string(), "/F"])
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd.status()
        .map(|status| status.success())
        .unwrap_or(false)
}
