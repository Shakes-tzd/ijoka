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
    let encoded_project = path
        .parent()
        .and_then(|p| p.file_name())
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "unknown".to_string());

    // Decode the project path (Claude uses - as path separator)
    // e.g., "-Users-shakes-DevProjects-agentkanban" -> "/Users/shakes/DevProjects/agentkanban"
    let project_dir = if encoded_project.starts_with('-') {
        encoded_project.replace('-', "/")
    } else {
        encoded_project
    };

    // Parse session ID from filename
    let session_id = path
        .file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());

    // Find active feature in this project
    let feature_id = get_active_feature_id(&project_dir);

    // Get last transcript entry for context
    let (tool_name, payload) = get_last_transcript_entry(path);

    let event = AgentEvent {
        id: None,
        event_type: "TranscriptUpdated".to_string(),
        source_agent: "claude-code".to_string(),
        session_id,
        project_dir,
        tool_name,
        payload,
        feature_id,
        created_at: chrono::Utc::now().to_rfc3339(),
    };

    // Store in database
    let db: tauri::State<DbState> = app.state();
    let _ = db.0.insert_event(&event);

    // Broadcast to frontend
    let _ = event_tx.send(event);
}

/// Parse the last entry from a transcript JSONL file
fn get_last_transcript_entry(path: &Path) -> (Option<String>, Option<String>) {
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(_) => return (None, None),
    };

    // Get last non-empty line
    let last_line = content.lines().filter(|l| !l.trim().is_empty()).last();
    let last_line = match last_line {
        Some(l) => l,
        None => return (None, None),
    };

    // Parse as JSON
    let entry: serde_json::Value = match serde_json::from_str(last_line) {
        Ok(v) => v,
        Err(_) => return (None, None),
    };

    // Extract useful info based on message type
    let msg_type = entry["type"].as_str().unwrap_or("unknown");

    match msg_type {
        "user" => {
            // User messages can have: text, image+text, or tool_result
            let content = entry["message"]["content"].as_array();
            if let Some(arr) = content {
                // Look for text in any content item
                for item in arr {
                    if item["type"].as_str() == Some("text") {
                        let text = item["text"].as_str()
                            .unwrap_or("")
                            .chars()
                            .take(500)
                            .collect::<String>();
                        if !text.is_empty() {
                            let payload = serde_json::json!({
                                "messageType": "user",
                                "preview": text
                            });
                            return (Some("UserMessage".to_string()), Some(payload.to_string()));
                        }
                    }
                    if item["type"].as_str() == Some("tool_result") {
                        let tool_use_id = item["tool_use_id"].as_str().unwrap_or("unknown");
                        let is_error = item["is_error"].as_bool().unwrap_or(false);

                        // Extract content preview
                        let content_preview = if let Some(content) = item["content"].as_str() {
                            content.chars().take(300).collect::<String>()
                        } else if let Some(arr) = item["content"].as_array() {
                            // Content can be array of text blocks
                            arr.iter()
                                .filter_map(|c| c["text"].as_str())
                                .collect::<Vec<_>>()
                                .join("\n")
                                .chars()
                                .take(300)
                                .collect::<String>()
                        } else {
                            String::new()
                        };

                        let payload = serde_json::json!({
                            "messageType": "tool_result",
                            "toolUseId": tool_use_id,
                            "isError": is_error,
                            "preview": content_preview
                        });
                        return (Some("ToolResult".to_string()), Some(payload.to_string()));
                    }
                    if item["type"].as_str() == Some("image") {
                        let payload = serde_json::json!({
                            "messageType": "image",
                            "preview": "📷 Image uploaded"
                        });
                        return (Some("Image".to_string()), Some(payload.to_string()));
                    }
                }
            }
            let payload = serde_json::json!({
                "messageType": "user",
                "preview": ""
            });
            (Some("UserMessage".to_string()), Some(payload.to_string()))
        }
        "assistant" => {
            // Check if it's a tool use, text response, or thinking
            let content = entry["message"]["content"].as_array();
            if let Some(arr) = content {
                for item in arr {
                    if item["type"].as_str() == Some("tool_use") {
                        let tool = item["name"].as_str().unwrap_or("unknown");
                        let tool_input = &item["input"];

                        // Extract common input fields based on tool type
                        let mut payload = serde_json::json!({
                            "messageType": "tool_use",
                            "tool": tool
                        });

                        // Add tool-specific input details
                        match tool {
                            "Bash" => {
                                if let Some(cmd) = tool_input["command"].as_str() {
                                    payload["command"] = serde_json::json!(cmd.chars().take(500).collect::<String>());
                                }
                                if let Some(desc) = tool_input["description"].as_str() {
                                    payload["description"] = serde_json::json!(desc);
                                }
                            }
                            "Edit" => {
                                if let Some(fp) = tool_input["file_path"].as_str() {
                                    payload["filePath"] = serde_json::json!(fp);
                                }
                                if let Some(old) = tool_input["old_string"].as_str() {
                                    payload["oldString"] = serde_json::json!(old.chars().take(200).collect::<String>());
                                }
                                if let Some(new) = tool_input["new_string"].as_str() {
                                    payload["newString"] = serde_json::json!(new.chars().take(200).collect::<String>());
                                }
                            }
                            "Write" => {
                                if let Some(fp) = tool_input["file_path"].as_str() {
                                    payload["filePath"] = serde_json::json!(fp);
                                }
                                if let Some(content) = tool_input["content"].as_str() {
                                    payload["contentPreview"] = serde_json::json!(content.chars().take(200).collect::<String>());
                                }
                            }
                            "Read" => {
                                if let Some(fp) = tool_input["file_path"].as_str() {
                                    payload["filePath"] = serde_json::json!(fp);
                                }
                                if let Some(offset) = tool_input["offset"].as_i64() {
                                    payload["offset"] = serde_json::json!(offset);
                                }
                                if let Some(limit) = tool_input["limit"].as_i64() {
                                    payload["limit"] = serde_json::json!(limit);
                                }
                            }
                            "Grep" => {
                                if let Some(pattern) = tool_input["pattern"].as_str() {
                                    payload["pattern"] = serde_json::json!(pattern);
                                }
                                if let Some(path) = tool_input["path"].as_str() {
                                    payload["path"] = serde_json::json!(path);
                                }
                            }
                            "Glob" => {
                                if let Some(pattern) = tool_input["pattern"].as_str() {
                                    payload["pattern"] = serde_json::json!(pattern);
                                }
                                if let Some(path) = tool_input["path"].as_str() {
                                    payload["path"] = serde_json::json!(path);
                                }
                            }
                            "Task" => {
                                if let Some(desc) = tool_input["description"].as_str() {
                                    payload["taskDescription"] = serde_json::json!(desc);
                                }
                                if let Some(agent) = tool_input["subagent_type"].as_str() {
                                    payload["subagentType"] = serde_json::json!(agent);
                                }
                            }
                            _ => {
                                // For other tools, include a preview of the input
                                let input_str = tool_input.to_string();
                                if input_str.len() > 2 { // More than just "{}"
                                    payload["inputPreview"] = serde_json::json!(input_str.chars().take(300).collect::<String>());
                                }
                            }
                        }

                        return (Some(tool.to_string()), Some(payload.to_string()));
                    }
                    if item["type"].as_str() == Some("text") {
                        let text = item["text"].as_str()
                            .unwrap_or("")
                            .chars()
                            .take(500)
                            .collect::<String>();
                        let payload = serde_json::json!({
                            "messageType": "assistant",
                            "preview": text
                        });
                        return (Some("Response".to_string()), Some(payload.to_string()));
                    }
                    if item["type"].as_str() == Some("thinking") {
                        let text = item["thinking"].as_str()
                            .unwrap_or("")
                            .chars()
                            .take(500)
                            .collect::<String>();
                        let payload = serde_json::json!({
                            "messageType": "thinking",
                            "preview": text
                        });
                        return (Some("Thinking".to_string()), Some(payload.to_string()));
                    }
                }
            }
            (Some("Assistant".to_string()), None)
        }
        "result" => {
            // Standalone result entry (different format)
            let is_error = entry["is_error"].as_bool().unwrap_or(false);
            let tool_use_id = entry["tool_use_id"].as_str().unwrap_or("unknown");

            // Extract content preview
            let content_preview = if let Some(content) = entry["content"].as_str() {
                content.chars().take(300).collect::<String>()
            } else if let Some(arr) = entry["content"].as_array() {
                arr.iter()
                    .filter_map(|c| c["text"].as_str())
                    .collect::<Vec<_>>()
                    .join("\n")
                    .chars()
                    .take(300)
                    .collect::<String>()
            } else if let Some(output) = entry["output"].as_str() {
                // Some results use "output" field
                output.chars().take(300).collect::<String>()
            } else {
                String::new()
            };

            let payload = serde_json::json!({
                "messageType": "tool_result",
                "toolUseId": tool_use_id,
                "isError": is_error,
                "preview": content_preview
            });
            (Some("ToolResult".to_string()), Some(payload.to_string()))
        }
        _ => (None, None),
    }
}

/// Get the active feature ID (project_dir:index) from feature_list.json
fn get_active_feature_id(project_dir: &str) -> Option<String> {
    let feature_path = PathBuf::from(project_dir).join("feature_list.json");
    let content = std::fs::read_to_string(&feature_path).ok()?;
    let features: Vec<serde_json::Value> = serde_json::from_str(&content).ok()?;

    for (index, feature) in features.iter().enumerate() {
        if feature["inProgress"].as_bool().unwrap_or(false) {
            return Some(format!("{}:{}", project_dir, index));
        }
    }
    None
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
        .map(|(i, f)| {
            let steps = f["steps"]
                .as_array()
                .map(|arr| {
                    arr.iter()
                        .filter_map(|s| s.as_str().map(String::from))
                        .collect()
                });

            Feature {
                id: format!("{}:{}", project_dir, i),
                project_dir: project_dir.clone(),
                description: f["description"].as_str().unwrap_or("").to_string(),
                category: f["category"].as_str().unwrap_or("functional").to_string(),
                passes: f["passes"].as_bool().unwrap_or(false),
                in_progress: f["inProgress"].as_bool().unwrap_or(false),
                agent: f["agent"].as_str().map(String::from),
                steps,
                updated_at: chrono::Utc::now().to_rfc3339(),
            }
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
