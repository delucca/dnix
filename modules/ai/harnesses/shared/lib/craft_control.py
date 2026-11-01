"""One request to a Craft desktop app's loopback control port."""

import json
import math
import socket
import time


class ControlError(Exception):
    pass


_RESPONSE_LIMIT = 32 * 1024 * 1024


def request(port: int, method: str, params: dict, *, request_limit: int, timeout: float = 70.0):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ControlError("port must be an integer from 1 to 65535")
    if not isinstance(method, str) or not method:
        raise ControlError("method must be a nonempty string")
    if not isinstance(params, dict):
        raise ControlError("params must be a JSON object")
    if type(request_limit) is not int or request_limit <= 0:
        raise ControlError("request limit must be a positive integer")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ControlError("timeout must be a finite positive number")
    try:
        payload = json.dumps({"id": 1, "method": method, "params": params}, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ControlError(f"request is not valid JSON: {exc}") from exc
    if len(payload) > request_limit:
        raise ControlError(f"request exceeds {request_limit} bytes")

    deadline = time.monotonic() + timeout

    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("deadline expired")
        return left

    try:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            connection.settimeout(remaining())
            connection.connect(("127.0.0.1", port))
        except (OSError, TimeoutError) as exc:
            connection.close()
            raise ControlError(f"cannot connect to 127.0.0.1:{port}; nothing was sent. Start the app with --control {port}: {exc}") from exc
    except OSError as exc:
        raise ControlError(f"cannot connect to 127.0.0.1:{port}; nothing was sent: {exc}") from exc

    with connection:
        try:
            data = payload + b"\n"
            sent = 0
            while sent < len(data):
                connection.settimeout(remaining())
                count = connection.send(data[sent:])
                if count == 0:
                    raise ConnectionError("connection closed while sending")
                sent += count

            reply = bytearray()
            while True:
                connection.settimeout(remaining())
                chunk = connection.recv(65536)
                if not chunk:
                    raise ConnectionError("connection closed before a complete reply")
                newline = chunk.find(b"\n")
                reply.extend(chunk if newline < 0 else chunk[:newline])
                if len(reply) > _RESPONSE_LIMIT:
                    raise ValueError("reply exceeds 32 MiB")
                if newline >= 0:
                    break

            try:
                message = json.loads(reply.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (UnicodeError, ValueError) as exc:
                raise ValueError(f"malformed reply: {exc}") from exc
            if not isinstance(message, dict):
                raise ValueError("reply is not an object")
            if type(message.get("id")) is not int or message["id"] != 1:
                raise ValueError("reply ID does not match request")
            if type(message.get("ok")) is not bool:
                raise ValueError("reply ok is not a boolean")
            if not message["ok"]:
                error = message.get("error")
                if not isinstance(error, str):
                    raise ValueError("error reply has no string error")
                raise ControlError(error)
            if "result" not in message:
                raise ValueError("success reply has no result")
            return message["result"]
        except ControlError:
            raise
        except (OSError, TimeoutError, ValueError, ConnectionError) as exc:
            raise ControlError(f"control reply failed after transmission may have begun; the action may have run. Inspect the app before retrying: {exc}") from exc
