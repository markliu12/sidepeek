"""Small Bark push client using only the Python standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def send_push(
    device_key: str,
    title: str,
    body: str,
    icon_url: str = "",
    timeout: float = 5.0,
) -> None:
    """Send one notification through Bark's hosted API.

    The key is part of the request path as required by Bark, but is never
    included in exceptions or application logs.
    """
    message = {"title": title, "body": body, "group": "SidePeek"}
    if icon_url:
        message["icon"] = icon_url
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.day.app/{device_key}",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError("Bark returned an unsuccessful response")
            # Bark can return an application-level error in a 200 response.
            result = json.loads(response.read().decode("utf-8"))
            if isinstance(result, dict) and result.get("code", 200) != 200:
                raise RuntimeError("Bark rejected the notification")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        # Do not chain the exception: urllib errors may include the request URL
        # and therefore the user's device key.
        raise RuntimeError(type(exc).__name__) from None
