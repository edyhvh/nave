"""
Storage backends for trade journal.
Supports SQLite (default) and JSON file storage.
"""

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import threading

from .models import Trade, TradeEnvironment, TradeStatus, TradeOutcome, PositionUpdate, TradeReview


class StorageBackend(ABC):
    """Abstract base for storage backends."""

    @abstractmethod
    def save_trade(self, trade: Trade) -> None:
        """Save or update a trade."""
        pass

    @abstractmethod
    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get a trade by ID."""
        pass

    @abstractmethod
    def get_trades(
        self,
        environment: Optional[TradeEnvironment] = None,
        status: Optional[TradeStatus] = None,
        coin: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Trade]:
        """Query trades with filters."""
        pass

    @abstractmethod
    def save_position_update(self, update: PositionUpdate) -> None:
        """Save a position update."""
        pass

    @abstractmethod
    def get_position_updates(self, trade_id: str) -> List[PositionUpdate]:
        """Get all position updates for a trade."""
        pass

    @abstractmethod
    def save_review(self, review: TradeReview) -> None:
        """Save a trade review."""
        pass

    @abstractmethod
    def get_review(self, trade_id: str) -> Optional[TradeReview]:
        """Get review for a trade."""
        pass

    @abstractmethod
    def get_performance_stats(
        self,
        environment: Optional[TradeEnvironment] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get aggregate performance statistics."""
        pass


class SQLiteStorage(StorageBackend):
    """SQLite storage backend - recommended for production use."""

    def __init__(self, db_path: str = "~/.nave/trades.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                strategy_name TEXT,
                coin TEXT NOT NULL,
                direction TEXT NOT NULL,
                size_usd REAL NOT NULL,
                leverage REAL DEFAULT 1.0,
                entry_price REAL NOT NULL,
                exit_price REAL,
                entry_fee REAL DEFAULT 0.0,
                exit_fee REAL DEFAULT 0.0,
                funding_fees REAL DEFAULT 0.0,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                status TEXT NOT NULL,
                environment TEXT NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                entry_signals TEXT,
                exit_signals TEXT,
                tags TEXT,
                notes TEXT,
                pnl_absolute REAL,
                pnl_percent REAL,
                outcome TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Position updates table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS position_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                current_price REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                funding_paid REAL DEFAULT 0.0,
                margin_used REAL DEFAULT 0.0,
                liquidation_price REAL,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        """)

        # Reviews table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT NOT NULL UNIQUE,
                reviewed_at TEXT NOT NULL,
                setup_quality INTEGER,
                entry_quality INTEGER,
                exit_quality INTEGER,
                risk_management INTEGER,
                what_went_well TEXT,
                what_went_wrong TEXT,
                lessons_learned TEXT,
                would_take_again BOOLEAN,
                improvements TEXT,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        """)

        # Indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_env ON trades(environment)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_coin ON trades(coin)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(entry_time)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_updates_trade ON position_updates(trade_id)")

        conn.commit()

    def save_trade(self, trade: Trade) -> None:
        """Save or update a trade."""
        conn = self._get_conn()
        cursor = conn.cursor()

        data = {
            'id': trade.id,
            'strategy_name': trade.strategy_name,
            'coin': trade.coin,
            'direction': trade.direction,
            'size_usd': trade.size_usd,
            'leverage': trade.leverage,
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'entry_fee': trade.entry_fee,
            'exit_fee': trade.exit_fee,
            'funding_fees': trade.funding_fees,
            'entry_time': trade.entry_time.isoformat(),
            'exit_time': trade.exit_time.isoformat() if trade.exit_time else None,
            'status': trade.status.value,
            'environment': trade.environment.value,
            'stop_loss': trade.stop_loss,
            'take_profit': trade.take_profit,
            'entry_signals': json.dumps(trade.entry_signals),
            'exit_signals': json.dumps(trade.exit_signals),
            'tags': json.dumps(trade.tags),
            'notes': trade.notes,
            'pnl_absolute': trade.pnl_absolute,
            'pnl_percent': trade.pnl_percent,
            'outcome': trade.outcome.value,
        }

        cursor.execute("""
            INSERT OR REPLACE INTO trades 
            (id, strategy_name, coin, direction, size_usd, leverage, entry_price, exit_price,
             entry_fee, exit_fee, funding_fees, entry_time, exit_time, status, environment,
             stop_loss, take_profit, entry_signals, exit_signals, tags, notes,
             pnl_absolute, pnl_percent, outcome)
            VALUES 
            (:id, :strategy_name, :coin, :direction, :size_usd, :leverage, :entry_price, :exit_price,
             :entry_fee, :exit_fee, :funding_fees, :entry_time, :exit_time, :status, :environment,
             :stop_loss, :take_profit, :entry_signals, :exit_signals, :tags, :notes,
             :pnl_absolute, :pnl_percent, :outcome)
        """, data)

        conn.commit()

    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get a trade by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        row = cursor.fetchone()

        if row:
            return self._row_to_trade(row)
        return None

    def get_trades(
        self,
        environment: Optional[TradeEnvironment] = None,
        status: Optional[TradeStatus] = None,
        coin: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Trade]:
        """Query trades with filters."""
        conn = self._get_conn()
        cursor = conn.cursor()

        conditions = []
        params = []

        if environment:
            conditions.append("environment = ?")
            params.append(environment.value)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if coin:
            conditions.append("coin = ?")
            params.append(coin)
        if start_date:
            conditions.append("entry_time >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("entry_time <= ?")
            params.append(end_date.isoformat())

        query = "SELECT * FROM trades"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [self._row_to_trade(row) for row in cursor.fetchall()]

    def save_position_update(self, update: PositionUpdate) -> None:
        """Save a position update."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO position_updates 
            (trade_id, timestamp, current_price, unrealized_pnl, funding_paid, margin_used, liquidation_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            update.trade_id,
            update.timestamp.isoformat(),
            update.current_price,
            update.unrealized_pnl,
            update.funding_paid,
            update.margin_used,
            update.liquidation_price,
        ))

        conn.commit()

    def get_position_updates(self, trade_id: str) -> List[PositionUpdate]:
        """Get all position updates for a trade."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM position_updates 
            WHERE trade_id = ? 
            ORDER BY timestamp ASC
        """, (trade_id,))

        updates = []
        for row in cursor.fetchall():
            updates.append(PositionUpdate(
                trade_id=row['trade_id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                current_price=row['current_price'],
                unrealized_pnl=row['unrealized_pnl'],
                funding_paid=row['funding_paid'],
                margin_used=row['margin_used'],
                liquidation_price=row['liquidation_price'],
            ))
        return updates

    def save_review(self, review: TradeReview) -> None:
        """Save a trade review."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO trade_reviews
            (trade_id, reviewed_at, setup_quality, entry_quality, exit_quality, risk_management,
             what_went_well, what_went_wrong, lessons_learned, would_take_again, improvements)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            review.trade_id,
            review.reviewed_at.isoformat(),
            review.setup_quality,
            review.entry_quality,
            review.exit_quality,
            review.risk_management,
            review.what_went_well,
            review.what_went_wrong,
            review.lessons_learned,
            review.would_take_again,
            review.improvements,
        ))

        conn.commit()

    def get_review(self, trade_id: str) -> Optional[TradeReview]:
        """Get review for a trade."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM trade_reviews WHERE trade_id = ?", (trade_id,))
        row = cursor.fetchone()

        if row:
            return TradeReview(
                trade_id=row['trade_id'],
                reviewed_at=datetime.fromisoformat(row['reviewed_at']),
                setup_quality=row['setup_quality'],
                entry_quality=row['entry_quality'],
                exit_quality=row['exit_quality'],
                risk_management=row['risk_management'],
                what_went_well=row['what_went_well'] or "",
                what_went_wrong=row['what_went_wrong'] or "",
                lessons_learned=row['lessons_learned'] or "",
                would_take_again=bool(row['would_take_again']),
                improvements=row['improvements'] or "",
            )
        return None

    def get_performance_stats(
        self,
        environment: Optional[TradeEnvironment] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get aggregate performance statistics."""
        conn = self._get_conn()
        cursor = conn.cursor()

        conditions = ["status = 'closed'"]
        params = []

        if environment:
            conditions.append("environment = ?")
            params.append(environment.value)
        if start_date:
            conditions.append("entry_time >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("entry_time <= ?")
            params.append(end_date.isoformat())

        query = f"""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN outcome = 'breakeven' THEN 1 ELSE 0 END) as breakevens,
                SUM(pnl_absolute) as total_pnl,
                AVG(pnl_absolute) as avg_pnl,
                AVG(CASE WHEN outcome = 'win' THEN pnl_absolute END) as avg_win,
                AVG(CASE WHEN outcome = 'loss' THEN pnl_absolute END) as avg_loss,
                AVG(pnl_percent) as avg_return_pct,
                MAX(pnl_absolute) as best_trade,
                MIN(pnl_absolute) as worst_trade,
                AVG(CASE WHEN julianday(exit_time) - julianday(entry_time) > 0 
                    THEN (julianday(exit_time) - julianday(entry_time)) * 24 END) as avg_duration_hours
            FROM trades
            WHERE {' AND '.join(conditions)}
        """

        cursor.execute(query, params)
        row = cursor.fetchone()

        if not row or row['total_trades'] == 0:
            return {'total_trades': 0}

        total = row['total_trades']
        wins = row['wins'] or 0
        losses = row['losses'] or 0

        return {
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'breakevens': row['breakevens'] or 0,
            'win_rate': wins / total if total > 0 else 0,
            'total_pnl': row['total_pnl'] or 0,
            'avg_pnl': row['avg_pnl'] or 0,
            'avg_win': row['avg_win'] or 0,
            'avg_loss': row['avg_loss'] or 0,
            'profit_factor': abs((row['avg_win'] * wins) / (row['avg_loss'] * losses)) if losses > 0 and row['avg_loss'] else float('inf'),
            'avg_return_pct': row['avg_return_pct'] or 0,
            'best_trade': row['best_trade'] or 0,
            'worst_trade': row['worst_trade'] or 0,
            'avg_duration_hours': row['avg_duration_hours'] or 0,
        }

    def _row_to_trade(self, row: sqlite3.Row) -> Trade:
        """Convert database row to Trade object."""
        return Trade(
            id=row['id'],
            strategy_name=row['strategy_name'] or "",
            coin=row['coin'],
            direction=row['direction'],
            size_usd=row['size_usd'],
            leverage=row['leverage'],
            entry_price=row['entry_price'],
            exit_price=row['exit_price'],
            entry_fee=row['entry_fee'],
            exit_fee=row['exit_fee'],
            funding_fees=row['funding_fees'],
            entry_time=datetime.fromisoformat(row['entry_time']),
            exit_time=datetime.fromisoformat(
                row['exit_time']) if row['exit_time'] else None,
            status=TradeStatus(row['status']),
            environment=TradeEnvironment(row['environment']),
            stop_loss=row['stop_loss'],
            take_profit=row['take_profit'],
            entry_signals=json.loads(
                row['entry_signals']) if row['entry_signals'] else {},
            exit_signals=json.loads(
                row['exit_signals']) if row['exit_signals'] else {},
            tags=json.loads(row['tags']) if row['tags'] else [],
            notes=row['notes'] or "",
            pnl_absolute=row['pnl_absolute'],
            pnl_percent=row['pnl_percent'],
            outcome=TradeOutcome(
                row['outcome']) if row['outcome'] else TradeOutcome.UNKNOWN,
        )


class JSONStorage(StorageBackend):
    """Simple JSON file storage - good for development/testing."""

    def __init__(self, data_dir: str = "~/.nave/trades"):
        self.data_dir = Path(data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.trades_file = self.data_dir / "trades.jsonl"
        self._lock = threading.Lock()

    def save_trade(self, trade: Trade) -> None:
        """Save trade to JSONL file."""
        with self._lock:
            # Read existing trades
            trades = self._load_all_trades()
            # Update or add
            trades = [t for t in trades if t.id != trade.id]
            trades.append(trade)
            # Write back
            self._save_all_trades(trades)

    def get_trade(self, trade_id: str) -> Optional[Trade]:
        """Get trade by ID."""
        trades = self._load_all_trades()
        for trade in trades:
            if trade.id == trade_id:
                return trade
        return None

    def get_trades(
        self,
        environment: Optional[TradeEnvironment] = None,
        status: Optional[TradeStatus] = None,
        coin: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Trade]:
        """Query trades with filters."""
        trades = self._load_all_trades()

        if environment:
            trades = [t for t in trades if t.environment == environment]
        if status:
            trades = [t for t in trades if t.status == status]
        if coin:
            trades = [t for t in trades if t.coin == coin]
        if start_date:
            trades = [t for t in trades if t.entry_time >= start_date]
        if end_date:
            trades = [t for t in trades if t.entry_time <= end_date]

        trades.sort(key=lambda t: t.entry_time, reverse=True)
        return trades[:limit]

    def save_position_update(self, update: PositionUpdate) -> None:
        """Save position update to separate file."""
        file_path = self.data_dir / f"updates_{update.trade_id}.jsonl"
        with open(file_path, 'a') as f:
            f.write(json.dumps(update.to_dict()) + '\n')

    def get_position_updates(self, trade_id: str) -> List[PositionUpdate]:
        """Get position updates for a trade."""
        file_path = self.data_dir / f"updates_{trade_id}.jsonl"
        if not file_path.exists():
            return []

        updates = []
        with open(file_path, 'r') as f:
            for line in f:
                data = json.loads(line)
                updates.append(PositionUpdate(
                    trade_id=data['trade_id'],
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    current_price=data['current_price'],
                    unrealized_pnl=data['unrealized_pnl'],
                    funding_paid=data.get('funding_paid', 0),
                    margin_used=data.get('margin_used', 0),
                    liquidation_price=data.get('liquidation_price'),
                ))
        return updates

    def save_review(self, review: TradeReview) -> None:
        """Save review to separate file."""
        file_path = self.data_dir / f"review_{review.trade_id}.json"
        with open(file_path, 'w') as f:
            json.dump(review.to_dict(), f, indent=2, default=str)

    def get_review(self, trade_id: str) -> Optional[TradeReview]:
        """Get review for a trade."""
        file_path = self.data_dir / f"review_{trade_id}.json"
        if not file_path.exists():
            return None

        with open(file_path, 'r') as f:
            data = json.load(f)
            return TradeReview(**data)

    def get_performance_stats(
        self,
        environment: Optional[TradeEnvironment] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Calculate performance stats."""
        trades = self.get_trades(
            environment=environment,
            status=TradeStatus.CLOSED,
            start_date=start_date,
            end_date=end_date,
        )

        if not trades:
            return {'total_trades': 0}

        wins = [t for t in trades if t.outcome == TradeOutcome.WIN]
        losses = [t for t in trades if t.outcome == TradeOutcome.LOSS]
        wins_pnl = [t.pnl_absolute for t in wins if t.pnl_absolute is not None]
        losses_pnl = [
            t.pnl_absolute for t in losses if t.pnl_absolute is not None]

        total_pnl = sum(t.pnl_absolute for t in trades if t.pnl_absolute)

        return {
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'breakevens': len([t for t in trades if t.outcome == TradeOutcome.BREAKEVEN]),
            'win_rate': len(wins) / len(trades) if trades else 0,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / len(trades) if trades else 0,
            'avg_win': sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0,
            'avg_loss': sum(losses_pnl) / len(losses_pnl) if losses_pnl else 0,
            'best_trade': max(t.pnl_absolute for t in trades if t.pnl_absolute) if trades else 0,
            'worst_trade': min(t.pnl_absolute for t in trades if t.pnl_absolute) if trades else 0,
        }

    def _load_all_trades(self) -> List[Trade]:
        """Load all trades from file."""
        if not self.trades_file.exists():
            return []

        trades = []
        with open(self.trades_file, 'r') as f:
            for line in f:
                data = json.loads(line)
                trades.append(Trade.from_dict(data))
        return trades

    def _save_all_trades(self, trades: List[Trade]) -> None:
        """Save all trades to file."""
        with open(self.trades_file, 'w') as f:
            for trade in trades:
                f.write(json.dumps(trade.to_dict(), default=str) + '\n')
