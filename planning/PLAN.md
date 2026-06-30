# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (free `gpt-oss-120b:free` model), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic. The backend lazily initializes the database on first request — creating tables and seeding default data if the SQLite file doesn't exist or is empty.
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

```bash
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices via a small built-in lookup for the default tickers (e.g., AAPL ~$190, GOOGL ~$175, etc.). A ticker added later that is not in the lookup is assigned a random plausible seed price (roughly $20-$500) on first use.
- Ticker validation in simulator mode is minimal: any 1-5 character A-Z symbol is accepted. In Massive mode a ticker is rejected if the API returns no data for it.
- Runs continuously as an in-process background task, regardless of real-world market hours, so the demo always shows movement. (With Massive, prices instead reflect the real market and are flat when it is closed — the simulator gives the liveliest demo.)
- No external dependencies

### Massive API (Optional)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for the union of all watched tickers on a configurable interval
- Free tier (5 calls/min): poll every 15 seconds
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds, per ticker: latest price, previous price, session-open price, and timestamp
- The cache tracks the union of (watchlist tickers ∪ tickers with an open position), so a held ticker stays priced for P&L even after it is removed from the watchlist
- The session-open price is the first price observed for a ticker after the backend starts. The watchlist "daily change %" is computed as `(latest - session_open) / session_open`. This is a per-session baseline, not a real previous-day close — adequate for the simulator and simple to compute.
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- The stream emits an event for a ticker only when its price changes since the last emit. With the simulator (which moves every tick) this is effectively every ~500ms; with the Massive poller it is only when a poll returns a new price. This avoids redundant ticks and spurious flash animations.
- The streamed tickers are every ticker in the price cache — the union of the watchlist and any open positions (see Shared Price Cache)
- Each SSE event contains ticker, latest price, previous price, session-open price, daily change %, change direction, and timestamp
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically
- On initialization the backend enables WAL journal mode and keeps every write in a short transaction, so the 30-second snapshot task and the request handlers can write concurrently without "database is locked" errors

### Schema

All tables include a `user_id` column defaulting to `"default"`. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

Monetary values (`cash_balance`, `price`, `avg_cost`, `total_value`) and P&L are stored as `REAL` and computed in full precision. The API and UI round currency to 2 decimal places and share quantities to 4 decimal places for display, so totals never show floating-point noise.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`
- When a sell reduces `quantity` to 0 the row is deleted, so the positions table and heatmap never show empty holdings

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded every 30 seconds by a background task, and immediately after each trade execution.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart) |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers with latest prices |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, receive complete JSON response (message + executed actions) |
| GET | `/api/chat/history` | Recent conversation history, so the chat panel repopulates on page reload |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment) |

---

## 9. LLM Integration

When writing code to make calls to LLMs, use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b:free` model (OpenRouter's free provider). Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads the last 20 messages of conversation history from the `chat_messages` table (a fixed window keeps prompt size and cost bounded)
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output
5. Parses the response with a tolerant JSON parser (see Structured Output Schema)
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming — a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (sufficient cash for buys, sufficient shares for sells)
- `watchlist_changes` (optional): Array of watchlist modifications

**Parsing robustness.** The `gpt-oss-120b:free` endpoint may not honor `response_format` / JSON-schema mode. The backend therefore treats robust parsing as the primary path: it requests JSON in the prompt (and sets `response_format` when the provider supports it), then parses the reply with a tolerant parser that extracts the JSON object from the text. If parsing still fails, the backend falls back to treating the raw reply as a plain `message` with no trades or watchlist changes, so the chat never hard-errors.

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), the error is included in the chat response so the LLM can inform the user.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling OpenRouter. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), daily change %, and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, price over time. It draws from the same SSE data accumulated since page load as the sparklines (the simulator has no real history), so it starts sparse and fills in as ticks arrive — just rendered larger and in more detail than the sparkline. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations.
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Connection indicator states are derived from the `EventSource`: green when `readyState === OPEN` and a message arrived recently; yellow when `readyState === CONNECTING` (the browser is auto-retrying after a drop); red when no message has been received for several seconds or `readyState === CLOSED`
- The chat panel loads `GET /api/chat/history` on mount to restore the prior conversation
- Canvas-based charting library preferred (Lightweight Charts or Recharts) for performance
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The `db/` directory in the project root maps to `/app/db` in the container. The backend writes `finally.db` to this path.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: disconnect and verify reconnection

---

## 13. Documentation Review — Questions & Feedback

This section collects open questions, clarifications, and simplification opportunities raised while reviewing this plan. It is advisory — resolve or consciously dismiss each item before/while building.

### Open Questions & Clarifications

1. **Where does the "main detailed chart" get its history?** Sparklines are explicitly "accumulated on the frontend from SSE since page load," so they start empty and fill in progressively. The main chart (Section 10) shows "price over time" for the selected ticker — but there is no historical price store or endpoint. Is the main chart also limited to data accumulated since page load (sparse right after launch), or do we need a price-history source? Recommend stating this explicitly.

2. **Baseline for the watchlist "daily change %".** The positions table "% change" is clearly vs `avg_cost`, but the watchlist's "daily change %" needs a reference price (session open / previous close). Nothing in the schema or simulator defines this baseline. Is it the price at container start, the first SSE tick, or a stored daily open? Recommend defining a per-ticker session-open reference.

3. **Seed price for newly added tickers.** When a user or the AI adds an arbitrary ticker (e.g. `PYPL`), the simulator has no seed price for it. How is a starting price chosen (random in a range, a small built-in lookup, fetched once)? And with `MASSIVE_API_KEY` set, how is an unknown/invalid ticker rejected? Recommend specifying ticker validation and seed-price behavior.

4. **Watchlist vs. priced tickers.** SSE pushes "all tickers known to the system." If a user removes a ticker from the watchlist but still holds a position in it, its price is still needed for P&L. Does the price cache track the union of (watchlist ∪ positions)? Recommend stating that an open position keeps a ticker "live" even when off the watchlist.

5. **No endpoint to load prior chat history.** `chat_messages` persists the conversation, but there is no `GET /api/chat` (or `/history`) endpoint. On page reload, how does the chat panel repopulate? Either add a history endpoint or state that the panel is intentionally ephemeral on the client.

6. **Bound on conversation history sent to the LLM.** Chat-flow step 2 loads "recent conversation history." Define a concrete limit (e.g. last N messages or a token budget) to keep prompt size and cost predictable.

7. **Structured outputs on the free model.** `openrouter/openai/gpt-oss-120b:free` may not reliably support `response_format` / JSON-schema structured outputs. Recommend confirming this early and, if unsupported, falling back to strict JSON-in-prompt plus tolerant parsing (the testing section already anticipates "malformed responses" — make that the primary path if schema mode is unavailable).

8. **SSE cadence vs. Massive poll interval.** SSE pushes at ~500ms, but the Massive free tier only refreshes every ~15s, so the stream would emit ~30 identical ticks per refresh. Should SSE emit only on actual price change? Recommend "emit on change" to avoid redundant traffic and spurious flash animations.

9. **Does the simulator run when markets are "closed"?** For a 24/7 demo the simulator presumably always moves — worth stating. Note that with real Massive data, prices are flat outside market hours, so the demo looks best on the simulator.

10. **"Reconnecting" vs "disconnected" indicator.** Native `EventSource` auto-retries and fires `onerror` for both transient and hard failures; it does not cleanly distinguish yellow (reconnecting) from red (disconnected). Recommend defining how the three states are derived, or simplifying to two (connected / not connected).

### Potential Gaps

11. **Position cleanup at zero quantity.** The E2E test says a sold-out position "updates or disappears." Make the rule explicit in Section 7: when `quantity` reaches 0, is the row deleted or kept at 0? (Deleting is cleaner for the heatmap and positions table.)

12. **Money as `REAL` (float).** Cash, prices, and P&L are floating point. Acceptable for a simulator, but define a display rounding convention (e.g. 2 decimals for currency) so totals don't show floating-point noise.

13. **SQLite concurrent writes.** A background snapshot task writes every 30s while request handlers also write (trades, watchlist, chat). Recommend enabling WAL mode and using short transactions to avoid "database is locked" errors.

### Resolutions (incorporated into the sections above)

1. Main chart draws from SSE-accumulated data since page load, same source as sparklines — Section 10.
2. "Daily change %" baseline is a per-session open price held in the price cache — Section 6 (Shared Price Cache).
3. Built-in seed table for defaults, random plausible seed for unknown tickers; minimal validation in sim mode, API-based rejection in Massive mode — Section 6 (Simulator).
4. Price cache tracks the union of watchlist and open positions — Section 6 (Shared Price Cache, SSE Streaming).
5. Added `GET /api/chat/history`; the chat panel repopulates on reload — Section 8, Section 10.
6. Conversation history bounded to the last 20 messages — Section 9 (How It Works, step 2).
7. Tolerant JSON parsing is the primary path with a plain-message fallback — Section 9 (Structured Output Schema).
8. SSE emits per ticker only on price change — Section 6 (SSE Streaming).
9. Simulator runs continuously regardless of market hours; Massive reflects real hours — Section 6 (Simulator).
10. Connection dot states derived from `EventSource.readyState` plus a recency timeout — Section 10 (Technical Notes).
11. A position row is deleted when quantity reaches 0 — Section 7 (positions).
12. Money kept as `REAL`, rounded to 2 dp (currency) / 4 dp (quantity) for display — Section 7 (Schema).
13. WAL mode + short transactions enabled on init — Section 7 (lazy initialization).



