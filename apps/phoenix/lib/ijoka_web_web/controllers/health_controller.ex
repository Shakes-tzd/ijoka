defmodule IjokaWebWeb.HealthController do
  @moduledoc """
  Health check endpoint for the API.
  """
  use IjokaWebWeb, :controller

  def check(conn, _params) do
    # Check Memgraph connection
    graph_status =
      case Bolt.Sips.query(Bolt.Sips.conn(), "RETURN 1 as n") do
        {:ok, _} -> "connected"
        {:error, _} -> "disconnected"
      end

    json(conn, %{
      status: "ok",
      memgraph: graph_status,
      timestamp: DateTime.utc_now() |> DateTime.to_iso8601()
    })
  end
end
