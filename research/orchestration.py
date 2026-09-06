"""Thin Quant presentation and safe job-declaration helpers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research.core.contracts import ResearchResult, ResearchStatus


@dataclass(frozen=True)
class JobDeclaration:
    key: str
    command: str
    schedule: str
    timezone: str
    old_job: str | None
    enabled: bool
    production_ready: bool
    migration_status: str
    model_lanes: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "JobDeclaration":
        required = ("key", "command", "schedule", "timezone", "migration_status")
        missing = [name for name in required if not str(value.get(name) or "").strip()]
        if missing:
            raise ValueError(f"job declaration missing: {', '.join(missing)}")
        raw_lanes = value.get("model_lanes") or {}
        if not isinstance(raw_lanes, Mapping):
            raise ValueError("model_lanes must be an object")
        return cls(
            key=str(value["key"]),
            command=str(value["command"]),
            schedule=str(value["schedule"]),
            timezone=str(value["timezone"]),
            old_job=str(value["old_job"]) if value.get("old_job") else None,
            enabled=bool(value.get("enabled", False)),
            production_ready=bool(value.get("production_ready", False)),
            migration_status=str(value["migration_status"]),
            model_lanes={
                str(name): tuple(str(item) for item in items)
                for name, items in raw_lanes.items()
                if isinstance(items, Sequence) and not isinstance(items, (str, bytes))
            },
        )


def load_job_declarations(path: Path) -> list[JobDeclaration]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("jobs") if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError("job declaration file must contain a list or jobs array")
    return [JobDeclaration.from_mapping(row) for row in rows]


def duplicate_job_keys(declarations: Sequence[JobDeclaration]) -> list[str]:
    counts = Counter(item.key for item in declarations)
    return sorted(key for key, count in counts.items() if count > 1)


def validate_job_declarations(declarations: Sequence[JobDeclaration]) -> list[str]:
    errors = [f"duplicate key: {key}" for key in duplicate_job_keys(declarations)]
    for item in declarations:
        if item.enabled and not item.production_ready:
            errors.append(f"enabled job is not production-ready: {item.key}")
        if item.migration_status != "PREPARE_ONLY" and not item.enabled:
            errors.append(f"disabled job must be PREPARE_ONLY: {item.key}")
    return errors


def discord_chunks(text: str, limit: int = 2000) -> list[str]:
    """Lossless UTF-16-sized chunks, including astral characters used on Discord."""
    if limit < 2:
        raise ValueError("chunk limit must be at least two")
    chunks, current, size = [], [], 0
    for char in text:
        units = len(char.encode("utf-16-le")) // 2
        if size + units > limit:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += units
    if current:
        chunks.append("".join(current))
    return chunks


def delivery_destination(channel_id: str | None, origin: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Discord threads/forum posts are transport channel IDs themselves."""
    if origin is None:
        return {"platform": "discord", "chat_id": channel_id, "surface": "parent", "origin_type": "scheduled", "ready": channel_id is not None}
    kind = origin.get("origin_type")
    if kind not in {"channel", "thread", "forum_post"}:
        raise ValueError("interactive origin_type is required")
    destination = origin.get("forum_post_id") if kind == "forum_post" else origin.get("thread_id") if kind == "thread" else origin.get("channel_id")
    if not isinstance(destination, str) or not destination.isdigit() or len(destination) < 15:
        raise ValueError("explicit originating Discord channel/thread ID required")
    return {"platform": "discord", "chat_id": destination, "surface": kind, "origin": dict(origin), "ready": True}


def _concise(value: Any) -> str:
    """Bound human output; complete structured data remains in the journal."""
    if isinstance(value, Mapping):
        fields = ("ticker", "symbol", "asset_key", "mint", "subject", "status", "action", "condition", "reason", "claim", "text", "value", "return_basis")
        facts = [f"{key}: {str(value[key])[:180]}" for key in fields if value.get(key) is not None and not isinstance(value[key], (dict, list))]
        if not facts:
            facts = [f"{key}: {str(item)[:120]}" for key, item in list(value.items())[:6] if not isinstance(item, (dict, list))]
        return "; ".join(facts) or "Detalle disponible en el resultado guardado."
    return str(value)[:240]


def _section(value: Any) -> str:
    rows = value if isinstance(value, list) else [value]
    text = "\n".join("- " + _concise(row) for row in rows[:5])
    if len(rows) > 5:
        text += f"\n- {len(rows) - 5} registros adicionales en el resultado guardado."
    return text


def present_result(result: ResearchResult | Mapping[str, Any], *, channel_id: str | None = None, origin: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the concise, evidence-aware object Quant can present."""
    if not isinstance(result, ResearchResult):
        result = ResearchResult.from_dict(result)
    result.validate()
    payload = dict(result.payload)
    if channel_id is not None and (not channel_id.isdigit() or len(channel_id) < 15):
        raise ValueError("Discord destination must be an explicit numeric parent-channel ID")
    if result.status is ResearchStatus.NO_SETUP:
        next_action = "Present NO_SETUP with scan evidence; do not invent a strategy thesis."
    elif result.status is ResearchStatus.ACTION_REQUIRED:
        next_action = "Present ACTION_REQUIRED and wait for human review."
    elif result.status in {ResearchStatus.INSUFFICIENT_EVIDENCE, ResearchStatus.DATA_UNAVAILABLE}:
        next_action = "Present the evidence gap and do not recommend an action."
    else:
        next_action = "Present the structured research result and preserve its evidence and warnings."
    prefix = "CRYPTO:" if result.workflow.startswith(("crypto.", "memecoin.")) else "STOCKS:"
    silent = result.status is ResearchStatus.NO_SETUP and (
        payload.get("silent") is True or result.workflow == "portfolio.watch"
    ) and not result.warnings
    action_es = (
        "Faltan datos o evidencia suficiente. No hay recomendación operativa."
        if result.status in {ResearchStatus.INSUFFICIENT_EVIDENCE, ResearchStatus.DATA_UNAVAILABLE, ResearchStatus.ERROR}
        else "Estrategia sin validar; continuar investigación, sin operar."
        if result.status is ResearchStatus.STRATEGY_NOT_VALIDATED
        else "Sin configuración confirmada; no inventar una tesis."
        if result.status is ResearchStatus.NO_SETUP
        else "Revisión humana requerida. Esto no es una orden ni una señal de compra."
    )
    lines = [f"{prefix} {result.workflow} — {result.status.value}",
             f"Fecha de decisión: {result.metadata.decision_time.isoformat()}", action_es]
    for key, title in (("positions", "Posiciones"), ("events", "Alertas"),
                       ("final_candidates", "Candidatos"), ("candidates", "Candidatos"),
                       ("selected", "Candidatos seleccionados"), ("claims", "Afirmaciones atribuidas"),
                       ("macro_implications", "Contexto macro"), ("funnel", "Cobertura y filtros"),
                       ("records", "Registros"), ("rejected_candidates", "Rechazos"),
                       ("metrics", "Métricas"), ("unparsed_responsibilities", "Responsabilidades pendientes")):
        if payload.get(key):
            lines.append(f"\n**{title}**\n" + _section(payload[key]))
    for key in ("summary", "reason", "corroboration_status", "evidence_quality"):
        if payload.get(key):
            lines.append(f"{key}: {payload[key]}")
    if result.warnings:
        lines.append("\n**Advertencias**\n" + "\n".join(str(w) for w in result.warnings))
    if result.evidence:
        lines.append("\n**Fuentes y disponibilidad**")
        lines.extend(f"{item.reference_id}: {item.citation or item.source} ({item.kind.value}; {item.point_in_time.availability})" for item in result.evidence)
    lines.append(f"ID de investigación: {result.metadata.run_id}. Ejecución deshabilitada.")
    text = "[SILENT]" if silent else "\n".join(lines)
    presentation_truncated = len(text.encode("utf-16-le")) // 2 > 12000
    if presentation_truncated:
        text = "".join(discord_chunks(text, 11000)[:1]) + f"\n[Extracto: reporte extenso. JSON completo preservado; ID {result.metadata.run_id}. No operar sin revisar la evidencia completa.]"
    return {
        "result": result.to_dict(),
        "payload": payload,
        "evidence": [item.to_dict() for item in result.evidence],
        "discord_text": text,
        "presentation_truncated": presentation_truncated,
        "discord_chunks": [] if silent else discord_chunks(text),
        "delivery": {**delivery_destination(channel_id, origin), "silent": silent},
        "workflow": result.workflow,
        "status": result.status.value,
        "strategy": result.metadata.strategy_name,
        "strategy_version": result.metadata.strategy_version,
        "decision_time": result.metadata.decision_time.isoformat(),
        "evidence_count": len(result.evidence),
        "warnings": list(result.warnings),
        "summary": {
            "candidate_count": len(payload.get("final_candidates") or payload.get("candidates") or []),
            "rejected_count": len(payload.get("rejected_candidates") or []),
            "execution_enabled": bool(payload.get("execution_enabled", False)),
        },
        "next_action": next_action,
        "human_decision_required": True,
        "safety_boundary": result.safety_boundary.value,
    }
