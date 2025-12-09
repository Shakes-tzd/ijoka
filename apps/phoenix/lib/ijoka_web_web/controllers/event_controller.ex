defmodule IjokaWebWeb.EventController do
  @moduledoc """
  API controller for event ingestion from hooks.
  Receives events from Claude Code hooks and stores them in Memgraph.
  """
  use IjokaWebWeb, :controller

  alias IjokaWeb.Graph.Memgraph

  def index(conn, params) do
    limit = Map.get(params, "limit", "50") |> String.to_integer()

    case Memgraph.get_events(limit) do
      {:ok, events} ->
        json(conn, %{events: events})

      {:error, reason} ->
        conn
        |> put_status(:internal_server_error)
        |> json(%{error: inspect(reason)})
    end
  end

  def create(conn, %{"event" => event_params}) do
    # Create event in Memgraph
    cypher = """
    CREATE (e:Event {
      id: randomUUID(),
      event_type: $event_type,
      source_agent: $source_agent,
      session_id: $session_id,
      project_dir: $project_dir,
      tool_name: $tool_name,
      payload: $payload,
      feature_id: $feature_id,
      created_at: localdatetime()
    })
    RETURN e.id as id
    """

    params = %{
      event_type: event_params["event_type"] || event_params["eventType"],
      source_agent: event_params["source_agent"] || event_params["sourceAgent"] || "unknown",
      session_id: event_params["session_id"] || event_params["sessionId"],
      project_dir: event_params["project_dir"] || event_params["projectDir"],
      tool_name: event_params["tool_name"] || event_params["toolName"],
      payload: encode_payload(event_params["payload"]),
      feature_id: event_params["feature_id"] || event_params["featureId"]
    }

    case Memgraph.query(cypher, params) do
      {:ok, [%{"id" => id} | _]} ->
        # Broadcast the new event
        Phoenix.PubSub.broadcast(
          IjokaWeb.PubSub,
          "events:all",
          {:new_event, Map.put(params, :id, id)}
        )

        conn
        |> put_status(:created)
        |> json(%{id: id, status: "created"})

      {:error, reason} ->
        conn
        |> put_status(:internal_server_error)
        |> json(%{error: inspect(reason)})
    end
  end

  def create(conn, params) do
    # Handle direct params (not nested under "event")
    create(conn, %{"event" => params})
  end

  defp encode_payload(nil), do: nil
  defp encode_payload(payload) when is_binary(payload), do: payload
  defp encode_payload(payload), do: Jason.encode!(payload)
end
