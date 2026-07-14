from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from job_store import ROOT, get_job_dir, get_log_snippets, iter_input_items, load_evaluation, load_job, load_result_summary, list_all_jobs
from model_contracts import artifact_index_for, model_contract_for


SETTINGS_DIR = ROOT / "settings"
SETTINGS_PATH = SETTINGS_DIR / "advisor.json"
ADVISOR_TRACE_PATH = ROOT / "local_jobs" / "_advisor" / "advisor_calls.jsonl"
DEFAULT_MODEL = "gpt-4o-mini"
REPORT_SCHEMA_VERSION = 2
DEFAULT_SYSTEM_PROMPT = """你是 KYKT Vision 项目的实验评估助手。

你的任务是根据任务模型、输入数量、关键参数、结果摘要、scene_meta、最近日志等信息，对三维重建任务做简洁而具体的判断。

请始终输出 JSON 对象，字段固定为：
- overall_score: 1 到 10 的整数分
- readiness: unusable / exploratory / usable / strong
- summary: 一段 2 到 4 句的总体判断
- issues: 字符串数组，列出最关键的问题
- next_actions: 字符串数组，列出最值得立刻执行的下一步
- teacher_talk: 一段适合向老师口头汇报的简短话术

要求：
- 不要空泛鼓励，要结合任务上下文。
- 如果结果只是链路验证，也要明确说清。
- 如果日志显示未配置 API 或任务失败，就直接点出阻塞项。
""".strip()

DEFAULT_CONFIG = {
    "enabled": False,
    "provider": "custom_openai_compatible",
    "base_url": "",
    "api_key": "",
    "model": DEFAULT_MODEL,
    "temperature": 0.2,
    "max_tokens": 1200,
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "structured_output": "auto",
    "timeout_seconds": 90,
}

PROVIDER_PRESETS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "structured_output": "json_schema",
        "notes": "Prefer Structured Outputs with strict JSON Schema when the selected model supports it.",
    },
    "gemini_openai": {
        "label": "Gemini OpenAI compatibility",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "structured_output": "prompt_only",
        "notes": "Gemini exposes an OpenAI-compatible chat completions endpoint; keep schema validation local unless response_format support is confirmed for the chosen model.",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "structured_output": "json_object",
        "notes": "Use an OpenAI-compatible gateway; capability depends on upstream model.",
    },
    "litellm": {
        "label": "LiteLLM Proxy",
        "base_url": "http://127.0.0.1:4000/v1",
        "structured_output": "json_schema",
        "notes": "Local or remote LiteLLM proxy can normalize many providers behind one OpenAI-compatible endpoint.",
    },
    "custom_openai_compatible": {
        "label": "Custom OpenAI-compatible",
        "base_url": "",
        "structured_output": "auto",
        "notes": "For local gateways or provider-compatible endpoints.",
    },
}

ADVISOR_REPORT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "overall_score": {"type": "integer"},
        "readiness": {"type": "string", "enum": ["unusable", "exploratory", "usable", "strong"]},
        "summary": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "next_actions": {"type": "array", "items": {"type": "string"}},
        "teacher_talk": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "overall_score",
        "readiness",
        "summary",
        "issues",
        "next_actions",
        "teacher_talk",
        "confidence",
        "evidence",
        "limitations",
    ],
}


def load_advisor_config() -> dict[str, Any]:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_CONFIG)
    if SETTINGS_PATH.exists():
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        merged.update(payload)
    _apply_advisor_env_overrides(merged)
    return merged


def advisor_config_public() -> dict[str, Any]:
    config = load_advisor_config()
    status = advisor_status()
    structured_output = _structured_output_mode(config)
    timeout_seconds = int(config.get("timeout_seconds") or 90)
    schema_version = REPORT_SCHEMA_VERSION
    return {
        **status,
        "has_api_key": bool(str(config.get("api_key") or "").strip()),
        "temperature": float(config.get("temperature") or 0.2),
        "max_tokens": int(config.get("max_tokens") or 1200),
        "system_prompt": str(config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT),
        "provider": str(config.get("provider") or "custom_openai_compatible"),
        "structured_output": structured_output,
        "timeout_seconds": timeout_seconds,
        "schema_version": schema_version,
        "hasApiKey": bool(str(config.get("api_key") or "").strip()),
        "maxTokens": int(config.get("max_tokens") or 1200),
        "systemPrompt": str(config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT),
        "structuredOutput": structured_output,
        "timeoutSeconds": timeout_seconds,
        "schemaVersion": schema_version,
    }


def save_advisor_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_advisor_config()
    merged = dict(DEFAULT_CONFIG)
    merged.update(current)

    if "enabled" in payload:
        merged["enabled"] = bool(payload.get("enabled"))
    if "provider" in payload:
        provider = str(payload.get("provider") or "custom_openai_compatible").strip()
        merged["provider"] = provider if provider in PROVIDER_PRESETS else "custom_openai_compatible"
    if "base_url" in payload or "baseUrl" in payload:
        merged["base_url"] = str(payload.get("base_url", payload.get("baseUrl")) or "").strip()
    if "model" in payload:
        merged["model"] = str(payload.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if "temperature" in payload:
        merged["temperature"] = float(payload.get("temperature") or 0.2)
    if "max_tokens" in payload or "maxTokens" in payload:
        merged["max_tokens"] = int(payload.get("max_tokens", payload.get("maxTokens")) or 1200)
    if "system_prompt" in payload or "systemPrompt" in payload:
        merged["system_prompt"] = str(payload.get("system_prompt", payload.get("systemPrompt")) or DEFAULT_SYSTEM_PROMPT).strip() or DEFAULT_SYSTEM_PROMPT
    if "structured_output" in payload or "structuredOutput" in payload:
        mode = str(payload.get("structured_output", payload.get("structuredOutput")) or "auto").strip()
        merged["structured_output"] = mode if mode in {"auto", "json_schema", "json_object", "prompt_only"} else "auto"
    if "timeout_seconds" in payload or "timeoutSeconds" in payload:
        merged["timeout_seconds"] = min(max(int(payload.get("timeout_seconds", payload.get("timeoutSeconds")) or 90), 10), 300)

    if "api_key" in payload or "apiKey" in payload:
        api_key = str(payload.get("api_key", payload.get("apiKey")) or "").strip()
        if api_key:
            merged["api_key"] = api_key
        elif payload.get("clear_api_key") or payload.get("clearApiKey"):
            merged["api_key"] = ""

    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return advisor_config_public()


def _apply_advisor_env_overrides(config: dict[str, Any]) -> None:
    env_enabled = os.getenv("KYKT_ADVISOR_ENABLED")
    if env_enabled is not None:
        config["enabled"] = env_enabled.strip().lower() in {"1", "true", "yes", "on"}

    env_map = {
        "provider": "KYKT_ADVISOR_PROVIDER",
        "base_url": "KYKT_ADVISOR_BASE_URL",
        "api_key": "KYKT_ADVISOR_API_KEY",
        "model": "KYKT_ADVISOR_MODEL",
        "system_prompt": "KYKT_ADVISOR_SYSTEM_PROMPT",
        "structured_output": "KYKT_ADVISOR_STRUCTURED_OUTPUT",
    }
    for key, env_name in env_map.items():
        value = os.getenv(env_name)
        if value is not None:
            config[key] = value.strip()

    env_temperature = os.getenv("KYKT_ADVISOR_TEMPERATURE")
    if env_temperature is not None:
        config["temperature"] = float(env_temperature)

    env_max_tokens = os.getenv("KYKT_ADVISOR_MAX_TOKENS")
    if env_max_tokens is not None:
        config["max_tokens"] = int(env_max_tokens)

    env_timeout = os.getenv("KYKT_ADVISOR_TIMEOUT_SECONDS")
    if env_timeout is not None:
        config["timeout_seconds"] = int(env_timeout)


def advisor_status() -> dict[str, Any]:
    config = load_advisor_config()
    base_url = str(config.get("base_url") or "").strip()
    api_key = str(config.get("api_key") or "").strip()
    model = str(config.get("model") or "").strip()
    provider = str(config.get("provider") or "custom_openai_compatible").strip()
    enabled = bool(config.get("enabled"))
    configured = bool(base_url and api_key and model)
    provider_label = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["custom_openai_compatible"])["label"]
    structured_output = _structured_output_mode(config)
    return {
        "enabled": enabled,
        "configured": configured,
        "provider": provider,
        "provider_label": provider_label,
        "base_url": base_url,
        "model": model or DEFAULT_MODEL,
        "has_api_key": bool(api_key),
        "structured_output": structured_output,
        "providerLabel": provider_label,
        "baseUrl": base_url,
        "hasApiKey": bool(api_key),
        "structuredOutput": structured_output,
        "message": _advisor_status_message(enabled, configured),
    }


def load_advisor_report(job_id: str) -> dict[str, Any] | None:
    path = get_job_dir(job_id) / "advisor_report.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_advisor_report(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    path = get_job_dir(job_id) / "advisor_report.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def advisor_provider_options() -> dict[str, Any]:
    providers = []
    for key, preset in PROVIDER_PRESETS.items():
        providers.append(
            {
                "value": key,
                **preset,
                "baseUrl": preset["base_url"],
                "structuredOutput": preset["structured_output"],
            }
        )
    report_schema = {
        "version": REPORT_SCHEMA_VERSION,
        "json_schema": ADVISOR_REPORT_SCHEMA,
        "jsonSchema": ADVISOR_REPORT_SCHEMA,
    }
    return {
        "providers": providers,
        "report_schema": report_schema,
        "reportSchema": report_schema,
    }


def fetch_advisor_models(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    saved = load_advisor_config()
    base_url = str(payload.get("base_url", payload.get("baseUrl")) or saved.get("base_url") or "").strip()
    api_key = str(payload.get("api_key", payload.get("apiKey")) or saved.get("api_key") or "").strip()
    timeout_seconds = min(max(int(payload.get("timeout_seconds", payload.get("timeoutSeconds")) or 30), 5), 60)
    if not base_url:
        raise RuntimeError("请先填写 Base URL。")
    if not api_key:
        raise RuntimeError("请先填写 API Key，或保存已有 Key。")

    models_url = base_url.rstrip("/")
    if not models_url.endswith("/models"):
        models_url += "/models"
    request = Request(
        models_url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"获取模型列表失败：HTTP {exc.code}。{detail[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"获取模型列表失败：{exc.reason}") from exc

    try:
        response_payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("模型接口返回的不是有效 JSON。") from exc

    raw_models = response_payload.get("data") if isinstance(response_payload, dict) else None
    if not isinstance(raw_models, list) and isinstance(response_payload, dict):
        raw_models = response_payload.get("models")
    if not isinstance(raw_models, list):
        raise RuntimeError("模型接口响应中缺少 data/models 数组。")

    models: list[str] = []
    seen: set[str] = set()
    for item in raw_models:
        if isinstance(item, str):
            model_id = item.strip()
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
        else:
            model_id = ""
        if model_id and model_id not in seen:
            seen.add(model_id)
            models.append(model_id)
    models.sort(key=str.casefold)
    return {"models": models, "count": len(models), "endpoint": models_url}


def advisor_diagnostics() -> dict[str, Any]:
    config = load_advisor_config()
    status = advisor_status()
    checks = []
    checks.append({"key": "enabled", "ok": bool(status["enabled"]), "message": "AI 评估已启用。" if status["enabled"] else "AI 评估当前关闭。"})
    checks.append({"key": "base_url", "ok": bool(status["base_url"]), "message": status["base_url"] or "缺少 base_url。"})
    checks.append({"key": "api_key", "ok": bool(status["has_api_key"]), "message": "API key 已配置。" if status["has_api_key"] else "缺少 API key。"})
    checks.append({"key": "model", "ok": bool(status["model"]), "message": status["model"] or "缺少 model。"})
    structured_output = _structured_output_mode(config)
    checks.append({"key": "structured_output", "ok": True, "message": f"结构化输出模式：{structured_output}"})
    provider = PROVIDER_PRESETS.get(str(config.get("provider") or ""), PROVIDER_PRESETS["custom_openai_compatible"])
    return {
        "ok": all(item["ok"] for item in checks),
        "status": status,
        "checks": checks,
        "provider": provider,
        "providerLabel": provider["label"],
        "structured_output_mode": structured_output,
        "structuredOutputMode": structured_output,
    }


def test_advisor_connection() -> dict[str, Any]:
    status = advisor_status()
    if not status["enabled"]:
        raise RuntimeError("AI 评估尚未启用。")
    if not status["configured"]:
        raise RuntimeError("AI 评估配置不完整，无法测试连接。")

    config = load_advisor_config()
    started = time.monotonic()
    context = {
        "project": "KYKT Vision",
        "purpose": "connection_test",
        "expected_output_format": ADVISOR_REPORT_SCHEMA,
    }
    raw_text = _call_openai_compatible_api(config, context, purpose="connection_test")
    parsed = _validate_report_payload(_parse_model_json(raw_text))
    return {
        "ok": True,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "latencyMs": int((time.monotonic() - started) * 1000),
        "provider": status["provider"],
        "model": status["model"],
        "structured_output": _structured_output_mode(config),
        "structuredOutput": _structured_output_mode(config),
        "sample": parsed,
    }


def evaluate_job_with_advisor(job_id: str) -> dict[str, Any]:
    status = advisor_status()
    if not status["enabled"]:
        raise RuntimeError("AI 评估尚未启用。请先在配置页或本地环境变量中启用，并填入 base_url、api_key、model。")
    if not status["configured"]:
        raise RuntimeError("AI 评估配置不完整。请检查配置页、本地 settings/advisor.json 或 KYKT_ADVISOR_* 环境变量。")

    config = load_advisor_config()
    context = build_advisor_context(job_id)
    raw_text = _call_openai_compatible_api(config, context, purpose="job_evaluation")
    try:
        parsed = _validate_report_payload(_parse_model_json(raw_text))
    except RuntimeError:
        repair_context = {
            "repair_instruction": "上一轮输出没有通过 JSON schema 校验。请只返回符合 schema 的 JSON 对象。",
            "schema": ADVISOR_REPORT_SCHEMA,
            "invalid_output": raw_text[:2000],
            "job_context": context,
        }
        raw_text = _call_openai_compatible_api(config, repair_context, purpose="job_evaluation_repair")
        parsed = _validate_report_payload(_parse_model_json(raw_text))

    report = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "job_id": job_id,
        "overall_score": int(parsed.get("overall_score") or 0),
        "readiness": str(parsed.get("readiness") or "exploratory"),
        "summary": str(parsed.get("summary") or "").strip(),
        "issues": _normalize_text_list(parsed.get("issues")),
        "next_actions": _normalize_text_list(parsed.get("next_actions")),
        "teacher_talk": str(parsed.get("teacher_talk") or "").strip(),
        "confidence": str(parsed.get("confidence") or "medium"),
        "evidence": _normalize_text_list(parsed.get("evidence")),
        "limitations": _normalize_text_list(parsed.get("limitations")),
        "advisor_model": str(config.get("model") or DEFAULT_MODEL),
        "provider": str(config.get("provider") or "custom_openai_compatible"),
        "schema_version": REPORT_SCHEMA_VERSION,
    }
    return save_advisor_report(job_id, report)


def build_advisor_context(job_id: str) -> dict[str, Any]:
    job = load_job(job_id)
    summary = load_result_summary(job_id)
    evaluation = load_evaluation(job_id)
    scene_meta = summary.get("scene_meta") if summary else None
    logs = get_log_snippets(job_id, limit=80)
    try:
        model_contract = model_contract_for(job.model)
    except KeyError:
        model_contract = None
    artifact_index = artifact_index_for(job.model, job.output_files)

    return {
        "project": "KYKT Vision",
        "advisor_schema_version": REPORT_SCHEMA_VERSION,
        "job": {
            "job_id": job.job_id,
            "model": job.model,
            "source_type": job.source_type,
            "created_at": job.created_at,
            "status": job.status,
            "phase": job.phase,
            "notes": job.notes,
            "params": job.params,
            "progress_message": job.progress_message,
            "error_message": job.error_message,
            "input_count": len(job.input_files),
            "input_names": [item["original_name"] for item in iter_input_items(job)],
            "output_files": job.output_files[:120],
        },
        "model_contract": model_contract,
        "artifact_index": artifact_index,
        "result_summary": summary,
        "manual_evaluation": evaluation,
        "scene_meta": scene_meta,
        "logs": [
            {
                "name": item["name"],
                "tail": item["tail"],
            }
            for item in logs
        ],
        "expected_output_format": {
            "json_schema": ADVISOR_REPORT_SCHEMA,
            "overall_score": "1-10 integer",
            "readiness": "unusable | exploratory | usable | strong",
            "summary": "brief Chinese summary",
            "issues": "string array",
            "next_actions": "string array",
            "teacher_talk": "brief Chinese oral update",
            "confidence": "low | medium | high",
            "evidence": "string array with concrete file/log/metric evidence",
            "limitations": "string array with missing evidence or uncertainty",
        },
    }


def _advisor_status_message(enabled: bool, configured: bool) -> str:
    if not enabled:
        return "AI 评估已接入，但当前处于关闭状态。"
    if not configured:
        return "AI 评估已启用，但配置不完整。"
    return "AI 评估已就绪。"


def _structured_output_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("structured_output") or "auto").strip()
    if mode != "auto":
        return mode
    provider = str(config.get("provider") or "").strip()
    if provider in PROVIDER_PRESETS:
        preset_mode = str(PROVIDER_PRESETS[provider]["structured_output"])
        if preset_mode != "auto":
            return preset_mode
    base_url = str(config.get("base_url") or "").lower()
    if "generativelanguage.googleapis.com" in base_url:
        return "prompt_only"
    if "openai.com" in base_url:
        return "json_schema"
    return "json_object"


def _chat_completions_url(config: dict[str, Any]) -> str:
    base_url = str(config.get("base_url") or "").rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    elif base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/chat/completions"


def _call_openai_compatible_api(config: dict[str, Any], context: dict[str, Any], *, purpose: str) -> str:
    url = _chat_completions_url(config)
    structured_mode = _structured_output_mode(config)

    payload = {
        "model": str(config.get("model") or DEFAULT_MODEL),
        "temperature": float(config.get("temperature") or 0.2),
        "max_tokens": int(config.get("max_tokens") or 1200),
        "messages": [
            {"role": "system", "content": str(config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT)},
            {
                "role": "user",
                "content": (
                    "请严格返回 JSON 对象，不要加 Markdown 代码块。\n\n"
                    "任务上下文如下：\n"
                    f"{json.dumps(context, ensure_ascii=False, indent=2)}"
                ),
            },
        ],
    }
    if structured_mode == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "kykt_advisor_report",
                "strict": True,
                "schema": ADVISOR_REPORT_SCHEMA,
            },
        }
    elif structured_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}

    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {str(config.get('api_key') or '').strip()}",
        },
        method="POST",
    )

    started = time.monotonic()
    try:
        with urlopen(request, timeout=int(config.get("timeout_seconds") or 90)) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"AI 评估请求失败：HTTP {exc.code}。{detail[:400]}") from exc
    except URLError as exc:
        raise RuntimeError(f"AI 评估连接失败：{exc.reason}") from exc

    latency_ms = int((time.monotonic() - started) * 1000)
    response_payload = json.loads(body)
    _record_advisor_call(
        {
            "at": datetime.now().isoformat(timespec="seconds"),
            "purpose": purpose,
            "provider": str(config.get("provider") or "custom_openai_compatible"),
            "model": str(config.get("model") or DEFAULT_MODEL),
            "url_host": re.sub(r"^(https?://[^/]+).*$", r"\1", url),
            "structured_output": structured_mode,
            "latency_ms": latency_ms,
            "response_id": response_payload.get("id"),
            "finish_reason": ((response_payload.get("choices") or [{}])[0] or {}).get("finish_reason"),
        }
    )
    choice = (response_payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                pieces.append(str(item.get("text") or ""))
        return "\n".join(piece for piece in pieces if piece).strip()
    return str(content or "").strip()


def _record_advisor_call(payload: dict[str, Any]) -> None:
    ADVISOR_TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ADVISOR_TRACE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _parse_model_json(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        raise RuntimeError("AI 评估接口返回了空内容。")

    cleaned = raw_text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise RuntimeError(f"AI 评估返回的不是合法 JSON：{cleaned[:400]}")


def _validate_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("AI 评估返回的 JSON 不是对象。")
    missing = [key for key in ADVISOR_REPORT_SCHEMA["required"] if key not in payload]
    if missing:
        raise RuntimeError(f"AI 评估 JSON 缺少字段：{', '.join(missing)}")
    try:
        score = int(payload["overall_score"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("overall_score 必须是 1 到 10 的整数。") from exc
    if score < 1 or score > 10:
        raise RuntimeError("overall_score 必须在 1 到 10 之间。")
    payload["overall_score"] = score

    readiness = str(payload.get("readiness") or "")
    if readiness not in {"unusable", "exploratory", "usable", "strong"}:
        raise RuntimeError("readiness 必须是 unusable / exploratory / usable / strong。")
    confidence = str(payload.get("confidence") or "")
    if confidence not in {"low", "medium", "high"}:
        raise RuntimeError("confidence 必须是 low / medium / high。")
    for key in ("issues", "next_actions", "evidence", "limitations"):
        if not isinstance(payload.get(key), list):
            raise RuntimeError(f"{key} 必须是字符串数组。")
        payload[key] = _normalize_text_list(payload[key])
    for key in ("summary", "teacher_talk"):
        payload[key] = str(payload.get(key) or "").strip()
    return payload


def _normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def recommend_parameters(job_id: str) -> dict[str, Any]:
    """基于历史任务推荐参数"""
    job = load_job(job_id)
    similar_jobs = []
    
    # 查找同模型、同来源类型的历史成功任务
    for j in list_all_jobs():
        if j.job_id == job_id:
            continue
        if j.model == job.model and j.source_type == job.source_type and j.status == "finished":
            similar_jobs.append(j)
    
    if not similar_jobs:
        return {
            "has_recommendations": False,
            "message": "暂无相似历史任务用于参数推荐",
            "recommended_params": None,
        }
    
    # 统计常用参数
    param_stats: dict[str, dict[str, int]] = {}
    for j in similar_jobs:
        for key, value in j.params.items():
            if key not in param_stats:
                param_stats[key] = {}
            value_str = str(value)
            param_stats[key][value_str] = param_stats[key].get(value_str, 0) + 1
    
    # 推荐最常用的参数值
    recommended = {}
    for key, counts in param_stats.items():
        if counts:
            best_value = max(counts, key=counts.get)
            recommended[key] = best_value
    
    return {
        "has_recommendations": True,
        "message": f"基于 {len(similar_jobs)} 个相似历史任务推荐参数",
        "recommended_params": recommended,
        "similar_job_count": len(similar_jobs),
    }


def diagnose_failure(job_id: str) -> dict[str, Any]:
    """深入诊断任务失败原因"""
    job = load_job(job_id)
    logs = get_log_snippets(job_id, limit=100)
    
    diagnosis = {
        "job_id": job_id,
        "status": job.status,
        "error_message": job.error_message,
        "diagnosis": [],
        "suggestions": [],
    }
    
    # 分析错误类型
    if job.status == "failed":
        error_msg = job.error_message or ""
        
        # OOM 错误
        if "CUDA out of memory" in error_msg or "out of memory" in error_msg.lower():
            diagnosis["diagnosis"].append("GPU 内存不足")
            diagnosis["suggestions"].append("减少 batch_size 或 image_size")
            diagnosis["suggestions"].append("尝试使用更小的模型或减少输入图像数量")
        
        # SSH 连接错误
        if "SSH" in error_msg or "connection" in error_msg.lower():
            diagnosis["diagnosis"].append("SSH 连接问题")
            diagnosis["suggestions"].append("检查服务器配置和网络连接")
            diagnosis["suggestions"].append("验证 SSH 密钥和服务器地址")
        
        # 环境错误
        if "ModuleNotFoundError" in error_msg or "ImportError" in error_msg:
            diagnosis["diagnosis"].append("Python 环境依赖缺失")
            diagnosis["suggestions"].append("检查 conda 环境是否正确配置")
            diagnosis["suggestions"].append("运行 pip install 安装缺失依赖")
        
        # 权限错误
        if "Permission" in error_msg or "denied" in error_msg.lower():
            diagnosis["diagnosis"].append("文件权限问题")
            diagnosis["suggestions"].append("检查工作目录和输出目录的读写权限")
        
        # 磁盘空间
        if "No space left" in error_msg or "disk full" in error_msg.lower():
            diagnosis["diagnosis"].append("磁盘空间不足")
            diagnosis["suggestions"].append("清理临时文件或输出目录")
            diagnosis["suggestions"].append("检查服务器磁盘使用情况")
    
    # 分析日志中的警告
    for log_item in logs:
        tail = log_item.get("tail", "")
        if "WARNING" in tail or "WARN" in tail:
            if "deprecated" in tail.lower():
                diagnosis["diagnosis"].append("使用了已弃用的 API 或参数")
                diagnosis["suggestions"].append("检查模型版本和参数配置")
    
    if not diagnosis["diagnosis"]:
        diagnosis["diagnosis"].append("未识别到特定错误模式")
        diagnosis["suggestions"].append("查看完整日志获取更多细节")
    
    return diagnosis


def batch_evaluate_jobs(job_ids: list[str]) -> dict[str, Any]:
    """批量评估多个任务"""
    status = advisor_status()
    if not status["enabled"]:
        raise RuntimeError("AI 评估尚未启用")
    if not status["configured"]:
        raise RuntimeError("AI 评估配置不完整")
    
    results = []
    errors = []
    
    for job_id in job_ids:
        try:
            report = evaluate_job_with_advisor(job_id)
            results.append({
                "job_id": job_id,
                "success": True,
                "report": report,
            })
        except Exception as e:
            errors.append({
                "job_id": job_id,
                "error": str(e),
            })
    
    return {
        "total": len(job_ids),
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
