from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from cryptography.hazmat.primitives.asymmetric import ec

from .credentials import CredentialsProvider, resolve
from .endpoints import get_jwks_url
from .enums import BancontactEnvironment
from .signing import jwk_to_public_key


@dataclass
class _EnvironmentCache:
    keys: dict[str, ec.EllipticCurvePublicKey] = field(default_factory=dict)
    generation: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class JwksClient:
    """Fetches and caches Bancontact's JWKS, one cache per environment.

    Follows the callback guide: keys are re-fetched when a ``kid`` is not found (Bancontact can rotate keys without
    notice, publishing a new key 24 hours before the old one is removed). Concurrent misses are coalesced into one
    fetch. Keys are also dropped after ``max_age_seconds`` (the guide allows caching for up to 12 hours).

    Long-lived by design: build one and keep it, never one per call.
    """

    def __init__(
        self,
        credentials: CredentialsProvider,
        http_client: httpx.AsyncClient | None = None,
        max_age_seconds: float = 12 * 3600,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._credentials = credentials
        self._http = http_client or httpx.AsyncClient(timeout=30)
        self._max_age = max_age_seconds
        self._clock = clock or time.monotonic
        self._caches: dict[BancontactEnvironment, _EnvironmentCache] = {}
        self._fetched_at: dict[BancontactEnvironment, float] = {}

    async def get_key(self, kid: str) -> ec.EllipticCurvePublicKey | None:
        environment = BancontactEnvironment((await resolve(self._credentials)).environment)
        cache = self._caches.setdefault(environment, _EnvironmentCache())

        fresh = self._clock() - self._fetched_at.get(environment, float("-inf")) < self._max_age
        key = cache.keys.get(kid) if fresh else None
        if key is not None:
            return key

        seen_generation = cache.generation
        async with cache.lock:
            if cache.generation != seen_generation:
                # Another thread refreshed while this one waited: use its result instead of fetching again.
                return cache.keys.get(kid)
            keys = await self._fetch(environment)
            cache.keys = keys
            cache.generation += 1
            self._fetched_at[environment] = self._clock()
            return keys.get(kid)

    async def _fetch(self, environment: BancontactEnvironment) -> dict[str, ec.EllipticCurvePublicKey]:
        response = await self._http.get(get_jwks_url(environment))
        response.raise_for_status()
        keys: dict[str, ec.EllipticCurvePublicKey] = {}
        for jwk in response.json().get("keys", []):
            kid = jwk.get("kid")
            if kid is None:
                continue
            key = jwk_to_public_key(jwk)
            if key is not None:
                keys[kid] = key
        return keys
