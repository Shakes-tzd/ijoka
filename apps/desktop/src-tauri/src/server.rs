use crate::db::{AgentEvent, DbState, Feature, Session};
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
use tauri::{Emitter, Manager};
use tokio::sync::broadcast;
use tower_http::cors::{Any, CorsLayer};

#[derive(Clone)]
struct AppState {
    app: tauri::AppHandle,
    event_tx: Arc<broadcast::Sender<AgentEvent>>,
}

pub async fn start_server(
    app: tauri::AppHandle,
    event_tx: Arc<broadcast::Sender<AgentEvent>>,
    port: u16,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let state = AppState { app, event_tx };

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let router = Router::new()
        .route("/health", get(health))
        .route("/events", get(get_events).post(receive_event))
        .route("/events/feature-update", post(receive_feature_update))
        .route("/events/{id}/link", post(link_event))
        .route("/sessions/start", post(session_start))
        .route("/sessions/end", post(session_end))
        .layer(cors)
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(format!("127.0.0.1:{}", port)).await?;

    tracing::info!("HTTP server listening on http://127.0.0.1:{}", port);

    axum::serve(listener, router).await?;

    Ok(())
}

async fn health() -> &'static str {
    "OK"
}

#[derive(Deserialize)]
struct EventsQuery {
    limit: Option<i64>,
    unlinked: Option<bool>,
    project_dir: Option<String>,
}

async fn get_events(
    State(state): State<AppState>,
    Query(query): Query<EventsQuery>,
) -> Json<Vec<AgentEvent>> {
    let db: tauri::State<DbState> = state.app.state();
    let limit = query.limit.unwrap_or(50);

    let events = if query.unlinked.unwrap_or(false) {
        db.0.get_unlinked_events(query.project_dir.as_deref(), limit)
            .unwrap_or_default()
    } else {
        db.0.get_events(limit).unwrap_or_default()
    };

    Json(events)
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct LinkEventRequest {
    feature_id: String,
}

async fn link_event(
    State(state): State<AppState>,
    Path(event_id): Path<i64>,
    Json(request): Json<LinkEventRequest>,
) -> Json<ApiResponse> {
    let db: tauri::State<DbState> = state.app.state();

    match db.0.link_event_to_feature(event_id, &request.feature_id) {
        Ok(true) => Json(ApiResponse { ok: true, error: None }),
        Ok(false) => Json(ApiResponse {
            ok: false,
            error: Some("Event not found".to_string()),
        }),
        Err(e) => Json(ApiResponse {
            ok: false,
            error: Some(e.to_string()),
        }),
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct IncomingEvent {
    event_type: String,
    source_agent: String,
    session_id: String,
    project_dir: String,
    tool_name: Option<String>,
    payload: Option<serde_json::Value>,
    feature_id: Option<String>,
}

#[derive(Serialize)]
struct ApiResponse {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

async fn receive_event(
    State(state): State<AppState>,
    Json(incoming): Json<IncomingEvent>,
) -> Json<ApiResponse> {
    let event = AgentEvent {
        id: None,
        event_type: incoming.event_type,
        source_agent: incoming.source_agent,
        session_id: incoming.session_id,
        project_dir: incoming.project_dir,
        tool_name: incoming.tool_name,
        payload: incoming.payload.map(|p| p.to_string()),
        feature_id: incoming.feature_id,
        created_at: chrono::Utc::now().to_rfc3339(),
    };

    // Store in database
    let db: tauri::State<DbState> = state.app.state();
    if let Err(e) = db.0.insert_event(&event) {
        tracing::error!("Failed to insert event: {}", e);
        return Json(ApiResponse {
            ok: false,
            error: Some(format!("Database error: {}", e)),
        });
    }

    // Broadcast to frontend
    let _ = state.event_tx.send(event);

    Json(ApiResponse { ok: true, error: None })
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct FeatureUpdateEvent {
    project_dir: String,
    stats: FeatureStats,
    changed_features: Vec<ChangedFeature>,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct FeatureStats {
    total: i64,
    completed: i64,
    percentage: f64,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ChangedFeature {
    description: String,
    category: String,
}

async fn receive_feature_update(
    State(state): State<AppState>,
    Json(update): Json<FeatureUpdateEvent>,
) -> Json<ApiResponse> {
    let db: tauri::State<DbState> = state.app.state();

    // Create events for completed features
    for feature in update.changed_features {
        let event = AgentEvent {
            id: None,
            event_type: "FeatureCompleted".to_string(),
            source_agent: "hook".to_string(),
            session_id: "feature-update".to_string(),
            project_dir: update.project_dir.clone(),
            tool_name: Some(feature.description.clone()),
            payload: Some(serde_json::json!({ "category": feature.category }).to_string()),
            feature_id: None,
            created_at: chrono::Utc::now().to_rfc3339(),
        };

        let _ = db.0.insert_event(&event);
        let _ = state.event_tx.send(event);

        // Desktop notification
        use tauri_plugin_notification::NotificationExt;
        let _ = state
            .app
            .notification()
            .builder()
            .title("✅ Feature Completed")
            .body(&feature.description)
            .show();
    }

    // Emit progress update to frontend
    let _ = state.app.emit("progress-update", &update.stats);

    Json(ApiResponse { ok: true, error: None })
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct SessionStartEvent {
    session_id: String,
    source_agent: String,
    project_dir: String,
}

async fn session_start(
    State(state): State<AppState>,
    Json(incoming): Json<SessionStartEvent>,
) -> Json<ApiResponse> {
    let db: tauri::State<DbState> = state.app.state();

    let now = chrono::Utc::now().to_rfc3339();
    let session = Session {
        session_id: incoming.session_id.clone(),
        source_agent: incoming.source_agent.clone(),
        project_dir: incoming.project_dir.clone(),
        started_at: now.clone(),
        last_activity: now.clone(),
        status: "active".to_string(),
    };

    if let Err(e) = db.0.upsert_session(&session) {
        tracing::error!("Failed to start session: {}", e);
        return Json(ApiResponse {
            ok: false,
            error: Some(e.to_string()),
        });
    }

    // Auto-register project if not already watched
    let project_dir = &incoming.project_dir;
    match db.0.add_watched_project(project_dir) {
        Ok(true) => {
            tracing::info!("Auto-registered new project: {}", project_dir);
            // Sync features from feature_list.json if it exists
            sync_features_from_file(&db, project_dir, &state.app);
        }
        Ok(false) => {
            // Project already registered, still sync features in case file changed
            sync_features_from_file(&db, project_dir, &state.app);
        }
        Err(e) => {
            tracing::error!("Failed to auto-register project: {}", e);
        }
    }

    // Create session start event
    let event = AgentEvent {
        id: None,
        event_type: "SessionStart".to_string(),
        source_agent: incoming.source_agent,
        session_id: incoming.session_id,
        project_dir: incoming.project_dir,
        tool_name: None,
        payload: None,
        feature_id: None,
        created_at: now,
    };

    let _ = db.0.insert_event(&event);
    let _ = state.event_tx.send(event);

    Json(ApiResponse { ok: true, error: None })
}

/// Sync features from feature_list.json file to database
fn sync_features_from_file(db: &tauri::State<DbState>, project_dir: &str, app: &tauri::AppHandle) {
    let feature_file = PathBuf::from(project_dir).join("feature_list.json");

    if !feature_file.exists() {
        return;
    }

    let content = match std::fs::read_to_string(&feature_file) {
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
                project_dir: project_dir.to_string(),
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

    if let Err(e) = db.0.sync_features(project_dir, parsed_features) {
        tracing::error!("Failed to sync features: {}", e);
    } else {
        tracing::info!("Synced {} features for {}", features.len(), project_dir);
        // Emit refresh event to frontend
        let _ = app.emit("features-updated", project_dir);
    }
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct SessionEndEvent {
    session_id: String,
}

async fn session_end(
    State(state): State<AppState>,
    Json(incoming): Json<SessionEndEvent>,
) -> Json<ApiResponse> {
    let db: tauri::State<DbState> = state.app.state();

    // Update session status
    if let Err(e) = db.0.update_session_status(&incoming.session_id, "ended") {
         tracing::error!("Failed to update session status: {}", e);
         // Continue to log event even if status update fails
    }

    let event = AgentEvent {
        id: None,
        event_type: "SessionEnd".to_string(),
        source_agent: "unknown".to_string(),
        session_id: incoming.session_id,
        project_dir: "".to_string(),
        tool_name: None,
        payload: None,
        feature_id: None,
        created_at: chrono::Utc::now().to_rfc3339(),
    };

    let _ = db.0.insert_event(&event);
    let _ = state.event_tx.send(event);

    Json(ApiResponse { ok: true, error: None })
}
