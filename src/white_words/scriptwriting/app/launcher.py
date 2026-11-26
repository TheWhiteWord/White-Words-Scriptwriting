"""Launcher CLI for the standalone app."""

from __future__ import annotations

import argparse
import socket
import threading
import time
import urllib.request
import webbrowser

from white_words.scriptwriting.app.config import load_config
from white_words.scriptwriting.app.server import create_app


def is_healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def seed_demo(root, *, replace=False):
    """Copy the bundled demo into `root`, returning where it landed.

    WAL sidecars are per-process state: a stale -wal copied next to a fresh db is a
    database that reads as corrupt. Copy the committed files only.
    """
    import shutil
    from pathlib import Path

    bundled = Path(__file__).resolve().parents[1] / "data" / "demo"
    dest = Path(root) / "projects" / "demo"
    if not bundled.exists():
        raise FileNotFoundError(f"No bundled demo at {bundled}")
    if replace and dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundled, dest, ignore=shutil.ignore_patterns("*-wal", "*-shm", "__pycache__"))
    return dest


def main(argv=None):
    import sys

    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "hermes":
        from white_words.scriptwriting.adapters.hermes.setup import setup, status

        sub = argv[1:2]
        rest = argv[2:]
        if sub and sub[0] == "status":
            return status(rest)
        return setup(rest)
    if argv and argv[0] == "seed-demo":
        parser = argparse.ArgumentParser(prog="white-words seed-demo")
        parser.add_argument("--root", default=None)
        parser.add_argument(
            "--restore",
            action="store_true",
            help="Replace an existing demo with a fresh copy from the bundle",
        )
        a = parser.parse_args(argv[1:])
        config = load_config(cli_root=a.root)
        dest = config.root / "projects" / "demo"
        if dest.exists() and not a.restore:
            print(f"Demo already exists at {dest}")
            print("Pass --restore to put it back the way it shipped.")
            return 0
        print(
            f"{'Restored' if a.restore else 'Seeded'} demo at "
            f"{seed_demo(config.root, replace=a.restore)}"
        )
        return 0

    parser = argparse.ArgumentParser(prog="white-words")
    parser.add_argument("--root", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="Add a launcher entry (and icon) to the desktop",
    )
    parser.add_argument(
        "--uninstall-desktop", action="store_true", help="Remove the launcher entry and icon"
    )
    parser.add_argument(
        "--no-idle-exit",
        action="store_true",
        help="Keep the server running after the last browser tab closes",
    )
    args = parser.parse_args(argv)

    from white_words.scriptwriting.app import desktop

    if args.install_desktop:
        return desktop.install()
    if args.uninstall_desktop:
        return desktop.uninstall()

    config = load_config(cli_root=args.root, cli_port=args.port, cli_no_open=args.no_open)
    config.idle_exit = not args.no_idle_exit

    # No prompt: launched from a .desktop entry there is no controlling terminal,
    # so waiting on stdin would hang the app with no way to answer.
    fresh_root = not config.root.exists()
    if fresh_root:
        config.root.mkdir(parents=True, exist_ok=True)
        (config.root / "projects").mkdir(exist_ok=True)
        print(f"Created root {config.root}")
        # The demo is what a new user has to look at, so a new root gets one. Only a new
        # root: a demo the user deletes stays deleted, or every launch would undo it.
        try:
            print(f"Added the demo project at {seed_demo(config.root)}")
        except FileNotFoundError:
            pass  # source checkout without the bundle; the rest of the app works

    if is_healthy(config.port):
        url = f"http://127.0.0.1:{config.port}"
        print(f"Already running at {url}")
        if config.open_browser:
            webbrowser.open(url)
        return 0

    s = socket.socket()
    try:
        s.settimeout(0.5)
        s.connect(("127.0.0.1", config.port))
        print(f"Port {config.port} is in use by another process. Try --port.")
        return 1
    except Exception:
        pass
    finally:
        s.close()

    app = create_app(config)
    url = f"http://127.0.0.1:{config.port}"
    print(f"Serving at {url}")
    if config.open_browser:

        def opener():
            for _ in range(50):
                if is_healthy(config.port):
                    webbrowser.open(url)
                    return
                time.sleep(0.1)

        threading.Thread(target=opener, daemon=True).start()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=config.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
