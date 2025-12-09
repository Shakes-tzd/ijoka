defmodule IjokaWebWeb.Router do
  use IjokaWebWeb, :router

  pipeline :browser do
    plug :accepts, ["html"]
    plug :fetch_session
    plug :fetch_live_flash
    plug :put_root_layout, html: {IjokaWebWeb.Layouts, :root}
    plug :protect_from_forgery
    plug :put_secure_browser_headers
  end

  pipeline :api do
    plug :accepts, ["json"]
  end

  scope "/", IjokaWebWeb do
    pipe_through :browser

    live "/", DashboardLive, :index
  end

  # API routes for hook events (replaces Rust HTTP server)
  scope "/api", IjokaWebWeb do
    pipe_through :api

    post "/events", EventController, :create
    get "/events", EventController, :index
    get "/health", HealthController, :check
  end
end
