# Trade Journal System

A comprehensive trade journaling system for tracking all trades across backtest, paper, and live environments.

## Features

- **Multi-environment support**: Track trades in backtest, paper, and live environments
- **Complete trade lifecycle**: Record entries, exits, position updates, and fees
- **Post-trade reviews**: Add quality ratings and lessons learned
- **Performance analytics**: Win rate, profit factor, P&L, and more
- **Multiple storage backends**: SQLite (default) and JSON storage

## Quick Start

```python
from trading.journal import TradeJournal, TradeEnvironment

# Initialize journal
journal = TradeJournal()

# Record a trade entry
trade = journal.record_entry(
    coin="BTC",
    direction="long",
    entry_price=65000,
    size_usd=1000,
    environment=TradeEnvironment.PAPER,
    leverage=5,
    stop_loss=62000,
    take_profit=70000,
    entry_signals={"cot_bias": "bullish", "rsi": 30},
    tags=["reversal", "cot_aligned"],
)

# Record position updates (periodic snapshots)
journal.record_position_update(
    trade_id=trade.id,
    current_price=67000,
    funding_paid=5.50,
)

# Record exit
journal.record_exit(
    trade_id=trade.id,
    exit_price=70000,
    exit_signals={"rsi": 70, "target_reached": True},
)

# Add a review
journal.add_review(
    trade_id=trade.id,
    setup_quality=9,
    entry_quality=8,
    exit_quality=7,
    what_went_well="Perfect entry on COT alignment",
    what_went_wrong="Could have held longer",
    lessons_learned="Trust the COT bias on weekly setups",
)

# Get performance stats
stats = journal.get_stats(environment=TradeEnvironment.PAPER)
print(f"Win rate: {stats['win_rate']:.1%}")
print(f"Total P&L: ${stats['total_pnl']:,.2f}")

# Generate a report
print(journal.generate_report(environment=TradeEnvironment.PAPER))
```

## Data Models

### Trade

Core trade record tracking all essential information:

```python
from trading.journal import Trade, TradeStatus, TradeEnvironment

trade = Trade(
    id="abc123",              # Auto-generated if not provided
    coin="BTC",
    direction="long",         # "long" or "short"
    entry_price=65000,
    size_usd=1000,
    leverage=5,
    entry_time=datetime.now(),
    status=TradeStatus.OPEN,
    environment=TradeEnvironment.PAPER,

    # Risk management
    stop_loss=62000,
    take_profit=70000,

    # Context
    entry_signals={"cot_bias": "bullish"},
    tags=["reversal"],
    notes="COT-confirmed setup",
)
```

### PositionUpdate

Periodic snapshots of position state:

```python
from trading.journal import PositionUpdate

update = PositionUpdate(
    trade_id="abc123",
    timestamp=datetime.now(),
    current_price=67000,
    unrealized_pnl=400,
    funding_paid=5.50,
    margin_used=200,
    liquidation_price=55000,
)
```

### TradeReview

Post-trade analysis and lessons:

```python
from trading.journal import TradeReview

review = TradeReview(
    trade_id="abc123",
    setup_quality=8,         # 1-10 rating
    entry_quality=7,
    exit_quality=6,
    risk_management=8,
    what_went_well="Good position sizing",
    what_went_wrong="Exited too early",
    lessons_learned="Let winners run to target",
    would_take_again=True,
)
```

## Storage Backends

### SQLite (Recommended)

Default backend, good for production use:

```python
from trading.journal import TradeJournal
from trading.journal.storage import SQLiteStorage

storage = SQLiteStorage(db_path="~/.nave/trades.db")
journal = TradeJournal(storage=storage)
```

### GitHub Data Repo (Backup/Sync)

For persistent backup without per-trade PRs, use a dedicated GitHub data repo with automated JSON exports:

```python
from trading.journal import TradeJournal

journal = TradeJournal.with_github_sync_from_env(auto_github_sync=True)

# Any entry/exit/review updates sync automatically when enabled.
trade = journal.record_entry("BTC", "long", 65000, 1000)
journal.record_exit(trade.id, 68000)

# You can also force sync manually:
journal.sync_to_github(trade_id=trade.id)
```

Configure a private repo (e.g. nave-trades-data) and set:

```bash
export NAVE_GITHUB_DATA_REPO_OWNER="your-github-user-or-org"
export NAVE_GITHUB_DATA_REPO_NAME="nave-trades-data"
export NAVE_GITHUB_TOKEN="ghp_xxx"
export NAVE_GITHUB_DATA_REPO_BRANCH="main"          # optional
export NAVE_GITHUB_DATA_BASE_PATH="trade_journal"   # optional
export NAVE_GITHUB_AUTO_SYNC="true"                 # optional
```

When auto-sync is enabled, journal events update files in your data repo:

- `trade_journal/trades/<trade_id>.json`
- `trade_journal/latest_snapshot.json`

### JSON

Simple file storage, good for development:

```python
from trading.journal.storage import JSONStorage

storage = JSONStorage(data_dir="~/.nave/trades")
journal = TradeJournal(storage=storage)
```

## Querying Trades

```python
# Get all open trades
open_trades = journal.get_open_trades()

# Get trades for a specific coin
btc_trades = journal.get_trade_history(coin="BTC")

# Get trades by environment
paper_trades = journal.get_trade_history(environment=TradeEnvironment.PAPER)

# Get trades in date range
from datetime import datetime, timedelta

recent = journal.get_trade_history(
    environment=TradeEnvironment.LIVE,
    start_date=datetime.now() - timedelta(days=30),
)
```

## Integration with Strategies

Add journaling to any strategy:

```python
from trading.crypto.strategy import BaseStrategy
from trading.journal import TradeJournal, TradeEnvironment
from trading.journal.integrations import StrategyJournalMixin

class COTStrategy(BaseStrategy, StrategyJournalMixin):
    def __init__(self, client, **kwargs):
        super().__init__(client, **kwargs)
        self.setup_journal(environment=TradeEnvironment.PAPER)

    def _open(self, coin, direction, size_usd):
        # Record in journal
        self.journal_entry(
            coin=coin,
            direction=direction.value,
            entry_price=self.get_current_price(coin),
            size_usd=size_usd,
            entry_signals=self.current_signals,
        )

        # Execute trade
        super()._open(coin, direction, size_usd)

    def _close(self, coin):
        # Record exit in journal
        self.journal_exit(coin, exit_price=self.get_current_price(coin))

        # Execute close
        super()._close(coin)
```

## Integration with Backtests

Record all backtest trades for analysis:

```python
from trading.journal.integrations import BacktestJournalMixin

class BacktestEngine(BacktestJournalMixin):
    def __init__(self):
        self.setup_journal()

    def run(self, strategy):
        # ... backtest logic ...

        # Record each trade
        for trade in trades:
            self.record_backtest_trade(trade)

        # Compare to live/paper performance
        comparison = self.compare_to_live()
        print(f"Backtest vs Live P&L diff: {comparison['comparison']['backtest_vs_live_pnl']}")
```

## Performance Metrics

The journal calculates key performance metrics:

| Metric                       | Description                  |
| ---------------------------- | ---------------------------- |
| `total_trades`               | Number of closed trades      |
| `wins` / `losses`            | Win/loss counts              |
| `win_rate`                   | Percentage of winning trades |
| `total_pnl`                  | Total profit/loss in USD     |
| `avg_pnl`                    | Average P&L per trade        |
| `avg_win` / `avg_loss`       | Average win/loss amounts     |
| `profit_factor`              | Gross wins / gross losses    |
| `avg_return_pct`             | Average return percentage    |
| `best_trade` / `worst_trade` | Best and worst trade P&L     |
| `avg_duration_hours`         | Average trade duration       |

## Export

Export trades for external analysis:

```python
# Export to CSV
journal.export_trades("trades.csv", environment=TradeEnvironment.PAPER, format="csv")

# Export to JSON
journal.export_trades("trades.json", environment=TradeEnvironment.PAPER, format="json")
```

## Database Schema

The SQLite database has three tables:

### trades

Main trade records with all trade data.

### position_updates

Periodic position snapshots for tracking P&L over time.

### trade_reviews

Post-trade analysis and lessons learned.

## Best Practices

1. **Always record entries**: Call `record_entry()` immediately when opening a position
2. **Track position updates**: Record regular snapshots for accurate P&L tracking
3. **Review your trades**: Add reviews to capture lessons learned
4. **Separate environments**: Use different environments for backtest, paper, and live
5. **Tag your trades**: Use tags to categorize and filter trades later
