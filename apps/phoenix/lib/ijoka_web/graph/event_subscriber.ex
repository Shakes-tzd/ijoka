defmodule IjokaWeb.Graph.EventSubscriber do
  @moduledoc """
  GenServer that polls Memgraph for new events and broadcasts them via PubSub.
  LiveView components subscribe to receive real-time updates.
  """
  use GenServer

  require Logger

  alias IjokaWeb.Graph.Memgraph

  @poll_interval 2_000  # Poll every 2 seconds

  def start_link(_opts) do
    GenServer.start_link(__MODULE__, %{}, name: __MODULE__)
  end

  @doc """
  Subscribe to event updates for a specific project.
  """
  def subscribe(project_path) do
    Phoenix.PubSub.subscribe(IjokaWeb.PubSub, "events:#{project_path}")
  end

  @doc """
  Subscribe to all events (project-agnostic).
  """
  def subscribe_all do
    Phoenix.PubSub.subscribe(IjokaWeb.PubSub, "events:all")
  end

  # GenServer callbacks

  @impl true
  def init(_state) do
    # Get initial last event timestamp
    schedule_poll()
    {:ok, %{last_event_time: nil}}
  end

  @impl true
  def handle_info(:poll, state) do
    new_state = poll_events(state)
    schedule_poll()
    {:noreply, new_state}
  end

  defp schedule_poll do
    Process.send_after(self(), :poll, @poll_interval)
  end

  defp poll_events(state) do
    case Memgraph.get_events(20) do
      {:ok, events} when events != [] ->
        # Check for new events since last poll
        latest_time = hd(events)[:created_at]

        if state.last_event_time != latest_time do
          # Broadcast new events
          new_events = filter_new_events(events, state.last_event_time)

          for event <- new_events do
            # Broadcast to project-specific channel
            if event[:project_dir] do
              Phoenix.PubSub.broadcast(
                IjokaWeb.PubSub,
                "events:#{event[:project_dir]}",
                {:new_event, event}
              )
            end

            # Also broadcast to global channel
            Phoenix.PubSub.broadcast(
              IjokaWeb.PubSub,
              "events:all",
              {:new_event, event}
            )
          end

          Logger.debug("Broadcast #{length(new_events)} new events")
          %{state | last_event_time: latest_time}
        else
          state
        end

      {:ok, []} ->
        state

      {:error, reason} ->
        Logger.warning("Failed to poll events: #{inspect(reason)}")
        state
    end
  end

  defp filter_new_events(events, nil), do: events

  defp filter_new_events(events, last_time) do
    Enum.filter(events, fn event ->
      event[:created_at] > last_time
    end)
  end
end
