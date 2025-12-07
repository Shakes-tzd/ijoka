use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::sync::{Arc, Mutex};

pub struct Database {
    conn: Mutex<Connection>,
}

pub struct DbState(pub Arc<Database>);

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentEvent {
    pub id: Option<i64>,
    pub event_type: String,
    pub source_agent: String,
    pub session_id: String,
    pub project_dir: String,
    pub tool_name: Option<String>,
    pub payload: Option<String>,
    pub feature_id: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Feature {
    pub id: String,
    pub project_dir: String,
    pub description: String,
    pub category: String,
    pub passes: bool,
    pub in_progress: bool,
    pub agent: Option<String>,
    pub steps: Option<Vec<String>>,
    pub updated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Session {
    pub session_id: String,
    pub source_agent: String,
    pub project_dir: String,
    pub started_at: String,
    pub last_activity: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Stats {
    pub total: i64,
    pub completed: i64,
    pub in_progress: i64,
    pub percentage: f64,
    pub active_sessions: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Config {
    pub watched_projects: Vec<String>,
    pub sync_server_port: u16,
    pub notifications_enabled: bool,
    pub selected_project: Option<String>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            watched_projects: vec![],
            sync_server_port: 4000,
            notifications_enabled: true,
            selected_project: None,
        }
    }
}

impl Database {
    pub fn new(path: &Path) -> Result<Self, rusqlite::Error> {
        let conn = Connection::open(path)?;

        // Create base tables
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                source_agent TEXT NOT NULL,
                session_id TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                tool_name TEXT,
                payload TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS features (
                id TEXT PRIMARY KEY,
                project_dir TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT DEFAULT 'functional',
                passes INTEGER DEFAULT 0,
                in_progress INTEGER DEFAULT 0,
                agent TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                source_agent TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                started_at TEXT DEFAULT (datetime('now')),
                last_activity TEXT DEFAULT (datetime('now')),
                status TEXT DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_dir);
            CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_features_project ON features(project_dir);
            "#,
        )?;

        // Migration: Add feature_id column if it doesn't exist
        // SQLite doesn't support IF NOT EXISTS for columns, so we try and ignore errors
        let _ = conn.execute("ALTER TABLE events ADD COLUMN feature_id TEXT", []);

        // Create index on feature_id (will only create if doesn't exist)
        conn.execute_batch("CREATE INDEX IF NOT EXISTS idx_events_feature_id ON events(feature_id);")?;

        // Migration: Add steps column to features table
        let _ = conn.execute("ALTER TABLE features ADD COLUMN steps TEXT", []);

        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    pub fn insert_event(&self, event: &AgentEvent) -> Result<i64, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT INTO events (event_type, source_agent, session_id, project_dir, tool_name, payload, feature_id)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                event.event_type,
                event.source_agent,
                event.session_id,
                event.project_dir,
                event.tool_name,
                event.payload,
                event.feature_id,
            ],
        )?;
        Ok(conn.last_insert_rowid())
    }

    pub fn get_events(&self, limit: i64) -> Result<Vec<AgentEvent>, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, event_type, source_agent, session_id, project_dir, tool_name, payload, feature_id, created_at
             FROM events ORDER BY created_at DESC LIMIT ?1",
        )?;

        let events = stmt
            .query_map([limit], |row| {
                Ok(AgentEvent {
                    id: Some(row.get(0)?),
                    event_type: row.get(1)?,
                    source_agent: row.get(2)?,
                    session_id: row.get(3)?,
                    project_dir: row.get(4)?,
                    tool_name: row.get(5)?,
                    payload: row.get(6)?,
                    feature_id: row.get(7)?,
                    created_at: row.get(8)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;

        Ok(events)
    }

    pub fn get_events_by_feature(&self, feature_id: &str, limit: i64) -> Result<Vec<AgentEvent>, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, event_type, source_agent, session_id, project_dir, tool_name, payload, feature_id, created_at
             FROM events WHERE feature_id = ?1 ORDER BY created_at DESC LIMIT ?2",
        )?;

        let events = stmt
            .query_map(params![feature_id, limit], |row| {
                Ok(AgentEvent {
                    id: Some(row.get(0)?),
                    event_type: row.get(1)?,
                    source_agent: row.get(2)?,
                    session_id: row.get(3)?,
                    project_dir: row.get(4)?,
                    tool_name: row.get(5)?,
                    payload: row.get(6)?,
                    feature_id: row.get(7)?,
                    created_at: row.get(8)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;

        Ok(events)
    }

    pub fn sync_features(
        &self,
        project_dir: &str,
        features: Vec<Feature>,
    ) -> Result<(), rusqlite::Error> {
        let conn = self.conn.lock().unwrap();

        for feature in features {
            let steps_json = feature
                .steps
                .as_ref()
                .map(|s| serde_json::to_string(s).unwrap_or_default());

            conn.execute(
                "INSERT OR REPLACE INTO features (id, project_dir, description, category, passes, in_progress, agent, steps, updated_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, datetime('now'))",
                params![
                    feature.id,
                    project_dir,
                    feature.description,
                    feature.category,
                    feature.passes,
                    feature.in_progress,
                    feature.agent,
                    steps_json,
                ],
            )?;
        }

        Ok(())
    }

    pub fn get_features(&self, project_dir: Option<&str>) -> Result<Vec<Feature>, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();

        fn parse_steps(steps_json: Option<String>) -> Option<Vec<String>> {
            steps_json.and_then(|s| serde_json::from_str(&s).ok())
        }

        if let Some(dir) = project_dir {
            let mut stmt = conn.prepare(
                "SELECT id, project_dir, description, category, passes, in_progress, agent, steps, updated_at
                 FROM features WHERE project_dir = ?1 ORDER BY id",
            )?;

            let features = stmt
                .query_map([dir], |row| {
                    Ok(Feature {
                        id: row.get(0)?,
                        project_dir: row.get(1)?,
                        description: row.get(2)?,
                        category: row.get(3)?,
                        passes: row.get(4)?,
                        in_progress: row.get(5)?,
                        agent: row.get(6)?,
                        steps: parse_steps(row.get(7)?),
                        updated_at: row.get(8)?,
                    })
                })?
                .collect::<Result<Vec<_>, _>>()?;

            Ok(features)
        } else {
            let mut stmt = conn.prepare(
                "SELECT id, project_dir, description, category, passes, in_progress, agent, steps, updated_at
                 FROM features ORDER BY project_dir, id",
            )?;

            let features = stmt
                .query_map([], |row| {
                    Ok(Feature {
                        id: row.get(0)?,
                        project_dir: row.get(1)?,
                        description: row.get(2)?,
                        category: row.get(3)?,
                        passes: row.get(4)?,
                        in_progress: row.get(5)?,
                        agent: row.get(6)?,
                        steps: parse_steps(row.get(7)?),
                        updated_at: row.get(8)?,
                    })
                })?
                .collect::<Result<Vec<_>, _>>()?;

            Ok(features)
        }
    }

    pub fn get_sessions(&self) -> Result<Vec<Session>, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT session_id, source_agent, project_dir, started_at, last_activity, status
             FROM sessions WHERE status = 'active' ORDER BY last_activity DESC",
        )?;

        let sessions = stmt
            .query_map([], |row| {
                Ok(Session {
                    session_id: row.get(0)?,
                    source_agent: row.get(1)?,
                    project_dir: row.get(2)?,
                    started_at: row.get(3)?,
                    last_activity: row.get(4)?,
                    status: row.get(5)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;

        Ok(sessions)
    }

    pub fn upsert_session(&self, session: &Session) -> Result<(), rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, source_agent, project_dir, started_at, last_activity, status)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                session.session_id,
                session.source_agent,
                session.project_dir,
                session.started_at,
                session.last_activity,
                session.status,
            ],
        )?;
        Ok(())
    }

    pub fn update_session_status(
        &self,
        session_id: &str,
        status: &str,
    ) -> Result<(), rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE sessions SET status = ?1, last_activity = datetime('now') WHERE session_id = ?2",
            params![status, session_id],
        )?;
        Ok(())
    }

    pub fn get_stats(&self) -> Result<Stats, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();

        let total: i64 = conn.query_row("SELECT COUNT(*) FROM features", [], |r| r.get(0))?;

        let completed: i64 =
            conn.query_row("SELECT COUNT(*) FROM features WHERE passes = 1", [], |r| {
                r.get(0)
            })?;

        let in_progress: i64 = conn.query_row(
            "SELECT COUNT(*) FROM features WHERE in_progress = 1 AND passes = 0",
            [],
            |r| r.get(0),
        )?;

        let active_sessions: i64 = conn.query_row(
            "SELECT COUNT(*) FROM sessions WHERE status = 'active'",
            [],
            |r| r.get(0),
        )?;

        let percentage = if total > 0 {
            (completed as f64 / total as f64) * 100.0
        } else {
            0.0
        };

        Ok(Stats {
            total,
            completed,
            in_progress,
            percentage,
            active_sessions,
        })
    }

    pub fn get_config(&self) -> Result<Config, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();

        let config_json: Option<String> = conn
            .query_row("SELECT value FROM config WHERE key = 'main'", [], |r| {
                r.get(0)
            })
            .ok();

        match config_json {
            Some(json) => Ok(serde_json::from_str(&json).unwrap_or_default()),
            None => Ok(Config::default()),
        }
    }

    pub fn save_config(&self, config: &Config) -> Result<(), rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        let json = serde_json::to_string(config).unwrap();
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('main', ?1)",
            [json],
        )?;
        Ok(())
    }

    pub fn get_projects(&self) -> Result<Vec<String>, rusqlite::Error> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT DISTINCT project_dir FROM features ORDER BY project_dir",
        )?;

        let projects = stmt
            .query_map([], |row| row.get(0))?
            .collect::<Result<Vec<String>, _>>()?;

        Ok(projects)
    }

    /// Add a project to watched_projects if not already present.
    /// Returns true if the project was added, false if already exists.
    pub fn add_watched_project(&self, project_dir: &str) -> Result<bool, rusqlite::Error> {
        let mut config = self.get_config()?;

        if config.watched_projects.contains(&project_dir.to_string()) {
            return Ok(false);
        }

        config.watched_projects.push(project_dir.to_string());
        self.save_config(&config)?;
        Ok(true)
    }
}
