defmodule IjokaWeb.Resources.Feature do
  @moduledoc """
  Feature data structure and query functions.
  """

  alias IjokaWeb.Graph.Memgraph

  defstruct [
    :id,
    :description,
    :category,
    :status,
    :passes,
    :in_progress,
    :agent,
    :work_count,
    :priority,
    :project_dir
  ]

  @doc """
  Get all features for a project.
  """
  def by_project(project_path) do
    case Memgraph.get_features(project_path) do
      {:ok, features} ->
        records = Enum.map(features, fn f ->
          %__MODULE__{
            id: f[:id],
            description: f[:description],
            category: f[:category],
            status: determine_status(f),
            passes: f[:passes] || false,
            in_progress: f[:in_progress] || false,
            agent: f[:agent],
            work_count: f[:work_count] || 0,
            priority: f[:priority] || 100,
            project_dir: project_path
          }
        end)
        {:ok, records}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get the active feature for a project.
  """
  def get_active(project_path) do
    case Memgraph.get_active_feature(project_path) do
      {:ok, nil} ->
        {:ok, nil}

      {:ok, f} ->
        record = %__MODULE__{
          id: f[:id],
          description: f[:description],
          category: f[:category],
          status: :in_progress,
          passes: false,
          in_progress: true,
          agent: f[:agent],
          project_dir: project_path
        }
        {:ok, record}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Group features by status for kanban display.
  """
  def group_by_status(features) do
    features
    |> Enum.group_by(& &1.status)
    |> Map.put_new(:pending, [])
    |> Map.put_new(:in_progress, [])
    |> Map.put_new(:completed, [])
  end

  defp determine_status(feature) do
    cond do
      feature[:passes] == true -> :completed
      feature[:in_progress] == true -> :in_progress
      true -> :pending
    end
  end
end
