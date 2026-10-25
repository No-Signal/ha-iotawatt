"""HTTP connection helper for the IoTaWatt device.

Modified as part of the iotawattpy-nosignal fork
(https://github.com/No-Signal/iotawattpy), see README.md.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

LOGGER = logging.getLogger(__name__)


class Connection:
    """Thin async HTTP wrapper around an httpx client."""

    def __init__(
        self,
        websession: httpx.AsyncClient,
        host: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the connection helper.

        With a username, a single ``httpx.DigestAuth`` is shared by every
        request. It caches the last challenge, so only the first request pays
        for the extra 401 round trip.

        Requests are serialised: the device firmware (ESP8266WebServer) serves
        one connection at a time, so overlapping requests would queue on the
        device or time out.
        """
        self._host = host
        self._websession = websession
        self._auth = (
            httpx.DigestAuth(username, password or "") if username is not None else None
        )
        self._lock = asyncio.Lock()

    async def get(self, url: str) -> httpx.Response:
        """Perform a GET request, with digest auth if credentials are set."""
        async with self._lock:
            LOGGER.debug("URL: %s", url)
            try:
                return await self._websession.get(url, auth=self._auth)
            except httpx.HTTPError:
                LOGGER.debug("HTTP error while requesting %s", url, exc_info=True)
                raise
