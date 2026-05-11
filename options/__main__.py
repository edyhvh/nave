"""Module entrypoint for options analysis."""

from datetime import datetime, timezone

from options.analyzer import OptionsAnalyzer, _save_report


if __name__ == "__main__":
    analyzer = OptionsAnalyzer()
    report = analyzer.run(ticker="MSFT", days_to_exp=30)
    path = analyzer.config.reports_dir / (
        f"MSFT_options_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    _save_report(report, path)
