"""Social graph parser: followers / following counts (lists are parsed in detail
by the connections analysis once available)."""
import json

from .common import load_json

META = {"key": "connections", "outputs": ["connections.json"]}


def _count_conn(o):
    if o is None:
        return 0
    n = 0

    def walk(x):
        nonlocal n
        if isinstance(x, dict):
            if "string_list_data" in x:
                n += 1
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(o)
    return n


def parse(env):
    raw, out = env["RAW"], env["OUT"]
    foll = {
        "following": _count_conn(load_json("connections/followers_and_following/following.json", raw)),
        "followers": _count_conn(load_json("connections/followers_and_following/followers_1.json", raw)),
    }
    with open(f"{out}/connections.json", "w") as fh:
        json.dump(foll, fh)
    print(f"  connections: {foll}")
    return foll
