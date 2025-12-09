defmodule IjokaWeb.Resources.Event do
  @moduledoc """
  Event data structure and query functions.
  Uses plain maps for simplicity with Memgraph backend.
  """

  alias IjokaWeb.Graph.Memgraph

  defstruct [
    :id,
    :event_type,
    :source_agent,
    :session_id,
    :project_dir,
    :tool_name,
    :payload,
    :feature_id,
    :created_at
  ]

  @doc """
  List recent events.
  """
  def list_recent(limit \\ 50) do
    case Memgraph.get_events(limit) do
      {:ok, events} ->
        records = Enum.map(events, &to_struct/1)
        {:ok, records}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  Get events for a specific feature.
  """
  def by_feature(feature_id) do
    cypher = """
    MATCH (e:Event)-[:LINKED_TO_FEATURE]->(f:Feature {id: $feature_id})
    RETURN e
    ORDER BY e.created_at DESC
    LIMIT 50
    """

    case Memgraph.query(cypher, %{feature_id: feature_id}) do
      {:ok, results} ->
        records = Enum.map(results, fn row ->
          to_struct(row["e"].properties)
        end)
        {:ok, records}

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp to_struct(event) when is_map(event) do
    %__MODULE__{
      id: event[:id] || event["id"],
      event_type: event[:event_type] || event["event_type"],
      source_agent: event[:source_agent] || event["source_agent"],
      session_id: event[:session_id] || event["session_id"],
      project_dir: event[:project_dir] || event["project_dir"],
      tool_name: event[:tool_name] || event["tool_name"],
      payload: event[:payload] || event["payload"],
      feature_id: event[:feature_id] || event["feature_id"],
      created_at: parse_datetime(event[:created_at] || event["created_at"])
    }
  end

  defp parse_datetime(nil), do: nil
  defp parse_datetime(str) when is_binary(str) do
    # Handle Memgraph timestamp format: "2025-12-09T13:05:16.328978+00:00[Etc/UTC]"
    clean_str = String.replace(str, ~r/\[.+\]$/, "")
    case DateTime.from_iso8601(clean_str) do
      {:ok, dt, _offset} -> dt
      _ -> nil
    end
  end
  defp parse_datetime(_), do: nil
end
