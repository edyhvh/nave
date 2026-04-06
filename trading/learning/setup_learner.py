"""Setup learning with lightweight ML models for ranking and discovery."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from joblib import dump, load
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer

from trading.config import DEFAULT_SETUPS


@dataclass
class SetupScore:
    setup: str
    samples: int = 0
    pnl_total: float = 0.0

    @property
    def avg_pnl(self) -> float:
        return self.pnl_total / self.samples if self.samples else 0.0


class SetupLearner:
    """Learns setup quality from backtest trades and ranks setups by expected pnl."""

    def __init__(
        self,
        default_setups: Optional[list[str]] = None,
        n_estimators: int = 150,
        random_state: int = 42,
    ):
        self.default_setups = list(default_setups or DEFAULT_SETUPS)
        self.n_estimators = n_estimators
        self.random_state = random_state

        self._scores: dict[str, dict[str, SetupScore]] = defaultdict(dict)

        self._global_vectorizer: DictVectorizer | None = None
        self._global_model: RandomForestRegressor | None = None
        self._regime_vectorizers: dict[str, DictVectorizer] = {}
        self._regime_models: dict[str, RandomForestRegressor] = {}
        self._trained_samples = 0

    def fit(self, backtest_results: Any) -> None:
        """Fit setup ranking model from a BacktestResult-like object."""
        trades = getattr(backtest_results, "trades", []) or []
        if not trades:
            return

        features: list[dict[str, Any]] = []
        labels: list[float] = []
        regime_rows: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)

        for trade in trades:
            metadata = getattr(trade, "metadata", {}) or {}
            if not isinstance(metadata, dict):
                continue

            setup = self._resolve_setup(metadata)
            regime = self._resolve_regime(metadata)
            pnl = float(getattr(trade, "pnl", 0.0) or 0.0)

            self._record_score(setup=setup, regime=regime, pnl=pnl)

            row = self._build_features(metadata=metadata, setup=setup, regime=regime)
            features.append(row)
            labels.append(pnl)
            regime_rows[regime].append((row, pnl))

        if len(features) < 5:
            return

        self._global_vectorizer = DictVectorizer(sparse=False)
        x_global = self._global_vectorizer.fit_transform(features)
        self._global_model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            min_samples_leaf=2,
        )
        self._global_model.fit(x_global, labels)
        self._trained_samples = len(features)

        self._regime_models = {}
        self._regime_vectorizers = {}
        for regime, rows in regime_rows.items():
            if len(rows) < 4:
                continue
            regime_features = [row for row, _ in rows]
            regime_labels = [pnl for _, pnl in rows]
            regime_vectorizer = DictVectorizer(sparse=False)
            x_regime = regime_vectorizer.fit_transform(regime_features)
            regime_model = RandomForestRegressor(
                n_estimators=max(64, self.n_estimators // 2),
                random_state=self.random_state,
                min_samples_leaf=1,
            )
            regime_model.fit(x_regime, regime_labels)
            self._regime_vectorizers[regime] = regime_vectorizer
            self._regime_models[regime] = regime_model

    def rank_setups(
        self,
        setups: list[str],
        regime: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        """Rank setups by learned expected pnl; fall back to score averages."""
        ordered = list(setups)
        if not ordered:
            return []

        regime_key = regime or "all"
        predictions: dict[str, float] = {}

        for setup in ordered:
            row = self._build_features(
                metadata=context or {},
                setup=setup,
                regime=regime_key,
            )
            predicted = self._predict_row(row=row, regime=regime_key)
            if predicted is not None:
                predictions[setup] = predicted
                continue

            score = self._scores.get(regime_key, {}).get(setup)
            if score is not None:
                predictions[setup] = score.avg_pnl
            else:
                predictions[setup] = float("-inf")

        indexed = {name: idx for idx, name in enumerate(ordered)}
        return sorted(
            ordered,
            key=lambda name: (-predictions.get(name, float("-inf")), indexed[name]),
        )

    def discover_new_patterns(
        self,
        backtest_results: Any,
        min_cluster_size: int = 4,
    ) -> list[dict[str, Any]]:
        """Discover promising setup patterns via clustering and anomaly filtering."""
        trades = getattr(backtest_results, "trades", []) or []
        rows: list[dict[str, Any]] = []
        pnls: list[float] = []

        for trade in trades:
            metadata = getattr(trade, "metadata", {}) or {}
            if not isinstance(metadata, dict):
                continue
            setup = self._resolve_setup(metadata)
            regime = self._resolve_regime(metadata)
            rows.append(self._build_features(metadata=metadata, setup=setup, regime=regime))
            pnls.append(float(getattr(trade, "pnl", 0.0) or 0.0))

        if len(rows) < max(6, min_cluster_size):
            return []

        vectorizer = DictVectorizer(sparse=False)
        x = vectorizer.fit_transform(rows)
        unique_points = max(1, len(np.unique(x, axis=0)))
        n_clusters = max(2, min(5, len(rows) // max(2, min_cluster_size), unique_points))
        if unique_points < 2:
            return []

        kmeans = KMeans(n_clusters=n_clusters, random_state=self.random_state, n_init=10)
        labels = kmeans.fit_predict(x)

        detector = IsolationForest(
            contamination=min(0.2, 2.0 / max(len(rows), 10)),
            random_state=self.random_state,
        )
        anomaly_flags = detector.fit_predict(x)

        results: list[dict[str, Any]] = []
        for cluster_id in range(n_clusters):
            idx = [i for i, label in enumerate(labels) if label == cluster_id]
            if len(idx) < min_cluster_size:
                continue

            cluster_rows = [rows[i] for i in idx]
            cluster_pnls = [pnls[i] for i in idx]
            setups = [str(cluster_rows[i]["setup_type"]) for i in range(len(cluster_rows))]
            dominant_setup, dominant_share = self._dominant_setup(setups)
            avg_pnl = float(np.mean(cluster_pnls))
            win_rate = float(np.mean([1.0 if pnl > 0 else 0.0 for pnl in cluster_pnls]))
            anomaly_ratio = float(
                np.mean([1.0 if anomaly_flags[i] == -1 else 0.0 for i in idx])
            )

            is_promising = avg_pnl > 0 and win_rate >= 0.5
            differs_from_known = dominant_share < 0.6
            if not (is_promising and differs_from_known):
                continue

            results.append(
                {
                    "cluster_id": cluster_id,
                    "samples": len(idx),
                    "avg_pnl": round(avg_pnl, 4),
                    "win_rate": round(win_rate, 4),
                    "dominant_setup": dominant_setup,
                    "dominant_setup_share": round(dominant_share, 4),
                    "avg_anomaly_ratio": round(anomaly_ratio, 4),
                    "regime_distribution": self._regime_distribution(cluster_rows),
                    "interpretation": (
                        "Promising variant setup cluster with non-dominant known setup mix"
                    ),
                }
            )

        return sorted(results, key=lambda x: (x["avg_pnl"], x["win_rate"]), reverse=True)

    def save_model(self, path: str | Path) -> Path:
        """Persist model artifacts with joblib."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "default_setups": self.default_setups,
            "n_estimators": self.n_estimators,
            "random_state": self.random_state,
            "scores": self._scores,
            "global_vectorizer": self._global_vectorizer,
            "global_model": self._global_model,
            "regime_vectorizers": self._regime_vectorizers,
            "regime_models": self._regime_models,
            "trained_samples": self._trained_samples,
        }
        dump(payload, target)
        return target

    def load_model(self, path: str | Path) -> bool:
        """Load model artifacts if available."""
        source = Path(path)
        if not source.exists():
            return False
        payload = load(source)
        self.default_setups = list(payload.get("default_setups", self.default_setups))
        self.n_estimators = int(payload.get("n_estimators", self.n_estimators))
        self.random_state = int(payload.get("random_state", self.random_state))
        self._scores = payload.get("scores", defaultdict(dict))
        self._global_vectorizer = payload.get("global_vectorizer")
        self._global_model = payload.get("global_model")
        self._regime_vectorizers = payload.get("regime_vectorizers", {})
        self._regime_models = payload.get("regime_models", {})
        self._trained_samples = int(payload.get("trained_samples", 0))
        return True

    def has_model(self) -> bool:
        """Return True if at least one ML model is trained/loaded."""
        return self._global_model is not None and self._global_vectorizer is not None

    def top_setups(
        self,
        regime: str = "all",
        setups: Optional[list[str]] = None,
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        """Return top ranked setups with predicted scores."""
        candidates = list(setups or self.default_setups)
        ranked = self.rank_setups(candidates, regime=regime)
        output: list[dict[str, Any]] = []
        for name in ranked[:top_n]:
            row = self._build_features(metadata={}, setup=name, regime=regime)
            predicted = self._predict_row(row=row, regime=regime)
            score = self._scores.get(regime, {}).get(name)
            output.append(
                {
                    "setup": name,
                    "predicted_pnl": round(predicted or 0.0, 4),
                    "samples": score.samples if score else 0,
                    "avg_pnl": round(score.avg_pnl, 4) if score else 0.0,
                }
            )
        return output

    def generate_report(
        self,
        regime: str = "all",
        setups: Optional[list[str]] = None,
        patterns: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Build a plain-text report for console output."""
        top = self.top_setups(regime=regime, setups=setups, top_n=5)
        lines = []
        lines.append("SETUP LEARNING REPORT")
        lines.append("=" * 40)
        lines.append(f"Regime: {regime}")
        lines.append(f"Trained samples: {self._trained_samples}")
        lines.append("")
        lines.append("Top Learned Setups:")
        if not top:
            lines.append("  (no learned setup ranking yet)")
        for idx, item in enumerate(top, start=1):
            lines.append(
                f"  {idx}. {item['setup']} | predicted_pnl={item['predicted_pnl']:.4f} "
                f"| avg_pnl={item['avg_pnl']:.4f} | samples={item['samples']}"
            )
        lines.append("")
        lines.append("New Patterns Detected:")
        if not patterns:
            lines.append("  (none)")
        else:
            for pattern in patterns[:5]:
                lines.append(
                    f"  - cluster={pattern['cluster_id']} samples={pattern['samples']} "
                    f"avg_pnl={pattern['avg_pnl']:.4f} win_rate={pattern['win_rate']:.2%} "
                    f"dominant={pattern['dominant_setup']}"
                )
        return "\n".join(lines)

    def _resolve_setup(self, metadata: dict[str, Any]) -> str:
        setup = metadata.get("setup")
        if isinstance(setup, str) and setup:
            return setup
        setups = metadata.get("setups")
        if isinstance(setups, list) and setups:
            return str(setups[0])
        return "unknown"

    def _resolve_regime(self, metadata: dict[str, Any]) -> str:
        regime = (
            metadata.get("market_regime")
            or metadata.get("regime")
            or metadata.get("market_state")
        )
        if isinstance(regime, str) and regime:
            return regime

        volatility = float(metadata.get("volatility", 0.0) or 0.0)
        momentum = float(metadata.get("momentum", 0.0) or 0.0)
        if volatility >= 0.03:
            return "high_vol"
        if momentum >= 0.0:
            return "bull"
        return "bear"

    def _build_features(self, metadata: dict[str, Any], setup: str, regime: str) -> dict[str, Any]:
        bias_strength = metadata.get("cot_bias_strength", metadata.get("bias_strength", "medium"))
        if isinstance(bias_strength, str):
            bias_strength = {"weak": 0.25, "medium": 0.6, "strong": 1.0}.get(
                bias_strength, 0.6
            )

        momentum = float(metadata.get("momentum", metadata.get("weekly_change", 0.0)) or 0.0)
        oi_level = float(metadata.get("oi_level", metadata.get("pct_oi", 0.0)) or 0.0)
        volatility = float(metadata.get("volatility", 0.0) or 0.0)
        score = float(
            metadata.get("fits_weighted_score", metadata.get("bias_score_100", 50.0)) or 50.0
        )
        confidence = float(metadata.get("confidence", 0.5) or 0.5)

        return {
            "setup_type": setup,
            "market_regime": regime,
            "cot_bias_strength": float(bias_strength),
            "momentum": momentum,
            "oi_level": oi_level,
            "volatility": volatility,
            "fits_score": score,
            "confidence": confidence,
        }

    def _record_score(self, setup: str, regime: str, pnl: float) -> None:
        for regime_key in {regime, "all"}:
            bucket = self._scores[regime_key]
            if setup not in bucket:
                bucket[setup] = SetupScore(setup=setup)
            bucket[setup].samples += 1
            bucket[setup].pnl_total += pnl

    def _predict_row(self, row: dict[str, Any], regime: str) -> float | None:
        if regime in self._regime_models and regime in self._regime_vectorizers:
            vec = self._regime_vectorizers[regime]
            model = self._regime_models[regime]
            return float(model.predict(vec.transform([row]))[0])

        if self._global_model is None or self._global_vectorizer is None:
            return None
        return float(self._global_model.predict(self._global_vectorizer.transform([row]))[0])

    def _dominant_setup(self, setups: list[str]) -> tuple[str, float]:
        counts: dict[str, int] = defaultdict(int)
        for setup in setups:
            counts[setup] += 1
        if not counts:
            return ("unknown", 0.0)
        dominant_setup = max(counts, key=counts.get)
        return dominant_setup, counts[dominant_setup] / len(setups)

    def _regime_distribution(self, cluster_rows: list[dict[str, Any]]) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        for row in cluster_rows:
            counts[str(row.get("market_regime", "unknown"))] += 1
        total = len(cluster_rows) or 1
        return {k: round(v / total, 4) for k, v in counts.items()}
