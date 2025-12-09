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
    cypher = """
    MATCH (e:Event)
    OPTIONAL MATCH (e)-[:BELONGS_TO_SESSION]->(s:Session)
    OPTIONAL MATCH (e)-[:LINKED_TO_FEATURE]->(f:Feature)
    RETURN e.id as id, e.event_type as event_type, e.source_agent as source_agent,
           coalesce(s.session_id, e.session_id) as session_id, e.project_dir as project_dir,
           e.tool_name as tool_name, e.payload as payload, coalesce(f.id, e.feature_id) as feature_id,
           toString(e.created_at) as created_at
    ORDER BY e.created_at DESC
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
  Get all features for a project.
  """
  def get_features(project_path) do
    cypher = """
    MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $project_path})
    RETURN f
    ORDER BY f.priority DESC, f.created_at DESC
    """

    case query(cypher, %{project_path: project_path}) do
      {:ok, results} ->
        features =
          Enum.map(results, fn row ->
            f = row["f"]
            %{
              id: f.properties["id"],
              description: f.properties["description"],
              category: f.properties["category"],
              status: determine_status(f.properties),
              passes: f.properties["passes"] || false,
              in_progress: f.properties["in_progress"] || false,
              agent: f.properties["agent"],
              work_count: f.properties["work_count"] || 0,
              priority: f.properties["priority"] || 100
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
    RETURN f
    LIMIT 1
    """

    case query(cypher, %{project_path: project_path}) do
      {:ok, [row | _]} ->
        f = row["f"]
        {:ok,
         %{
           id: f.properties["id"],
           description: f.properties["description"],
           category: f.properties["category"],
           in_progress: true,
           agent: f.properties["agent"]
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
    RETURN s
    ORDER BY s.last_activity DESC
    """

    case query(cypher) do
      {:ok, results} ->
        sessions =
          Enum.map(results, fn row ->
            s = row["s"]
            %{
              session_id: s.properties["session_id"],
              source_agent: s.properties["source_agent"],
              project_dir: s.properties["project_dir"],
              started_at: s.properties["started_at"],
              last_activity: s.properties["last_activity"],
              status: s.properties["status"] || "active"
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
      sum(CASE WHEN f.passes = false AND f.in_progress = false THEN 1 ELSE 0 END) as pending
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
    RETURN p
    ORDER BY p.path
    """

    case query(cypher) do
      {:ok, results} ->
        projects =
          Enum.map(results, fn row ->
            p = row["p"]
            %{
              path: p.properties["path"],
              name: p.properties["name"] || Path.basename(p.properties["path"])
            }
          end)

        {:ok, projects}

      {:error, reason} ->
        {:error, reason}
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
