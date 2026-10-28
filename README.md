# CFB Lines

A live dashboard of college football lines across the major sportsbooks, built to make
mispricings easy to spot. It polls an odds feed, lines up every book's spread, total and
moneyline side by side, and ranks what's off:

| Type | What it means |
|---|---|
| **Arbitrage** | Best prices on opposite sides at two books add up to a guaranteed profit. Stake split shown. |
| **+EV** | A price beats the fair (no-vig) price at the same line by at least `EV_THRESHOLD`. Fair comes from a sharp book (Pinnacle, Circa, ...) when it quotes that line, otherwise the median of the other books. |
| **Off-market** | A book's spread/total sits ≥ 1 / 1.5 points from the most-quoted line. Notes when it crosses a key number (3, 7, 10, 14, ...). |
| **Middle** | Opposite sides at two books leave a window where both bets win. |
| **Stale** | Tag on any book that hasn't updated in `STALE_SECONDS` while others have. A stale book that's also off-market is usually the best spot on the board. |
| **Promo** | Best hedged use of each promo you've entered (see below). |

The lines board outlines the best available number on each side, shades +EV and off-market
cells, and flashes cells as they move. A line-move feed sits underneath.

## Bet sizing

Enter a **Bet size** at the top and every opportunity shows the stake for each leg and the
resulting profit, using the same total cash per play:

- **Arbitrage / Promo:** stakes are split so every outcome pays the same; profit shown is the
  guaranteed amount after rounding (and the upside if a middle also hits).
- **Middle:** equal-payout split; shows the win if the middle hits and the cost if it misses.
- **+EV:** the full amount on one leg; shows expected profit and the payout if it wins.

**Round stakes to** ($1 / $5 / $10) rounds each leg to amounts that look normal to a book;
the profit shown is recomputed on the rounded stakes.

## Promotions

No odds feed publishes promos in a usable form: they're personalized by account and state.
So you enter the ones in your accounts (Promotions panel, or `POST /api/promos`) and the app
finds the best hedge for each against the live lines, ranks the top 3 plays per promo, and
sizes both legs:

| Promo | How it's valued |
|---|---|
| **Bonus bet** | Stake isn't returned, so it's placed on a longshot and hedged with cash. Shows the % converted to cash. |
| **Profit boost** | Winnings multiplied by (1 + boost) up to the max stake, hedged at another book. |
| **No-sweat** | A losing bet is refunded as a bonus bet, valued at your expected conversion (70% default). |

Promos can be limited by minimum odds, market and expiry, and are saved to `promos.json`.
The unhedged EV is also shown when a fair price is available, in case you'd rather not hedge.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add ODDS_API_KEY; leave blank to run on demo data
uvicorn cfb_lines.app:app --port 8000
```

Open http://localhost:8000. With no API key it runs on a synthetic market so you can try the UI.

## Data source and how "real-time" it is

Live data comes from [The Odds API](https://the-odds-api.com), which aggregates
DraftKings, FanDuel, BetMGM, Caesars, ESPN BET, BetRivers, Fanatics, Hard Rock, Bovada,
BetOnline, LowVig, Pinnacle and others in a single call. Things to know:

- **Freshness.** The app pushes each poll to the browser instantly (server-sent events), so
  the floor is your `POLL_SECONDS` plus the feed's own refresh, which is roughly every
  30–60 seconds pre-game. That's fast enough for stale-line and off-market spots. For true
  sub-second line-moves (steam chasing, live betting) you'd want a push feed such as
  OpticOdds or SportsDataIO; add it as a provider (below) and nothing else changes.
- **Cost.** Each poll costs `region-units × markets` credits (the startup log prints the
  monthly estimate). Defaults: 2 regions × 3 markets = 6 credits/poll. At 60s that's ~260k
  credits/month if run around the clock, so either pick a plan to match or raise
  `POLL_SECONDS` / run it only on game days. Polling pauses itself when credits drop under
  `MIN_CREDITS_RESERVE`; the **Refresh now** button forces a poll.
- **Pinnacle** is the most useful sharp reference but lives in the `eu` region. Add it via
  `BOOKMAKERS=...,pinnacle` (cheaper) or `REGIONS=us,us2,eu`.

## API

| Endpoint | |
|---|---|
| `GET /api/snapshot` | Everything: games, every book's quotes, consensus/fair lines, opportunities, status |
| `GET /api/opportunities?type=arb,ev&min_edge=0.03` | Ranked opportunities only |
| `GET /api/stream` | Server-sent events; a full snapshot after every poll |
| `GET /api/games/{id}/history` | Recent price/line history per book and side |
| `POST /api/refresh` | Poll now |
| `GET/POST /api/promos`, `DELETE /api/promos/{id}` | Manage promos |

Set `HISTORY_DB` to log every line move to SQLite (`line_moves` table) for closing-line
value tracking or backtesting your thresholds.

## Layout

```
cfb_lines/
  providers/odds_api.py   The Odds API client -> normalized Game/Quote models
  providers/demo.py       Synthetic market for running without a key
  analysis.py             Fair prices, +EV, arbs, middles, off-market, stale and promo plays
  sizing.py               Stake split and profit for cash, bonus, boosted and no-sweat legs
  promos.py               Promo model and JSON store
  history.py              Line-move tracking (memory + optional SQLite)
  service.py              Poll loop, credit guard, fan-out to browsers
  app.py                  FastAPI routes
  static/index.html       Dashboard
```

To add another feed, implement `fetch() -> FetchResult` and `aclose()` (see
`providers/__init__.py`) and register it in `make_provider`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
