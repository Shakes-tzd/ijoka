defmodule IjokaWebWeb.DashboardLive do
  @moduledoc """
  Main dashboard LiveView for Ijoka observability.
  Displays real-time events, features kanban, and session activity.
  """
  use IjokaWebWeb, :live_view

  alias IjokaWeb.Graph.{Memgraph, EventSubscriber}

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      # Subscribe to real-time event updates
      EventSubscriber.subscribe_all()
    end

    # Load initial data with graceful error handling
    events = case Memgraph.get_events(50) do
      {:ok, events} -> events
      {:error, _} -> []
    end

    sessions = case Memgraph.get_sessions() do
      {:ok, sessions} -> sessions
      {:error, _} -> []
    end

    projects = case Memgraph.get_projects() do
      {:ok, projects} -> projects
      {:error, _} -> []
    end

    # Get first project's features if available
    {features, stats, active_project} =
      case projects do
        [project | _] ->
          features = case Memgraph.get_features(project.path) do
            {:ok, f} -> f
            {:error, _} -> []
          end
          stats = case Memgraph.get_stats(project.path) do
            {:ok, s} -> s
            {:error, _} -> %{total: 0, completed: 0, in_progress: 0, pending: 0}
          end
          {features, stats, project.path}

        [] ->
          {[], %{total: 0, completed: 0, in_progress: 0, pending: 0}, nil}
      end

    # Add dom_id to events for streaming
    events_with_id = Enum.map(events, fn e ->
      Map.put(e, :dom_id, "event-#{e.id || :rand.uniform(100_000)}")
    end)

    socket =
      socket
      |> assign(:page_title, "Ijoka Dashboard")
      |> assign(:projects, projects)
      |> assign(:active_project, active_project)
      |> assign(:stats, stats)
      |> assign(:sessions, sessions)
      |> stream(:events, events_with_id, at: 0)
      |> stream(:features_pending, filter_by_status(features, :pending), at: -1)
      |> stream(:features_in_progress, filter_by_status(features, :in_progress), at: -1)
      |> stream(:features_completed, filter_by_status(features, :completed), at: -1)

    {:ok, socket}
  end

  @impl true
  def handle_info({:new_event, event}, socket) do
    # Add dom_id for streaming
    event_with_id = Map.put(event, :dom_id, "event-#{event[:id] || :rand.uniform(100_000)}")

    # Prepend new event to the stream (real-time update)
    socket =
      socket
      |> stream_insert(:events, event_with_id, at: 0)
      |> maybe_reload_features(event)

    {:noreply, socket}
  end

  @impl true
  def handle_event("select_project", %{"path" => path}, socket) do
    features = case Memgraph.get_features(path) do
      {:ok, f} -> f
      {:error, _} -> []
    end
    stats = case Memgraph.get_stats(path) do
      {:ok, s} -> s
      {:error, _} -> %{total: 0, completed: 0, in_progress: 0, pending: 0}
    end

    socket =
      socket
      |> assign(:active_project, path)
      |> assign(:stats, stats)
      |> stream(:features_pending, filter_by_status(features, :pending), reset: true)
      |> stream(:features_in_progress, filter_by_status(features, :in_progress), reset: true)
      |> stream(:features_completed, filter_by_status(features, :completed), reset: true)

    {:noreply, socket}
  end

  defp maybe_reload_features(socket, event) do
    event_type = event[:event_type] || event["event_type"]

    if event_type in ["FeatureCompleted", "FeatureStarted", "FeatureUpdated"] &&
         socket.assigns.active_project do
      features = case Memgraph.get_features(socket.assigns.active_project) do
        {:ok, f} -> f
        {:error, _} -> []
      end
      stats = case Memgraph.get_stats(socket.assigns.active_project) do
        {:ok, s} -> s
        {:error, _} -> socket.assigns.stats
      end

      socket
      |> assign(:stats, stats)
      |> stream(:features_pending, filter_by_status(features, :pending), reset: true)
      |> stream(:features_in_progress, filter_by_status(features, :in_progress), reset: true)
      |> stream(:features_completed, filter_by_status(features, :completed), reset: true)
    else
      socket
    end
  end

  defp filter_by_status(features, status) do
    features
    |> Enum.filter(fn f ->
      case status do
        :pending -> !f.passes && !f.in_progress
        :in_progress -> f.in_progress
        :completed -> f.passes
      end
    end)
    |> Enum.map(fn f -> Map.put(f, :dom_id, "feature-#{f.id}") end)
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="dashboard">
      <!-- Header with project selector -->
      <header class="dashboard-header">
        <div class="header-left">
          <h1>Ijoka</h1>
          <span class="subtitle">Agent Observability</span>
        </div>
        <div class="header-right">
          <select phx-change="select_project" name="path" class="project-select">
            <option :for={project <- @projects} value={project.path} selected={project.path == @active_project}>
              {project.name}
            </option>
          </select>
        </div>
      </header>

      <!-- Stats bar -->
      <div class="stats-bar">
        <div class="stat">
          <span class="stat-value">{@stats.total}</span>
          <span class="stat-label">Total</span>
        </div>
        <div class="stat stat-completed">
          <span class="stat-value">{@stats.completed}</span>
          <span class="stat-label">Completed</span>
        </div>
        <div class="stat stat-in-progress">
          <span class="stat-value">{@stats.in_progress}</span>
          <span class="stat-label">In Progress</span>
        </div>
        <div class="stat stat-pending">
          <span class="stat-value">{@stats.pending}</span>
          <span class="stat-label">Pending</span>
        </div>
        <div class="stat stat-progress">
          <div class="progress-bar">
            <div class="progress-fill" style={"width: #{progress_percent(@stats)}%"}></div>
          </div>
          <span class="stat-label">{progress_percent(@stats)}% Complete</span>
        </div>
      </div>

      <!-- Main content: Kanban + Activity -->
      <div class="main-content">
        <!-- Kanban Board -->
        <div class="kanban-board">
          <.kanban_column title="Pending" stream={@streams.features_pending} status="pending" />
          <.kanban_column title="In Progress" stream={@streams.features_in_progress} status="in_progress" />
          <.kanban_column title="Completed" stream={@streams.features_completed} status="completed" />
        </div>

        <!-- Activity Timeline -->
        <aside class="activity-timeline">
          <h2>Activity</h2>
          <div class="events-list" id="events-list" phx-update="stream">
            <.event_card :for={{dom_id, event} <- @streams.events} event={event} id={dom_id} />
          </div>
        </aside>
      </div>
    </div>
    """
  end

  defp kanban_column(assigns) do
    ~H"""
    <div class={"kanban-column column-#{@status}"}>
      <h3 class="column-header">
        {@title}
        <span class="count">{length(Map.get(@stream, :inserts, []))}</span>
      </h3>
      <div class="column-content" id={"column-#{@status}"} phx-update="stream">
        <.feature_card :for={{dom_id, feature} <- @stream} feature={feature} id={dom_id} />
      </div>
    </div>
    """
  end

  defp feature_card(assigns) do
    ~H"""
    <div class="feature-card" id={@id}>
      <div class="feature-category">{@feature.category}</div>
      <p class="feature-description">{@feature.description}</p>
      <div class="feature-meta">
        <span :if={@feature.agent} class="feature-agent">{@feature.agent}</span>
        <span class="feature-work-count">{@feature.work_count || 0} work</span>
      </div>
    </div>
    """
  end

  defp event_card(assigns) do
    ~H"""
    <div class="event-card" id={@id}>
      <div class="event-header">
        <span class={"event-type type-#{event_type_class(@event[:event_type])}"}>{@event[:event_type]}</span>
        <span class="event-agent">{@event[:source_agent]}</span>
      </div>
      <div :if={@event[:tool_name]} class="event-tool">{@event[:tool_name]}</div>
      <div class="event-time">{format_time(@event[:created_at])}</div>
    </div>
    """
  end

  defp progress_percent(%{total: 0}), do: 0
  defp progress_percent(%{total: total, completed: completed}) do
    round(completed / total * 100)
  end

  defp event_type_class(nil), do: "other"
  defp event_type_class(type) do
    cond do
      String.contains?(type, "Session") -> "session"
      String.contains?(type, "Feature") -> "feature"
      String.contains?(type, "Tool") -> "tool"
      true -> "other"
    end
  end

  defp format_time(nil), do: ""
  defp format_time(datetime) when is_binary(datetime) do
    case DateTime.from_iso8601(String.replace(datetime, ~r/\[.+\]$/, "")) do
      {:ok, dt, _} -> Calendar.strftime(dt, "%H:%M:%S")
      _ -> datetime
    end
  end
  defp format_time(%DateTime{} = dt), do: Calendar.strftime(dt, "%H:%M:%S")
end
