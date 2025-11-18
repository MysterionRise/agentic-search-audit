# Vision Model Provider Setup Guide

This guide explains how to set up and use different vision model providers for intelligent search box detection in Agentic Search Audit.

## Overview

The intelligent search box detection feature supports multiple vision model providers:

- **vLLM** - Local or self-hosted vision models (no API costs, full privacy)
- **OpenRouter** - Cloud-based unified API for multiple vision models (Qwen-VL, Claude, GPT-4V, etc.)
- **OpenAI** - Direct OpenAI API (GPT-4o, GPT-4o-mini with vision)
- **Anthropic** - Claude 3.5 Sonnet (coming soon)

## Supported Providers

1. **vLLM** - Local or self-hosted vision models (LLaVA, Qwen-VL, etc.)
2. **OpenRouter** - Cloud API gateway for multiple vision models
3. **OpenAI** - GPT-4o, GPT-4o-mini with vision
4. **Anthropic** - Claude 3.5 Sonnet (coming soon)

## Quick Start with vLLM

### Prerequisites

- Python 3.10+
- CUDA-capable GPU (recommended: 16GB+ VRAM for LLaVA-v1.6-7B)
- vLLM installed

### 1. Install vLLM

```bash
# Install vLLM with CUDA support
pip install vllm

# For CPU-only (not recommended for vision models)
pip install vllm-cpu-only
```

### 2. Start vLLM Server

Choose a vision-capable model and start the vLLM server:

```bash
# Example: LLaVA v1.6 Mistral 7B (requires ~16GB VRAM)
vllm serve llava-hf/llava-v1.6-mistral-7b-hf \
    --dtype auto \
    --api-key EMPTY \
    --port 8000

# Example: Qwen-VL (requires ~20GB VRAM)
vllm serve Qwen/Qwen-VL-Chat \
    --dtype auto \
    --api-key EMPTY \
    --port 8000

# For multi-GPU setups
vllm serve llava-hf/llava-v1.6-mistral-7b-hf \
    --tensor-parallel-size 2 \
    --dtype auto \
    --port 8000
```

The server will start on `http://localhost:8000` with an OpenAI-compatible API.

### 3. Configure Agentic Search Audit

Update your `configs/default.yaml` or site-specific config:

```yaml
llm:
  provider: "vllm"
  model: "llava-hf/llava-v1.6-mistral-7b-hf"  # Must match server model
  max_tokens: 1000
  temperature: 0.2
  base_url: "http://localhost:8000/v1"
  api_key: null  # or set VLLM_API_KEY env var
```

### 4. Run Your Audit

```bash
# The audit will now use your local vLLM server for vision detection
search-audit --site nike --config configs/sites/nike.yaml
```

---

## Quick Start with OpenRouter

OpenRouter provides a unified API gateway for accessing multiple vision models from different providers through a single endpoint. No GPU required!

### Prerequisites

- OpenRouter account (sign up at https://openrouter.ai/)
- OpenRouter API key

### 1. Get OpenRouter API Key

1. Sign up at https://openrouter.ai/
2. Go to https://openrouter.ai/keys
3. Create a new API key
4. Copy your key (starts with `sk-or-...`)

### 2. Configure Environment

Add your API key to `.env`:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

### 3. Configure Agentic Search Audit

Update your `configs/default.yaml` or use `configs/openrouter-example.yaml`:

```yaml
llm:
  provider: "openrouter"
  model: "qwen/qwen-vl-plus"  # Recommended for vision tasks
  max_tokens: 1000
  temperature: 0.2
  base_url: "https://openrouter.ai/api/v1"  # Default, can be omitted
  api_key: null  # Uses OPENROUTER_API_KEY env var
```

### 4. Run Your Audit

```bash
# The audit will now use OpenRouter's cloud API
search-audit --site nike --config configs/openrouter-example.yaml
```

### Available Vision Models on OpenRouter

| Model | Provider | Quality | Speed | Cost (per 1M tokens) | Best For |
|-------|----------|---------|-------|---------------------|----------|
| `qwen/qwen-vl-plus` | Alibaba | Excellent | Fast | $8 | **Recommended - Best value** |
| `qwen/qwen-vl-max` | Alibaba | Superior | Medium | $20 | Highest quality |
| `anthropic/claude-3.5-sonnet` | Anthropic | Excellent | Fast | $3 | General vision tasks |
| `openai/gpt-4-vision-preview` | OpenAI | Excellent | Medium | $10 | Complex analysis |
| `google/gemini-pro-vision` | Google | Good | Fast | $2.50 | Budget option |

**Note**: Pricing is approximate and may change. Check https://openrouter.ai/models for current pricing.

### Why Use OpenRouter?

- ✅ **No GPU needed** - Cloud-based, works on any machine
- ✅ **Multiple models** - Easy to switch between providers
- ✅ **Pay-as-you-go** - Only pay for what you use
- ✅ **Unified API** - Single integration for all providers
- ✅ **No rate limits** - (depends on your plan)
- ✅ **Fallback support** - Automatic fallback to other models if primary fails

---

## Recommended Vision Models (vLLM)

### LLaVA Models (Best for General Use)

| Model | VRAM | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| `llava-hf/llava-1.5-7b-hf` | 14GB | Fast | Good | Quick testing |
| `llava-hf/llava-v1.6-mistral-7b-hf` | 16GB | Medium | Better | **Recommended** |
| `llava-hf/llava-v1.6-34b-hf` | 70GB | Slow | Best | Production |

### Qwen-VL Models (Better for Chinese + English)

| Model | VRAM | Speed | Quality |
|-------|------|-------|---------|
| `Qwen/Qwen-VL-Chat` | 20GB | Medium | Excellent |
| `Qwen/Qwen-VL-Plus` | 30GB | Slow | Superior |

### Other Options

- **CogVLM**: `THUDM/cogvlm-chat-hf` (requires 24GB+ VRAM)
- **InternVL**: `OpenGVLab/InternVL-Chat-V1-5` (multi-lingual)

## Configuration Examples

### Local vLLM Server

```yaml
llm:
  provider: "vllm"
  model: "llava-hf/llava-v1.6-mistral-7b-hf"
  base_url: "http://localhost:8000/v1"
  api_key: null
  max_tokens: 1000
  temperature: 0.2
```

### Remote vLLM Server (Cloud/On-Prem)

```yaml
llm:
  provider: "vllm"
  model: "llava-hf/llava-v1.6-mistral-7b-hf"
  base_url: "https://your-vllm-server.com/v1"
  api_key: "your-api-key"
  max_tokens: 1000
  temperature: 0.2
```

### Fallback to OpenAI

```yaml
llm:
  provider: "openai"
  model: "gpt-4o-mini"
  api_key: null  # uses OPENAI_API_KEY env var
  max_tokens: 800
  temperature: 0.2
```

## Environment Variables

Set these in your `.env` file:

```bash
# For vLLM
VLLM_API_KEY=your-api-key  # Optional, if server requires auth

# For OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...

# For OpenAI direct API
OPENAI_API_KEY=sk-...

# For Anthropic (future)
ANTHROPIC_API_KEY=sk-ant-...
```

## Troubleshooting

### vLLM Server Not Responding

```bash
# Check if server is running
curl http://localhost:8000/v1/models

# Should return JSON with your model listed
```

### Out of Memory Error

- Use a smaller model (e.g., LLaVA-1.5-7B instead of 34B)
- Enable tensor parallelism: `--tensor-parallel-size 2`
- Reduce batch size: `--max-num-seqs 8`

### JSON Parsing Errors

Some vLLM models may not support strict JSON output mode. The system will automatically try to extract JSON from markdown code blocks.

If you see parsing errors:
1. Try adjusting the temperature (lower = more consistent)
2. Use a model known for better instruction following (LLaVA-v1.6+)
3. Check the logs for the raw response

### Model Download Issues

Models are downloaded from HuggingFace on first run:

```bash
# Pre-download model
huggingface-cli download llava-hf/llava-v1.6-mistral-7b-hf

# Or set custom cache directory
export HF_HOME=/path/to/cache
vllm serve llava-hf/llava-v1.6-mistral-7b-hf
```

## Performance Tips

### GPU Memory Optimization

```bash
# Enable KV cache quantization (saves ~40% memory)
vllm serve llava-hf/llava-v1.6-mistral-7b-hf \
    --quantization awq \
    --dtype auto

# Use float16 precision
vllm serve llava-hf/llava-v1.6-mistral-7b-hf \
    --dtype float16
```

### Speed Optimization

```bash
# Increase batch size (if you have VRAM)
vllm serve llava-hf/llava-v1.6-mistral-7b-hf \
    --max-num-seqs 16 \
    --max-model-len 4096
```

## Architecture Notes

### How It Works

1. **Vision Provider Abstraction**: `src/agentic_search_audit/extractors/vision_provider.py`
   - Supports multiple vision providers (OpenAI, vLLM, Anthropic)
   - Factory pattern for easy provider switching

2. **Intelligent Finder**: `src/agentic_search_audit/extractors/intelligent_finder.py`
   - Takes screenshot + HTML snippet
   - Calls vision provider to analyze page
   - Returns CSS selectors for search box

3. **OpenAI-Compatible API**: vLLM implements the same API as OpenAI
   - Same request/response format
   - Drop-in replacement

### Model Selection Flow

```
Configuration (YAML)
    ↓
LLMConfig (provider, model, base_url)
    ↓
VisionProviderFactory
    ├─→ OpenAIVisionProvider (if provider="openai")
    ├─→ VLLMVisionProvider (if provider="vllm")
    ├─→ OpenRouterVisionProvider (if provider="openrouter")
    └─→ AnthropicVisionProvider (if provider="anthropic")
    ↓
IntelligentSearchBoxFinder
    ↓
Vision Analysis (screenshot + prompt)
    ↓
CSS Selectors + Confidence
```

## Cost & Privacy Comparison

| Provider | Cost (per 1K images) | Privacy | Latency | Quality |
|----------|---------------------|---------|---------|---------|
| vLLM (local) | $0 (GPU cost) | ✅ Full | Low | Good-Excellent |
| OpenRouter (Qwen-VL-Plus) | ~$0.08 | ⚠️ API | Low | Excellent |
| OpenRouter (Qwen-VL-Max) | ~$0.20 | ⚠️ API | Medium | Superior |
| OpenAI GPT-4o-mini | ~$0.15 | ⚠️ API | Medium | Excellent |
| OpenAI GPT-4o | ~$1.50 | ⚠️ API | Medium | Superior |

**Recommendation by Use Case:**
- **Best for privacy & zero cost**: vLLM (requires GPU)
- **Best value cloud option**: OpenRouter with Qwen-VL-Plus (8x cheaper than GPT-4o)
- **Best quality cloud option**: OpenRouter with Qwen-VL-Max or GPT-4o
- **Easiest setup**: OpenRouter or OpenAI (no GPU needed)

## FAQ

**Q: Can I use multiple vision providers?**
A: Yes! Configure different providers per site in your site-specific YAML files.

**Q: Which model should I use?**
A: Start with `llava-v1.6-mistral-7b-hf`. It offers the best balance of quality, speed, and VRAM usage.

**Q: Do I need a GPU?**
A: Highly recommended. Vision models are very slow on CPU. Minimum 16GB VRAM for 7B models.

**Q: Can I use this with cloud GPU providers?**
A: Yes! Deploy vLLM on RunPod, Lambda Labs, Vast.ai, etc., and point `base_url` to your server.

**Q: What if vLLM detection fails?**
A: The system will log errors and fall back to CSS selectors. Check logs for details.

## Support

For issues specific to:
- **vLLM**: https://github.com/vllm-project/vllm/issues
- **LLaVA models**: https://github.com/haotian-liu/LLaVA/issues
- **This integration**: Open an issue in the agentic-search-audit repo

## Next Steps

- Try different vision models and compare results
- Fine-tune a model on your specific search UI patterns
- Contribute support for new vision providers
