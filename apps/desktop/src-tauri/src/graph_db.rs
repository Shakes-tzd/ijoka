//! Graph Database Module for Ijoka
//!
//! Provides connectivity to Memgraph/Neo4j for the source of truth data store.
//! SQLite remains as a local read cache for fast UI rendering.

use anyhow::{Context, Result};
use neo4rs::{query, ConfigBuilder, Graph, Node};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::RwLock;

/// Graph database connection pool
pub struct GraphDb {
    graph: Arc<RwLock<Option<Graph>>>,
    config: GraphDbConfig,
}

#[derive(Clone, Debug)]
pub struct GraphDbConfig {
    pub uri: String,
    pub user: String,
    pub password: String,
    pub database: String,
}

impl Default for GraphDbConfig {
    fn default() -> Self {
        Self {
            uri: std::env::var("IJOKA_GRAPH_URI")
                .unwrap_or_else(|_| "bolt://localhost:7687".to_string()),
            user: std::env::var("IJOKA_GRAPH_USER").unwrap_or_else(|_| "".to_string()),
            password: std::env::var("IJOKA_GRAPH_PASSWORD")
                .unwrap_or_else(|_| "".to_string()),
            database: std::env::var("IJOKA_GRAPH_DATABASE")
                .unwrap_or_else(|_| "memgraph".to_string()),
        }
    }
}

impl GraphDb {
    /// Create a new GraphDb instance with default config
    pub fn new() -> Self {
        Self::with_config(GraphDbConfig::default())
    }

    /// Create a new GraphDb instance with custom config
    pub fn with_config(config: GraphDbConfig) -> Self {
        Self {
            graph: Arc::new(RwLock::new(None)),
            config,
        }
    }

    /// Connect to the graph database
    pub async fn connect(&self) -> Result<()> {
        tracing::info!("Connecting to graph database at {}", self.config.uri);

        // Use ConfigBuilder to explicitly set empty database for Memgraph
        // (neo4rs defaults to "neo4j" which Memgraph doesn't support)
        let config = ConfigBuilder::new()
            .uri(&self.config.uri)
            .user(&self.config.user)
            .password(&self.config.password)
            .db("memgraph") // Memgraph only accepts "memgraph" as db name
            .build()
            .context("Failed to build graph config")?;

        let graph = Graph::connect(config)
            .await
            .context("Failed to connect to graph database")?;

        // Verify connection with a simple query
        let mut result = graph.execute(query("RETURN 1 as n")).await?;
        if result.next().await?.is_some() {
            tracing::info!("Successfully connected to graph database");
        }

        let mut guard = self.graph.write().await;
        *guard = Some(graph);

        Ok(())
    }

    /// Check if connected to the graph database
    pub async fn is_connected(&self) -> bool {
        self.graph.read().await.is_some()
    }

    /// Get the graph connection (panics if not connected)
    async fn get_graph(&self) -> Result<Graph> {
        let guard = self.graph.read().await;
        guard
            .clone()
            .ok_or_else(|| anyhow::anyhow!("Not connected to graph database"))
    }

    // =========================================================================
    // PROJECT OPERATIONS
    // =========================================================================

    /// Create or update a project
    pub async fn upsert_project(&self, project: &Project) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MERGE (p:Project {path: $path})
            ON CREATE SET
                p.id = $id,
                p.name = $name,
                p.description = $description,
                p.created_at = datetime(),
                p.updated_at = datetime(),
                p.settings = $settings
            ON MATCH SET
                p.name = $name,
                p.description = $description,
                p.updated_at = datetime(),
                p.settings = $settings
            RETURN p
            "#,
        )
        .param("id", project.id.clone())
        .param("path", project.path.clone())
        .param("name", project.name.clone())
        .param("description", project.description.clone().unwrap_or_default())
        .param(
            "settings",
            serde_json::to_string(&project.settings).unwrap_or_default(),
        );

        graph.run(q).await?;
        Ok(())
    }

    /// Get all projects
    pub async fn get_projects(&self) -> Result<Vec<Project>> {
        let graph = self.get_graph().await?;

        let q = query("MATCH (p:Project) RETURN p ORDER BY p.name");
        let mut result = graph.execute(q).await?;

        let mut projects = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("p")?;
            projects.push(Project::from_node(&node)?);
        }

        Ok(projects)
    }

    /// Get project by path
    pub async fn get_project_by_path(&self, path: &str) -> Result<Option<Project>> {
        let graph = self.get_graph().await?;

        let q = query("MATCH (p:Project {path: $path}) RETURN p").param("path", path);
        let mut result = graph.execute(q).await?;

        if let Some(row) = result.next().await? {
            let node: Node = row.get("p")?;
            Ok(Some(Project::from_node(&node)?))
        } else {
            Ok(None)
        }
    }

    // =========================================================================
    // FEATURE OPERATIONS
    // =========================================================================

    /// Create a new feature linked to a project
    pub async fn create_feature(&self, feature: &Feature, project_path: &str) -> Result<String> {
        let graph = self.get_graph().await?;

        let feature_id = feature
            .id
            .clone()
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());

        let q = query(
            r#"
            MATCH (p:Project {path: $project_path})
            CREATE (f:Feature {
                id: $id,
                description: $description,
                category: $category,
                status: $status,
                priority: $priority,
                steps: $steps,
                created_at: datetime(),
                updated_at: datetime(),
                work_count: 0
            })-[:BELONGS_TO]->(p)
            RETURN f.id as id
            "#,
        )
        .param("project_path", project_path)
        .param("id", feature_id.clone())
        .param("description", feature.description.clone())
        .param("category", feature.category.clone())
        .param("status", feature.status.clone())
        .param("priority", feature.priority.unwrap_or(0) as i64)
        .param("steps", feature.steps.clone().unwrap_or_default());

        graph.run(q).await?;
        Ok(feature_id)
    }

    /// Get all features for a project
    pub async fn get_features_for_project(&self, project_path: &str) -> Result<Vec<Feature>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $project_path})
            RETURN f
            ORDER BY f.priority DESC, f.created_at DESC
            "#,
        )
        .param("project_path", project_path);

        let mut result = graph.execute(q).await?;

        let mut features = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("f")?;
            let mut feature = Feature::from_node(&node)?;
            feature.project_dir = Some(project_path.to_string());
            features.push(feature);
        }

        Ok(features)
    }

    /// Get active feature for a project (status = 'in_progress')
    pub async fn get_active_feature(&self, project_path: &str) -> Result<Option<Feature>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $project_path})
            RETURN f
            LIMIT 1
            "#,
        )
        .param("project_path", project_path);

        let mut result = graph.execute(q).await?;

        if let Some(row) = result.next().await? {
            let node: Node = row.get("f")?;
            Ok(Some(Feature::from_node(&node)?))
        } else {
            Ok(None)
        }
    }

    /// Update feature status
    pub async fn update_feature_status(&self, feature_id: &str, status: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (f:Feature {id: $id})
            SET f.status = $status, f.updated_at = datetime()
            "#,
        )
        .param("id", feature_id)
        .param("status", status);

        graph.run(q).await?;
        Ok(())
    }

    /// Activate a feature (set to in_progress)
    /// Multiple features can be in_progress simultaneously
    pub async fn activate_feature(&self, _project_path: &str, feature_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        // Activate the specified feature (no longer deactivates others)
        let q = query(
            r#"
            MATCH (f:Feature {id: $id})
            SET f.status = 'in_progress', f.updated_at = datetime()
            "#,
        )
        .param("id", feature_id);
        graph.run(q).await?;

        Ok(())
    }

    /// Complete a feature
    pub async fn complete_feature(&self, feature_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (f:Feature {id: $id})
            SET f.status = 'complete', f.completed_at = datetime(), f.updated_at = datetime()
            "#,
        )
        .param("id", feature_id);

        graph.run(q).await?;
        Ok(())
    }

    /// Increment work count for a feature
    pub async fn increment_work_count(&self, feature_id: &str) -> Result<i64> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (f:Feature {id: $id})
            SET f.work_count = f.work_count + 1, f.updated_at = datetime()
            RETURN f.work_count as count
            "#,
        )
        .param("id", feature_id);

        let mut result = graph.execute(q).await?;
        if let Some(row) = result.next().await? {
            Ok(row.get::<i64>("count")?)
        } else {
            Ok(0)
        }
    }

    // =========================================================================
    // EVENT OPERATIONS
    // =========================================================================

    /// Record an event
    pub async fn record_event(&self, event: &Event, session_id: &str) -> Result<String> {
        let graph = self.get_graph().await?;

        let event_id = event
            .id
            .clone()
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());

        let q = query(
            r#"
            MATCH (s:Session {id: $session_id})
            CREATE (e:Event {
                id: $id,
                event_type: $event_type,
                tool_name: $tool_name,
                payload: $payload,
                summary: $summary,
                timestamp: datetime(),
                success: $success
            })-[:TRIGGERED_BY]->(s)
            RETURN e.id as id
            "#,
        )
        .param("session_id", session_id)
        .param("id", event_id.clone())
        .param("event_type", event.event_type.clone())
        .param("tool_name", event.tool_name.clone().unwrap_or_default())
        .param(
            "payload",
            serde_json::to_string(&event.payload).unwrap_or_default(),
        )
        .param("summary", event.summary.clone().unwrap_or_default())
        .param("success", event.success.unwrap_or(true));

        graph.run(q).await?;
        Ok(event_id)
    }

    /// Link an event to a feature
    pub async fn link_event_to_feature(&self, event_id: &str, feature_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (e:Event {id: $event_id}), (f:Feature {id: $feature_id})
            MERGE (e)-[:LINKED_TO]->(f)
            "#,
        )
        .param("event_id", event_id)
        .param("feature_id", feature_id);

        graph.run(q).await?;
        Ok(())
    }

    /// Get recent events for a project
    pub async fn get_recent_events(&self, project_path: &str, limit: i64) -> Result<Vec<Event>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (e:Event)-[:TRIGGERED_BY]->(s:Session)-[:IN_PROJECT]->(p:Project {path: $project_path})
            OPTIONAL MATCH (e)-[:LINKED_TO]->(f:Feature)
            RETURN e.id as id,
                   e.event_type as event_type,
                   e.tool_name as tool_name,
                   e.payload as payload,
                   e.summary as summary,
                   toString(e.timestamp) as timestamp,
                   e.success as success,
                   e.source_agent as source_agent,
                   s.id as session_id,
                   p.path as project_path,
                   f.id as feature_id,
                   f.description as feature_description
            ORDER BY e.timestamp DESC
            LIMIT $limit
            "#,
        )
        .param("project_path", project_path)
        .param("limit", limit);

        let mut result = graph.execute(q).await?;

        let mut events = Vec::new();
        while let Some(row) = result.next().await? {
            let payload_str: Option<String> = row.get("payload").ok();
            let payload: Option<serde_json::Value> = payload_str
                .and_then(|s| serde_json::from_str(&s).ok());

            events.push(Event {
                id: row.get("id").ok(),
                event_type: row.get("event_type")?,
                tool_name: row.get("tool_name").ok(),
                payload,
                summary: row.get("summary").ok(),
                timestamp: row.get("timestamp").ok(),
                success: row.get("success").ok(),
                source_agent: row.get("source_agent").ok(),
                session_id: row.get("session_id").ok(),
                project_path: row.get("project_path").ok(),
                feature_id: row.get("feature_id").ok(),
                feature_description: row.get("feature_description").ok(),
            });
        }

        Ok(events)
    }

    /// Get recent events across all projects (global view)
    pub async fn get_all_recent_events(&self, limit: i64) -> Result<Vec<Event>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (e:Event)
            OPTIONAL MATCH (e)-[:TRIGGERED_BY]->(s:Session)-[:IN_PROJECT]->(p:Project)
            OPTIONAL MATCH (e)-[:LINKED_TO]->(f:Feature)
            RETURN e.id as id,
                   e.event_type as event_type,
                   e.tool_name as tool_name,
                   e.payload as payload,
                   e.summary as summary,
                   toString(e.timestamp) as timestamp,
                   e.success as success,
                   e.source_agent as source_agent,
                   s.id as session_id,
                   p.path as project_path,
                   f.id as feature_id,
                   f.description as feature_description
            ORDER BY e.timestamp DESC
            LIMIT $limit
            "#,
        )
        .param("limit", limit);

        let mut result = graph.execute(q).await?;

        let mut events = Vec::new();
        while let Some(row) = result.next().await? {
            let payload_str: Option<String> = row.get("payload").ok();
            let payload: Option<serde_json::Value> = payload_str
                .and_then(|s| serde_json::from_str(&s).ok());

            events.push(Event {
                id: row.get("id").ok(),
                event_type: row.get("event_type")?,
                tool_name: row.get("tool_name").ok(),
                payload,
                summary: row.get("summary").ok(),
                timestamp: row.get("timestamp").ok(),
                success: row.get("success").ok(),
                source_agent: row.get("source_agent").ok(),
                session_id: row.get("session_id").ok(),
                project_path: row.get("project_path").ok(),
                feature_id: row.get("feature_id").ok(),
                feature_description: row.get("feature_description").ok(),
            });
        }

        Ok(events)
    }

    /// Get events linked to a specific feature
    pub async fn get_events_by_feature(&self, feature_id: &str, limit: i64) -> Result<Vec<Event>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (e:Event)-[:LINKED_TO]->(f:Feature {id: $feature_id})
            OPTIONAL MATCH (e)-[:TRIGGERED_BY]->(s:Session)-[:IN_PROJECT]->(p:Project)
            RETURN e.id as id,
                   e.event_type as event_type,
                   e.tool_name as tool_name,
                   e.payload as payload,
                   e.summary as summary,
                   toString(e.timestamp) as timestamp,
                   e.success as success,
                   e.source_agent as source_agent,
                   s.id as session_id,
                   p.path as project_path,
                   f.description as feature_description
            ORDER BY e.timestamp DESC
            LIMIT $limit
            "#,
        )
        .param("feature_id", feature_id)
        .param("limit", limit);

        let mut result = graph.execute(q).await?;

        let mut events = Vec::new();
        while let Some(row) = result.next().await? {
            let payload_str: Option<String> = row.get("payload").ok();
            let payload: Option<serde_json::Value> = payload_str
                .and_then(|s| serde_json::from_str(&s).ok());

            events.push(Event {
                id: row.get("id").ok(),
                event_type: row.get("event_type")?,
                tool_name: row.get("tool_name").ok(),
                payload,
                summary: row.get("summary").ok(),
                timestamp: row.get("timestamp").ok(),
                success: row.get("success").ok(),
                source_agent: row.get("source_agent").ok(),
                session_id: row.get("session_id").ok(),
                project_path: row.get("project_path").ok(),
                feature_id: Some(feature_id.to_string()),
                feature_description: row.get("feature_description").ok(),
            });
        }

        Ok(events)
    }

    // =========================================================================
    // SESSION OPERATIONS
    // =========================================================================

    /// Start a new session
    pub async fn start_session(
        &self,
        session_id: &str,
        agent: &str,
        project_path: &str,
    ) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (p:Project {path: $project_path})
            CREATE (s:Session {
                id: $id,
                agent: $agent,
                status: 'active',
                started_at: datetime(),
                last_activity: datetime(),
                event_count: 0,
                is_subagent: false
            })-[:IN_PROJECT]->(p)
            "#,
        )
        .param("project_path", project_path)
        .param("id", session_id)
        .param("agent", agent);

        graph.run(q).await?;
        Ok(())
    }

    /// End a session
    pub async fn end_session(&self, session_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (s:Session {id: $id})
            SET s.status = 'ended', s.ended_at = datetime()
            "#,
        )
        .param("id", session_id);

        graph.run(q).await?;
        Ok(())
    }

    /// Update session activity
    pub async fn update_session_activity(&self, session_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (s:Session {id: $id})
            SET s.last_activity = datetime(), s.event_count = s.event_count + 1
            "#,
        )
        .param("id", session_id);

        graph.run(q).await?;
        Ok(())
    }

    /// Get active sessions for a project
    pub async fn get_active_sessions(&self, project_path: &str) -> Result<Vec<Session>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (s:Session {status: 'active'})-[:IN_PROJECT]->(p:Project {path: $project_path})
            RETURN s
            ORDER BY s.last_activity DESC
            "#,
        )
        .param("project_path", project_path);

        let mut result = graph.execute(q).await?;

        let mut sessions = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("s")?;
            sessions.push(Session::from_node(&node)?);
        }

        Ok(sessions)
    }

    /// Get all sessions (global view)
    pub async fn get_all_sessions(&self, limit: i64) -> Result<Vec<Session>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (s:Session)
            RETURN s
            ORDER BY s.last_activity DESC
            LIMIT $limit
            "#,
        )
        .param("limit", limit);

        let mut result = graph.execute(q).await?;

        let mut sessions = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("s")?;
            sessions.push(Session::from_node(&node)?);
        }

        Ok(sessions)
    }

    // =========================================================================
    // INSIGHT OPERATIONS
    // =========================================================================

    /// Record a new insight
    pub async fn record_insight(&self, insight: &Insight, event_id: Option<&str>) -> Result<String> {
        let graph = self.get_graph().await?;

        let insight_id = insight
            .id
            .clone()
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());

        let q = query(
            r#"
            CREATE (i:Insight {
                id: $id,
                description: $description,
                pattern_type: $pattern_type,
                tags: $tags,
                created_at: datetime(),
                usage_count: 0,
                effectiveness_score: $effectiveness_score
            })
            RETURN i.id as id
            "#,
        )
        .param("id", insight_id.clone())
        .param("description", insight.description.clone())
        .param("pattern_type", insight.pattern_type.clone())
        .param("tags", insight.tags.clone().unwrap_or_default())
        .param("effectiveness_score", insight.effectiveness_score.unwrap_or(0.0));

        graph.run(q).await?;

        // Link to source event if provided
        if let Some(eid) = event_id {
            let link_q = query(
                r#"
                MATCH (i:Insight {id: $insight_id}), (e:Event {id: $event_id})
                MERGE (i)-[:LEARNED_FROM]->(e)
                "#,
            )
            .param("insight_id", insight_id.clone())
            .param("event_id", eid);
            graph.run(link_q).await?;
        }

        Ok(insight_id)
    }

    /// Get insights by tags
    pub async fn get_insights_by_tags(&self, tags: &[String], limit: i64) -> Result<Vec<Insight>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (i:Insight)
            WHERE any(tag IN $tags WHERE tag IN i.tags)
            RETURN i
            ORDER BY i.usage_count DESC, i.created_at DESC
            LIMIT $limit
            "#,
        )
        .param("tags", tags.to_vec())
        .param("limit", limit);

        let mut result = graph.execute(q).await?;

        let mut insights = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("i")?;
            insights.push(Insight::from_node(&node)?);
        }

        Ok(insights)
    }

    /// Get insights by pattern type
    pub async fn get_insights_by_type(&self, pattern_type: &str, limit: i64) -> Result<Vec<Insight>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (i:Insight {pattern_type: $pattern_type})
            RETURN i
            ORDER BY i.usage_count DESC, i.created_at DESC
            LIMIT $limit
            "#,
        )
        .param("pattern_type", pattern_type)
        .param("limit", limit);

        let mut result = graph.execute(q).await?;

        let mut insights = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("i")?;
            insights.push(Insight::from_node(&node)?);
        }

        Ok(insights)
    }

    /// Increment usage count for an insight
    pub async fn increment_insight_usage(&self, insight_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (i:Insight {id: $id})
            SET i.usage_count = i.usage_count + 1
            "#,
        )
        .param("id", insight_id);

        graph.run(q).await?;
        Ok(())
    }

    /// Search insights by description
    pub async fn search_insights(&self, search_term: &str, limit: i64) -> Result<Vec<Insight>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (i:Insight)
            WHERE i.description CONTAINS $search_term
            RETURN i
            ORDER BY i.usage_count DESC
            LIMIT $limit
            "#,
        )
        .param("search_term", search_term)
        .param("limit", limit);

        let mut result = graph.execute(q).await?;

        let mut insights = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("i")?;
            insights.push(Insight::from_node(&node)?);
        }

        Ok(insights)
    }

    // =========================================================================
    // RULE OPERATIONS
    // =========================================================================

    /// Create a new rule
    pub async fn create_rule(&self, rule: &Rule, project_path: Option<&str>) -> Result<String> {
        let graph = self.get_graph().await?;

        let rule_id = rule
            .id
            .clone()
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());

        let q = query(
            r#"
            CREATE (r:Rule {
                id: $id,
                name: $name,
                description: $description,
                trigger: $trigger,
                action: $action,
                scope: $scope,
                enforcement: $enforcement,
                enabled: $enabled,
                created_at: datetime(),
                triggered_count: 0,
                source_instruction_count: $source_instruction_count
            })
            RETURN r.id as id
            "#,
        )
        .param("id", rule_id.clone())
        .param("name", rule.name.clone())
        .param("description", rule.description.clone())
        .param("trigger", serde_json::to_string(&rule.trigger).unwrap_or_default())
        .param("action", serde_json::to_string(&rule.action).unwrap_or_default())
        .param("scope", rule.scope.clone())
        .param("enforcement", rule.enforcement.clone())
        .param("enabled", rule.enabled.unwrap_or(true))
        .param("source_instruction_count", rule.source_instruction_count.unwrap_or(0) as i64);

        graph.run(q).await?;

        // Link to project if project-scoped
        if let Some(path) = project_path {
            if rule.scope == "project" {
                let link_q = query(
                    r#"
                    MATCH (r:Rule {id: $rule_id}), (p:Project {path: $project_path})
                    MERGE (r)-[:APPLIES_TO]->(p)
                    "#,
                )
                .param("rule_id", rule_id.clone())
                .param("project_path", path);
                graph.run(link_q).await?;
            }
        }

        Ok(rule_id)
    }

    /// Get rules by scope
    pub async fn get_rules_by_scope(&self, scope: &str, project_path: Option<&str>) -> Result<Vec<Rule>> {
        let graph = self.get_graph().await?;

        let q = if scope == "project" && project_path.is_some() {
            query(
                r#"
                MATCH (r:Rule {scope: 'project'})-[:APPLIES_TO]->(p:Project {path: $project_path})
                WHERE r.enabled = true
                RETURN r
                ORDER BY r.created_at DESC
                "#,
            )
            .param("project_path", project_path.unwrap())
        } else {
            query(
                r#"
                MATCH (r:Rule {scope: $scope})
                WHERE r.enabled = true
                RETURN r
                ORDER BY r.created_at DESC
                "#,
            )
            .param("scope", scope)
        };

        let mut result = graph.execute(q).await?;

        let mut rules = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("r")?;
            rules.push(Rule::from_node(&node)?);
        }

        Ok(rules)
    }

    /// Get all enabled rules (global + project-specific)
    pub async fn get_enabled_rules(&self, project_path: &str) -> Result<Vec<Rule>> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (r:Rule)
            WHERE r.enabled = true
            AND (r.scope = 'global'
                 OR (r.scope = 'project' AND EXISTS {
                     MATCH (r)-[:APPLIES_TO]->(p:Project {path: $project_path})
                 }))
            RETURN r
            ORDER BY r.scope, r.created_at DESC
            "#,
        )
        .param("project_path", project_path);

        let mut result = graph.execute(q).await?;

        let mut rules = Vec::new();
        while let Some(row) = result.next().await? {
            let node: Node = row.get("r")?;
            rules.push(Rule::from_node(&node)?);
        }

        Ok(rules)
    }

    /// Toggle rule enabled status
    pub async fn toggle_rule(&self, rule_id: &str, enabled: bool) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (r:Rule {id: $id})
            SET r.enabled = $enabled
            "#,
        )
        .param("id", rule_id)
        .param("enabled", enabled);

        graph.run(q).await?;
        Ok(())
    }

    /// Increment triggered count for a rule
    pub async fn increment_rule_triggered(&self, rule_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (r:Rule {id: $id})
            SET r.triggered_count = r.triggered_count + 1
            "#,
        )
        .param("id", rule_id);

        graph.run(q).await?;
        Ok(())
    }

    /// Link a rule to an insight it was derived from
    pub async fn link_rule_to_insight(&self, rule_id: &str, insight_id: &str) -> Result<()> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (r:Rule {id: $rule_id}), (i:Insight {id: $insight_id})
            MERGE (r)-[:DERIVED_FROM]->(i)
            "#,
        )
        .param("rule_id", rule_id)
        .param("insight_id", insight_id);

        graph.run(q).await?;
        Ok(())
    }

    // =========================================================================
    // STATISTICS
    // =========================================================================

    /// Get project statistics
    pub async fn get_project_stats(&self, project_path: &str) -> Result<ProjectStats> {
        let graph = self.get_graph().await?;

        let q = query(
            r#"
            MATCH (p:Project {path: $project_path})
            OPTIONAL MATCH (f:Feature)-[:BELONGS_TO]->(p)
            WITH p,
                 count(f) as total,
                 sum(CASE WHEN f.status = 'complete' THEN 1 ELSE 0 END) as completed,
                 sum(CASE WHEN f.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress
            OPTIONAL MATCH (s:Session {status: 'active'})-[:IN_PROJECT]->(p)
            WITH total, completed, in_progress, count(s) as active_sessions
            RETURN total, completed, in_progress, active_sessions
            "#,
        )
        .param("project_path", project_path);

        let mut result = graph.execute(q).await?;

        if let Some(row) = result.next().await? {
            let total: i64 = row.get("total")?;
            let completed: i64 = row.get("completed")?;
            let in_progress: i64 = row.get("in_progress")?;
            let active_sessions: i64 = row.get("active_sessions")?;

            Ok(ProjectStats {
                total: total as i32,
                completed: completed as i32,
                in_progress: in_progress as i32,
                percentage: if total > 0 {
                    (completed as f64 / total as f64 * 100.0) as i32
                } else {
                    0
                },
                active_sessions: active_sessions as i32,
            })
        } else {
            Ok(ProjectStats::default())
        }
    }
}

// =============================================================================
// DATA MODELS
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Project {
    pub id: String,
    pub path: String,
    pub name: String,
    pub description: Option<String>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
    pub settings: serde_json::Value,
}

impl Project {
    fn from_node(node: &Node) -> Result<Self> {
        Ok(Self {
            id: node.get("id")?,
            path: node.get("path")?,
            name: node.get("name")?,
            description: node.get("description").ok(),
            created_at: node.get::<String>("created_at").ok(),
            updated_at: node.get::<String>("updated_at").ok(),
            settings: serde_json::from_str(&node.get::<String>("settings").unwrap_or_default())
                .unwrap_or_default(),
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Feature {
    pub id: Option<String>,
    pub description: String,
    pub category: String,
    // Graph DB uses "status" but frontend expects "passes"/"inProgress"
    #[serde(skip_serializing)]
    pub status: String,
    // Computed from status for frontend compatibility
    pub passes: bool,
    pub in_progress: bool,
    pub priority: Option<i32>,
    pub steps: Option<Vec<String>>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
    pub completed_at: Option<String>,
    pub work_count: Option<i32>,
    #[serde(rename = "agent")]
    pub assigned_agent: Option<String>,
    // Project path (populated by caller)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub project_dir: Option<String>,
}

impl Feature {
    fn from_node(node: &Node) -> Result<Self> {
        let status: String = node.get("status")?;
        Ok(Self {
            id: node.get("id").ok(),
            description: node.get("description")?,
            category: node.get("category")?,
            passes: status == "complete",
            in_progress: status == "in_progress",
            status,
            priority: node.get::<i64>("priority").ok().map(|p| p as i32),
            steps: node.get::<Vec<String>>("steps").ok(),
            created_at: node.get::<String>("created_at").ok(),
            updated_at: node.get::<String>("updated_at").ok(),
            completed_at: node.get::<String>("completed_at").ok(),
            work_count: node.get::<i64>("work_count").ok().map(|w| w as i32),
            assigned_agent: node.get("assigned_agent").ok(),
            project_dir: None, // Set by caller
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Event {
    pub id: Option<String>,
    pub event_type: String,
    pub tool_name: Option<String>,
    pub payload: Option<serde_json::Value>,
    pub summary: Option<String>,
    #[serde(rename = "createdAt")]
    pub timestamp: Option<String>,
    pub success: Option<bool>,
    pub source_agent: Option<String>,
    pub session_id: Option<String>,
    // Enriched fields (populated by queries)
    #[serde(skip_serializing_if = "Option::is_none")]
    #[serde(rename = "projectDir")]
    pub project_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub feature_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub feature_description: Option<String>,
}

impl Event {
    fn from_node(node: &Node) -> Result<Self> {
        Ok(Self {
            id: node.get("id").ok(),
            event_type: node.get("event_type")?,
            tool_name: node.get("tool_name").ok(),
            payload: serde_json::from_str(&node.get::<String>("payload").unwrap_or_default()).ok(),
            summary: node.get("summary").ok(),
            timestamp: node.get::<String>("timestamp").ok(),
            success: node.get("success").ok(),
            source_agent: node.get("source_agent").ok(),
            session_id: None, // Populated from Session relationship
            // These are populated by the caller after from_node
            project_path: None,
            feature_id: None,
            feature_description: None,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Session {
    pub id: String,
    pub agent: String,
    pub status: String,
    pub started_at: Option<String>,
    pub ended_at: Option<String>,
    pub last_activity: Option<String>,
    pub event_count: Option<i32>,
    pub is_subagent: Option<bool>,
}

impl Session {
    fn from_node(node: &Node) -> Result<Self> {
        Ok(Self {
            id: node.get("id")?,
            agent: node.get("agent")?,
            status: node.get("status")?,
            started_at: node.get::<String>("started_at").ok(),
            ended_at: node.get::<String>("ended_at").ok(),
            last_activity: node.get::<String>("last_activity").ok(),
            event_count: node.get::<i64>("event_count").ok().map(|c| c as i32),
            is_subagent: node.get("is_subagent").ok(),
        })
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectStats {
    pub total: i32,
    pub completed: i32,
    pub in_progress: i32,
    pub percentage: i32,
    pub active_sessions: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Insight {
    pub id: Option<String>,
    pub description: String,
    pub pattern_type: String, // solution, anti_pattern, best_practice, tool_usage
    pub tags: Option<Vec<String>>,
    pub created_at: Option<String>,
    pub usage_count: Option<i32>,
    pub effectiveness_score: Option<f64>,
}

impl Insight {
    fn from_node(node: &Node) -> Result<Self> {
        Ok(Self {
            id: node.get("id").ok(),
            description: node.get("description")?,
            pattern_type: node.get("pattern_type")?,
            tags: node.get::<Vec<String>>("tags").ok(),
            created_at: node.get::<String>("created_at").ok(),
            usage_count: node.get::<i64>("usage_count").ok().map(|c| c as i32),
            effectiveness_score: node.get::<f64>("effectiveness_score").ok(),
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Rule {
    pub id: Option<String>,
    pub name: String,
    pub description: String,
    pub trigger: serde_json::Value, // RuleTrigger serialized
    pub action: serde_json::Value,  // RuleAction serialized
    pub scope: String,              // global, project, feature
    pub enforcement: String,        // hook, prompt_inject, reminder
    pub enabled: Option<bool>,
    pub created_at: Option<String>,
    pub triggered_count: Option<i32>,
    pub source_instruction_count: Option<i32>,
}

impl Rule {
    fn from_node(node: &Node) -> Result<Self> {
        Ok(Self {
            id: node.get("id").ok(),
            name: node.get("name")?,
            description: node.get("description")?,
            trigger: serde_json::from_str(&node.get::<String>("trigger").unwrap_or_default())
                .unwrap_or_default(),
            action: serde_json::from_str(&node.get::<String>("action").unwrap_or_default())
                .unwrap_or_default(),
            scope: node.get("scope")?,
            enforcement: node.get("enforcement")?,
            enabled: node.get("enabled").ok(),
            created_at: node.get::<String>("created_at").ok(),
            triggered_count: node.get::<i64>("triggered_count").ok().map(|c| c as i32),
            source_instruction_count: node.get::<i64>("source_instruction_count").ok().map(|c| c as i32),
        })
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = GraphDbConfig::default();
        assert_eq!(config.uri, "bolt://localhost:7687");
        assert_eq!(config.user, "ijoka");
    }
}
