defmodule IjokaWeb.Graph.Memgraph do
  @moduledoc """
  Memgraph connection and query module using Bolt protocol.
  Provides functions to query events, features, and sessions from the graph database.
  """

  require Logger

  @doc """
  Execute a Cypher query against Memgraph.
  Returns {:ok, results} or {:error, reason}.
  """
  def query(cypher, params \\ %{}) do
    case Bolt.Sips.query(Bolt.Sips.conn(), cypher, params) do
      {:ok, response} ->
        {:ok, response.results}

      {:error, reason} ->
        Logger.error("Memgraph query failed: #{inspect(reason)}")
        {:error, reason}
    end
  end

  @doc """
  Get recent events from the graph database.
  """
  def get_events(limit \\ 50) do
    # Note: Convert ZonedDateTime to string using toString() to avoid bolt_sips encoding issues
    # Graph structure: Event -[:TRIGGERED_BY]-> Session -[:IN_PROJECT]-> Project
    # Use aggregation to avoid row multiplication from multiple relationships
    cypher = """
    MATCH (e:Event)
    OPTIONAL MATCH (e)-[:TRIGGERED_BY]->(s:Session)
    OPTIONAL MATCH (s)-[:IN_PROJECT]->(p:Project)
    OPTIONAL MATCH (e)-[:LINKED_TO]->(f:Feature)
    WITH e,
         collect(DISTINCT s.agent)[0] as session_agent,
         collect(DISTINCT s.id)[0] as session_id,
         collect(DISTINCT p.path)[0] as project_path,
         collect(DISTINCT f.id)[0] as feature_id
    RETURN DISTINCT e.id as id, e.event_type as event_type,
           coalesce(session_agent, e.source_agent) as source_agent,
           coalesce(session_id, e.session_id) as session_id,
           project_path as project_dir,
           e.tool_name as tool_name, e.payload as payload,
           feature_id,
           toString(coalesce(e.timestamp, e.created_at)) as created_at
    ORDER BY created_at DESC
    LIMIT $limit
    """

    case query(cypher, %{limit: limit}) do
      {:ok, results} ->
        events =
          Enum.map(results, fn row ->
            %{
              id: row["id"],
              event_type: row["event_type"],
              source_agent: row["source_agent"],
              session_id: row["session_id"],
              project_dir: row["project_dir"],
              tool_name: row["tool_name"],
              payload: row["payload"],
              feature_id: row["feature_id"],
              created_at: row["created_at"]
            }
          end)

        {:ok, events}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get all features for a project with parent info.
  """
  def get_features(project_path) do
    cypher = """
    MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $project_path})
    OPTIONAL MATCH (f)-[:CHILD_OF]->(parent:Feature)
    RETURN f.id as id, f.description as description, f.category as category,
           f.passes as passes, f.in_progress as in_progress, f.agent as agent,
           f.work_count as work_count, f.priority as priority, f.type as type,
           f.parent_id as parent_id, parent.description as parent_description
    ORDER BY f.priority DESC, f.created_at DESC
    """

    case query(cypher, %{project_path: project_path}) do
      {:ok, results} ->
        features =
          Enum.map(results, fn row ->
            %{
              id: row["id"],
              description: row["description"],
              category: row["category"],
              status: determine_status(row),
              passes: row["passes"] || false,
              in_progress: row["in_progress"] || false,
              agent: row["agent"],
              work_count: row["work_count"] || 0,
              priority: row["priority"] || 100,
              type: row["type"] || "feature",
              parent_id: row["parent_id"],
              parent_description: row["parent_description"]
            }
          end)

        {:ok, features}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get the active feature for a project.
  """
  def get_active_feature(project_path) do
    cypher = """
    MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $project_path})
    WHERE f.in_progress = true
    RETURN f.id as id, f.description as description, f.category as category, f.agent as agent
    LIMIT 1
    """

    case query(cypher, %{project_path: project_path}) do
      {:ok, [row | _]} ->
        {:ok,
         %{
           id: row["id"],
           description: row["description"],
           category: row["category"],
           in_progress: true,
           agent: row["agent"]
         }}

      {:ok, []} ->
        {:ok, nil}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get active sessions.
  """
  def get_sessions do
    cypher = """
    MATCH (s:Session)
    RETURN s.session_id as session_id, s.source_agent as source_agent,
           s.project_dir as project_dir, toString(s.started_at) as started_at,
           toString(s.last_activity) as last_activity, s.status as status
    ORDER BY s.last_activity DESC
    """

    case query(cypher) do
      {:ok, results} ->
        sessions =
          Enum.map(results, fn row ->
            %{
              session_id: row["session_id"],
              source_agent: row["source_agent"],
              project_dir: row["project_dir"],
              started_at: row["started_at"],
              last_activity: row["last_activity"],
              status: row["status"] || "active"
            }
          end)

        {:ok, sessions}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get project statistics.
  """
  def get_stats(project_path) do
    cypher = """
    MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $project_path})
    RETURN
      count(f) as total,
      sum(CASE WHEN f.passes = true THEN 1 ELSE 0 END) as completed,
      sum(CASE WHEN f.in_progress = true THEN 1 ELSE 0 END) as in_progress,
      sum(CASE WHEN coalesce(f.passes, false) = false AND coalesce(f.in_progress, false) = false THEN 1 ELSE 0 END) as pending
    """

    case query(cypher, %{project_path: project_path}) do
      {:ok, [row | _]} ->
        {:ok,
         %{
           total: row["total"] || 0,
           completed: row["completed"] || 0,
           in_progress: row["in_progress"] || 0,
           pending: row["pending"] || 0
         }}

      {:ok, []} ->
        {:ok, %{total: 0, completed: 0, in_progress: 0, pending: 0}}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get all projects.
  """
  def get_projects do
    cypher = """
    MATCH (p:Project)
    RETURN p.path as path, p.name as name
    ORDER BY p.path
    """

    case query(cypher) do
      {:ok, results} ->
        projects =
          Enum.map(results, fn row ->
            %{
              path: row["path"],
              name: row["name"] || Path.basename(row["path"])
            }
          end)

        {:ok, projects}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get child count for a feature.
  """
  def get_child_count(feature_id) do
    cypher = """
    MATCH (child:Feature)-[:CHILD_OF]->(parent:Feature {id: $feature_id})
    RETURN count(child) as count
    """

    case query(cypher, %{feature_id: feature_id}) do
      {:ok, [%{"count" => count}]} -> {:ok, count}
      {:ok, []} -> {:ok, 0}
      {:error, reason} -> {:error, reason}
    end
  end

  @doc """
  Get aggregated event count (feature + all descendants).
  """
  def get_hierarchy_event_count(feature_id) do
    cypher = """
    MATCH (f:Feature {id: $feature_id})
    OPTIONAL MATCH (descendant:Feature)-[:CHILD_OF*0..]->(f)
    WITH collect(DISTINCT f) + collect(DISTINCT descendant) as features
    UNWIND features as feature
    MATCH (e:Event)-[:LINKED_TO]->(feature)
    RETURN count(e) as count
    """

    case query(cypher, %{feature_id: feature_id}) do
      {:ok, [%{"count" => count}]} -> {:ok, count}
      {:ok, []} -> {:ok, 0}
      {:error, reason} -> {:error, reason}
    end
  end

  # Helper to determine feature status from properties
  defp determine_status(props) do
    cond do
      props["passes"] == true -> "completed"
      props["in_progress"] == true -> "in_progress"
      true -> "pending"
    end
  end
end
