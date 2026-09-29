import os
from dataclasses import dataclass
from typing import Protocol

import requests
from django.conf import settings


class ProviderError(Exception):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderCallError(ProviderError):
    pass


@dataclass(frozen=True)
class CompletionResult:
    reply: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    mode: str = 'real'


class CompletionBackend(Protocol):
    def complete(self, model, prompt, max_output_tokens): ...


class MockBackend:
    def complete(self, model, prompt, max_output_tokens):
        return CompletionResult(
            reply='MOCK MODE: This simulated reply was generated locally; no provider was contacted.',
            mode='mock',
        )


class ProxyBackend:
    def __init__(self, endpoint, provider, model_key, request_style, api_key):
        self.endpoint = endpoint
        self.provider = provider
        self.model_key = model_key
        self.request_style = request_style
        self.api_key = api_key

    def complete(self, model, prompt, max_output_tokens):
        payload = self._payload(model, prompt, max_output_tokens)
        headers = self._headers()
        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=30,
                allow_redirects=False,
            )
        except Exception:
            raise ProviderCallError('The configured model proxy could not be reached.') from None

        if not 200 <= response.status_code < 300:
            raise ProviderCallError('The configured model proxy returned an error.')

        try:
            data = response.json()
            if self.request_style == 'openai_compatible':
                reply, usage = self._parse_openai(data)
            elif self.provider == 'anthropic':
                reply, usage = self._parse_anthropic(data)
            elif self.provider == 'google':
                reply, usage = self._parse_google(data)
            else:
                reply, usage = self._parse_openai(data)
        except Exception:
            raise ProviderCallError('The configured model proxy returned an unusable response.') from None

        if not isinstance(reply, str) or not reply.strip():
            raise ProviderCallError('The configured model proxy returned no reply text.')

        return CompletionResult(
            reply=reply,
            input_tokens=self._token_count(usage.get('input')),
            output_tokens=self._token_count(usage.get('output')),
            mode='real',
        )

    def _payload(self, model, prompt, max_output_tokens):
        if self.request_style == 'openai_compatible' or self.provider == 'openai':
            return {
                'model': self.model_key,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_output_tokens,
            }
        if self.provider == 'anthropic':
            return {
                'model': self.model_key,
                'max_tokens': max_output_tokens,
                'messages': [{'role': 'user', 'content': prompt}],
            }
        if self.provider == 'google':
            return {
                'model': self.model_key,
                'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
                'generationConfig': {'maxOutputTokens': max_output_tokens},
            }
        raise ProviderConfigurationError('The selected provider is not supported.')

    def _headers(self):
        if self.request_style == 'openai_compatible' or self.provider == 'openai':
            authorization = f'Bearer {self.api_key}'
            return {'Authorization': authorization, 'Content-Type': 'application/json'}
        if self.provider == 'anthropic':
            return {
                'x-api-key': self.api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            }
        if self.provider == 'google':
            return {'x-goog-api-key': self.api_key, 'Content-Type': 'application/json'}
        raise ProviderConfigurationError('The selected provider is not supported.')

    @staticmethod
    def _content_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return ''.join(
                item.get('text', '')
                for item in content
                if isinstance(item, dict) and isinstance(item.get('text', ''), str)
            )
        return ''

    @classmethod
    def _parse_openai(cls, data):
        choice = data['choices'][0]
        message = choice.get('message', {})
        usage = data.get('usage') or {}
        return cls._content_text(message.get('content', choice.get('text', ''))), {
            'input': usage.get('prompt_tokens'),
            'output': usage.get('completion_tokens'),
        }

    @classmethod
    def _parse_anthropic(cls, data):
        usage = data.get('usage') or {}
        return cls._content_text(data.get('content', [])), {
            'input': usage.get('input_tokens'),
            'output': usage.get('output_tokens'),
        }

    @classmethod
    def _parse_google(cls, data):
        candidate = data['candidates'][0]
        content = candidate.get('content', {})
        usage = data.get('usageMetadata') or {}
        return cls._content_text(content.get('parts', [])), {
            'input': usage.get('promptTokenCount'),
            'output': usage.get('candidatesTokenCount'),
        }

    @staticmethod
    def _token_count(value):
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None


def get_backend(model):
    provider = model.provider
    endpoint = (
        getattr(settings, f'{provider.upper()}_PROXY_BASE_URL', '')
        or settings.LLM_PROXY_BASE_URL
    )
    if not endpoint:
        return MockBackend()

    key_names = {
        'openai': 'OPENAI_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'google': 'GOOGLE_API_KEY',
    }
    key = os.getenv(key_names.get(provider, ''), '').strip()
    if not key:
        raise ProviderConfigurationError('A credential is required for the configured provider proxy.')

    request_style = settings.LLM_PROXY_REQUEST_STYLE
    if request_style not in ('openai_compatible', 'provider_native'):
        raise ProviderConfigurationError('The configured proxy request style is missing or unsupported.')

    return ProxyBackend(endpoint, provider, model.model_id, request_style, key)
