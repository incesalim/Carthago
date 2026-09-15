"""Read-only HTTP checks after a release; bound requests and verify page/API content."""
import argparse
import json
import time
import urllib.request


def check(origin: str) -> None:
    for path, expected in (("/", "Carthago"), ("/banks/AKBNK", "Akbank"),
                           ("/api/v1", "Carthago Data API"),
                           ("/api/app/v1", "Carthago Mobile API")):
        for attempt in range(3):
            try:
                req = urllib.request.Request(origin.rstrip("/") + path,
                                             headers={"Cache-Control": "no-cache", "User-Agent": "Carthago-release-check"})
                with urllib.request.urlopen(req, timeout=20) as response:
                    body = response.read().decode("utf-8")
                    if response.status != 200 or expected.casefold() not in body.casefold():
                        raise ValueError(f"unexpected response at {path}")
                    if path.startswith("/api/") and json.loads(body).get("name") != expected:
                        raise ValueError(f"unexpected API envelope at {path}")
                print(f"PASS {path}")
                break
            except Exception as exc:
                if attempt == 2:
                    raise RuntimeError(f"Release smoke failed: {path}") from exc
                time.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default="https://carthago.app")
    check(parser.parse_args().origin)
