"""Model catalog definitions: curated and extended downloadable model lists.

Separated from OllamaService to reduce file size of ollama.py. Pure data; no HTTP.
Keep alias entries required by tests (e.g., plain 'llava', 'moondream').
"""

def get_best_models():
    return [
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
            "name": "qwen2.5:7b",
            "description": "Qwen 2.5 with improved tool calling",
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
            "name": "mistral:7b",
            "description": "Mistral AI's 7B model with function calling",
            "parameter_size": "7B",
            "size": "4.1GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "mixtral:8x7b",
            "description": "Mixtral MoE with tool calling",
            "parameter_size": "8x7B",
            "size": "26GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
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
            "name": "llava-llama3:8b",
            "description": "LLaVA based on Llama 3 with vision",
            "parameter_size": "8B",
            "size": "5.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "moondream:1.6b",
            "description": "Tiny vision language model",
            "parameter_size": "1.6B",
            "size": "1.7GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "moondream",
            "description": "Tiny vision language model (alias)",
            "parameter_size": "1.6B",
            "size": "1.7GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        # Alias entries (without variant suffix)
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
        {
            "name": "deepseek-r1:8b",
            "description": "DeepSeek R1 reasoning model",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "deepseek-r1:14b",
            "description": "DeepSeek R1 medium reasoning model",
            "parameter_size": "14B",
            "size": "8.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
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
            "name": "gemma:7b",
            "description": "Google Gemma 7B model",
            "parameter_size": "7B",
            "size": "4.8GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        }
    ]


def get_all_downloadable_models():
    best = get_best_models()
    additional = [
        # Tool-capable models
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
            "name": "aya:8b",
            "description": "Cohere Aya with tool calling",
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
        # Vision models
        {
            "name": "bakllava:7b",
            "description": "Better LLaVA multimodal variant",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "bakllava",
            "description": "Better LLaVA multimodal variant (alias)",
            "parameter_size": "7B",
            "size": "4.5GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "qwen2-vl:7b",
            "description": "Qwen 2 Vision Language model",
            "parameter_size": "7B",
            "size": "7.2GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
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
            "name": "llava-phi3:mini",
            "description": "LLaVA based on Phi-3 mini",
            "parameter_size": "3.8B",
            "size": "2.9GB",
            "has_vision": True,
            "has_tools": False,
            "has_reasoning": False
        },
        # Reasoning models
        {
            "name": "qwq:32b",
            "description": "Qwen with Questions reasoning specialist",
            "parameter_size": "32B",
            "size": "19GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "deepseek-r1:32b",
            "description": "DeepSeek R1 large reasoning model",
            "parameter_size": "32B",
            "size": "19GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        {
            "name": "deepseek-r1:671b",
            "description": "DeepSeek R1 large-scale reasoning model",
            "parameter_size": "671B",
            "size": "400GB+",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": True
        },
        # Classic models
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
            "name": "llama3:8b",
            "description": "Meta Llama 3 base model",
            "parameter_size": "8B",
            "size": "4.7GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        # Code models
        {
            "name": "codellama:7b",
            "description": "Code Llama programming specialist",
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
        # Lightweight models
        {
            "name": "phi3:medium",
            "description": "Microsoft Phi-3 medium model",
            "parameter_size": "4B",
            "size": "2.3GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        {
            "name": "gemma2:2b",
            "description": "Google Gemma 2 small model",
            "parameter_size": "2B",
            "size": "1.3GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        },
        # Specialized models
        {
            "name": "dolphin-mixtral:8x7b",
            "description": "Uncensored Mixtral variant",
            "parameter_size": "8x7B",
            "size": "26GB",
            "has_vision": False,
            "has_tools": True,
            "has_reasoning": False
        },
        {
            "name": "wizardlm:7b",
            "description": "Microsoft WizardLM instruction model",
            "parameter_size": "7B",
            "size": "4.1GB",
            "has_vision": False,
            "has_tools": False,
            "has_reasoning": False
        }
    ]
    return best + additional


def get_downloadable_models(category='best'):
    if category == 'all':
        return get_all_downloadable_models()
    return get_best_models()
