#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod db;
mod server;
mod watcher;

use std::sync::Arc;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, WindowEvent,
};
use tokio::sync::broadcast;
use tracing_subscriber;

fn main() {
    // Initialize logging
    tracing_subscriber::fmt::init();

    // Event channel for real-time updates
    let (event_tx, _) = broadcast::channel::<db::AgentEvent>(100);
    let event_tx = Arc::new(event_tx);

    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
            let handle = app.handle().clone();
            let _event_tx_clone = Arc::clone(&event_tx);

            // Initialize database
            let db_path = app
                .path()
                .app_data_dir()
                .expect("Failed to get app data dir")
                .join("agentkanban.db");

            // Ensure parent directory exists
            if let Some(parent) = db_path.parent() {
                std::fs::create_dir_all(parent)?;
            }

            let database = db::Database::new(&db_path)?;
            app.manage(db::DbState(Arc::new(database)));

            // Start file watcher in background thread
            let watcher_handle = handle.clone();
            let watcher_tx = Arc::clone(&event_tx);
            std::thread::spawn(move || {
                if let Err(e) = watcher::start_watching(watcher_handle, watcher_tx) {
                    tracing::error!("File watcher error: {}", e);
                }
            });

            // Start HTTP server for hook events
            let http_handle = handle.clone();
            let http_tx = Arc::clone(&event_tx);
            tauri::async_runtime::spawn(async move {
                if let Err(e) = server::start_server(http_handle, http_tx, 4000).await {
                    tracing::error!("HTTP server error: {}", e);
                }
            });

            // Forward events to frontend via Tauri events
            let event_handle = handle.clone();
            let mut event_rx = event_tx.subscribe();
            tauri::async_runtime::spawn(async move {
                while let Ok(event) = event_rx.recv().await {
                    let _ = event_handle.emit("agent-event", &event);
                }
            });

            // Setup system tray
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let show = MenuItem::with_id(app, "show", "Show Dashboard", true, None::<&str>)?;
            let scan = MenuItem::with_id(app, "scan", "Scan Projects", true, None::<&str>)?;

            let menu = Menu::with_items(app, &[&show, &scan, &quit])?;

            let _tray = TrayIconBuilder::new()
                .icon(tauri::image::Image::from_bytes(include_bytes!("../icons/32x32.png"))?)
                .menu(&menu)
                .tooltip("AgentKanban")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        app.exit(0);
                    }
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "scan" => {
                        let _ = app.emit("scan-requested", ());
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_features,
            commands::get_events,
            commands::get_feature_events,
            commands::get_sessions,
            commands::get_stats,
            commands::scan_projects,
            commands::watch_project,
            commands::get_config,
            commands::save_config,
        ])
        .on_window_event(|window, event| {
            // Minimize to tray instead of closing
            if let WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
