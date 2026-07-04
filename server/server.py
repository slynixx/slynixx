"""Workbay JSON API server (pure stdlib http.server).

Runs on port 8642.  Seeds a default admin (admin / admin123) on first run.
Can be imported and started in-process (used by the frozen exe) or run as
a script.
"""

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import auth
    import db
except ImportError:  # imported as a package (e.g. tests)
    from . import auth, db

DEFAULT_PORT = 8642
DEFAULT_ADMIN = ("admin", "admin123")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class WorkbayService:
    """All request handling logic, independent of the HTTP plumbing."""

    def __init__(self, database=None):
        self.db = database or db.Database()
        self.sessions = auth.SessionStore()
        if self.db.create_admin_if_missing(
            DEFAULT_ADMIN[0], auth.hash_password(DEFAULT_ADMIN[1])
        ):
            print("Seeded default admin account: admin / admin123")

    # ---------------------------------------------------------- helpers

    def _require_user(self, token):
        user_id = self.sessions.user_id_for(token or "")
        if not user_id:
            raise ApiError(401, "Not signed in")
        user = self.db.get_user(user_id)
        if not user:
            raise ApiError(401, "Account no longer exists")
        return user

    @staticmethod
    def _require_admin(user):
        if user["role"] != "admin":
            raise ApiError(403, "Admin access required")

    @staticmethod
    def _check_workshop_access(user, workshop_id):
        if user["role"] == "admin":
            return
        if user["workshop_id"] != workshop_id:
            raise ApiError(403, "This vehicle belongs to another workshop")

    @staticmethod
    def _public_user(user):
        return {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "workshop_id": user["workshop_id"],
        }

    # ------------------------------------------------------------ routes

    def handle(self, method, path, body, token):
        """Dispatch to a route handler.  Returns (status, payload)."""
        routes = [
            ("GET", r"^/api/ping$", self.ping),
            ("POST", r"^/api/login$", self.login),
            ("POST", r"^/api/logout$", self.logout),
            ("POST", r"^/api/register$", self.register),
            ("GET", r"^/api/me$", self.me),
            ("POST", r"^/api/password$", self.change_password),
            ("GET", r"^/api/workshops$", self.list_workshops),
            ("GET", r"^/api/workshops/(\d+)$", self.get_workshop),
            ("PATCH", r"^/api/workshops/(\d+)$", self.update_workshop),
            ("DELETE", r"^/api/workshops/(\d+)$", self.delete_workshop),
            ("GET", r"^/api/vehicles$", self.list_vehicles),
            ("POST", r"^/api/vehicles$", self.create_vehicle),
            ("GET", r"^/api/vehicles/(\d+)$", self.get_vehicle),
            ("PATCH", r"^/api/vehicles/(\d+)$", self.update_vehicle),
            ("DELETE", r"^/api/vehicles/(\d+)$", self.delete_vehicle),
            ("POST", r"^/api/vehicles/(\d+)/items$", self.add_items),
            ("PATCH", r"^/api/items/(\d+)$", self.update_item),
            ("DELETE", r"^/api/items/(\d+)$", self.delete_item),
            ("POST", r"^/api/vehicles/(\d+)/parts$", self.add_part),
            ("PATCH", r"^/api/parts/(\d+)$", self.update_part),
            ("DELETE", r"^/api/parts/(\d+)$", self.delete_part),
        ]
        path_only, _, query = path.partition("?")
        for route_method, pattern, handler in routes:
            if route_method != method:
                continue
            match = re.match(pattern, path_only)
            if match:
                params = _parse_query(query)
                args = [int(g) for g in match.groups()]
                return handler(body or {}, token, params, *args)
        raise ApiError(404, f"No such endpoint: {method} {path_only}")

    # ---- auth

    def ping(self, body, token, params):
        return 200, {"ok": True, "app": "workbay"}

    def login(self, body, token, params):
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        user = self.db.get_user_by_username(username)
        if not user or not auth.verify_password(password, user["password_hash"]):
            raise ApiError(401, "Incorrect username or password")
        new_token = self.sessions.create(user["id"])
        return 200, {"token": new_token, "user": self._public_user(user)}

    def logout(self, body, token, params):
        self.sessions.revoke(token or "")
        return 200, {"ok": True}

    def register(self, body, token, params):
        workshop_name = (body.get("workshop_name") or "").strip()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not workshop_name:
            raise ApiError(400, "Workshop name is required")
        if not username:
            raise ApiError(400, "Username is required")
        if len(password) < 4:
            raise ApiError(400, "Password must be at least 4 characters")
        if self.db.get_user_by_username(username):
            raise ApiError(409, "That username is already taken")
        try:
            workshop_id = self.db.create_workshop_with_user(
                workshop_name, username, auth.hash_password(password)
            )
        except Exception:
            raise ApiError(409, "A workshop with that name already exists")
        user = self.db.get_user_by_username(username)
        new_token = self.sessions.create(user["id"])
        return 201, {
            "token": new_token,
            "user": self._public_user(user),
            "workshop_id": workshop_id,
        }

    def me(self, body, token, params):
        user = self._require_user(token)
        result = self._public_user(user)
        if user["workshop_id"]:
            result["workshop"] = self.db.get_workshop(user["workshop_id"])
        return 200, result

    def change_password(self, body, token, params):
        user = self._require_user(token)
        current = body.get("current") or ""
        new = body.get("new") or ""
        if not auth.verify_password(current, user["password_hash"]):
            raise ApiError(400, "Current password is incorrect")
        if len(new) < 4:
            raise ApiError(400, "New password must be at least 4 characters")
        self.db.set_password(user["id"], auth.hash_password(new))
        return 200, {"ok": True}

    # ---- workshops

    def list_workshops(self, body, token, params):
        user = self._require_user(token)
        self._require_admin(user)
        return 200, {"workshops": self.db.list_workshops()}

    def get_workshop(self, body, token, params, workshop_id):
        user = self._require_user(token)
        self._check_workshop_access(user, workshop_id)
        workshop = self.db.get_workshop(workshop_id)
        if not workshop:
            raise ApiError(404, "Workshop not found")
        return 200, workshop

    def update_workshop(self, body, token, params, workshop_id):
        user = self._require_user(token)
        self._check_workshop_access(user, workshop_id)
        if not self.db.get_workshop(workshop_id):
            raise ApiError(404, "Workshop not found")
        name = body.get("name")
        if name is not None:
            name = name.strip()
            if not name:
                raise ApiError(400, "Workshop name cannot be blank")
            if user["role"] != "admin":
                raise ApiError(403, "Only the admin can rename a workshop")
        rate = body.get("labour_rate_cents")
        if rate is not None:
            rate = int(rate)
            if rate < 0:
                raise ApiError(400, "Labour rate cannot be negative")
        self.db.update_workshop(workshop_id, name=name, labour_rate_cents=rate)
        return 200, self.db.get_workshop(workshop_id)

    def delete_workshop(self, body, token, params, workshop_id):
        user = self._require_user(token)
        self._require_admin(user)
        self.db.delete_workshop(workshop_id)
        return 200, {"ok": True}

    # ---- vehicles

    def list_vehicles(self, body, token, params):
        user = self._require_user(token)
        scope = params.get("scope", "open")
        query = params.get("q", "").strip()
        if user["role"] == "admin":
            workshop_id = params.get("workshop_id")
            workshop_id = int(workshop_id) if workshop_id else None
        else:
            workshop_id = user["workshop_id"]
        vehicles = self.db.list_vehicles(
            workshop_id=workshop_id, scope=scope, query=query
        )
        return 200, {"vehicles": vehicles}

    def create_vehicle(self, body, token, params):
        user = self._require_user(token)
        if user["role"] == "admin":
            workshop_id = body.get("workshop_id")
            if not workshop_id:
                raise ApiError(400, "workshop_id is required for admin")
            workshop_id = int(workshop_id)
        else:
            workshop_id = user["workshop_id"]
        registration = (body.get("registration") or "").strip().upper()
        if not registration:
            raise ApiError(400, "Registration is required")
        year = _parse_year(body.get("year"))
        hours = _parse_hours(body.get("labour_hours"))
        items = db.split_items(body.get("job") or "")
        vehicle_id = self.db.create_vehicle(
            workshop_id,
            {
                "registration": registration,
                "year": year,
                "make": (body.get("make") or "").strip(),
                "customer": (body.get("customer") or "").strip(),
                "phone": (body.get("phone") or "").strip(),
                "labour_hours": hours,
            },
            items,
        )
        return 201, self.db.get_vehicle(vehicle_id)

    def _vehicle_or_404(self, user, vehicle_id):
        vehicle = self.db.get_vehicle(vehicle_id)
        if not vehicle:
            raise ApiError(404, "Vehicle not found")
        self._check_workshop_access(user, vehicle["workshop_id"])
        return vehicle

    def get_vehicle(self, body, token, params, vehicle_id):
        user = self._require_user(token)
        return 200, self._vehicle_or_404(user, vehicle_id)

    def update_vehicle(self, body, token, params, vehicle_id):
        user = self._require_user(token)
        self._vehicle_or_404(user, vehicle_id)
        fields = {}
        if "registration" in body:
            registration = (body["registration"] or "").strip().upper()
            if not registration:
                raise ApiError(400, "Registration is required")
            fields["registration"] = registration
        if "year" in body:
            fields["year"] = _parse_year(body["year"])
        for key in ("make", "customer", "phone"):
            if key in body:
                fields[key] = (body[key] or "").strip()
        if "labour_hours" in body:
            fields["labour_hours"] = _parse_hours(body["labour_hours"])
        if "status" in body:
            if body["status"] not in ("open", "done"):
                raise ApiError(400, "Status must be open or done")
            fields["status"] = body["status"]
        self.db.update_vehicle(vehicle_id, fields)
        return 200, self.db.get_vehicle(vehicle_id)

    def delete_vehicle(self, body, token, params, vehicle_id):
        user = self._require_user(token)
        self._vehicle_or_404(user, vehicle_id)
        self.db.delete_vehicle(vehicle_id)
        return 200, {"ok": True}

    # ---- repair items

    def add_items(self, body, token, params, vehicle_id):
        user = self._require_user(token)
        self._vehicle_or_404(user, vehicle_id)
        texts = db.split_items(body.get("text") or "")
        if not texts:
            raise ApiError(400, "Type at least one repair item")
        self.db.add_items(vehicle_id, texts)
        return 201, self.db.get_vehicle(vehicle_id)

    def _item_or_404(self, user, item_id):
        item = self.db.get_item(item_id)
        if not item:
            raise ApiError(404, "Repair item not found")
        self._check_workshop_access(user, item["workshop_id"])
        return item

    def update_item(self, body, token, params, item_id):
        user = self._require_user(token)
        item = self._item_or_404(user, item_id)
        if "done" in body:
            self.db.set_item_done(item_id, bool(body["done"]))
        return 200, self.db.get_vehicle(item["vehicle_id"])

    def delete_item(self, body, token, params, item_id):
        user = self._require_user(token)
        item = self._item_or_404(user, item_id)
        self.db.delete_item(item_id)
        return 200, self.db.get_vehicle(item["vehicle_id"])

    # ---- parts

    def add_part(self, body, token, params, vehicle_id):
        user = self._require_user(token)
        self._vehicle_or_404(user, vehicle_id)
        self.db.add_part(vehicle_id, _clean_part_fields(body, creating=True))
        return 201, self.db.get_vehicle(vehicle_id)

    def _part_or_404(self, user, part_id):
        part = self.db.get_part(part_id)
        if not part:
            raise ApiError(404, "Part not found")
        self._check_workshop_access(user, part["workshop_id"])
        return part

    def update_part(self, body, token, params, part_id):
        user = self._require_user(token)
        part = self._part_or_404(user, part_id)
        self.db.update_part(part_id, _clean_part_fields(body, creating=False))
        return 200, self.db.get_vehicle(part["vehicle_id"])

    def delete_part(self, body, token, params, part_id):
        user = self._require_user(token)
        part = self._part_or_404(user, part_id)
        self.db.delete_part(part_id)
        return 200, self.db.get_vehicle(part["vehicle_id"])


def _parse_query(query):
    params = {}
    for pair in query.split("&"):
        if "=" in pair:
            key, _, value = pair.partition("=")
            from urllib.parse import unquote_plus

            params[unquote_plus(key)] = unquote_plus(value)
    return params


def _parse_year(value):
    if value in (None, ""):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        raise ApiError(400, "Year must be a number, e.g. 2019")
    if not 1900 <= year <= 2100:
        raise ApiError(400, "Year looks wrong -- use a 4-digit year")
    return year


def _parse_hours(value):
    if value in (None, ""):
        return 0.0
    try:
        hours = float(value)
    except (TypeError, ValueError):
        raise ApiError(400, "Labour hours must be a number")
    if hours < 0:
        raise ApiError(400, "Labour hours cannot be negative")
    return hours


def _clean_part_fields(body, creating):
    fields = {}
    for key in ("part_number", "name", "supplier"):
        if creating or key in body:
            fields[key] = (body.get(key) or "").strip()
    if creating or "cost_cents" in body:
        try:
            cost = int(body.get("cost_cents") or 0)
        except (TypeError, ValueError):
            raise ApiError(400, "Part cost must be a number")
        if cost < 0:
            raise ApiError(400, "Part cost cannot be negative")
        fields["cost_cents"] = cost
    if creating or "discount_pct" in body:
        try:
            discount = float(body.get("discount_pct") or 0)
        except (TypeError, ValueError):
            raise ApiError(400, "Discount must be a number")
        if not 0 <= discount <= 100:
            raise ApiError(400, "Discount must be between 0 and 100")
        fields["discount_pct"] = discount
    if creating or "status" in body:
        status = body.get("status") or "Ordered"
        if status not in db.PART_STATUSES:
            raise ApiError(400, "Part status must be Ordered, Arrived or Fitted")
        fields["status"] = status
    return fields


class _Handler(BaseHTTPRequestHandler):
    service = None  # set by make_server
    protocol_version = "HTTP/1.1"

    def _dispatch(self, method):
        try:
            body = None
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except ValueError:
                    raise ApiError(400, "Request body is not valid JSON")
            token = None
            header = self.headers.get("Authorization") or ""
            if header.startswith("Bearer "):
                token = header[len("Bearer "):]
            status, payload = self.service.handle(method, self.path, body, token)
        except ApiError as exc:
            status, payload = exc.status, {"error": exc.message}
        except Exception as exc:  # pragma: no cover - safety net
            import traceback

            traceback.print_exc()
            status, payload = 500, {"error": f"Server error: {exc}"}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def log_message(self, fmt, *args):  # keep the console quiet
        pass


def make_server(host="0.0.0.0", port=DEFAULT_PORT, database=None):
    service = WorkbayService(database)

    class BoundHandler(_Handler):
        pass

    BoundHandler.service = service
    httpd = ThreadingHTTPServer((host, port), BoundHandler)
    httpd.daemon_threads = True
    return httpd


def run_in_thread(host="127.0.0.1", port=DEFAULT_PORT):
    """Used by the frozen client exe: start the server on a daemon thread
    inside the client process."""
    httpd = make_server(host, port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    host, port = "0.0.0.0", DEFAULT_PORT
    if argv:
        try:
            port = int(argv[0])
        except ValueError:
            print(f"Ignoring bad port argument: {argv[0]!r}")
    httpd = make_server(host, port)
    print(f"Workbay server listening on port {port}")
    print(f"Database: {httpd.RequestHandlerClass.service.db.path}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
