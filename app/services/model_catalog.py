"""Model catalog definitions: curated and extended downloadable model lists.

Separated from OllamaService to reduce file size of ollama.py. Pure data; no HTTP.
Keep alias entries required by tests (e.g., plain 'llava', 'moondream').

Updated February 2026 to reflect the latest Ollama library.
"""


def get_best_models():
    return [
        # ── Flagship general-purpose models ──────────────────────────────
        {
            "name": "qwen3:8b",
            "description": "Qwen 3 dense model with tool calling & thinking",
            "parameter_size": "8B",
            "size": "4.9GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "qwen3:14b",
            "description": "Qwen 3 medium dense model with tool calling & thinking",
            "parameter_size": "14B",
            "size": "8.7GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "qwen3:32b",
            "description": "Qwen 3 large dense model with tool calling & thinking",
            "parameter_size": "32B",
            "size": "19GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "llama3.3:70b",
            "description": "Meta Llama 3.3 70B with tool calling, rivaling 405B performance",
            "parameter_size": "70B",
            "size": "40GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "llama3.2:3b",
            "description": "Meta Llama 3.2 small model with tool calling",
            "parameter_size": "3B",
            "size": "2.0GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "llama3.1:8b",
            "description": "Meta Llama 3.1 with tool calling support",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "llama3.1:70b",
            "description": "Meta Llama 3.1 large with tool calling",
            "parameter_size": "70B",
            "size": "40GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "gemma3:4b",
            "description": "Google Gemma 3 lightweight vision model",
            "parameter_size": "4B",
            "size": "3.3GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma3:12b",
            "description": "Google Gemma 3 medium vision model",
            "parameter_size": "12B",
            "size": "8.1GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma3:27b",
            "description": "Google Gemma 3 large vision model",
            "parameter_size": "27B",
            "size": "17GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "deepseek-r1:8b",
            "description": "DeepSeek R1 reasoning model with tool calling & thinking",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "deepseek-r1:14b",
            "description": "DeepSeek R1 medium reasoning model with tool calling & thinking",
            "parameter_size": "14B",
            "size": "8.1GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "deepseek-r1:32b",
            "description": "DeepSeek R1 large reasoning model with tool calling & thinking",
            "parameter_size": "32B",
            "size": "19GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "mistral:7b",
            "description": "Mistral AI 7B v0.3 with function calling",
            "parameter_size": "7B",
            "size": "4.1GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "qwen2.5:7b",
            "description": "Qwen 2.5 with tool calling, 128K context",
            "parameter_size": "7B",
            "size": "4.4GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "qwen2.5:14b",
            "description": "Qwen 2.5 medium with tool calling",
            "parameter_size": "14B",
            "size": "8.2GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "phi4:14b",
            "description": "Microsoft Phi-4, state-of-the-art 14B open model",
            "parameter_size": "14B",
            "size": "8.4GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gpt-oss:20b",
            "description": "OpenAI open-weight model for reasoning & agentic tasks",
            "parameter_size": "20B",
            "size": "12GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "mixtral:8x7b",
            "description": "Mistral Mixtral MoE with tool calling",
            "parameter_size": "8x7B",
            "size": "26GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        # ── Vision models ────────────────────────────────────────────────
        {
            "name": "llava:7b",
            "description": "LLaVA multimodal vision + language",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "qwen2.5-vl:7b",
            "description": "Qwen 2.5 Vision Language with tool calling",
            "parameter_size": "7B",
            "size": "7.9GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "llama3.2-vision:11b",
            "description": "Meta Llama 3.2 Vision 11B image reasoning model",
            "parameter_size": "11B",
            "size": "7.9GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llava-llama3:8b",
            "description": "LLaVA based on Llama 3 with vision",
            "parameter_size": "8B",
            "size": "5.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "moondream:1.8b",
            "description": "Tiny vision language model for edge devices",
            "parameter_size": "1.8B",
            "size": "1.7GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "minicpm-v:8b",
            "description": "MiniCPM-V multimodal vision-language model",
            "parameter_size": "8B",
            "size": "5.6GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        # ── Coding models ────────────────────────────────────────────────
        {
            "name": "qwen2.5-coder:7b",
            "description": "Qwen 2.5 Coder with tool calling, optimized for code",
            "parameter_size": "7B",
            "size": "4.4GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "qwen3-coder:30b",
            "description": "Alibaba Qwen3 Coder for agentic & coding tasks",
            "parameter_size": "30B",
            "size": "18GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        # ── Lightweight models ───────────────────────────────────────────
        {
            "name": "phi4-mini:3.8b",
            "description": "Microsoft Phi-4 Mini with tool calling, multilingual",
            "parameter_size": "3.8B",
            "size": "2.4GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "phi3:mini",
            "description": "Microsoft Phi-3 mini lightweight model",
            "parameter_size": "3.8B",
            "size": "2.3GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma2:2b",
            "description": "Google Gemma 2 compact model",
            "parameter_size": "2B",
            "size": "1.3GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "smollm2:1.7b",
            "description": "SmolLM2 compact language model with tool calling",
            "parameter_size": "1.7B",
            "size": "1.0GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        # ── Alias entries (required by tests — keep plain names) ─────────
        {
            "name": "moondream",
            "description": "Tiny vision language model (alias)",
            "parameter_size": "1.8B",
            "size": "1.7GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llava",
            "description": "LLaVA multimodal vision + language (alias)",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llava-llama3",
            "description": "LLaVA based on Llama 3 (alias)",
            "parameter_size": "8B",
            "size": "5.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llava-phi3",
            "description": "LLaVA based on Phi-3 (alias)",
            "parameter_size": "3.8B",
            "size": "2.9GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
    ]


def get_all_downloadable_models():
    best = get_best_models()
    additional = [
        # ── Additional general-purpose models ────────────────────────────
        {
            "name": "qwen3:0.6b",
            "description": "Qwen 3 ultra-light dense model",
            "parameter_size": "0.6B",
            "size": "0.4GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "qwen3:4b",
            "description": "Qwen 3 small dense model with reasoning & tools",
            "parameter_size": "4B",
            "size": "2.6GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "qwen3:30b",
            "description": "Qwen 3 30B MoE model with reasoning & tools",
            "parameter_size": "30B",
            "size": "18GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "qwen3:235b",
            "description": "Qwen 3 235B MoE flagship reasoning model",
            "parameter_size": "235B",
            "size": "140GB+",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "llama3.2:1b",
            "description": "Meta Llama 3.2 ultra-small with tool calling",
            "parameter_size": "1B",
            "size": "0.7GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "gemma3:1b",
            "description": "Google Gemma 3 ultra-compact model",
            "parameter_size": "1B",
            "size": "0.8GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "deepseek-r1:1.5b",
            "description": "DeepSeek R1 tiny reasoning model",
            "parameter_size": "1.5B",
            "size": "1.1GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "deepseek-r1:70b",
            "description": "DeepSeek R1 70B reasoning model",
            "parameter_size": "70B",
            "size": "40GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "deepseek-r1:671b",
            "description": "DeepSeek R1 full-scale 671B reasoning model",
            "parameter_size": "671B",
            "size": "400GB+",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "gpt-oss:120b",
            "description": "OpenAI open-weight large reasoning & agentic model",
            "parameter_size": "120B",
            "size": "72GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "mistral-nemo:12b",
            "description": "Mistral Nemo 12B, 128K context, built with NVIDIA",
            "parameter_size": "12B",
            "size": "7.1GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "mistral-small:24b",
            "description": "Mistral Small 3 — high-performance under 70B",
            "parameter_size": "24B",
            "size": "14GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "mistral-large:123b",
            "description": "Mistral Large 2 flagship with tool calling",
            "parameter_size": "123B",
            "size": "72GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "magistral:24b",
            "description": "Mistral Magistral 24B efficient reasoning model",
            "parameter_size": "24B",
            "size": "14GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "command-r:35b",
            "description": "Cohere Command R with function calling",
            "parameter_size": "35B",
            "size": "20GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "command-r7b:7b",
            "description": "Cohere Command R7B lightweight model with tools",
            "parameter_size": "7B",
            "size": "4.4GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "command-a:111b",
            "description": "Cohere Command A — enterprise-grade 111B",
            "parameter_size": "111B",
            "size": "66GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "aya:8b",
            "description": "Cohere Aya multilingual with tool calling",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "hermes3:8b",
            "description": "Nous Hermes 3 with function calling",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "cogito:8b",
            "description": "Deep Cogito hybrid reasoning model with tool calling",
            "parameter_size": "8B",
            "size": "4.9GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "cogito:14b",
            "description": "Deep Cogito 14B reasoning model with tools",
            "parameter_size": "14B",
            "size": "8.7GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "olmo2:7b",
            "description": "AI2 OLMo 2 open language model, 7B",
            "parameter_size": "7B",
            "size": "4.4GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "falcon3:7b",
            "description": "TII Falcon 3 efficient model for science & coding",
            "parameter_size": "7B",
            "size": "4.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma:7b",
            "description": "Google Gemma 7B (v1.1)",
            "parameter_size": "7B",
            "size": "4.8GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma2:9b",
            "description": "Google Gemma 2 high-performing 9B model",
            "parameter_size": "9B",
            "size": "5.4GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma3n:e4b",
            "description": "Google Gemma 3n optimized for on-device usage",
            "parameter_size": "e4B",
            "size": "3.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "granite3.3:8b",
            "description": "IBM Granite 3.3 128K context with tool calling",
            "parameter_size": "8B",
            "size": "4.9GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "granite4:3b",
            "description": "IBM Granite 4 with tool calling, enterprise-ready",
            "parameter_size": "3B",
            "size": "1.9GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        # ── Vision models ────────────────────────────────────────────────
        {
            "name": "qwen3-vl:8b",
            "description": "Qwen 3 Vision-Language model with tools & thinking",
            "parameter_size": "8B",
            "size": "5.6GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "qwen3-vl:32b",
            "description": "Qwen 3 Vision-Language 32B with tools & thinking",
            "parameter_size": "32B",
            "size": "19GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "qwen2.5-vl:14b",
            "description": "Qwen 2.5 Vision Language medium",
            "parameter_size": "14B",
            "size": "14GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "qwen2.5vl:7b",
            "description": "Qwen 2.5 VL flagship vision-language model",
            "parameter_size": "7B",
            "size": "5.1GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llama3.2-vision:90b",
            "description": "Meta Llama 3.2 Vision 90B large image reasoning",
            "parameter_size": "90B",
            "size": "54GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llama4:16x17b",
            "description": "Meta Llama 4 Scout multimodal MoE with vision & tools",
            "parameter_size": "16x17B",
            "size": "55GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "mistral-small3.2:24b",
            "description": "Mistral Small 3.2 with vision & tool calling",
            "parameter_size": "24B",
            "size": "14GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "mistral-small3.1:24b",
            "description": "Mistral Small 3.1 vision + 128K context",
            "parameter_size": "24B",
            "size": "14GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "granite3.2-vision:2b",
            "description": "IBM Granite 3.2 Vision for document understanding",
            "parameter_size": "2B",
            "size": "1.8GB",
            "has_vision": True,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "bakllava:7b",
            "description": "BakLLaVA — Mistral 7B augmented with LLaVA vision",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "bakllava",
            "description": "BakLLaVA multimodal variant (alias)",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llava-phi3:mini",
            "description": "LLaVA based on Phi-3 mini",
            "parameter_size": "3.8B",
            "size": "2.9GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        # ── Reasoning models ─────────────────────────────────────────────
        {
            "name": "qwq:32b",
            "description": "Qwen QwQ reasoning specialist with tool calling",
            "parameter_size": "32B",
            "size": "19GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": True
        },
        {
            "name": "phi4-reasoning:14b",
            "description": "Microsoft Phi-4 Reasoning, rivaling larger models",
            "parameter_size": "14B",
            "size": "8.4GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "phi4-mini-reasoning:3.8b",
            "description": "Microsoft Phi-4 Mini Reasoning, lightweight reasoner",
            "parameter_size": "3.8B",
            "size": "2.4GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "deepscaler:1.5b",
            "description": "R1-distilled reasoning model, strong math perf at 1.5B",
            "parameter_size": "1.5B",
            "size": "1.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "openthinker:7b",
            "description": "Open-source family of reasoning models (R1 distill)",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "exaone-deep:7.8b",
            "description": "LG AI EXAONE Deep reasoning — math & coding",
            "parameter_size": "7.8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "marco-o1:7b",
            "description": "Alibaba AIDC open reasoning model",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        # ── Coding models ────────────────────────────────────────────────
        {
            "name": "qwen2.5-coder:14b",
            "description": "Qwen 2.5 Coder 14B with tool calling",
            "parameter_size": "14B",
            "size": "8.2GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "qwen2.5-coder:32b",
            "description": "Qwen 2.5 Coder 32B with tool calling",
            "parameter_size": "32B",
            "size": "19GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "codestral:22b",
            "description": "Mistral Codestral — code generation specialist",
            "parameter_size": "22B",
            "size": "12GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "devstral:24b",
            "description": "Mistral Devstral — best open-source coding agent model",
            "parameter_size": "24B",
            "size": "14GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "deepcoder:14b",
            "description": "DeepCoder 14B open-source coder at O3-mini level",
            "parameter_size": "14B",
            "size": "8.2GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "deepcoder:1.5b",
            "description": "DeepCoder 1.5B lightweight coding model",
            "parameter_size": "1.5B",
            "size": "1.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "codellama:7b",
            "description": "Meta Code Llama programming specialist",
            "parameter_size": "7B",
            "size": "3.8GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "deepseek-coder:6.7b",
            "description": "DeepSeek Coder programming model",
            "parameter_size": "6.7B",
            "size": "3.9GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "deepseek-coder-v2:16b",
            "description": "DeepSeek Coder V2 MoE, GPT-4 Turbo level coding",
            "parameter_size": "16B",
            "size": "8.9GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "codegemma:7b",
            "description": "Google CodeGemma for code completion & generation",
            "parameter_size": "7B",
            "size": "4.8GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "starcoder2:7b",
            "description": "StarCoder2 open code LLM",
            "parameter_size": "7B",
            "size": "4.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        # ── Classic / legacy models ──────────────────────────────────────
        {
            "name": "llama3:8b",
            "description": "Meta Llama 3 base model",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "llama2:7b",
            "description": "Meta Llama 2 (legacy)",
            "parameter_size": "7B",
            "size": "3.8GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "deepseek-v3:671b",
            "description": "DeepSeek V3 MoE flagship (37B active per token)",
            "parameter_size": "671B",
            "size": "400GB+",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        # ── Lightweight / edge models ────────────────────────────────────
        {
            "name": "tinyllama:1.1b",
            "description": "Compact 1.1B Llama model, trained on 3T tokens",
            "parameter_size": "1.1B",
            "size": "0.6GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "phi3:medium",
            "description": "Microsoft Phi-3 medium (14B) model",
            "parameter_size": "14B",
            "size": "7.9GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "phi3.5:3.8b",
            "description": "Microsoft Phi-3.5 lightweight model",
            "parameter_size": "3.8B",
            "size": "2.3GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma2:27b",
            "description": "Google Gemma 2 large 27B model",
            "parameter_size": "27B",
            "size": "16GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        # ── Specialized / uncensored models ──────────────────────────────
        {
            "name": "dolphin3:8b",
            "description": "Dolphin 3.0 general-purpose, coding & agentic",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "dolphin-mixtral:8x7b",
            "description": "Uncensored Mixtral variant by Eric Hartford",
            "parameter_size": "8x7B",
            "size": "26GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "wizardlm2:7b",
            "description": "Microsoft WizardLM 2 — chat, reasoning & agents",
            "parameter_size": "7B",
            "size": "4.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "yi:9b",
            "description": "01.AI Yi 1.5 bilingual high-performing model",
            "parameter_size": "9B",
            "size": "5.4GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "glm4:9b",
            "description": "Zhipu GLM-4 multi-lingual general model",
            "parameter_size": "9B",
            "size": "5.5GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
    ]
    return best + additional


def get_downloadable_models(category='best'):
    if category == 'all':
        return get_all_downloadable_models()
    return get_best_models()
