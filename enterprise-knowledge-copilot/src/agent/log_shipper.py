"""Background shipper that forwards audit logs to an external endpoint."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


logger = logging.getLogger(__name__)


@dataclass
class LogShipperConfig:
    endpoint_url: str
    api_key: Optional[str] = None
    batch_size: int = 50
    flush_interval: float = 2.0
    max_retries: int = 5
    retry_backoff: float = 2.0
    verify_ssl: bool = True
    request_timeout: float = 10.0


class LogShipper:
    """Ship structured logs to an HTTP endpoint with buffering and retries."""

    def __init__(self, config: LogShipperConfig):
        self.config = config
        self.queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=5000)
        self._shutdown = threading.Event()
        self._worker = threading.Thread(target=self._run, name="LogShipper", daemon=True)
        self._worker.start()

    def enqueue(self, payload: Dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            logger.warning("Log ship buffer full; dropping payload")

    def shutdown(self) -> None:
        self._shutdown.set()
        self._worker.join(timeout=5)

    def _run(self) -> None:
        client = httpx.Client(timeout=self.config.request_timeout, verify=self.config.verify_ssl)
        buffer: List[Dict[str, Any]] = []

        while not self._shutdown.is_set():
            try:
                item = self.queue.get(timeout=self.config.flush_interval)
                buffer.append(item)
            except queue.Empty:
                pass

            if buffer and (len(buffer) >= self.config.batch_size or self.queue.empty()):
                self._send_batch(client, buffer)
                buffer = []

        # Flush remaining events on shutdown
        if buffer:
            self._send_batch(client, buffer)
        client.close()

    def _send_batch(self, client: httpx.Client, batch: List[Dict[str, Any]]) -> None:
        payload = {"events": batch, "count": len(batch)}
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        attempt = 0
        backoff = 1.0
        while attempt < self.config.max_retries:
            try:
                response = client.post(
                    self.config.endpoint_url,
                    headers=headers,
                    content=json.dumps(payload)
                )
                response.raise_for_status()
                logger.debug("Shipped %d log events", len(batch))
                return
            except Exception as exc:
                attempt += 1
                logger.warning(
                    "Log shipping attempt %d/%d failed: %s",
                    attempt,
                    self.config.max_retries,
                    exc
                )
                time.sleep(backoff)
                backoff *= self.config.retry_backoff
        logger.error("Failed to ship %d log events after %d attempts", len(batch), self.config.max_retries)
