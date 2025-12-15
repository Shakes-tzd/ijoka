defmodule IjokaWebWeb.DashboardLive do
  @moduledoc """
  Main dashboard LiveView for Ijoka observability.
  VS Code-style layout with activity bar, projects sidebar, kanban board, and activity panel.
  """
  use IjokaWebWeb, :live_view

  alias IjokaWeb.Graph.{Memgraph, EventSubscriber}

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      EventSubscriber.subscribe_all()
    end

    # Load initial data
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
            {:ok, f} -> enrich_with_hierarchy(f)
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

    # Track seen event IDs for deduplication
    seen_event_ids = events
      |> Enum.map(& &1.id)
      |> Enum.filter(& &1)
      |> MapSet.new()

    # Group events by session
    grouped_events = group_events_by_session(events_with_id)

    socket =
      socket
      |> assign(:page_title, "Dashboard")
      |> assign(:projects, projects)
      |> assign(:active_project, active_project)
      |> assign(:stats, stats)
      |> assign(:sessions, sessions)
      |> assign(:grouped_events, grouped_events)
      |> assign(:seen_event_ids, seen_event_ids)
      |> assign(:active_tab, "kanban")
      |> assign(:sidebar_open, true)
      |> assign(:activity_panel_open, true)
      |> assign(:collapsed_sessions, MapSet.new())
      |> assign(:selected_feature, nil)
      |> assign(:selected_event, nil)
      |> stream(:events, events_with_id, at: 0)
      |> stream(:features_pending, filter_by_status(features, :pending), at: -1)
      |> stream(:features_in_progress, filter_by_status(features, :in_progress), at: -1)
      |> stream(:features_completed, filter_by_status(features, :completed), at: -1)

    {:ok, socket}
  end

  @impl true
  def handle_info({:new_event, event}, socket) do
    event_id = event[:id]

    # Skip if we've already seen this event (deduplication)
    seen_events = socket.assigns[:seen_event_ids] || MapSet.new()
    if event_id && MapSet.member?(seen_events, event_id) do
      {:noreply, socket}
    else
      event_with_id = Map.put(event, :dom_id, "event-#{event_id || :rand.uniform(100_000)}")

      # Track seen event IDs (keep last 500 to prevent memory growth)
      new_seen = if event_id do
        seen = MapSet.put(seen_events, event_id)
        if MapSet.size(seen) > 500 do
          # Remove oldest entries by converting to list and back
          seen |> MapSet.to_list() |> Enum.take(-500) |> MapSet.new()
        else
          seen
        end
      else
        seen_events
      end

      # Update grouped events
      grouped_events = add_event_to_groups(socket.assigns.grouped_events, event_with_id)

      socket =
        socket
        |> assign(:seen_event_ids, new_seen)
        |> assign(:grouped_events, grouped_events)
        |> stream_insert(:events, event_with_id, at: 0)
        |> maybe_reload_features(event)

      {:noreply, socket}
    end
  end

  @impl true
  def handle_event("select_project", %{"path" => path}, socket) do
    features = case Memgraph.get_features(path) do
      {:ok, f} -> enrich_with_hierarchy(f)
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

  def handle_event("toggle_sidebar", _, socket) do
    {:noreply, assign(socket, :sidebar_open, !socket.assigns.sidebar_open)}
  end

  def handle_event("toggle_activity_panel", _, socket) do
    {:noreply, assign(socket, :activity_panel_open, !socket.assigns.activity_panel_open)}
  end

  def handle_event("select_tab", %{"tab" => tab}, socket) do
    {:noreply, assign(socket, :active_tab, tab)}
  end

  def handle_event("toggle_session", %{"session" => session_id}, socket) do
    collapsed = socket.assigns.collapsed_sessions
    new_collapsed = if MapSet.member?(collapsed, session_id) do
      MapSet.delete(collapsed, session_id)
    else
      MapSet.put(collapsed, session_id)
    end
    {:noreply, assign(socket, :collapsed_sessions, new_collapsed)}
  end

  def handle_event("open_feature", %{"id" => feature_id}, socket) do
    # Find the feature from streams - we need to search all status streams
    feature = find_feature_by_id(socket, feature_id)
    {:noreply, assign(socket, :selected_feature, feature)}
  end

  def handle_event("close_modal", _, socket) do
    {:noreply, assign(socket, :selected_feature, nil)}
  end

  def handle_event("open_event", %{"id" => event_id}, socket) do
    # Find event from grouped_events
    event = find_event_by_id(socket.assigns.grouped_events, event_id)
    {:noreply, assign(socket, :selected_event, event)}
  end

  def handle_event("close_event_modal", _, socket) do
    {:noreply, assign(socket, :selected_event, nil)}
  end

  # Noop handler for stopping event propagation without action
  def handle_event("noop", _, socket) do
    {:noreply, socket}
  end

  defp find_feature_by_id(socket, feature_id) do
    # We can't iterate streams directly, so fetch from DB
    case socket.assigns.active_project do
      nil -> nil
      project_path ->
        case Memgraph.get_features(project_path) do
          {:ok, features} -> Enum.find(features, fn f -> f.id == feature_id end)
          _ -> nil
        end
    end
  end

  defp find_event_by_id(grouped_events, event_id) do
    # Search through all session groups to find the event
    Enum.find_value(grouped_events, fn session ->
      Enum.find(session.events, fn e -> e[:dom_id] == event_id end)
    end)
  end

  defp maybe_reload_features(socket, event) do
    event_type = event[:event_type] || event["event_type"]

    if event_type in ["FeatureCompleted", "FeatureStarted", "FeatureUpdated"] &&
         socket.assigns.active_project do
      features = case Memgraph.get_features(socket.assigns.active_project) do
        {:ok, f} -> enrich_with_hierarchy(f)
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

  defp enrich_with_hierarchy(features) do
    Enum.map(features, fn feature ->
      child_count = case Memgraph.get_child_count(feature.id) do
        {:ok, count} -> count
        {:error, _} -> 0
      end

      # Only fetch hierarchy events for epics (performance)
      hierarchy_events = if feature[:type] == "epic" do
        case Memgraph.get_hierarchy_event_count(feature.id) do
          {:ok, count} -> count
          {:error, _} -> 0
        end
      else
        nil
      end

      feature
      |> Map.put(:child_count, child_count)
      |> Map.put(:hierarchy_events, hierarchy_events)
    end)
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

  defp group_events_by_session(events) do
    now = DateTime.utc_now()
    stale_minutes = 15

    events
    |> Enum.group_by(fn e -> e[:session_id] || "unknown" end)
    |> Enum.map(fn {session_id, session_events} ->
      # Sort events chronologically (oldest first) for processing
      sorted_events = Enum.sort_by(session_events, & &1[:created_at])
      first_event = List.first(sorted_events)
      last_event = List.last(sorted_events)

      # Check if session has ended
      has_session_end = Enum.any?(session_events, fn e -> e[:event_type] == "SessionEnd" end)

      # Determine if session is active (not ended and recent activity)
      is_active = if has_session_end do
        false
      else
        last_activity_time = parse_datetime(last_event[:created_at])
        if last_activity_time do
          DateTime.diff(now, last_activity_time, :minute) < stale_minutes
        else
          false
        end
      end

      # Reverse events so latest appears at top
      display_events = Enum.reverse(sorted_events)

      %{
        session_id: session_id,
        source_agent: first_event[:source_agent] || "unknown",
        project_dir: first_event[:project_dir] || "",
        events: display_events,
        event_count: length(session_events),
        start_time: first_event[:created_at],
        last_activity: last_event[:created_at],
        is_active: is_active
      }
    end)
    # Sort: active first, then by most recent activity
    |> Enum.sort_by(fn session ->
      {not session.is_active, session.last_activity}
    end, fn {a1, t1}, {a2, t2} ->
      cond do
        a1 != a2 -> a1 < a2
        true -> t1 >= t2
      end
    end)
  end

  defp parse_datetime(nil), do: nil
  defp parse_datetime(datetime) when is_binary(datetime) do
    cleaned = datetime
      |> String.replace(~r/\[.+\]$/, "")
      |> String.trim()

    case DateTime.from_iso8601(cleaned) do
      {:ok, dt, _} -> dt
      _ ->
        case NaiveDateTime.from_iso8601(cleaned) do
          {:ok, ndt} -> DateTime.from_naive!(ndt, "Etc/UTC")
          _ -> nil
        end
    end
  end
  defp parse_datetime(%DateTime{} = dt), do: dt

  defp add_event_to_groups(groups, event) do
    session_id = event[:session_id] || "unknown"
    existing = Enum.find(groups, fn g -> g.session_id == session_id end)

    if existing do
      Enum.map(groups, fn g ->
        if g.session_id == session_id do
          is_active = event[:event_type] != "SessionEnd"
          %{g |
            events: [event | g.events],
            event_count: g.event_count + 1,
            last_activity: event[:created_at],
            is_active: is_active
          }
        else
          g
        end
      end)
      # Re-sort: active first, then by most recent activity
      |> Enum.sort_by(fn session ->
        {not session.is_active, session.last_activity}
      end, fn {a1, t1}, {a2, t2} ->
        cond do
          a1 != a2 -> a1 < a2
          true -> t1 >= t2
        end
      end)
    else
      new_group = %{
        session_id: session_id,
        source_agent: event[:source_agent] || "unknown",
        project_dir: event[:project_dir] || "",
        events: [event],
        event_count: 1,
        start_time: event[:created_at],
        last_activity: event[:created_at],
        is_active: event[:event_type] != "SessionEnd"
      }
      [new_group | groups]
    end
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="app-container">
      <!-- Activity Bar -->
      <aside class="activity-bar">
        <div class="activity-bar-item active" title="Features">
          <svg class="activity-bar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
        </div>
        <div class="activity-bar-item" phx-click="toggle_sidebar" title="Projects">
          <svg class="activity-bar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <div class="activity-bar-item" phx-click="toggle_activity_panel" title="Activity">
          <svg class="activity-bar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12,6 12,12 16,14" />
          </svg>
        </div>
        <div class="activity-bar-spacer"></div>
        <div class="activity-bar-item" title="Settings">
          <svg class="activity-bar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </div>
      </aside>

      <!-- Projects Sidebar -->
      <aside class={["projects-sidebar", !@sidebar_open && "collapsed"]}>
        <div class="sidebar-header">
          <span>Projects</span>
        </div>
        <div class="sidebar-content">
          <div
            :for={project <- @projects}
            class={["project-item", project.path == @active_project && "active"]}
            phx-click="select_project"
            phx-value-path={project.path}
          >
            <div class="project-name">{project.name}</div>
            <div class="project-path">{truncate_path(project.path)}</div>
          </div>
          <div :if={@projects == []} class="empty-state">
            <div class="empty-state-text">No projects found</div>
          </div>
        </div>
      </aside>

      <!-- Main Area -->
      <main class="main-area">
        <!-- Tabs Bar -->
        <div class="tabs-bar">
          <div
            class={["tab", @active_tab == "kanban" && "active"]}
            phx-click="select_tab"
            phx-value-tab="kanban"
          >
            <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="3" width="7" height="7" rx="1" />
              <rect x="3" y="14" width="7" height="7" rx="1" />
              <rect x="14" y="14" width="7" height="7" rx="1" />
            </svg>
            Features
          </div>
          <div
            class={["tab", @active_tab == "timeline" && "active"]}
            phx-click="select_tab"
            phx-value-tab="timeline"
          >
            <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="20" x2="12" y2="10" />
              <line x1="18" y1="20" x2="18" y2="4" />
              <line x1="6" y1="20" x2="6" y2="16" />
            </svg>
            Timeline
          </div>
        </div>

        <!-- Content -->
        <div class="content-split">
          <!-- Kanban Board -->
          <div class="kanban-board">
            <.kanban_column title="Pending" stream={@streams.features_pending} status="pending" />
            <.kanban_column title="In Progress" stream={@streams.features_in_progress} status="in_progress" />
            <.kanban_column title="Completed" stream={@streams.features_completed} status="completed" />
          </div>

          <!-- Activity Panel -->
          <aside class={["activity-panel", !@activity_panel_open && "collapsed"]}>
            <!-- Expanded Content -->
            <div class="sidebar-content" :if={@activity_panel_open}>
              <div class="activity-header" phx-click="toggle_activity_panel">
                <h2>Activity</h2>
                <span class="session-count">{length(@grouped_events)} sessions</span>
              </div>
              <div class="activity-timeline">
                <.session_group
                  :for={session <- @grouped_events}
                  session={session}
                  collapsed={MapSet.member?(@collapsed_sessions, session.session_id)}
                />
                <div :if={@grouped_events == []} class="empty-timeline">
                  <p>No activity yet</p>
                  <p class="hint">Events will appear here as agents work</p>
                </div>
              </div>
            </div>

            <!-- Collapsed State -->
            <div class="collapsed-label" :if={!@activity_panel_open} phx-click="toggle_activity_panel">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="22,12 18,12 15,21 9,3 6,12 2,12" />
              </svg>
              <span>Activity</span>
            </div>
          </aside>
        </div>
      </main>

      <!-- Feature Modal -->
      <.feature_modal :if={@selected_feature} feature={@selected_feature} />

      <!-- Event Detail Modal -->
      <.event_detail_modal :if={@selected_event} event={@selected_event} />
    </div>
    """
  end

  defp feature_modal(assigns) do
    ~H"""
    <div class="modal-overlay" phx-click="close_modal">
      <div class="modal-content" phx-click-away="close_modal">
        <div class="modal-header">
          <span class={"feature-category category-#{@feature.category}"}>{@feature.category}</span>
          <button class="modal-close" phx-click="close_modal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <h2 class="modal-title">{@feature.description}</h2>
          <div class="modal-details">
            <div class="detail-row">
              <span class="detail-label">Status</span>
              <span class={"detail-value status-#{status_class(@feature)}"}>
                {status_text(@feature)}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Priority</span>
              <span class="detail-value">P{@feature.priority || 0}</span>
            </div>
            <div :if={@feature.agent} class="detail-row">
              <span class="detail-label">Agent</span>
              <span class={"detail-value agent-#{agent_type(@feature.agent)}"}>
                {format_agent(@feature.agent)}
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Work Count</span>
              <span class="detail-value">{@feature.work_count || 0} actions</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">ID</span>
              <span class="detail-value detail-id">{@feature.id}</span>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button :if={!@feature.in_progress && !@feature.passes} class="btn btn-primary">
            Start Feature
          </button>
          <button :if={@feature.in_progress} class="btn btn-success">
            Complete Feature
          </button>
          <button class="btn btn-secondary" phx-click="close_modal">
            Close
          </button>
        </div>
      </div>
    </div>
    """
  end

  defp event_detail_modal(assigns) do
    payload = parse_payload(assigns.event[:payload])
    success_status = get_success_status(assigns.event)

    assigns =
      assigns
      |> assign(:payload, payload)
      |> assign(:success_status, success_status)

    ~H"""
    <div class="modal-overlay event-modal-overlay" phx-click="close_event_modal" phx-click-away="close_event_modal">
      <div class="event-modal-content" phx-click="noop">
        <!-- Header -->
        <div class="event-modal-header">
          <div class="event-modal-title-row">
            <div class="event-modal-icon">
              <.tool_icon tool={get_event_icon(@event)} />
            </div>
            <div class="event-modal-title-info">
              <h2 class="event-modal-title">{get_descriptive_title(@event)}</h2>
              <div class="event-modal-badges">
                <span class="event-type-badge">{@event[:event_type]}</span>
                <span :if={@event[:tool_name]} class="event-tool-badge">{@event[:tool_name]}</span>
                <span :if={@success_status == true} class="status-badge status-success">Success</span>
                <span :if={@success_status == false} class="status-badge status-error">Failed</span>
              </div>
            </div>
          </div>
          <button class="modal-close" phx-click="close_event_modal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <!-- Metadata Grid -->
        <div class="event-modal-body">
          <div class="event-meta-grid">
            <div class="meta-item">
              <span class="meta-label">Agent</span>
              <span class={"meta-value agent-#{agent_type(@event[:source_agent])}"}>
                {format_agent(@event[:source_agent])}
              </span>
            </div>
            <div :if={@event[:tool_name]} class="meta-item">
              <span class="meta-label">Tool</span>
              <span class="meta-value">{@event[:tool_name]}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Time</span>
              <span class="meta-value">{format_full_time(@event[:created_at])}</span>
            </div>
            <div :if={@event[:project_dir]} class="meta-item">
              <span class="meta-label">Project</span>
              <span class="meta-value">{get_project_name(@event[:project_dir])}</span>
            </div>
            <div :if={@event[:feature_id]} class="meta-item">
              <span class="meta-label">Feature</span>
              <span class="meta-value feature-value">{@event[:feature_id]}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Session</span>
              <span class="meta-value session-value">{@event[:session_id]}</span>
            </div>
          </div>

          <!-- Tool-specific content -->
          <.tool_content event={@event} payload={@payload} />

          <!-- Raw Payload -->
          <details class="raw-payload-section">
            <summary>Raw Payload</summary>
            <pre class="raw-payload">{format_payload_json(@payload)}</pre>
          </details>
        </div>
      </div>
    </div>
    """
  end

  defp tool_content(assigns) do
    tool_name = assigns.event[:tool_name] || ""
    event_type = assigns.event[:event_type] || ""
    payload = assigns.payload || %{}

    assigns =
      assigns
      |> assign(:tool_name, tool_name)
      |> assign(:event_type, event_type)
      |> assign(:p, payload)

    ~H"""
    <div class="tool-content-section">
      <%= cond do %>
        <% String.contains?(String.downcase(@tool_name), "bashoutput") -> %>
          <div class="tool-detail">
            <h4>Background Shell ID</h4>
            <code class="file-path">{@p["bash_id"] || "N/A"}</code>
          </div>
          <div :if={@p["outputPreview"]} class="tool-detail">
            <h4>Output Preview</h4>
            <pre class="code-block bash-output">{@p["outputPreview"]}</pre>
          </div>

        <% String.contains?(String.downcase(@tool_name), "bash") -> %>
          <div class="tool-detail">
            <h4>Command</h4>
            <pre class="code-block bash-command">{@p["command"] || "N/A"}</pre>
          </div>
          <div :if={@p["description"]} class="tool-detail">
            <h4>Description</h4>
            <p class="tool-description">{@p["description"]}</p>
          </div>
          <div :if={@p["outputPreview"]} class="tool-detail">
            <h4>Output Preview</h4>
            <pre class="code-block bash-output">{@p["outputPreview"]}</pre>
          </div>

        <% String.contains?(String.downcase(@tool_name), "edit") -> %>
          <div class="tool-detail">
            <h4>File</h4>
            <code class="file-path">{@p["filePath"] || "N/A"}</code>
          </div>
          <div :if={@p["oldString"]} class="tool-detail diff-section">
            <h4>Old String</h4>
            <pre class="code-block diff-old">{@p["oldString"]}</pre>
          </div>
          <div :if={@p["newString"]} class="tool-detail diff-section">
            <h4>New String</h4>
            <pre class="code-block diff-new">{@p["newString"]}</pre>
          </div>

        <% String.contains?(String.downcase(@tool_name), "todowrite") -> %>
          <.todo_list_display todos={@p["todos"] || []} input_summary={@p["inputSummary"]} />

        <% String.contains?(String.downcase(@tool_name), "write") -> %>
          <div class="tool-detail">
            <h4>File</h4>
            <code class="file-path">{@p["filePath"] || "N/A"}</code>
          </div>
          <div :if={@p["contentPreview"]} class="tool-detail">
            <h4>Content Preview</h4>
            <pre class="code-block">{@p["contentPreview"]}</pre>
          </div>

        <% String.contains?(String.downcase(@tool_name), "read") -> %>
          <div class="tool-detail">
            <h4>File</h4>
            <code class="file-path">{@p["filePath"] || "N/A"}</code>
          </div>
          <div :if={@p["offset"] || @p["limit"]} class="tool-detail">
            <h4>Range</h4>
            <span>Offset: {@p["offset"] || 0}, Limit: {@p["limit"] || "all"}</span>
          </div>

        <% String.contains?(String.downcase(@tool_name), "grep") -> %>
          <div class="tool-detail">
            <h4>Pattern</h4>
            <code class="search-pattern">{@p["pattern"] || "N/A"}</code>
          </div>
          <div :if={@p["path"]} class="tool-detail">
            <h4>Path</h4>
            <code class="file-path">{@p["path"]}</code>
          </div>
          <div :if={@p["glob"]} class="tool-detail">
            <h4>Glob Filter</h4>
            <code>{@p["glob"]}</code>
          </div>

        <% String.contains?(String.downcase(@tool_name), "glob") -> %>
          <div class="tool-detail">
            <h4>Pattern</h4>
            <code class="search-pattern">{@p["pattern"] || "N/A"}</code>
          </div>
          <div :if={@p["path"]} class="tool-detail">
            <h4>Path</h4>
            <code class="file-path">{@p["path"]}</code>
          </div>

        <% String.contains?(String.downcase(@tool_name), "task") -> %>
          <div :if={@p["taskDescription"] || @p["description"]} class="tool-detail">
            <h4>Task Description</h4>
            <p class="tool-description">{@p["taskDescription"] || @p["description"]}</p>
          </div>
          <div :if={@p["subagentType"]} class="tool-detail">
            <h4>Subagent Type</h4>
            <span class="subagent-type">{@p["subagentType"]}</span>
          </div>
          <div :if={@p["resultSummary"]} class="tool-detail">
            <h4>Result Summary</h4>
            <pre class="code-block">{@p["resultSummary"]}</pre>
          </div>

        <% @event_type == "UserQuery" -> %>
          <div class="tool-detail">
            <h4>User Prompt</h4>
            <p class="user-prompt">{@p["prompt"] || @p["preview"] || "N/A"}</p>
          </div>

        <% @event_type in ["SessionStart", "SessionEnd"] -> %>
          <div :if={@p["reason"]} class="tool-detail">
            <h4>Reason</h4>
            <span>{@p["reason"]}</span>
          </div>

        <% @event_type == "AgentStop" -> %>
          <div class="tool-detail">
            <h4>Stop Reason</h4>
            <span>{@p["reason"] || @p["stopReason"] || "completed"}</span>
          </div>
          <div :if={@p["lastMessage"]} class="tool-detail">
            <h4>Last Message</h4>
            <p class="tool-description">{@p["lastMessage"]}</p>
          </div>

        <% @event_type in ["FeatureStarted", "FeatureCompleted"] -> %>
          <div :if={@p["featureDescription"] || @p["description"]} class="tool-detail">
            <h4>Feature</h4>
            <p class="tool-description">{@p["featureDescription"] || @p["description"]}</p>
          </div>
          <div :if={@p["completionStatus"]} class="tool-detail">
            <h4>Completion Status</h4>
            <span>{@p["completionStatus"]}</span>
          </div>

        <% true -> %>
          <div :if={@p["inputSummary"]} class="tool-detail">
            <h4>Summary</h4>
            <p class="tool-description">{@p["inputSummary"]}</p>
          </div>
      <% end %>
    </div>
    """
  end

  defp format_full_time(nil), do: "N/A"
  defp format_full_time(datetime) when is_binary(datetime) do
    cleaned = datetime
      |> String.replace(~r/\[.+\]$/, "")
      |> String.trim()

    case DateTime.from_iso8601(cleaned) do
      {:ok, dt, _} -> Calendar.strftime(dt, "%Y-%m-%d %H:%M:%S")
      _ ->
        case NaiveDateTime.from_iso8601(cleaned) do
          {:ok, dt} -> Calendar.strftime(dt, "%Y-%m-%d %H:%M:%S")
          _ -> datetime
        end
    end
  end
  defp format_full_time(%DateTime{} = dt), do: Calendar.strftime(dt, "%Y-%m-%d %H:%M:%S")

  defp format_payload_json(nil), do: "{}"
  defp format_payload_json(payload) when is_map(payload) do
    case Jason.encode(payload, pretty: true) do
      {:ok, json} -> json
      _ -> inspect(payload, pretty: true)
    end
  end
  defp format_payload_json(payload), do: inspect(payload, pretty: true)

  defp status_class(feature) do
    cond do
      feature.passes -> "completed"
      feature.in_progress -> "in-progress"
      true -> "pending"
    end
  end

  defp status_text(feature) do
    cond do
      feature.passes -> "Completed"
      feature.in_progress -> "In Progress"
      true -> "Pending"
    end
  end

  defp kanban_column(assigns) do
    ~H"""
    <div class={"kanban-column column-#{@status}"}>
      <div class="column-header">
        <div class="column-header-left">
          <svg class="collapse-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6,9 12,15 18,9" />
          </svg>
          <span>{@title}</span>
        </div>
      </div>
      <div class="column-content" id={"column-#{@status}"} phx-update="stream">
        <.feature_card :for={{dom_id, feature} <- @stream} feature={feature} id={dom_id} />
      </div>
    </div>
    """
  end

  defp feature_card(assigns) do
    ~H"""
    <div class="feature-card" id={@id} phx-click="open_feature" phx-value-id={@feature.id}>
      <div class="feature-header">
        <!-- Type badge -->
        <span :if={@feature[:type] && @feature[:type] != "feature"}
              class={"feature-type type-#{@feature.type}"}>
          {@feature.type}
        </span>

        <!-- Category badge -->
        <span class={"feature-category category-#{@feature.category}"}>{@feature.category}</span>

        <!-- Priority -->
        <span :if={@feature[:priority]} class="feature-priority">P{@feature.priority}</span>

        <!-- Child count indicator -->
        <span :if={@feature[:child_count] && @feature[:child_count] > 0}
              class="feature-children"
              title={"#{@feature.child_count} subtask(s)"}>
          {@feature.child_count}
        </span>
      </div>

      <!-- Parent link -->
      <div :if={@feature[:parent_id]} class="feature-parent">
        <span class="parent-label">Child of:</span>
        <span class="parent-name">{truncate(@feature[:parent_description], 30)}</span>
      </div>

      <p class="feature-description">{@feature.description}</p>

      <!-- Aggregated event count for epics -->
      <div :if={@feature[:type] == "epic" && @feature[:hierarchy_events]}
           class="feature-hierarchy-stats">
        <span class="hierarchy-events">
          {@feature.hierarchy_events} events across subtasks
        </span>
      </div>

      <!-- Existing event count for this feature only -->
      <div :if={@feature[:work_count] && @feature[:work_count] > 0} class="feature-events">
        <span class="event-count">{@feature.work_count} actions</span>
      </div>

      <div class="feature-meta">
        <span :if={@feature.agent} class={"feature-agent agent-#{agent_type(@feature.agent)}"}>
          <span class="agent-dot"></span>
          {format_agent(@feature.agent)}
        </span>
        <span class="feature-work-count">{@feature.work_count || 0} actions</span>
      </div>
      <div :if={@feature.in_progress} class="feature-status-indicator status-streaming"></div>
    </div>
    """
  end

  defp session_group(assigns) do
    ~H"""
    <div class={["session-group", @session.is_active && "session-active"]}>
      <!-- Session Header (clickable) -->
      <div
        class="session-header"
        phx-click="toggle_session"
        phx-value-session={@session.session_id}
      >
        <!-- Row 1: Agent + Status -->
        <div class="session-row-primary">
          <div class="session-agent-info">
            <svg class={["collapse-icon", @collapsed && "collapsed"]} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="6,9 12,15 18,9" />
            </svg>
            <span class={"agent-dot agent-#{agent_type(@session.source_agent)}"}></span>
            <span class="session-agent">{format_agent(@session.source_agent)}</span>
          </div>
          <span class={["session-status", session_status_class(@session)]}>{session_status_text(@session)}</span>
        </div>
        <!-- Row 2: Project + Stats -->
        <div class="session-row-secondary">
          <div class="session-info-left">
            <span class="session-project">{get_project_name(@session.project_dir)}</span>
            <span class="session-separator">·</span>
            <span class="session-id">{truncate_session_id(@session.session_id)}</span>
          </div>
          <div class="session-meta">
            <span class="session-stats">{@session.event_count} events</span>
            <span class="session-duration">{format_duration(@session.start_time, @session.last_activity)}</span>
          </div>
        </div>
      </div>
      <!-- Session Events (collapsible) -->
      <div class={["session-events", @collapsed && "collapsed"]}>
        <.activity_card :for={event <- @session.events} event={event} />
      </div>
    </div>
    """
  end

  defp activity_card(assigns) do
    success_status = get_success_status(assigns.event)
    assigns = assign(assigns, :success_status, success_status)

    ~H"""
    <div
      class={[
        "activity-card",
        @success_status == true && "status-success",
        @success_status == false && "status-error"
      ]}
      id={@event[:dom_id]}
      phx-click="open_event"
      phx-value-id={@event[:dom_id]}
    >
      <!-- Left: Icon + Type stacked -->
      <div class="card-left">
        <div class="card-icon">
          <.tool_icon tool={get_event_icon(@event)} />
        </div>
        <span class="event-type-label">{get_event_badge(@event[:event_type])}</span>
      </div>

      <!-- Right: Content -->
      <div class="card-body">
        <!-- Title (descriptive) -->
        <p class="card-title">{get_descriptive_title(@event)}</p>

        <!-- Feature link if present -->
        <span :if={@event[:feature_id]} class="feature-link">
          {truncate_feature_id(@event[:feature_id])}
        </span>

        <!-- Footer: Agent dot + Time + Status -->
        <div class="card-footer">
          <span class={"agent-dot agent-#{agent_type(@event[:source_agent])}"} title={@event[:source_agent]}></span>
          <span class="event-time">{format_time(@event[:created_at])}</span>
          <span :if={@success_status == true} class="status-check" title="Success">✓</span>
          <span :if={@success_status == false} class="status-x" title="Failed">✗</span>
        </div>
      </div>
    </div>
    """
  end

  defp todo_list_display(assigns) do
    todos = assigns.todos || []
    # Parse todos from inputSummary if not provided directly
    todos = if is_list(todos) and length(todos) > 0 do
      todos
    else
      parse_todos_from_summary(assigns.input_summary)
    end

    assigns = assign(assigns, :parsed_todos, todos)

    ~H"""
    <div class="tool-detail">
      <h4>Todo Items</h4>
      <div class="todo-list-display">
        <%= if length(@parsed_todos) > 0 do %>
          <div :for={todo <- @parsed_todos} class={"todo-item todo-#{todo["status"] || "pending"}"}>
            <span class="todo-status-icon">
              <%= case todo["status"] do %>
                <% "completed" -> %>✓
                <% "in_progress" -> %>●
                <% _ -> %>○
              <% end %>
            </span>
            <span class="todo-content">{todo["content"] || todo["activeForm"] || "Unknown"}</span>
          </div>
        <% else %>
          <p class="no-todos">No todos parsed</p>
        <% end %>
      </div>
    </div>
    """
  end

  defp parse_todos_from_summary(nil), do: []
  defp parse_todos_from_summary(summary) when is_binary(summary) do
    # Try to extract todos from inputSummary string like:
    # "TodoWrite: {'todos': [{'content': 'Fix hook error...', 'status': 'completed'..."
    case Regex.scan(~r/'content':\s*'([^']+)'[^}]*'status':\s*'([^']+)'/, summary) do
      matches when is_list(matches) and length(matches) > 0 ->
        Enum.map(matches, fn [_, content, status] ->
          %{"content" => content, "status" => status}
        end)
      _ -> []
    end
  end
  defp parse_todos_from_summary(_), do: []


  defp tool_icon(assigns) do
    tool_type = tool_class(assigns.tool)
    # Generate a unique ID for the icon based on the tool name to help LiveView diff correctly
    icon_id = "icon-#{:erlang.phash2({assigns.tool, tool_type})}"
    assigns = assigns
      |> assign(:tool_type, tool_type)
      |> assign(:icon_id, icon_id)

    ~H"""
    <svg id={@icon_id} class={"event-tool-icon tool-#{@tool_type}"} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <%= case @tool_type do %>
        <% "read" -> %>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14,2 14,8 20,8" />
        <% "write" -> %>
          <path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        <% "edit" -> %>
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        <% "bash" -> %>
          <polyline points="4,17 10,11 4,5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        <% "grep" -> %>
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        <% "glob" -> %>
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        <% "task" -> %>
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        <% "rocket" -> %>
          <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
          <path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
          <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
          <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
        <% "flag" -> %>
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
          <line x1="4" y1="22" x2="4" y2="15" />
        <% "user" -> %>
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        <% "stop" -> %>
          <circle cx="12" cy="12" r="10" />
          <rect x="9" y="9" width="6" height="6" />
        <% "cpu" -> %>
          <rect x="4" y="4" width="16" height="16" rx="2" ry="2" />
          <rect x="9" y="9" width="6" height="6" />
          <line x1="9" y1="1" x2="9" y2="4" />
          <line x1="15" y1="1" x2="15" y2="4" />
          <line x1="9" y1="20" x2="9" y2="23" />
          <line x1="15" y1="20" x2="15" y2="23" />
          <line x1="20" y1="9" x2="23" y2="9" />
          <line x1="20" y1="14" x2="23" y2="14" />
          <line x1="1" y1="9" x2="4" y2="9" />
          <line x1="1" y1="14" x2="4" y2="14" />
        <% "play" -> %>
          <polygon points="5,3 19,12 5,21 5,3" />
        <% "check" -> %>
          <polyline points="20,6 9,17 4,12" />
        <% "todo" -> %>
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
          <line x1="9" y1="7" x2="9" y2="7.01" />
          <line x1="9" y1="11" x2="9" y2="11.01" />
          <line x1="9" y1="15" x2="9" y2="15.01" />
        <% "circle" -> %>
          <circle cx="12" cy="12" r="10" />
        <%!-- MCP tool icons --%>
        <% "camera" -> %>
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        <% "pointer" -> %>
          <path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z" />
          <path d="M13 13l6 6" />
        <% "compass" -> %>
          <circle cx="12" cy="12" r="10" />
          <polygon points="16.24,7.76 14.12,14.12 7.76,16.24 9.88,9.88 16.24,7.76" />
        <% "form" -> %>
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <line x1="9" y1="9" x2="15" y2="9" />
          <line x1="9" y1="13" x2="15" y2="13" />
          <line x1="9" y1="17" x2="12" y2="17" />
        <% "terminal" -> %>
          <polyline points="4,17 10,11 4,5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        <% "network" -> %>
          <circle cx="12" cy="5" r="3" />
          <line x1="12" y1="8" x2="12" y2="14" />
          <circle cx="6" cy="19" r="3" />
          <circle cx="18" cy="19" r="3" />
          <line x1="12" y1="14" x2="6" y2="16" />
          <line x1="12" y1="14" x2="18" y2="16" />
        <% "code" -> %>
          <polyline points="16,18 22,12 16,6" />
          <polyline points="8,6 2,12 8,18" />
        <% "browser" -> %>
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <line x1="3" y1="9" x2="21" y2="9" />
          <circle cx="7" cy="6" r="1" fill="currentColor" />
          <circle cx="11" cy="6" r="1" fill="currentColor" />
        <% "gauge" -> %>
          <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z" />
          <path d="M12 6v6l4 2" />
        <% "dashboard" -> %>
          <rect x="3" y="3" width="7" height="9" rx="1" />
          <rect x="14" y="3" width="7" height="5" rx="1" />
          <rect x="14" y="12" width="7" height="9" rx="1" />
          <rect x="3" y="16" width="7" height="5" rx="1" />
        <% "lightbulb" -> %>
          <path d="M9 18h6" />
          <path d="M10 22h4" />
          <path d="M12 2a7 7 0 0 0-4 12.7V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.3A7 7 0 0 0 12 2z" />
        <% "kanban" -> %>
          <rect x="3" y="3" width="5" height="18" rx="1" />
          <rect x="10" y="3" width="5" height="12" rx="1" />
          <rect x="17" y="3" width="5" height="7" rx="1" />
        <% "folder" -> %>
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        <% "database" -> %>
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        <% "git" -> %>
          <circle cx="12" cy="18" r="3" />
          <circle cx="6" cy="6" r="3" />
          <circle cx="18" cy="6" r="3" />
          <path d="M18 9a9 9 0 0 1-9 9" />
          <path d="M6 9v3a3 3 0 0 0 3 3h3" />
        <% "plug" -> %>
          <path d="M12 22v-5" />
          <path d="M9 8V2" />
          <path d="M15 8V2" />
          <path d="M18 8v5a6 6 0 0 1-12 0V8z" />
        <% "other" -> %>
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        <% _ -> %>
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
      <% end %>
    </svg>
    """
  end

  # Helper functions

  defp format_time(nil), do: ""
  defp format_time(datetime) when is_binary(datetime) do
    # Handle various timestamp formats
    cleaned = datetime
      |> String.replace(~r/\[.+\]$/, "")
      |> String.trim()

    case DateTime.from_iso8601(cleaned) do
      {:ok, dt, _} -> Calendar.strftime(dt, "%H:%M:%S")
      _ ->
        case NaiveDateTime.from_iso8601(cleaned) do
          {:ok, dt} -> Calendar.strftime(dt, "%H:%M:%S")
          _ -> String.slice(datetime, 0, 8)
        end
    end
  end
  defp format_time(%DateTime{} = dt), do: Calendar.strftime(dt, "%H:%M:%S")

  defp format_agent(nil), do: "Agent"
  defp format_agent(agent) when is_binary(agent) do
    agent
    |> String.split("-")
    |> List.first()
    |> String.capitalize()
  end

  defp agent_type(nil), do: "unknown"
  defp agent_type(agent) when is_binary(agent) do
    cond do
      String.contains?(String.downcase(agent), "claude") -> "claude"
      String.contains?(String.downcase(agent), "codex") -> "codex"
      String.contains?(String.downcase(agent), "gemini") -> "gemini"
      true -> "unknown"
    end
  end

  defp tool_class(nil), do: "other"
  defp tool_class(tool) do
    tool_lower = String.downcase(tool)
    cond do
      # MCP tools - extract server and action
      String.starts_with?(tool_lower, "mcp__") -> mcp_tool_class(tool_lower)
      String.contains?(tool_lower, "todowrite") -> "todo"
      String.contains?(tool_lower, "bashoutput") -> "terminal"
      String.contains?(tool_lower, "killshell") -> "stop"
      String.contains?(tool_lower, "read") -> "read"
      String.contains?(tool_lower, "write") -> "write"
      String.contains?(tool_lower, "edit") -> "edit"
      String.contains?(tool_lower, "bash") -> "bash"
      String.contains?(tool_lower, "grep") -> "grep"
      String.contains?(tool_lower, "glob") -> "glob"
      String.contains?(tool_lower, "task") -> "task"
      tool_lower in ["rocket", "flag", "user", "stop", "cpu", "play", "check", "circle", "todo"] -> tool_lower
      true -> "other"
    end
  end

  # Map MCP tools to icon classes based on server and action
  defp mcp_tool_class(tool) do
    # Extract parts: mcp__<server>__<action>
    parts = String.split(tool, "__")
    server = Enum.at(parts, 1, "")
    action = Enum.at(parts, 2, "")

    cond do
      # Chrome DevTools
      String.contains?(server, "chrome") ->
        cond do
          String.contains?(action, "screenshot") -> "camera"
          String.contains?(action, "snapshot") -> "camera"
          String.contains?(action, "click") -> "pointer"
          String.contains?(action, "navigate") -> "compass"
          String.contains?(action, "fill") -> "form"
          String.contains?(action, "console") -> "terminal"
          String.contains?(action, "network") -> "network"
          String.contains?(action, "evaluate") -> "code"
          String.contains?(action, "page") -> "browser"
          String.contains?(action, "performance") -> "gauge"
          true -> "browser"
        end

      # Ijoka tools
      String.contains?(server, "ijoka") ->
        cond do
          String.contains?(action, "status") -> "dashboard"
          String.contains?(action, "feature") -> "flag"
          String.contains?(action, "insight") -> "lightbulb"
          true -> "kanban"
        end

      # Filesystem / file-related
      String.contains?(server, "filesystem") or String.contains?(server, "file") ->
        cond do
          String.contains?(action, "read") -> "read"
          String.contains?(action, "write") -> "write"
          String.contains?(action, "list") -> "folder"
          true -> "folder"
        end

      # Database
      String.contains?(server, "database") or String.contains?(server, "sql") or String.contains?(server, "db") ->
        "database"

      # Git
      String.contains?(server, "git") ->
        "git"

      # Default MCP
      true -> "plug"
    end
  end

  defp truncate_path(path) when is_binary(path) do
    case String.split(path, "/") do
      parts when length(parts) > 3 ->
        ".../" <> Enum.join(Enum.take(parts, -2), "/")
      _ ->
        path
    end
  end
  defp truncate_path(_), do: ""

  defp truncate_session_id(id) when is_binary(id) do
    if String.length(id) > 12 do
      String.slice(id, 0, 8) <> "..."
    else
      id
    end
  end
  defp truncate_session_id(_), do: ""

  defp truncate(str, max) when is_binary(str) and byte_size(str) > max do
    String.slice(str, 0, max) <> "..."
  end
  defp truncate(str, _), do: str || ""

  # Session status helpers
  defp session_status_class(%{is_active: true}), do: "active"
  defp session_status_class(_), do: "ended"

  defp session_status_text(%{is_active: true}), do: "active"
  defp session_status_text(_), do: "ended"

  defp get_project_name(nil), do: "unknown"
  defp get_project_name(""), do: "unknown"
  defp get_project_name(path) when is_binary(path) do
    path |> String.trim_trailing("/") |> Path.basename()
  end

  defp format_duration(nil, _), do: "--"
  defp format_duration(_, nil), do: "--"
  defp format_duration(start_time, end_time) do
    with start_dt when not is_nil(start_dt) <- parse_datetime(start_time),
         end_dt when not is_nil(end_dt) <- parse_datetime(end_time) do
      diff_seconds = abs(DateTime.diff(end_dt, start_dt, :second))
      hours = div(diff_seconds, 3600)
      minutes = div(rem(diff_seconds, 3600), 60)
      seconds = rem(diff_seconds, 60)

      cond do
        hours > 0 -> "#{hours}h #{minutes}m"
        minutes > 0 -> "#{minutes}m #{seconds}s"
        true -> "#{seconds}s"
      end
    else
      _ -> "--"
    end
  end

  # Event helpers for activity cards
  defp get_event_icon(event) do
    cond do
      event[:tool_name] -> event[:tool_name]
      event[:event_type] == "SessionStart" -> "rocket"
      event[:event_type] == "SessionEnd" -> "flag"
      event[:event_type] == "UserQuery" -> "user"
      event[:event_type] == "AgentStop" -> "stop"
      event[:event_type] == "SubagentStop" -> "cpu"
      event[:event_type] == "FeatureStarted" -> "play"
      event[:event_type] == "FeatureCompleted" -> "check"
      true -> "circle"
    end
  end

  defp get_event_badge(nil), do: "event"
  defp get_event_badge("ToolCall"), do: "call"
  defp get_event_badge("TranscriptUpdated"), do: "result"
  defp get_event_badge("UserQuery"), do: "query"
  defp get_event_badge("SessionStart"), do: "start"
  defp get_event_badge("SessionEnd"), do: "end"
  defp get_event_badge("AgentStop"), do: "stop"
  defp get_event_badge("SubagentStop"), do: "agent"
  defp get_event_badge(type), do: type |> String.downcase() |> String.slice(0, 8)

  defp get_success_status(event) do
    payload = parse_payload(event[:payload])
    case payload do
      %{"success" => success} when is_boolean(success) -> success
      _ -> nil
    end
  end

  defp parse_payload(nil), do: nil
  defp parse_payload(payload) when is_map(payload), do: payload
  defp parse_payload(payload) when is_binary(payload) do
    case Jason.decode(payload) do
      {:ok, decoded} -> decoded
      _ -> nil
    end
  end

  defp get_descriptive_title(event) do
    payload = parse_payload(event[:payload])
    event_type = event[:event_type]
    tool_name = event[:tool_name]

    case event_type do
      "UserQuery" ->
        prompt = get_in(payload, ["prompt"]) || get_in(payload, ["preview"]) || ""
        if prompt != "", do: truncate(clean_string(prompt), 55), else: "User Query"

      "SessionStart" ->
        project = event[:project_dir]
        if project, do: "Session: #{get_project_name(project)}", else: "Session Started"

      "SessionEnd" ->
        reason = get_in(payload, ["reason"]) || get_in(payload, ["stopReason"])
        if reason, do: "Session Ended (#{reason})", else: "Session Ended"

      "AgentStop" ->
        reason = get_in(payload, ["reason"]) || get_in(payload, ["stopReason"]) || "completed"
        "Agent Stopped: #{reason}"

      "SubagentStop" ->
        task = get_in(payload, ["taskDescription"]) || get_in(payload, ["description"])
        agent_type = get_in(payload, ["subagentType"]) || get_in(payload, ["subagent_type"])
        cond do
          task -> "Subagent Done: #{truncate(task, 35)}"
          agent_type -> "Subagent Done: #{agent_type}"
          true -> "Subagent Completed"
        end

      "ToolCall" when not is_nil(tool_name) ->
        get_tool_title(tool_name, payload)

      "TranscriptUpdated" ->
        msg_type = get_in(payload, ["messageType"]) || tool_name
        cond do
          msg_type in ["tool_result", "ToolResult"] ->
            input_summary = get_in(payload, ["inputSummary"])
            if input_summary, do: "Result: #{truncate(input_summary, 40)}", else: "Tool Result"
          msg_type == "assistant" ->
            preview = get_in(payload, ["preview"])
            if preview, do: "Response: #{truncate(preview, 40)}", else: "Assistant Response"
          msg_type == "user" ->
            preview = get_in(payload, ["preview"])
            if preview, do: "User: #{truncate(preview, 45)}", else: "User Message"
          true ->
            msg_type || "Transcript Update"
        end

      "FeatureStarted" ->
        desc = get_in(payload, ["featureDescription"]) || get_in(payload, ["description"])
        if desc, do: "Started: #{truncate(desc, 40)}", else: "Feature Started"

      "FeatureCompleted" ->
        desc = get_in(payload, ["featureDescription"]) || get_in(payload, ["description"])
        if desc, do: "Completed: #{truncate(desc, 38)}", else: "Feature Completed"

      _ when not is_nil(tool_name) ->
        get_tool_title(tool_name, payload)

      _ ->
        desc = get_in(payload, ["description"]) || get_in(payload, ["preview"])
        if desc, do: truncate(desc, 50), else: (event_type || "Event")
    end
  end

  defp get_tool_title(tool_name, payload) do
    tool_lower = String.downcase(tool_name || "")

    cond do
      String.contains?(tool_lower, "bashoutput") ->
        bash_id = get_in(payload, ["bash_id"]) || ""
        description = get_in(payload, ["commandDescription"]) || ""
        original_cmd = get_in(payload, ["originalCommand"]) || ""

        cond do
          description != "" ->
            # Use the description if available (most informative)
            "Output: #{truncate(description, 40)}"
          original_cmd != "" ->
            # Fall back to command preview
            parts = original_cmd |> String.trim() |> String.split(~r/\s+/) |> Enum.take(3)
            "Output: $ #{truncate(Enum.join(parts, " "), 35)}"
          bash_id != "" ->
            # Just show the ID if no context available
            "Get Output: #{bash_id}"
          true ->
            "Get Background Output"
        end

      String.contains?(tool_lower, "killshell") ->
        shell_id = get_in(payload, ["shell_id"]) || ""
        if shell_id != "", do: "Kill Shell: #{shell_id}", else: "Kill Background Shell"

      String.contains?(tool_lower, "bash") ->
        cmd = get_in(payload, ["command"]) || ""
        if cmd != "" do
          parts = cmd |> String.trim() |> String.split(~r/\s+/) |> Enum.take(4)
          "$ #{truncate(Enum.join(parts, " "), 45)}"
        else
          "Run Command"
        end

      String.contains?(tool_lower, "read") ->
        file = get_in(payload, ["filePath"]) || get_in(payload, ["file_path"]) || ""
        offset = get_in(payload, ["offset"])
        limit = get_in(payload, ["limit"])

        filename = if file != "", do: Path.basename(file), else: nil

        # Build line range info if offset/limit specified
        line_info = cond do
          offset && limit ->
            start_line = offset + 1  # offset is 0-based, display as 1-based
            end_line = offset + limit
            "L#{start_line}-#{end_line}"
          offset ->
            "L#{offset + 1}+"
          limit ->
            "L1-#{limit}"
          true -> nil
        end

        cond do
          filename && line_info -> "Read #{filename} (#{line_info})"
          filename -> "Read #{filename}"
          line_info -> "Read File (#{line_info})"
          true -> "Read File"
        end

      String.contains?(tool_lower, "todowrite") ->
        # Try to extract todo content from inputSummary which contains the actual task text
        input_summary = get_in(payload, ["inputSummary"]) || ""
        # Parse out the first todo content from the summary string
        # Format: "TodoWrite: {'todos': [{'content': 'Fix hook error..."
        case Regex.run(~r/'content':\s*'([^']+)'/, input_summary) do
          [_, first_todo] ->
            truncate(first_todo, 50)
          _ ->
            # Fallback: check for structured todos
            todos = get_in(payload, ["todos"]) || []
            if is_list(todos) and length(todos) > 0 do
              # Get the in_progress todo content, or first todo
              active_todo = Enum.find(todos, fn t -> t["status"] == "in_progress" end) ||
                            Enum.at(todos, 0)
              content = active_todo["content"] || active_todo["activeForm"]
              if content, do: truncate(content, 50), else: "Update Todos"
            else
              "Update Todos"
            end
        end

      String.contains?(tool_lower, "write") ->
        file = get_in(payload, ["filePath"]) || get_in(payload, ["file_path"]) || ""
        if file != "", do: "Write #{Path.basename(file)}", else: "Write File"

      String.contains?(tool_lower, "edit") ->
        file = get_in(payload, ["filePath"]) || get_in(payload, ["file_path"]) || ""
        old_str = get_in(payload, ["oldString"]) || get_in(payload, ["old_string"]) || ""
        new_str = get_in(payload, ["newString"]) || get_in(payload, ["new_string"]) || ""

        filename = if file != "", do: Path.basename(file), else: nil

        # Extract meaningful identifier from the change (function name, etc.)
        change_preview = extract_edit_preview(old_str, new_str)

        # Use actual line numbers from payload when available (from Edit response)
        start_line = get_in(payload, ["startLine"])
        end_line = get_in(payload, ["endLine"])

        line_info = cond do
          # Use actual line numbers if available
          start_line && end_line && start_line != end_line ->
            "(L#{start_line}-#{end_line})"
          start_line && end_line ->
            "(L#{start_line})"
          start_line ->
            "(L#{start_line}+)"
          # Fall back to line counts from content
          true ->
            old_lines = if old_str != "", do: length(String.split(old_str, "\n")), else: 0
            new_lines = if new_str != "", do: length(String.split(new_str, "\n")), else: 0
            cond do
              old_lines == new_lines and old_lines > 0 -> "(#{old_lines}L)"
              old_lines > 0 and new_lines > 0 -> "(#{old_lines}→#{new_lines}L)"
              true -> nil
            end
        end

        # Build title: filename + change context + line info
        cond do
          filename && change_preview && line_info ->
            "Edit #{filename}: #{truncate(change_preview, 25)} #{line_info}"
          filename && change_preview ->
            "Edit #{filename}: #{truncate(change_preview, 30)}"
          filename && line_info ->
            "Edit #{filename} #{line_info}"
          filename ->
            "Edit #{filename}"
          change_preview ->
            "Edit: #{truncate(change_preview, 40)}"
          true ->
            "Edit File"
        end

      String.contains?(tool_lower, "grep") ->
        pattern = get_in(payload, ["pattern"]) || ""
        path = get_in(payload, ["path"])
        search_path = if path, do: " in #{Path.basename(path)}", else: ""
        if pattern != "", do: "Search: \"#{truncate(pattern, 25)}\"#{search_path}", else: "Search Code"

      String.contains?(tool_lower, "glob") ->
        pattern = get_in(payload, ["pattern"]) || ""
        path = get_in(payload, ["path"])
        search_path = if path, do: " in #{Path.basename(path)}", else: ""
        if pattern != "", do: "Find: #{truncate(pattern, 30)}#{search_path}", else: "Find Files"

      String.contains?(tool_lower, "task") ->
        desc = get_in(payload, ["description"]) || get_in(payload, ["taskDescription"])
        agent_type = get_in(payload, ["subagentType"]) || get_in(payload, ["subagent_type"])
        cond do
          desc -> "#{if agent_type, do: "[#{agent_type}] ", else: ""}#{truncate(desc, 40)}"
          agent_type -> "Task: #{agent_type}"
          true -> "Run Task"
        end

      String.contains?(tool_lower, "webfetch") ->
        url = get_in(payload, ["url"]) || ""
        if url != "" do
          case URI.parse(url) do
            %URI{host: host, path: path} when not is_nil(host) ->
              "Fetch: #{host}#{truncate(path || "", 20)}"
            _ ->
              "Fetch: #{truncate(url, 40)}"
          end
        else
          "Fetch Web Page"
        end

      String.contains?(tool_lower, "websearch") ->
        query = get_in(payload, ["query"]) || ""
        if query != "", do: "Search: \"#{truncate(query, 35)}\"", else: "Web Search"

      # MCP tools - format nicely based on server and action
      String.starts_with?(tool_lower, "mcp__") ->
        format_mcp_tool_title(tool_lower, payload)

      true ->
        tool_name
    end
  end

  # Format MCP tool titles to be more descriptive
  defp format_mcp_tool_title(tool_lower, payload) do
    parts = String.split(tool_lower, "__")
    server = Enum.at(parts, 1, "")
    action = Enum.at(parts, 2, "")

    cond do
      # Chrome DevTools
      String.contains?(server, "chrome") ->
        case action do
          "take_screenshot" -> "Screenshot"
          "take_snapshot" -> "Page Snapshot"
          "click" ->
            uid = get_in(payload, ["uid"]) || ""
            if uid != "", do: "Click: #{uid}", else: "Click Element"
          "navigate_page" ->
            url = get_in(payload, ["url"]) || ""
            if url != "" do
              case URI.parse(url) do
                %URI{host: host} when not is_nil(host) -> "Navigate: #{host}"
                _ -> "Navigate: #{truncate(url, 35)}"
              end
            else
              "Navigate Page"
            end
          "fill" ->
            value = get_in(payload, ["value"]) || ""
            if value != "", do: "Fill: \"#{truncate(value, 30)}\"", else: "Fill Input"
          "fill_form" -> "Fill Form"
          "list_pages" -> "List Browser Pages"
          "select_page" -> "Select Page"
          "new_page" ->
            url = get_in(payload, ["url"]) || ""
            if url != "", do: "Open: #{truncate(url, 35)}", else: "Open New Page"
          "close_page" -> "Close Page"
          "list_console_messages" -> "Console Messages"
          "get_console_message" -> "Get Console Message"
          "list_network_requests" -> "Network Requests"
          "get_network_request" -> "Get Network Request"
          "evaluate_script" -> "Evaluate Script"
          "press_key" ->
            key = get_in(payload, ["key"]) || ""
            if key != "", do: "Press: #{key}", else: "Press Key"
          "hover" -> "Hover Element"
          "drag" -> "Drag Element"
          "upload_file" -> "Upload File"
          "handle_dialog" -> "Handle Dialog"
          "wait_for" ->
            text = get_in(payload, ["text"]) || ""
            if text != "", do: "Wait: \"#{truncate(text, 30)}\"", else: "Wait For"
          "resize_page" -> "Resize Page"
          "emulate" -> "Emulate Device"
          "performance_start_trace" -> "Start Performance Trace"
          "performance_stop_trace" -> "Stop Performance Trace"
          "performance_analyze_insight" -> "Analyze Performance"
          _ -> "Chrome: #{humanize_action(action)}"
        end

      # Ijoka tools
      String.contains?(server, "ijoka") ->
        case action do
          "ijoka_status" -> "Get Project Status"
          "ijoka_start_feature" -> "Start Feature"
          "ijoka_complete_feature" -> "Complete Feature"
          "ijoka_block_feature" -> "Block Feature"
          "ijoka_create_feature" ->
            desc = get_in(payload, ["description"]) || ""
            if desc != "", do: "Create: #{truncate(desc, 35)}", else: "Create Feature"
          "ijoka_record_insight" -> "Record Insight"
          "ijoka_get_insights" -> "Get Insights"
          _ -> "Ijoka: #{humanize_action(action)}"
        end

      # Filesystem
      String.contains?(server, "filesystem") or String.contains?(server, "file") ->
        case action do
          a when a in ["read", "read_file"] ->
            path = get_in(payload, ["path"]) || ""
            if path != "", do: "Read: #{Path.basename(path)}", else: "Read File"
          a when a in ["write", "write_file"] ->
            path = get_in(payload, ["path"]) || ""
            if path != "", do: "Write: #{Path.basename(path)}", else: "Write File"
          "list" -> "List Directory"
          "list_directory" -> "List Directory"
          _ -> humanize_action(action)
        end

      # Default MCP
      true ->
        "#{humanize_action(server)}: #{humanize_action(action)}"
    end
  end

  # Convert snake_case to Title Case
  defp humanize_action(nil), do: ""
  defp humanize_action(""), do: ""
  defp humanize_action(action) do
    action
    |> String.replace("_", " ")
    |> String.split(" ")
    |> Enum.map(&String.capitalize/1)
    |> Enum.join(" ")
  end

  # Extract a meaningful preview from edit old/new strings
  # Tries to identify function names, class names, or other significant identifiers
  defp extract_edit_preview(old_str, new_str) do
    # First try to find meaningful code identifiers in the new string
    content = if new_str != "", do: new_str, else: old_str
    content = clean_string(content)

    cond do
      content == "" ->
        nil

      # Elixir function definition: defp/def function_name
      match = Regex.run(~r/\bdef(?:p|macro|macrop)?\s+([a-z_][a-zA-Z0-9_?!]*)/u, content) ->
        [_, func_name] = match
        func_name

      # Elixir module: defmodule ModuleName
      match = Regex.run(~r/defmodule\s+([A-Z][a-zA-Z0-9_.]*)/u, content) ->
        [_, mod_name] = match
        mod_name

      # JavaScript/TypeScript function: function name( or const name =
      match = Regex.run(~r/(?:function|const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)/u, content) ->
        [_, func_name] = match
        func_name

      # Python function: def function_name
      match = Regex.run(~r/def\s+([a-z_][a-zA-Z0-9_]*)/u, content) ->
        [_, func_name] = match
        func_name

      # Class definition: class ClassName
      match = Regex.run(~r/class\s+([A-Z][a-zA-Z0-9_]*)/u, content) ->
        [_, class_name] = match
        class_name

      # CSS class or HTML element change
      match = Regex.run(~r/class="([^"]+)"/u, content) ->
        [_, class_val] = match
        first_class = class_val |> String.split() |> List.first()
        ".#{first_class}"

      # Any identifier-like pattern at start of string
      match = Regex.run(~r/^([a-zA-Z_][a-zA-Z0-9_]*(?:\s*=)?)/u, content) ->
        [_, identifier] = match
        identifier |> String.trim()

      # Just use first significant words from content
      true ->
        content
        |> String.split(~r/\s+/)
        |> Enum.take(3)
        |> Enum.join(" ")
    end
  end

  defp clean_string(str) when is_binary(str) do
    str |> String.replace(~r/\s+/, " ") |> String.trim()
  end
  defp clean_string(_), do: ""

  defp truncate_feature_id(nil), do: ""
  defp truncate_feature_id(id) when is_binary(id) do
    # Get just the last part after any colons
    id |> String.split(":") |> List.last() |> truncate(12)
  end
end
