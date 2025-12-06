use crate::db::{Config, DbState, Feature, AgentEvent, Session, Stats};
use tauri::State;

#[tauri::command]
pub async fn get_features(
    db: State<'_, DbState>,
    project_dir: Option<String>,
) -> Result<Vec<Feature>, String> {
    db.0.get_features(project_dir.as_deref())
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn get_events(
    db: State<'_, DbState>,
    limit: Option<i64>,
) -> Result<Vec<AgentEvent>, String> {
    db.0.get_events(limit.unwrap_or(50))
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn get_feature_events(
    db: State<'_, DbState>,
    feature_id: String,
    limit: Option<i64>,
) -> Result<Vec<AgentEvent>, String> {
    db.0.get_events_by_feature(&feature_id, limit.unwrap_or(100))
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn get_sessions(db: State<'_, DbState>) -> Result<Vec<Session>, String> {
    db.0.get_sessions().map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn get_stats(db: State<'_, DbState>) -> Result<Stats, String> {
    db.0.get_stats().map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn scan_projects() -> Result<Vec<String>, String> {
    let home = dirs::home_dir().ok_or("No home directory")?;
    let mut projects = vec![];

    // Common project locations
    let search_dirs = vec![
        home.join("projects"),
        home.join("code"),
        home.join("dev"),
        home.join("workspace"),
        home.join("Documents/projects"),
    ];

    for search_dir in search_dirs {
        if !search_dir.exists() {
            continue;
        }

        // Look for feature_list.json files
        let pattern = format!("{}/**/feature_list.json", search_dir.display());
        if let Ok(paths) = glob::glob(&pattern) {
            for entry in paths.flatten() {
                if let Some(parent) = entry.parent() {
                    projects.push(parent.to_string_lossy().to_string());
                }
            }
        }
    }

    // Also check Claude projects directory for recent projects
    let claude_projects = home.join(".claude/projects");
    if claude_projects.exists() {
        if let Ok(entries) = std::fs::read_dir(&claude_projects) {
            for entry in entries.flatten() {
                // Claude encodes project paths - we'd need to decode them
                // For now, just note that there are Claude projects
                let name = entry.file_name().to_string_lossy().to_string();
                if !name.starts_with('.') {
                    // Decode the project path (it's typically URL-encoded or similar)
                    // This is a simplified version
                    if let Ok(decoded) = urlencoding::decode(&name) {
                        let path = decoded.to_string();
                        if std::path::Path::new(&path).exists() && !projects.contains(&path) {
                            projects.push(path);
                        }
                    }
                }
            }
        }
    }

    projects.sort();
    projects.dedup();

    Ok(projects)
}

#[tauri::command]
pub async fn watch_project(
    db: State<'_, DbState>,
    project_dir: String,
) -> Result<(), String> {
    let mut config = db.0.get_config().map_err(|e| e.to_string())?;

    if !config.watched_projects.contains(&project_dir) {
        config.watched_projects.push(project_dir);
        db.0.save_config(&config).map_err(|e| e.to_string())?;
    }

    Ok(())
}

#[tauri::command]
pub async fn get_config(db: State<'_, DbState>) -> Result<Config, String> {
    db.0.get_config().map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn save_config(db: State<'_, DbState>, config: Config) -> Result<(), String> {
    db.0.save_config(&config).map_err(|e| e.to_string())
}
