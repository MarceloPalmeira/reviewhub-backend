import threading
import time
from collections import OrderedDict

import httpx


class ProviderError(Exception):
    def __init__(
        self, message: str, status: int = 503, upstream_status: int | None = None
    ):
        super().__init__(message)
        self.status = status
        self.upstream_status = upstream_status


class TTLCache:
    def __init__(self, ttl=300, maxsize=256):
        self.ttl, self.maxsize = ttl, maxsize
        self.data = OrderedDict()
        self.lock = threading.RLock()

    def get_or_load(self, key, loader):
        # Serialização evita duplicar consultas simultâneas idênticas.
        with self.lock:
            value = self.data.get(key)
            if value and value[0] > time.monotonic():
                self.data.move_to_end(key)
                return value[1]
            result = loader()
            self.data[key] = (time.monotonic() + self.ttl, result)
            self.data.move_to_end(key)
            while len(self.data) > self.maxsize:
                self.data.popitem(last=False)
            return result


def request(client, method, url, **kwargs):
    try:
        response = client.request(method, url, timeout=4.0, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException as exc:
        raise ProviderError("O provedor demorou para responder", 504) from exc
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            raise ProviderError("Conteúdo externo não encontrado", 404) from exc
        if code == 429:
            raise ProviderError(
                "Limite do provedor atingido; tente novamente mais tarde", 429
            ) from exc
        if code in (401, 403):
            raise ProviderError(
                "Provedor não autorizado ou indisponível", 503, upstream_status=code
            ) from exc
        raise ProviderError("Provedor externo indisponível", 503) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError("Provedor externo indisponível", 503) from exc


class RateGate:
    """Limita chamadas por processo; em produção use um coordenador compartilhado."""

    def __init__(self, interval):
        self.interval = interval
        self.next_allowed = 0.0
        self.lock = threading.Lock()

    def call(self, loader):
        if not self.lock.acquire(blocking=False):
            raise ProviderError("Provedor ocupado; tente novamente em instantes", 429)
        try:
            delay = self.next_allowed - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                return loader()
            finally:
                self.next_allowed = time.monotonic() + self.interval
        finally:
            self.lock.release()
