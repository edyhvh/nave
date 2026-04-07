"""Manual trade journal sync to GitHub Wiki monthly pages."""

from __future__ import annotations

import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from .manual_trade import ManualTrade


class ManualTradeWikiSync:
    """Sync manual trades to repo wiki pages grouped by month."""

    def __init__(self, owner: str, repo: str, token: str):
        self.owner = owner
        self.repo = repo
        self.token = token

    def sync(self, trades: List[ManualTrade]) -> Dict[str, int]:
        if not trades:
            return {"synced": 0, "pages": 0}

        by_month: Dict[str, List[ManualTrade]] = defaultdict(list)
        for trade in trades:
            month = trade.date_created[:7]
            by_month[month].append(trade)

        with tempfile.TemporaryDirectory(prefix="nave-wiki-") as tmp:
            wiki_dir = Path(tmp) / "wiki"
            remote = f"https://x-access-token:{self.token}@github.com/{self.owner}/{self.repo}.wiki.git"
            clone = subprocess.run(
                ["git", "clone", remote, str(wiki_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if clone.returncode != 0:
                wiki_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run(["git", "init"], cwd=wiki_dir, check=True)
                subprocess.run(["git", "remote", "add", "origin",
                               remote], cwd=wiki_dir, check=True)

            changed_pages = 0
            synced = 0
            for month, rows in by_month.items():
                page_name = f"Journal-{month}"
                page_path = wiki_dir / f"{page_name}.md"
                content = page_path.read_text(
                    encoding="utf-8") if page_path.exists() else f"# Journal {month}\n\n"

                for trade in rows:
                    marker = f"<!-- trade:{trade.trade_id} -->"
                    if marker in content:
                        continue
                    content += self._format_trade_entry(trade)
                    synced += 1

                new_content = content.rstrip() + "\n"
                previous = page_path.read_text(
                    encoding="utf-8") if page_path.exists() else ""
                if new_content != previous:
                    page_path.write_text(new_content, encoding="utf-8")
                    changed_pages += 1

            if changed_pages == 0:
                return {"synced": 0, "pages": 0}

            subprocess.run(["git", "add", "."], cwd=wiki_dir, check=True)
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=wiki_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            if not status.stdout.strip():
                return {"synced": 0, "pages": 0}

            subprocess.run(
                ["git", "commit", "-m", "journal: sync manual trades"],
                cwd=wiki_dir,
                check=True,
            )
            subprocess.run(["git", "push", "origin", "master"],
                           cwd=wiki_dir, check=True)
            return {"synced": synced, "pages": changed_pages}

    @staticmethod
    def _format_trade_entry(trade: ManualTrade) -> str:
        tp1 = f"{trade.take_profit_price_1}" if trade.take_profit_price_1 is not None else "-"
        tp2 = f"{trade.take_profit_price_2}" if trade.take_profit_price_2 is not None else "-"
        tpf = f"{trade.take_profit_final_price}" if trade.take_profit_final_price is not None else "-"
        cot = "N/A"
        if trade.cot_insight:
            cot = (
                f"{trade.cot_insight.get('bias_label', trade.cot_insight.get('bias', 'unknown'))} "
                f"(conf {trade.cot_insight.get('confidence', 0):.2f})"
            )

        return (
            f"<!-- trade:{trade.trade_id} -->\n"
            f"## Trade {trade.trade_id}\n"
            f"- Created: {trade.date_created}\n"
            f"- Asset: {trade.asset}\n"
            f"- Platform: {trade.platform}\n"
            f"- Trading mode: {trade.trading_mode}\n"
            f"- Market type: {trade.market_type}\n"
            f"- Side: {trade.side}\n"
            f"- Entry: {trade.entry_price}\n"
            f"- Target: {trade.target_price}\n"
            f"- Stop loss: {trade.stop_loss_price}\n"
            f"- Fees: {trade.fees}\n"
            f"- Size: {trade.size}\n"
            f"- Leverage: {trade.leverage}\n"
            f"- TP1: {tp1}\n"
            f"- TP2: {tp2}\n"
            f"- Final TP: {tpf}\n"
            f"- Status: {trade.status}\n"
            f"- COT: {cot}\n"
            f"- Setup: {trade.setup or '-'}\n"
            f"- Notes: {trade.notes or '-'}\n\n"
        )
