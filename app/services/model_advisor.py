"""Hardware-aware model and context recommendations."""
from __future__ import annotations

from typing import Any


def _tier(vram_mb: float) -> str:
    if vram_mb <= 0:
        return 'cpu'
    if vram_mb < 6000:
        return 'low'
    if vram_mb < 12000:
        return 'mid'
    if vram_mb < 20000:
        return 'high'
    return 'xl'


def advise_from_hardware(
    *,
    vram_total_mb: float = 0,
    ram_total_mb: float = 8192,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Suggest models and num_ctx from detected hardware."""
    tier = _tier(vram_total_mb)
    suggestions: dict[str, Any] = {
        'tier': tier,
        'vram_total_mb': vram_total_mb,
        'ram_total_mb': ram_total_mb,
    }

    if tier == 'cpu':
        suggestions.update({
            'recommended_models': ['phi3:mini', 'gemma2:2b', 'qwen2.5:3b'],
            'num_ctx': 4096,
            'quant': 'Q4_K_M',
            'note': 'No GPU VRAM detected; prefer small models on CPU.',
        })
    elif tier == 'low':
        suggestions.update({
            'recommended_models': ['qwen2.5-coder:7b', 'deepseek-coder:6.7b', 'llama3.2:3b'],
            'num_ctx': 8192,
            'quant': 'Q4_K_M',
            'note': '6GB VRAM — 7B Q4 with 8K context is a safe default.',
        })
    elif tier == 'mid':
        suggestions.update({
            'recommended_models': ['qwen3-coder:9b', 'qwen2.5-coder:14b', 'deepseek-coder-v2:16b'],
            'num_ctx': 16384,
            'quant': 'Q4_K_M',
            'note': '12GB VRAM — 9–14B coder models with 16K context.',
        })
    elif tier == 'high':
        suggestions.update({
            'recommended_models': ['qwen3-coder:14b', 'qwen2.5-coder:32b', 'deepseek-r1:14b'],
            'num_ctx': 32768,
            'quant': 'Q4_K_M',
            'note': '16–20GB VRAM — larger coders or reasoning models at 32K ctx.',
        })
    else:
        suggestions.update({
            'recommended_models': ['qwen3-coder:32b', 'deepseek-r1:32b', 'qwen2.5-coder:32b'],
            'num_ctx': 65536,
            'quant': 'Q5_K_M',
            'note': '24GB+ VRAM — 32B models with high context for Copilot.',
        })

    if model_name:
        name_l = model_name.lower()
        if any(k in name_l for k in ('coder', 'code', 'starcoder', 'devstral')):
            suggestions['profile_hint'] = 'coding_specialist'
        elif any(k in name_l for k in ('r1', 'qwq', 'reason', 'think')):
            suggestions['profile_hint'] = 'reasoning_thinking'
        elif any(k in name_l for k in ('vl', 'vision', 'llava')):
            suggestions['profile_hint'] = 'vision_multimodal'

    suggestions['proxy_base_url'] = 'http://127.0.0.1:5000/ollama'
    suggestions['proxy_endpoint'] = suggestions['proxy_base_url']
    return suggestions
