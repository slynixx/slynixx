# Workbay

Vehicle & parts job book for car workshops (South Africa). Book vehicles
in, track parts per vehicle (Ordered → Arrived → Fitted), tick off repair
items, search full vehicle history by registration, and see invoice-style
totals with 15% VAT in Rand. Multiple workshops can share one server on a
LAN; an admin account (`admin` / `admin123`, seeded on first run) manages
everything.

Pure Python stdlib — **no pip dependencies to run** (PyInstaller is only
needed to build the exe).

## Run from source

```
cd client
py -3 app.py        (or double-click client\run.bat)
```

The client auto-starts a hidden local server on port 8642 and stops it on
close. Data lives in `%APPDATA%\Workbay\workbay.db` (override with
`WORKBAY_DB_DIR` or `WORKBAY_DB`) — never next to the program. The client
config (`client_config.json`) and `error.log` live in the same folder.

## Build the standalone exe

```
client\build-exe.bat      ->  client\dist\Workbay.exe
```

The exe is `--onefile --windowed` (no console ever) and runs the bundled
server in-process on a daemon thread. **Everything is this one exe** --
the workshop app, the hidden local server, and LAN host mode.

## LAN mode (still just the one exe)

On the host PC run `Workbay.exe --server` (make a shortcut with that
argument). A small status window shows the address to use. On each
workshop PC, open Workbay, click the "Server:" link on the sign-in
screen and enter `<host-ip>:8642`.

From source the equivalent is `py -3 app.py --server` (or
`server\run-server.bat`).

## Layout

- `server/` — stdlib `http.server` JSON API (port 8642), SQLite in
  `db.py`, PBKDF2 auth + in-memory token sessions in `auth.py`.
- `client/` — Tkinter GUI. `app.py` entry point, `api.py` (urllib with
  ~3s connect retries), `theme.py` (dark palette + money/VAT maths),
  `widgets.py`, `netutil.py` (thread + queue poller), `server_manager.py`
  (auto-start hidden server), `screens/`.
- `tests/` — stdlib `unittest` suite: `py -3 -m unittest discover tests`.
