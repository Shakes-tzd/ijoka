defmodule IjokaWeb.Resources.Session do
  @moduledoc """
  Session data structure and query functions.
  """

  alias IjokaWeb.Graph.Memgraph

  defstruct [
    :session_id,
    :source_agent,
    :project_dir,
    :started_at,
    :last_activity,
    :status
  ]

  @doc """
  List all sessions.
  """
  def list_all do
    case Memgraph.get_sessions() do
      {:ok, sessions} ->
        records = Enum.map(sessions, &to_struct/1)
        {:ok, records}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @doc """
  List active sessions only.
  """
  def list_active do
    case Memgraph.get_sessions() do
      {:ok, sessions} ->
        active = sessions
        |> Enum.filter(fn s -> s[:status] == "active" end)
        |> Enum.map(&to_struct/1)
        {:ok, active}

      {:error, reason} ->
        {:error, reason}
    end
  end

  defp to_struct(session) do
    %__MODULE__{
      session_id: session[:session_id],
      source_agent: session[:source_agent],
      project_dir: session[:project_dir],
      started_at: parse_datetime(session[:started_at]),
      last_activity: parse_datetime(session[:last_activity]),
      status: String.to_atom(session[:status] || "active")
    }
  end

  defp parse_datetime(nil), do: nil
  defp parse_datetime(str) when is_binary(str) do
    clean_str = String.replace(str, ~r/\[.+\]$/, "")
    case DateTime.from_iso8601(clean_str) do
      {:ok, dt, _offset} -> dt
      _ -> nil
    end
  end
  defp parse_datetime(_), do: nil
end
