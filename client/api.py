"""HTTP layer for the Workbay client (urllib, no dependencies).

Connection errors retry for about 3 seconds so that a server the client
has only just auto-started has time to come up.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_SERVER = "127.0.0.1:8642"
RETRY_WINDOW = 3.0
RETRY_DELAY = 0.25


class ApiUnavailable(Exception):
    """Server could not be reached at all."""


class ApiRequestError(Exception):
    """Server answered with an error status; .message is user-friendly."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class ApiClient:
    def __init__(self, server=DEFAULT_SERVER):
        self.server = server
        self.token = None
        self.user = None

    @property
    def base_url(self):
        server = self.server
        if "://" not in server:
            server = "http://" + server
        return server.rstrip("/")

    # ------------------------------------------------------------ core

    def request(self, method, path, body=None, params=None, retry=True):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v not in (None, "")}
            )
        data = json.dumps(body).encode("utf-8") if body is not None else None
        deadline = time.monotonic() + (RETRY_WINDOW if retry else 0)
        while True:
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Content-Type", "application/json")
            if self.token:
                req.add_header("Authorization", "Bearer " + self.token)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                try:
                    payload = json.loads(exc.read().decode("utf-8"))
                    message = payload.get("error") or f"Server error {exc.code}"
                except Exception:
                    message = f"Server error {exc.code}"
                raise ApiRequestError(exc.code, message)
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                if time.monotonic() >= deadline:
                    raise ApiUnavailable(
                        f"Cannot reach the Workbay server at {self.server}"
                    )
                time.sleep(RETRY_DELAY)

    # ------------------------------------------------------------ auth

    def ping(self, retry=True):
        return self.request("GET", "/api/ping", retry=retry)

    def login(self, username, password):
        result = self.request(
            "POST", "/api/login",
            {"username": username, "password": password},
        )
        self.token = result["token"]
        self.user = result["user"]
        return result

    def logout(self):
        try:
            self.request("POST", "/api/logout", {}, retry=False)
        except (ApiUnavailable, ApiRequestError):
            pass
        self.token = None
        self.user = None

    def register(self, workshop_name, username, password):
        result = self.request(
            "POST", "/api/register",
            {
                "workshop_name": workshop_name,
                "username": username,
                "password": password,
            },
        )
        self.token = result["token"]
        self.user = result["user"]
        return result

    def me(self):
        return self.request("GET", "/api/me")

    def change_password(self, current, new):
        return self.request(
            "POST", "/api/password", {"current": current, "new": new}
        )

    # ------------------------------------------------------- workshops

    def list_workshops(self):
        return self.request("GET", "/api/workshops")["workshops"]

    def get_workshop(self, workshop_id):
        return self.request("GET", f"/api/workshops/{workshop_id}")

    def update_workshop(self, workshop_id, **fields):
        return self.request("PATCH", f"/api/workshops/{workshop_id}", fields)

    def delete_workshop(self, workshop_id):
        return self.request("DELETE", f"/api/workshops/{workshop_id}")

    # -------------------------------------------------------- vehicles

    def list_vehicles(self, scope="open", query="", workshop_id=None):
        return self.request(
            "GET", "/api/vehicles",
            params={"scope": scope, "q": query, "workshop_id": workshop_id},
        )["vehicles"]

    def create_vehicle(self, fields):
        return self.request("POST", "/api/vehicles", fields)

    def get_vehicle(self, vehicle_id):
        return self.request("GET", f"/api/vehicles/{vehicle_id}")

    def update_vehicle(self, vehicle_id, **fields):
        return self.request("PATCH", f"/api/vehicles/{vehicle_id}", fields)

    def delete_vehicle(self, vehicle_id):
        return self.request("DELETE", f"/api/vehicles/{vehicle_id}")

    # ----------------------------------------------- items and parts

    def add_items(self, vehicle_id, text):
        return self.request(
            "POST", f"/api/vehicles/{vehicle_id}/items", {"text": text}
        )

    def set_item_done(self, item_id, done):
        return self.request("PATCH", f"/api/items/{item_id}", {"done": done})

    def delete_item(self, item_id):
        return self.request("DELETE", f"/api/items/{item_id}")

    def add_part(self, vehicle_id, fields):
        return self.request(
            "POST", f"/api/vehicles/{vehicle_id}/parts", fields
        )

    def update_part(self, part_id, **fields):
        return self.request("PATCH", f"/api/parts/{part_id}", fields)

    def delete_part(self, part_id):
        return self.request("DELETE", f"/api/parts/{part_id}")
