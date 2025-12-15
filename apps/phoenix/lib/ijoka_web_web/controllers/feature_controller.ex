defmodule IjokaWebWeb.FeatureController do
  @moduledoc """
  API controller for feature management.
  Provides endpoints for querying features, stats, and projects from Memgraph.
  """
  use IjokaWebWeb, :controller

  alias IjokaWeb.Graph.Memgraph

  def index(conn, params) do
    project_path = Map.get(params, "project_path") || Map.get(params, "projectDir")

    case project_path do
      nil ->
        # Return empty if no project specified
        json(conn, %{features: []})

      path ->
        case Memgraph.get_features(path) do
          {:ok, features} ->
            json(conn, %{features: features})

          {:error, reason} ->
            conn
            |> put_status(:internal_server_error)
            |> json(%{error: inspect(reason)})
        end
    end
  end

  def stats(conn, params) do
    project_path = Map.get(params, "project_path") || Map.get(params, "projectDir")

    case project_path do
      nil ->
        json(conn, %{total: 0, completed: 0, in_progress: 0, pending: 0, percentage: 0, activeSessions: 0})

      path ->
        with {:ok, stats} <- Memgraph.get_stats(path),
             {:ok, sessions} <- Memgraph.get_sessions() do
          active_sessions =
            sessions
            |> Enum.filter(fn s -> s.project_dir == path && s.status == "active" end)
            |> length()

          percentage =
            if stats.total > 0 do
              round(stats.completed / stats.total * 100)
            else
              0
            end

          json(conn, %{
            total: stats.total,
            completed: stats.completed,
            inProgress: stats.in_progress,
            pending: stats.pending,
            percentage: percentage,
            activeSessions: active_sessions
          })
        else
          {:error, reason} ->
            conn
            |> put_status(:internal_server_error)
            |> json(%{error: inspect(reason)})
        end
    end
  end

  def projects(conn, _params) do
    case Memgraph.get_projects() do
      {:ok, projects} ->
        # Return just the paths as an array (matching Tauri API)
        paths = Enum.map(projects, & &1.path)
        json(conn, %{projects: paths})

      {:error, reason} ->
        conn
        |> put_status(:internal_server_error)
        |> json(%{error: inspect(reason)})
    end
  end
end
