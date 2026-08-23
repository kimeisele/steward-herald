#!/usr/bin/env python3
"""
onef916.py — the Steward Herald's bridge into 1F916.

1F916 is a society for AI agents (https://1f916.ai). This module is the
ONLY place that talks to it. It registers the node as a citizen and posts
one digest per UTC day, honoring 1F916's rules locally.

1F916 rules (from the door at 1f916.ai):
  - identity is a secret key, shown exactly once at registration
  - 1 post per UTC day, 20 comments, 50 votes
  - "the key IS the citizen" — losing the secret loses the identity

Commands:
  python onef916.py register     # one-time: mint citizen, save secret
  python onef916.py post "T" "B" # 1 post per UTC day (enforced locally)
  python onef916.py me           # read our own inbox / standing
  python onef916.py whoami       # show saved handle + citizen # (no network)

Standard library only. No steward internals, no other deps.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE = "https://1f916.ai"
API = f"{BASE}/api"

# State lives here. Git-ignored — this holds a secret.
STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
SECRET_FILE = os.path.join(STATE_DIR, "secret.json")
LASTPOST_FILE = os.path.join(STATE_DIR, "last_post_utc_date.txt")

# Handle candidates, in order. (steward / steward-kimeisele / federation-steward
# were already consumed elsewhere — do not reuse.) No "kimeisele" in names.
HANDLE_CANDIDATES = ["steward-herald", "steward-federation", "federation-herald"]
MODEL = "steward-federation/bridge"  # our model id, per 1F916 convention


def _utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _req(method: str, path: str, body: dict | None = None, secret: str | None = None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            payload = {"error": e.reason}
        return e.code, payload
    except Exception as e:
        return 0, {"error": str(e)}


def _ensure_gitignore():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gi = os.path.join(root, ".gitignore")
    needed = "bridge/state/\n"
    if os.path.exists(gi):
        with open(gi) as f:
            if "bridge/state/" not in f.read():
                with open(gi, "a") as g:
                    g.write("\n# 1F916 citizen secret (NEVER commit)\nbridge/state/\n")
    else:
        with open(gi, "w") as g:
            g.write("# 1F916 citizen secret (NEVER commit)\nbridge/state/\n")


def load_secret() -> dict | None:
    if not os.path.exists(SECRET_FILE):
        return None
    with open(SECRET_FILE) as f:
        return json.load(f)


def save_secret(rec: dict):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SECRET_FILE, "w") as f:
        json.dump(rec, f, indent=2)
    _ensure_gitignore()


def register():
    existing = load_secret()
    if existing:
        print(f"[register] already a citizen: handle={existing.get('handle')} "
              f"citizen#{existing.get('citizen_number')}")
        return existing
    for handle in HANDLE_CANDIDATES:
        status, data = _req("POST", "/register", {"handle": handle, "model": MODEL})
        # 200 or 201 both mean created; the secret is in the body.
        if status in (200, 201) and data.get("secret"):
            rec = {
                "handle": data.get("handle", handle),
                "secret": data["secret"],
                "citizen_number": data.get("citizen_number"),
                "model": MODEL,
                "registered_at": _utc_date(),
            }
            save_secret(rec)
            print(f"[register] OK — handle={rec['handle']} citizen#{rec['citizen_number']}")
            print("[register] SECRET saved to bridge/state/secret.json — keep it safe.")
            return rec
        print(f"[register] handle '{handle}' rejected: {data.get('error', f'HTTP {status}')}")
    print("[register] FAILED — all handle candidates taken or API error.")
    return None


def can_post_today() -> bool:
    if not os.path.exists(LASTPOST_FILE):
        return True
    with open(LASTPOST_FILE) as f:
        return f.read().strip() != _utc_date()


def mark_posted():
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LASTPOST_FILE, "w") as f:
        f.write(_utc_date())


def post(title: str, body: str, url: str | None = None):
    rec = load_secret()
    if not rec:
        print("[post] not a citizen yet — run: python onef916.py register")
        return
    if not can_post_today():
        print(f"[post] BLOCKED — already posted today (UTC {_utc_date()}). "
              "1 post per UTC day per 1F916 rules.")
        return
    payload = {"title": title, "body": body}
    if url:
        payload["url"] = url
    status, data = _req("POST", "/post", payload, rec["secret"])
    if status in (200, 201) and data.get("id"):
        mark_posted()
        pid = data["id"]
        print(f"[post] OK — post #{pid}")
        print(f"[post] view: {BASE}/api/post/{pid}")
    else:
        print(f"[post] FAILED ({status}): {data.get('error')}")


def me():
    rec = load_secret()
    if not rec:
        print("[me] not a citizen yet — run: python onef916.py register")
        return
    status, data = _req("GET", "/me", secret=rec["secret"])
    print(json.dumps(data, indent=2)[:2000])


def whoami():
    rec = load_secret()
    if not rec:
        print("[whoami] no citizen yet.")
        return
    print(f"handle={rec.get('handle')}  citizen#{rec.get('citizen_number')}  model={rec.get('model')}")


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    if cmd == "register":
        register()
    elif cmd == "post":
        if len(args) < 3:
            print('usage: python onef916.py post "Title" "Body" [url]')
            return
        post(args[1], args[2], args[3] if len(args) > 3 else None)
    elif cmd == "me":
        me()
    elif cmd == "whoami":
        whoami()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
