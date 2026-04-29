from __future__ import annotations

from collections import deque
from typing import Any

from app.ws import WebSocketHub


confirmed_history: deque[dict[str, Any]] = deque(maxlen=200)
raw_history: deque[dict[str, Any]] = deque(maxlen=1000)
ws_hub = WebSocketHub()
