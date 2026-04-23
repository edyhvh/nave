# ops — scheduling the daily scan

This directory holds templates and notes for running `scripts/daily_scan.py`
on a schedule. The scan itself writes to `var/reports/daily_scan_YYYY-MM-DD.json`;
the agent reads those reports via the `scan_history` tool.

## macOS (launchd) — preferred on dev machines

1. Copy `com.nave.daily-scan.plist.example` to
   `~/Library/LaunchAgents/com.nave.daily-scan.plist`.
2. Edit the file: replace every `{PROJECT_ROOT}` with the absolute path
   to this repo (e.g. `/Users/you/nave`) and `{PYTHON_BIN}` with the
   absolute path to the Python interpreter that has the project deps
   installed (e.g. `/Users/you/nave/.venv/bin/python`).
   - launchd does **not** expand `~`, `$HOME`, or shell variables — use
     absolute paths only.
3. Load it:

   ```
   launchctl load ~/Library/LaunchAgents/com.nave.daily-scan.plist
   ```

4. Confirm it registered:

   ```
   launchctl list | grep com.nave.daily-scan
   ```

5. Wait for the next 09:05 trigger, or force a run now:

   ```
   launchctl start com.nave.daily-scan
   ```

6. Reports land in `var/reports/`; logs in `var/logs/daily_scan.{out,err}.log`.

To uninstall: `launchctl unload ~/Library/LaunchAgents/com.nave.daily-scan.plist`.

## Linux (cron) — for servers

Add to the user's crontab (`crontab -e`):

```
5 9 * * * cd /path/to/nave && /path/to/nave/.venv/bin/python scripts/daily_scan.py --coins "BTC ETH" --format json >> var/logs/daily_scan.out.log 2>> var/logs/daily_scan.err.log
```

Then create the log directory: `mkdir -p /path/to/nave/var/logs`.

## systemd timer (alternative on Linux)

Not included here — use cron unless you already have a systemd-driven
deployment. If you need it, copy the cron command into a `.service` unit
and pair it with an `OnCalendar=*-*-* 09:05:00` `.timer` unit.

## What the agent does with the persisted reports

Each `daily_scan_YYYY-MM-DD.json` file contains:

```json
{
  "generated_at": "...",
  "coins_requested": "BTC ETH",
  "scan":    { ... full theory_v2_scan output ... },
  "context": { ... strategy_context snapshot ... },
  "persisted_to": "var/reports/daily_scan_YYYY-MM-DD.json"
}
```

The agent reads the last N days via `scan_history(days=N)`. Typical use:

- Compare today's stage/reason to yesterday's — is the regime persistent?
- Check whether extreme-COT blocks are 1-day blips or multi-week patterns.
- Report to the user when a stand-aside has been in effect for more than
  a week (possible mean-reversion setup upcoming).

## Do NOT put secrets in `ops/`

Wallet keys live in the encrypted vault (`WalletVault`). The plist and
cron entries should only contain file paths and schedule info.
