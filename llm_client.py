"""
Unified LLM client for Ollama (local dev) and xAI API (production).
"""

from __future__ import annotations

import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

VALID_PROVIDERS = {'ollama', 'xai'}
DEFAULT_OLLAMA_HOST = 'http://localhost:11434'
DEFAULT_OLLAMA_MODEL = 'qwen3:8b'
DEFAULT_XAI_MODEL = 'grok-4.20-0309-non-reasoning'
DEFAULT_XAI_API_BASE = 'https://api.x.ai/v1'
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = (1, 2, 4)


class LLMConfigurationError(RuntimeError):
    """Raised when LLM provider environment is invalid."""


def get_provider() -> str:
    provider = os.environ.get('LLM_PROVIDER', 'ollama').strip().lower()
    if provider not in VALID_PROVIDERS:
        raise LLMConfigurationError(
            f"Invalid LLM_PROVIDER '{provider}'. Expected one of: {', '.join(sorted(VALID_PROVIDERS))}"
        )
    return provider


def validate_llm_config() -> None:
    """Fail fast when production LLM settings are missing."""
    provider = get_provider()
    if provider == 'xai' and not os.environ.get('XAI_API_KEY', '').strip():
        raise LLMConfigurationError(
            'LLM_PROVIDER=xai requires XAI_API_KEY to be set in the environment.'
        )


def _ollama_host() -> str:
    return os.environ.get('OLLAMA_HOST', DEFAULT_OLLAMA_HOST).rstrip('/')


def _ollama_model() -> str:
    return os.environ.get('OLLAMA_MODEL', DEFAULT_OLLAMA_MODEL)


def _xai_api_base() -> str:
    return os.environ.get('XAI_API_BASE', DEFAULT_XAI_API_BASE).rstrip('/')


def _xai_model() -> str:
    return os.environ.get('XAI_MODEL', DEFAULT_XAI_MODEL)


def _xai_api_key() -> str:
    api_key = os.environ.get('XAI_API_KEY', '').strip()
    if not api_key:
        raise LLMConfigurationError('XAI_API_KEY is required when LLM_PROVIDER=xai.')
    return api_key


def _should_retry(exc: Exception, response: Optional[requests.Response]) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True

    status_code = getattr(response, 'status_code', None)
    if status_code is None and isinstance(exc, requests.HTTPError):
        status_code = getattr(exc.response, 'status_code', None)

    return status_code in {429, 500, 502, 503, 504}


def _extract_ollama_text(payload) -> Optional[str]:
    if isinstance(payload, dict):
        if 'results' in payload and isinstance(payload['results'], list):
            for result in payload['results']:
                if isinstance(result, dict):
                    for key in ('output', 'generated', 'text', 'response', 'content'):
                        value = result.get(key)
                        if value:
                            return str(value).strip()
        for key in ('output', 'generated', 'text', 'response', 'content'):
            value = payload.get(key)
            if value:
                return str(value).strip()
    return None


def _extract_xai_text(payload) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    choices = payload.get('choices') or []
    if not choices:
        return None
    message = choices[0].get('message') or {}
    content = message.get('content')
    if content is None:
        return None
    return str(content).strip()


def _post_with_retries(url: str, *, headers: dict, json_payload: dict, timeout: int) -> Optional[requests.Response]:
    last_error = None
    for attempt in range(MAX_RETRIES):
        response = None
        try:
            response = requests.post(url, headers=headers, json=json_payload, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1 and _should_retry(exc, response):
                time.sleep(RETRY_BACKOFF_SECONDS[attempt])
                continue
            break

    status = getattr(getattr(last_error, 'response', None), 'status_code', 'n/a')
    print(f"  ⚠️ LLM request failed after {MAX_RETRIES} attempts ({url}, status={status}): {last_error}")
    return None


def _generate_with_ollama(prompt: str, *, temperature: float, max_tokens: int, timeout: int) -> Optional[str]:
    url = f"{_ollama_host()}/api/generate"
    payload = {
        'model': _ollama_model(),
        'prompt': prompt,
        'stream': False,
        'think': False,
        'options': {
            'temperature': temperature,
            'num_predict': max_tokens,
        },
    }
    response = _post_with_retries(url, headers={'Content-Type': 'application/json'}, json_payload=payload, timeout=timeout)
    if response is None:
        return None

    try:
        data = response.json()
    except ValueError:
        text = response.text.strip()
        return text or None

    return _extract_ollama_text(data)


def _generate_with_xai(prompt: str, *, temperature: float, max_tokens: int, timeout: int) -> Optional[str]:
    url = f"{_xai_api_base()}/chat/completions"
    payload = {
        'model': _xai_model(),
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stream': False,
    }
    response = _post_with_retries(
        url,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {_xai_api_key()}',
        },
        json_payload=payload,
        timeout=timeout,
    )
    if response is None:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    return _extract_xai_text(data)


def generate_text(
    prompt: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 20,
    timeout: int = 60,
) -> Optional[str]:
    """Return trimmed assistant text, or None on failure."""
    if not prompt or not str(prompt).strip():
        return None

    validate_llm_config()
    provider = get_provider()

    if provider == 'xai':
        return _generate_with_xai(prompt, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    return _generate_with_ollama(prompt, temperature=temperature, max_tokens=max_tokens, timeout=timeout)