"""Setup learning with lightweight ML models for ranking, filtering, and sizing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from joblib import dump, load
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest, RandomForestClassifier, RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer

from trading.config import DEFAULT_SETUPS


@dataclass
class SetupScore:
    setup: str
    samples: int = 0
    pnl_total: float = 0.0
    wins: int = 0

    @property
    def avg_pnl(self) -> float:
        return self.pnl_total / self.samples if self.samples else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.samples if self.samples else 0.0


class SetupLearner:
    """Learns setup quality and action policies from backtest trade outcomes."""

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
        self._policy_stats: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
        self._bucket_stats: dict[tuple[str, str, str, str, str], dict[str, float]] = {}

        self._global_vectorizer: DictVectorizer | None = None
        self._global_model: RandomForestRegressor | None = None
        self._global_classifier: RandomForestClassifier | None = None
        self._regime_vectorizers: dict[str, DictVectorizer] = {}
        self._regime_models: dict[str, RandomForestRegressor] = {}
        self._regime_classifiers: dict[str, RandomForestClassifier] = {}
        self._trained_samples = 0

    def fit(self, backtest_results: Any) -> None:
        """Fit ranking + skip/sizing policy models from backtest trades."""
        trades = getattr(backtest_results, "trades", []) or []
        if not trades:
            return

        features: list[dict[str, Any]] = []
        pnl_labels: list[float] = []
        win_labels: list[int] = []
        regime_rows: dict[str, list[tuple[dict[str, Any], float, int]]] = defaultdict(list)

        policy_rollup: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {
            "samples": 0.0,
            "wins": 0.0,
            "pnl_total": 0.0,
            "confidence_sum": 0.0,
            "vol_sum": 0.0,
            "bias_sum": 0.0,
            "momentum_sum": 0.0,
        }))
        bucket_rollup: dict[tuple[str, str, str, str, str], dict[str, float]] = defaultdict(lambda: {
            "samples": 0.0,
            "wins": 0.0,
            "pnl_total": 0.0,
        })

        for trade in trades:
            metadata = getattr(trade, "metadata", {}) or {}
            if not isinstance(metadata, dict):
                continue

            setup = self._resolve_setup(metadata)
            regime = self._resolve_regime(metadata)
            pnl = float(getattr(trade, "pnl", 0.0) or 0.0)
            row = self._build_features(metadata=metadata, setup=setup, regime=regime)

            self._record_score(setup=setup, regime=regime, pnl=pnl)
            features.append(row)
            pnl_labels.append(pnl)
            win = 1 if pnl > 0 else 0
            win_labels.append(win)
            regime_rows[regime].append((row, pnl, win))

            summary = policy_rollup[regime][setup]
            summary["samples"] += 1
            summary["wins"] += win
            summary["pnl_total"] += pnl
            summary["confidence_sum"] += float(row["confidence"])
            summary["vol_sum"] += float(row["volatility"])
            summary["bias_sum"] += float(row["cot_bias_strength"])
            summary["momentum_sum"] += float(row["momentum"])

            bucket_key = (
                regime,
                setup,
                self._bias_bucket(float(row["cot_bias_strength"])),
                self._vol_bucket(float(row["volatility"])),
                self._momentum_bucket(float(row["momentum"])),
            )
            bucket_stats = bucket_rollup[bucket_key]
            bucket_stats["samples"] += 1
            bucket_stats["wins"] += win
            bucket_stats["pnl_total"] += pnl

        if len(features) < 5:
            return

        self._global_vectorizer = DictVectorizer(sparse=False)
        x_global = self._global_vectorizer.fit_transform(features)
        self._global_model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            min_samples_leaf=2,
        )
        self._global_model.fit(x_global, pnl_labels)

        self._global_classifier = RandomForestClassifier(
            n_estimators=max(64, self.n_estimators // 2),
            random_state=self.random_state,
            min_samples_leaf=2,
        )
        self._global_classifier.fit(x_global, win_labels)
        self._trained_samples = len(features)

        self._regime_models = {}
        self._regime_classifiers = {}
        self._regime_vectorizers = {}
        for regime, rows in regime_rows.items():
            if len(rows) < 6:
                continue
            regime_features = [row for row, _, _ in rows]
            regime_pnls = [pnl for _, pnl, _ in rows]
            regime_wins = [win for _, _, win in rows]
            regime_vectorizer = DictVectorizer(sparse=False)
            x_regime = regime_vectorizer.fit_transform(regime_features)

            regime_model = RandomForestRegressor(
                n_estimators=max(64, self.n_estimators // 2),
                random_state=self.random_state,
                min_samples_leaf=1,
            )
            regime_model.fit(x_regime, regime_pnls)

            regime_classifier = RandomForestClassifier(
                n_estimators=max(48, self.n_estimators // 3),
                random_state=self.random_state,
                min_samples_leaf=1,
            )
            regime_classifier.fit(x_regime, regime_wins)

            self._regime_vectorizers[regime] = regime_vectorizer
            self._regime_models[regime] = regime_model
            self._regime_classifiers[regime] = regime_classifier

        self._policy_stats = self._finalize_policy_stats(policy_rollup)
        self._bucket_stats = dict(bucket_rollup)

    def rank_setups(
        self,
        setups: list[str],
        regime: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        """Rank setups by expected edge; falls back to average realized pnl."""
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
            predictions[setup] = score.avg_pnl if score else float("-inf")

        indexed = {name: idx for idx, name in enumerate(ordered)}
        return sorted(
            ordered,
            key=lambda name: (-predictions.get(name, float("-inf")), indexed[name]),
        )

    def recommend_for_signal(
        self,
        metadata: dict[str, Any],
        base_confidence: float,
        setups: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Recommend setup usage, skip decision, size multiplier, and leverage multiplier."""
        context = dict(metadata or {})
        regime = self._resolve_regime(context)
        candidates = list(setups or context.get("setups") or self.default_setups)
        if not candidates:
            candidates = list(self.default_setups)

        ranked = self.rank_setups(candidates, regime=regime, context=context)
        evaluations: list[dict[str, Any]] = []
        for setup in ranked:
            eval_result = self.recommend_setup_action(
                setup=setup,
                regime=regime,
                context=context,
                base_confidence=base_confidence,
            )
            evaluations.append(eval_result)

        tradable = [r for r in evaluations if r["should_trade"]]
        chosen = tradable[0] if tradable else evaluations[0]
        return {
            **chosen,
            "ranked_setups": ranked,
            "evaluations": evaluations,
        }

    def recommend_setup_action(
        self,
        setup: str,
        regime: str,
        context: dict[str, Any],
        base_confidence: float,
    ) -> dict[str, Any]:
        """Return action policy for one setup in one context."""
        row = self._build_features(metadata=context, setup=setup, regime=regime)
        predicted_pnl = self._predict_row(row, regime)
        if predicted_pnl is None:
            predicted_pnl = self._lookup_avg_pnl(setup=setup, regime=regime)
        win_probability = self._predict_win_probability(row, regime)
        if win_probability is None:
            win_probability = self._lookup_win_rate(setup=setup, regime=regime)

        volatility = float(row["volatility"])
        bias_strength = float(row["cot_bias_strength"])
        momentum = float(row["momentum"])
        oi_level = float(row["oi_level"])

        confidence_term = float(np.clip(base_confidence, 0.0, 1.0))
        win_term = float(np.clip(win_probability, 0.0, 1.0))
        edge_score = float(np.clip(predicted_pnl / 90.0, -1.0, 1.0))
        regime_key = regime if regime in {"bull", "bear", "high_vol"} else "all"

        regime_thresholds = {
            "bull": {
                "weak_bias": 0.38,
                "weak_win": 0.42,
                "clear_negative": -34.0,
                "strong_negative": -48.0,
                "high_vol": 0.055,
                "vol_scale": 0.78,
                "quality_shift": 0.08,
                "size_cap": 2.20,
                "lev_cap": 1.95,
            },
            "bear": {
                "weak_bias": 0.45,
                "weak_win": 0.44,
                "clear_negative": -26.0,
                "strong_negative": -42.0,
                "high_vol": 0.042,
                "vol_scale": 1.12,
                "quality_shift": -0.03,
                "size_cap": 1.70,
                "lev_cap": 1.45,
            },
            "high_vol": {
                "weak_bias": 0.44,
                "weak_win": 0.43,
                "clear_negative": -24.0,
                "strong_negative": -36.0,
                "high_vol": 0.038,
                "vol_scale": 1.32,
                "quality_shift": -0.05,
                "size_cap": 1.55,
                "lev_cap": 1.35,
            },
            "all": {
                "weak_bias": 0.42,
                "weak_win": 0.45,
                "clear_negative": -22.0,
                "strong_negative": -38.0,
                "high_vol": 0.04,
                "vol_scale": 1.0,
                "quality_shift": 0.0,
                "size_cap": 1.75,
                "lev_cap": 1.60,
            },
        }[regime_key]

        weak_bias = bias_strength < float(regime_thresholds["weak_bias"])
        high_vol = volatility >= float(regime_thresholds["high_vol"])
        weak_win_prob = win_term < float(regime_thresholds["weak_win"])
        clearly_negative_edge = predicted_pnl < float(regime_thresholds["clear_negative"])
        strong_negative_edge = predicted_pnl < float(regime_thresholds["strong_negative"])
        extreme_oi = abs(oi_level) >= 26.0

        should_trade = True
        reasons: list[str] = []
        if strong_negative_edge and weak_win_prob and (weak_bias or high_vol):
            should_trade = False
            reasons.append(f"strong negative {regime_key} edge with weak bias/odds")
        elif clearly_negative_edge and weak_win_prob and weak_bias and high_vol:
            should_trade = False
            reasons.append(f"clear negative {regime_key} edge in weak-bias/high-volatility context")

        vol_penalty = float(
            np.clip((volatility - 0.028) * 6.5, 0.0, 0.34) * float(regime_thresholds["vol_scale"])
        )
        momentum_signal = float(np.clip(momentum / 2500.0, -0.45, 0.50))
        if regime_key == "bull":
            momentum_bonus = (0.26 * max(momentum_signal, 0.0)) - (0.08 * max(-momentum_signal, 0.0))
        elif regime_key == "bear":
            momentum_bonus = (0.10 * max(momentum_signal, 0.0)) - (0.23 * max(-momentum_signal, 0.0))
        elif regime_key == "high_vol":
            momentum_bonus = (0.12 * max(momentum_signal, 0.0)) - (0.16 * max(-momentum_signal, 0.0))
        else:
            momentum_bonus = (0.14 * max(momentum_signal, 0.0)) - (0.11 * max(-momentum_signal, 0.0))
        oi_penalty = 0.06 if (extreme_oi and predicted_pnl < 0) else 0.0
        quality = (
            0.45 * win_term
            + 0.35 * confidence_term
            + 0.20 * float(np.clip(bias_strength, 0.0, 1.0))
        )
        quality += float(regime_thresholds["quality_shift"])
        quality = float(np.clip(quality, 0.0, 1.0))

        edge_strength = max(edge_score, 0.0)
        if predicted_pnl >= 35 and win_term >= 0.55:
            if regime_key == "bull":
                size_floor, lev_floor = 1.30, 1.25
            elif regime_key == "bear":
                size_floor, lev_floor = 1.04, 1.00
            elif regime_key == "high_vol":
                size_floor, lev_floor = 0.96, 0.92
            else:
                size_floor, lev_floor = 1.15, 1.10
        elif predicted_pnl >= 12 and win_term >= 0.50:
            if regime_key == "bull":
                size_floor, lev_floor = 1.05, 1.00
            elif regime_key == "bear":
                size_floor, lev_floor = 0.86, 0.84
            elif regime_key == "high_vol":
                size_floor, lev_floor = 0.78, 0.75
            else:
                size_floor, lev_floor = 0.95, 0.95
        elif predicted_pnl >= 0:
            if regime_key == "bull":
                size_floor, lev_floor = 0.82, 0.78
            elif regime_key == "bear":
                size_floor, lev_floor = 0.72, 0.70
            elif regime_key == "high_vol":
                size_floor, lev_floor = 0.66, 0.62
            else:
                size_floor, lev_floor = 0.78, 0.75
        else:
            size_floor, lev_floor = 0.56, 0.56

        size_multiplier = float(np.clip(
            size_floor
            + (0.58 * quality)
            + (0.22 * edge_strength)
            + momentum_bonus
            - vol_penalty
            - oi_penalty,
            size_floor,
            float(regime_thresholds["size_cap"]),
        ))
        leverage_multiplier = float(np.clip(
            lev_floor
            + (0.52 * quality)
            + (0.30 * edge_strength)
            + (0.42 * momentum_bonus)
            - (vol_penalty * 1.05),
            lev_floor,
            float(regime_thresholds["lev_cap"]),
        ))

        if (
            should_trade
            and regime_key == "bull"
            and predicted_pnl >= 30
            and win_term >= 0.56
            and momentum_signal > 0.08
        ):
            size_multiplier = min(float(regime_thresholds["size_cap"]), size_multiplier + 0.30)
            leverage_multiplier = min(float(regime_thresholds["lev_cap"]), leverage_multiplier + 0.25)
        elif (
            should_trade
            and regime_key == "high_vol"
            and predicted_pnl >= 26
            and win_term >= 0.55
            and momentum_signal > 0.10
            and volatility <= 0.035
        ):
            size_multiplier = min(float(regime_thresholds["size_cap"]), size_multiplier + 0.16)
            leverage_multiplier = min(float(regime_thresholds["lev_cap"]), leverage_multiplier + 0.14)

        if should_trade and predicted_pnl < 0:
            size_multiplier = max(0.55, min(size_multiplier, 0.88))
            leverage_multiplier = max(0.55, min(leverage_multiplier, 0.82))

        if not should_trade:
            size_multiplier = 0.0
            leverage_multiplier = 0.0
            reason = "; ".join(reasons) if reasons else "policy rule triggered"
        else:
            momentum_text = "supportive" if momentum >= 0 else "adverse"
            reason = (
                f"expected_pnl={predicted_pnl:.2f}, win_prob={win_probability:.2%}, "
                f"regime={regime}, bias={bias_strength:.2f}, oi={oi_level:.1f}, "
                f"momentum={momentum_text}, volatility={volatility:.3f}"
            )

        return {
            "setup": setup,
            "regime": regime,
            "should_trade": should_trade,
            "reason": reason,
            "predicted_pnl": float(predicted_pnl),
            "win_probability": float(win_probability),
            "size_multiplier": size_multiplier,
            "leverage_multiplier": leverage_multiplier,
            "edge_label": self._edge_label(predicted_pnl),
        }

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
            "policy_stats": self._policy_stats,
            "bucket_stats": self._bucket_stats,
            "global_vectorizer": self._global_vectorizer,
            "global_model": self._global_model,
            "global_classifier": self._global_classifier,
            "regime_vectorizers": self._regime_vectorizers,
            "regime_models": self._regime_models,
            "regime_classifiers": self._regime_classifiers,
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
        self._policy_stats = payload.get("policy_stats", defaultdict(dict))
        self._bucket_stats = payload.get("bucket_stats", {})
        self._global_vectorizer = payload.get("global_vectorizer")
        self._global_model = payload.get("global_model")
        self._global_classifier = payload.get("global_classifier")
        self._regime_vectorizers = payload.get("regime_vectorizers", {})
        self._regime_models = payload.get("regime_models", {})
        self._regime_classifiers = payload.get("regime_classifiers", {})
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
        """Return top ranked setups with predicted scores and action policy hints."""
        candidates = list(setups or self.default_setups)
        ranked = self.rank_setups(candidates, regime=regime)
        output: list[dict[str, Any]] = []
        for name in ranked[:top_n]:
            row = self._build_features(metadata={}, setup=name, regime=regime)
            predicted = self._predict_row(row=row, regime=regime)
            win_probability = self._predict_win_probability(row=row, regime=regime)
            score = self._scores.get(regime, {}).get(name)
            policy = self.recommend_setup_action(
                setup=name,
                regime=regime,
                context={},
                base_confidence=0.65,
            )
            output.append(
                {
                    "setup": name,
                    "predicted_pnl": round(predicted or 0.0, 4),
                    "win_probability": round(win_probability or 0.5, 4),
                    "samples": score.samples if score else 0,
                    "avg_pnl": round(score.avg_pnl, 4) if score else 0.0,
                    "recommended_size_multiplier": round(policy["size_multiplier"], 3),
                    "recommended_leverage_multiplier": round(policy["leverage_multiplier"], 3),
                    "suggested_leverage_x": round(min(10.0, max(0.0, 10.0 * policy["leverage_multiplier"])), 2),
                    "edge_label": policy["edge_label"],
                    "action": "use" if policy["should_trade"] else "skip",
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
        lines.append("Top Learned Setups (what to use):")
        if not top:
            lines.append("  (no learned setup ranking yet)")
        for idx, item in enumerate(top, start=1):
            lines.append(
                f"  {idx}. {item['setup']} | action={item['action']} "
                f"| predicted_pnl={item['predicted_pnl']:.4f} "
                f"| win_prob={item['win_probability']:.2%} "
                f"| size_mult={item['recommended_size_multiplier']:.2f} "
                f"| lev_mult={item['recommended_leverage_multiplier']:.2f} "
                f"| lev_x≈{item['suggested_leverage_x']:.2f} "
                f"| expected_edge={item['edge_label']} "
                f"| avg_pnl={item['avg_pnl']:.4f} | samples={item['samples']}"
            )
        lines.append("")
        lines.append("Policy Rules (when to use / skip):")
        policy_lines = self._policy_rule_lines(regime=regime, setups=setups)
        if not policy_lines:
            lines.append("  (insufficient samples for detailed policy rules)")
        else:
            lines.extend(policy_lines[:8])
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
            if pnl > 0:
                bucket[setup].wins += 1

    def _predict_row(self, row: dict[str, Any], regime: str) -> float | None:
        if regime in self._regime_models and regime in self._regime_vectorizers:
            vec = self._regime_vectorizers[regime]
            model = self._regime_models[regime]
            return float(model.predict(vec.transform([row]))[0])

        if self._global_model is None or self._global_vectorizer is None:
            return None
        return float(self._global_model.predict(self._global_vectorizer.transform([row]))[0])

    def _predict_win_probability(self, row: dict[str, Any], regime: str) -> float | None:
        if regime in self._regime_classifiers and regime in self._regime_vectorizers:
            clf = self._regime_classifiers[regime]
            vec = self._regime_vectorizers[regime]
            proba = clf.predict_proba(vec.transform([row]))[0]
            if len(proba) == 1:
                return float(proba[0])
            return float(proba[1])

        if self._global_classifier is None or self._global_vectorizer is None:
            return None
        proba = self._global_classifier.predict_proba(self._global_vectorizer.transform([row]))[0]
        if len(proba) == 1:
            return float(proba[0])
        return float(proba[1])

    def _lookup_avg_pnl(self, setup: str, regime: str) -> float:
        score = self._scores.get(regime, {}).get(setup) or self._scores.get("all", {}).get(setup)
        return score.avg_pnl if score else 0.0

    def _lookup_win_rate(self, setup: str, regime: str) -> float:
        score = self._scores.get(regime, {}).get(setup) or self._scores.get("all", {}).get(setup)
        return score.win_rate if score else 0.5

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

    def _bias_bucket(self, bias_strength: float) -> str:
        if bias_strength >= 0.8:
            return "strong"
        if bias_strength >= 0.5:
            return "medium"
        return "weak"

    def _vol_bucket(self, volatility: float) -> str:
        if volatility >= 0.04:
            return "high"
        if volatility >= 0.025:
            return "medium"
        return "low"

    def _momentum_bucket(self, momentum: float) -> str:
        if momentum >= 500:
            return "up"
        if momentum <= -500:
            return "down"
        return "flat"

    def _finalize_policy_stats(
        self,
        policy_rollup: dict[str, dict[str, dict[str, float]]],
    ) -> dict[str, dict[str, dict[str, float]]]:
        out: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
        combined: dict[str, dict[str, float]] = defaultdict(lambda: {
            "samples": 0.0,
            "wins": 0.0,
            "pnl_total": 0.0,
            "confidence_sum": 0.0,
            "vol_sum": 0.0,
            "bias_sum": 0.0,
            "momentum_sum": 0.0,
        })
        for regime, setups in policy_rollup.items():
            for setup, stats in setups.items():
                samples = stats["samples"] or 1.0
                out[regime][setup] = {
                    "samples": stats["samples"],
                    "avg_pnl": stats["pnl_total"] / samples,
                    "win_rate": stats["wins"] / samples,
                    "avg_confidence": stats["confidence_sum"] / samples,
                    "avg_volatility": stats["vol_sum"] / samples,
                    "avg_bias_strength": stats["bias_sum"] / samples,
                    "avg_momentum": stats["momentum_sum"] / samples,
                }
                for key in combined[setup]:
                    combined[setup][key] += stats[key]

        for setup, stats in combined.items():
            samples = stats["samples"] or 1.0
            out["all"][setup] = {
                "samples": stats["samples"],
                "avg_pnl": stats["pnl_total"] / samples,
                "win_rate": stats["wins"] / samples,
                "avg_confidence": stats["confidence_sum"] / samples,
                "avg_volatility": stats["vol_sum"] / samples,
                "avg_bias_strength": stats["bias_sum"] / samples,
                "avg_momentum": stats["momentum_sum"] / samples,
            }

        return out

    def _policy_rule_lines(self, regime: str, setups: Optional[list[str]]) -> list[str]:
        candidates = list(setups or self.default_setups)
        regime_key = regime if regime in self._policy_stats else "all"
        lines: list[str] = []
        for setup in self.rank_setups(candidates, regime=regime_key):
            stats = self._policy_stats.get(regime_key, {}).get(setup)
            if not stats:
                continue
            if regime_key == "bull":
                bias_gate = max(0.40, stats["avg_bias_strength"] - 0.10)
                vol_cap = max(0.02, stats["avg_volatility"] + 0.014)
                momentum_gate = stats["avg_momentum"] - 150.0
                sizing_hint = "scale up when expected_pnl>30 and momentum is positive"
            elif regime_key == "bear":
                bias_gate = max(0.50, stats["avg_bias_strength"] - 0.03)
                vol_cap = max(0.02, stats["avg_volatility"] + 0.006)
                momentum_gate = stats["avg_momentum"] - 50.0
                sizing_hint = "stay selective; trim size/leverage when momentum turns negative"
            elif regime_key == "high_vol":
                bias_gate = max(0.48, stats["avg_bias_strength"] - 0.03)
                vol_cap = max(0.02, stats["avg_volatility"] + 0.004)
                momentum_gate = stats["avg_momentum"] - 120.0
                sizing_hint = "prefer lower-volatility pockets; only boost on strong edge + momentum"
            else:
                bias_gate = max(0.45, stats["avg_bias_strength"] - 0.06)
                vol_cap = max(0.02, stats["avg_volatility"] + 0.008)
                momentum_gate = stats["avg_momentum"] - 250.0
                sizing_hint = "scale with edge quality and win probability"
            use_rule = (
                f"use when regime=={regime_key}, bias_strength>{bias_gate:.2f}, "
                f"volatility<={vol_cap:.3f}, momentum>{momentum_gate:.0f}, "
                f"win_rate≈{stats['win_rate']:.2%}; {sizing_hint}"
            )
            skip_rule = self._best_skip_rule(regime_key, setup)
            lines.append(
                f"  - {setup}: {use_rule}; skip when {skip_rule}"
            )
        return lines

    def _best_skip_rule(self, regime: str, setup: str) -> str:
        candidates: list[tuple[tuple[str, str, str, str, str], dict[str, float]]] = []
        for key, stats in self._bucket_stats.items():
            reg, stp, *_ = key
            if reg == regime and stp == setup and stats["samples"] >= 4:
                candidates.append((key, stats))
        if not candidates:
            return self._default_skip_rule(regime)

        worst = min(
            candidates,
            key=lambda item: (
                (item[1]["pnl_total"] / max(item[1]["samples"], 1.0)),
                (item[1]["wins"] / max(item[1]["samples"], 1.0)),
            ),
        )
        key, stats = worst
        _, _, bias_bucket, vol_bucket, momentum_bucket = key
        avg_pnl = stats["pnl_total"] / max(stats["samples"], 1.0)
        return (
            f"regime={regime}, bias={bias_bucket}, vol={vol_bucket}, momentum={momentum_bucket} "
            f"(avg_pnl={avg_pnl:.2f})"
        )

    def _default_skip_rule(self, regime: str) -> str:
        if regime == "bull":
            return "expected_pnl < -34 and win_probability < 42% and weak-bias/high-volatility"
        if regime == "bear":
            return "expected_pnl < -26 and win_probability < 44% and weak-bias/high-volatility"
        if regime == "high_vol":
            return "expected_pnl < -24 and win_probability < 43% and weak-bias/high-volatility"
        return "expected_pnl < -22 and win_probability < 45% and weak-bias/high-volatility"

    def _edge_label(self, predicted_pnl: float) -> str:
        if predicted_pnl >= 30:
            return "strong-positive"
        if predicted_pnl >= 8:
            return "positive"
        if predicted_pnl >= -10:
            return "marginal"
        if predicted_pnl >= -22:
            return "weak-negative"
        return "negative"
