"""Enhanced LLM client for OpenRouter / OpenAI-compatible chat API.

Standard library only.
Features:
- Reads LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (falls back to OPENROUTER_API_KEY).
- Disk caching by SHA-256 hash in .cache/ (zero cost on repeated prompts).
- Concurrency & retry with exponential backoff & jitter for 429/5xx errors.
- Appends token usage to usage.jsonl (same format as starter kit llm.py).
"""
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_DIR = Path(".cache_llm")


def get_credentials():
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    base_url = (os.environ.get("LLM_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL") or "openai/gpt-4o-mini"
    return api_key, base_url, model


def prompt_hash(model, messages, temperature, response_format):
    payload = json.dumps({"m": model, "msgs": messages, "t": temperature, "rf": response_format}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def chat(messages, model=None, temperature=0, max_tokens=None, response_format=None, timeout=60, max_retries=4):
    """Call the LLM with disk caching, retry/backoff, and token logging.
    
    Returns response text, or None if API key is not configured or all retries fail.
    """
    api_key, base_url, default_model = get_credentials()
    if not api_key:
        return None

    use_model = model or default_model

    # Check disk cache
    CACHE_DIR.mkdir(exist_ok=True)
    h = prompt_hash(use_model, messages, temperature, response_format)
    cache_file = CACHE_DIR / f"{h}.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            return cached.get("content")
        except Exception:
            pass

    body = {
        "model": use_model,
        "messages": messages,
        "temperature": temperature
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    if response_format:
        body["response_format"] = response_format

    req_data = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://goals.xpert.chat",
        "X-Title": "Cold Start Intern Challenge"
    }

    url = f"{base_url}/chat/completions"

    for attempt in range(max_retries):
        started = time.time()
        try:
            req = urllib.request.Request(url, data=req_data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}

            # Log usage
            try:
                with open("usage.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "model": use_model,
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "seconds": round(time.time() - started, 2)
                    }) + "\n")
            except Exception:
                pass

            # Save cache
            try:
                cache_file.write_text(json.dumps({"content": content}), encoding="utf-8")
            except Exception:
                pass

            return content

        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
            status_code = getattr(e, "code", None)
            if status_code in (400, 401, 403):
                # Fatal client errors, don't retry endlessly
                print(f"[LLM] Fatal API error {status_code}: {e}")
                return None

            backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
            if attempt < max_retries - 1:
                time.sleep(backoff)
            else:
                print(f"[LLM] Failed after {max_retries} attempts: {e}")
                return None

    return None
