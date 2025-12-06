use crate::db::{AgentEvent, DbState, Feature};
use notify::{RecommendedWatcher, RecursiveMode, Watcher};
use notify_debouncer_mini::{new_debouncer, DebouncedEvent};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::broadcast;

pub fn start_watching(
    app: tauri::AppHandle,
    event_tx: Arc<broadcast::Sender<AgentEvent>>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let home = dirs::home_dir().ok_or("Could not find home directory")?;

    // Paths to watch
    let claude_projects = home.join(".claude/projects");

    let (tx, rx) = std::sync::mpsc::channel();

    let mut debouncer = new_debouncer(Duration::from_millis(500), tx)?;

    // Watch Claude Code transcripts
    if claude_projects.exists() {
        debouncer
            .watcher()
            .watch(&claude_projects, RecursiveMode::Recursive)?;
        tracing::info!("Watching Claude projects: {:?}", claude_projects);
    }

    // Load config and watch configured project directories
    let db: tauri::State<DbState> = app.state();
    if let Ok(config) = db.0.get_config() {
        for project in &config.watched_projects {
            let feature_file = PathBuf::from(project).join("feature_list.json");
            if let Some(parent) = feature_file.parent() {
                if parent.exists() {
                    let _ = debouncer
                        .watcher()
                        .watch(parent, RecursiveMode::NonRecursive);
                    tracing::info!("Watching project: {:?}", parent);
                }
            }
        }
    }

    tracing::info!("File watcher started");

    for result in rx {
        match result {
            Ok(events) => {
                for event in events {
                    handle_file_event(&app, &event_tx, &event.path);
                }
            }
            Err(e) => tracing::error!("Watch error: {:?}", e),
        }
    }

    Ok(())
}

fn handle_file_event(
    app: &tauri::AppHandle,
    event_tx: &broadcast::Sender<AgentEvent>,
    path: &Path,
) {
    let path_str = path.to_string_lossy();

    // Handle transcript files (Claude Code sessions)
    if path_str.ends_with(".jsonl") && path_str.contains(".claude/projects") {
        handle_transcript_change(app, event_tx, path);
    }

    // Handle feature_list.json changes
    if path_str.ends_with("feature_list.json") {
        handle_feature_list_change(app, event_tx, path);
    }
}

fn handle_transcript_change(
    app: &tauri::AppHandle,
    event_tx: &broadcast::Sender<AgentEvent>,
    path: &Path,
) {
    // Extract project dir from transcript path
    // Path format: ~/.claude/projects/{encoded-project}/session.jsonl
    let project_dir = path
        .parent()
        .and_then(|p| p.file_name())
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "unknown".to_string());

    // Parse session ID from filename
    let session_id = path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());

    let event = AgentEvent {
        id: None,
        event_type: "TranscriptUpdated".to_string(),
        source_agent: "claude-code".to_string(),
        session_id,
        project_dir,
        tool_name: None,
        payload: Some(path.to_string_lossy().to_string()),
        feature_id: None,
        created_at: chrono::Utc::now().to_rfc3339(),
    };

    // Store in database
    let db: tauri::State<DbState> = app.state();
    let _ = db.0.insert_event(&event);

    // Broadcast to frontend
    let _ = event_tx.send(event);
}

fn handle_feature_list_change(
    app: &tauri::AppHandle,
    event_tx: &broadcast::Sender<AgentEvent>,
    path: &Path,
) {
    let project_dir = path
        .parent()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default();

    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(e) => {
            tracing::error!("Failed to read feature_list.json: {}", e);
            return;
        }
    };

    let features: Vec<serde_json::Value> = match serde_json::from_str(&content) {
        Ok(f) => f,
        Err(e) => {
            tracing::error!("Failed to parse feature_list.json: {}", e);
            return;
        }
    };

    let db: tauri::State<DbState> = app.state();

    // Get old features to detect changes
    let old_features = db.0.get_features(Some(&project_dir)).unwrap_or_default();
    let old_completed: HashSet<String> = old_features
        .iter()
        .filter(|f| f.passes)
        .map(|f| f.description.clone())
        .collect();

    // Parse new features
    let parsed_features: Vec<Feature> = features
        .iter()
        .enumerate()
        .map(|(i, f)| Feature {
            id: format!("{}:{}", project_dir, i),
            project_dir: project_dir.clone(),
            description: f["description"].as_str().unwrap_or("").to_string(),
            category: f["category"].as_str().unwrap_or("functional").to_string(),
            passes: f["passes"].as_bool().unwrap_or(false),
            in_progress: f["inProgress"].as_bool().unwrap_or(false),
            agent: f["agent"].as_str().map(String::from),
            updated_at: chrono::Utc::now().to_rfc3339(),
        })
        .collect();

    // Detect newly completed features
    for feature in &parsed_features {
        if feature.passes && !old_completed.contains(&feature.description) {
            // New completion!
            let event = AgentEvent {
                id: None,
                event_type: "FeatureCompleted".to_string(),
                source_agent: feature
                    .agent
                    .clone()
                    .unwrap_or_else(|| "unknown".to_string()),
                session_id: "file-watch".to_string(),
                project_dir: project_dir.clone(),
                tool_name: Some(feature.description.clone()),
                payload: Some(
                    serde_json::json!({
                        "category": feature.category
                    })
                    .to_string(),
                ),
                feature_id: Some(feature.id.clone()),
                created_at: chrono::Utc::now().to_rfc3339(),
            };

            let _ = db.0.insert_event(&event);
            let _ = event_tx.send(event);

            // Send desktop notification
            send_notification(app, "✅ Feature Completed", &feature.description);
        }
    }

    // Sync all features to database
    let _ = db.0.sync_features(&project_dir, parsed_features);

    // Emit refresh event to frontend
    let _ = app.emit("features-updated", &project_dir);
}

fn send_notification(app: &tauri::AppHandle, title: &str, body: &str) {
    use tauri_plugin_notification::NotificationExt;
    let _ = app.notification().builder().title(title).body(body).show();
}
