//! The Visão as a Mac app (docs/APP_MAC.md, ADR-0027).
//!
//! The app carries the Visão's server, frozen by PyInstaller (desktop/visao-servidor.spec), as a
//! resource. On opening it shows a loading page, starts the server on 127.0.0.1 (the same
//! `visao iniciar` as the command line, with the worker inside and the web app on the same
//! address), waits until it answers and then shows the web app in the window. Quitting the app
//! stops the server it started.
//!
//! When a Visão already answers on the usual port (the service of `visao servico instalar`, or a
//! `visao iniciar` in a terminal), the app only opens a window onto it and leaves it running.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

/// The port of `visao iniciar`, so the app and the command line find each other.
const USUAL_PORT: u16 = 8000;
/// The first start makes the database (migrations); later ones take a few seconds.
const START_WAIT: Duration = Duration::from_secs(120);
/// The server finishes what it is doing (a reply, a worker step) before it stops.
const STOP_WAIT: Duration = Duration::from_secs(25);

/// The server this app started, if it started one.
struct Server(Mutex<Option<Child>>);

/// Whether a Visão answers on this port: GET /api/health, 200 with "ok".
fn answers(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(500)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let request =
        format!("GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut reply = String::new();
    let _ = stream.read_to_string(&mut reply);
    reply.starts_with("HTTP/1.1 200") && reply.contains("\"ok\"")
}

fn port_is_free(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

/// A free port picked by the system, for when something else holds the usual one.
fn any_free_port() -> Option<u16> {
    TcpListener::bind(("127.0.0.1", 0)).ok()?.local_addr().ok().map(|a| a.port())
}

/// ~/.visao, or VISAO_HOME: the same place as the command line (configuration, database, log).
fn visao_home() -> PathBuf {
    if let Some(home) = std::env::var_os("VISAO_HOME") {
        return PathBuf::from(home);
    }
    let user_home = std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    user_home.join(".visao")
}

fn start_server(app: &AppHandle, port: u16) -> Result<Child, String> {
    let resources = app.path().resource_dir().map_err(|e| e.to_string())?;
    let executable = resources.join("visao-servidor").join("visao-servidor");
    if !executable.is_file() {
        return Err(format!("o servidor não está dentro do app ({})", executable.display()));
    }
    let home = visao_home();
    fs::create_dir_all(&home).map_err(|e| e.to_string())?;
    let log = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(home.join("visao-app.log"))
        .map_err(|e| e.to_string())?;
    let errors = log.try_clone().map_err(|e| e.to_string())?;
    Command::new(executable)
        .args(["iniciar", "--porta", &port.to_string()])
        .env("VISAO_HOME", &home)
        // The server stops by itself if this app goes away without stopping it (killed, crashed).
        .env("VISAO_PARENT_WATCH", "1")
        .current_dir(&home)
        .stdin(Stdio::null())
        .stdout(log)
        .stderr(errors)
        .spawn()
        .map_err(|e| format!("o servidor não abriu ({e})"))
}

/// Finds or starts the Visão; returns the port it answers on.
fn bring_up(app: &AppHandle) -> Result<u16, String> {
    if answers(USUAL_PORT) {
        return Ok(USUAL_PORT); // the service or a terminal already runs it: only a window onto it
    }
    let port = if port_is_free(USUAL_PORT) {
        USUAL_PORT
    } else {
        any_free_port().ok_or("nenhuma porta livre em 127.0.0.1")?
    };
    let child = start_server(app, port)?;
    let state = app.state::<Server>();
    *state.0.lock().unwrap() = Some(child);
    let deadline = Instant::now() + START_WAIT;
    while Instant::now() < deadline {
        if answers(port) {
            return Ok(port);
        }
        let exited = state.0.lock().unwrap().as_mut().map(|c| c.try_wait().ok().flatten().is_some());
        if exited == Some(true) {
            return Err("o servidor parou ao abrir".into());
        }
        thread::sleep(Duration::from_millis(300));
    }
    Err("o servidor demorou demais para responder".into())
}

fn say(window: &WebviewWindow, title: &str, text: &str) {
    let script = format!(
        "document.body.dataset.erro = '1'; document.getElementById('titulo').textContent = {}; \
         document.getElementById('estado').textContent = {};",
        serde_json::to_string(title).unwrap_or_default(),
        serde_json::to_string(text).unwrap_or_default(),
    );
    let _ = window.eval(&script);
}

/// Stops the server this app started: first asks (SIGTERM), then insists.
fn stop_server(app: &AppHandle) {
    let Some(mut child) = app.state::<Server>().0.lock().unwrap().take() else {
        return;
    };
    #[cfg(unix)]
    unsafe {
        libc::kill(child.id() as libc::pid_t, libc::SIGTERM);
    }
    let deadline = Instant::now() + STOP_WAIT;
    while Instant::now() < deadline {
        if let Ok(Some(_)) = child.try_wait() {
            return;
        }
        thread::sleep(Duration::from_millis(200));
    }
    let _ = child.kill();
    let _ = child.wait();
}

fn main() {
    tauri::Builder::default()
        .manage(Server(Mutex::new(None)))
        .setup(|app| {
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("V.I.S.A.O.")
                .inner_size(1200.0, 820.0)
                .min_inner_size(420.0, 600.0)
                .build()?;
            let handle = app.handle().clone();
            thread::spawn(move || match bring_up(&handle) {
                Ok(port) => {
                    let address = format!("http://127.0.0.1:{port}/");
                    match address.parse::<Url>() {
                        Ok(url) => {
                            if let Err(e) = window.navigate(url) {
                                say(&window, "Não consegui abrir a janela do Visão", &e.to_string());
                            }
                        }
                        Err(e) => say(&window, "Endereço inválido", &e.to_string()),
                    }
                }
                Err(reason) => {
                    let log = visao_home().join("visao-app.log");
                    say(
                        &window,
                        "O Visão não abriu",
                        &format!("{reason}. O que aconteceu fica em {}.", log.display()),
                    );
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("o app do Visão não abriu")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_server(app);
            }
        });
}
