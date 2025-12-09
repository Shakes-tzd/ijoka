defmodule IjokaWeb.Application do
  # See https://hexdocs.pm/elixir/Application.html
  # for more information on OTP Applications
  @moduledoc false

  use Application

  @impl true
  def start(_type, _args) do
    children = [
      IjokaWebWeb.Telemetry,
      {DNSCluster, query: Application.get_env(:ijoka_web, :dns_cluster_query) || :ignore},
      {Phoenix.PubSub, name: IjokaWeb.PubSub},
      # Memgraph Bolt connection
      {Bolt.Sips, Application.get_env(:bolt_sips, Bolt)},
      # Event subscription worker for real-time updates
      IjokaWeb.Graph.EventSubscriber,
      # Start to serve requests, typically the last entry
      IjokaWebWeb.Endpoint
    ]

    # See https://hexdocs.pm/elixir/Supervisor.html
    # for other strategies and supported options
    opts = [strategy: :one_for_one, name: IjokaWeb.Supervisor]
    Supervisor.start_link(children, opts)
  end

  # Tell Phoenix to update the endpoint configuration
  # whenever the application is updated.
  @impl true
  def config_change(changed, _new, removed) do
    IjokaWebWeb.Endpoint.config_change(changed, removed)
    :ok
  end
end
