"""Shared user-configuration loader for the InstagramAnalysis pipeline.

Open-source friendly:
  * config.example.yaml  — committed template (safe, no personal data) = the base.
  * config.yaml          — YOUR personal overrides (gitignored, never pushed).

The loader starts from built-in defaults, overlays config.example.yaml (if present),
then overlays config.yaml (if present) so your personal settings win. Nested blocks
(privacy, sections) are deep-merged, so overriding one key keeps the others. New users
who only have the example file still get a fully working configuration. Every key is
optional.
"""
import os, json

DEFAULTS = {
    "exclude_people": [],
    "exclude_phrases": [],
    "date_from": None,
    "date_to": None,
    "min_chat_messages": 1,
    "topics_k": 12,
    "top_chats": 60,
    "timezone": "Europe/Bratislava",
    "sentiment_model": "cardiffnlp/twitter-xlm-roberta-base-sentiment",
    # privacy controls for sharing the generated dashboard
    "privacy": {
        "include_examples": True,   # embed a sample of real messages in the explorer
        "anonymize_names": False,   # contacts become "Person 01", "Person 02", ...
        "include_sensitive": True,  # sections marked privacy=high (logins, searches, ...)
    },
    # per-section enable/disable: {"connections": false} hides that whole section
    "sections": {},
}

# base template first, personal override last (last write wins)
_SOURCES = ("config.example.yaml", "config.yaml", "config.yml", "config.json")


def _read(path):
    if path.endswith(".json"):
        return json.load(open(path, encoding="utf-8"))
    import yaml
    return yaml.safe_load(open(path, encoding="utf-8")) or {}


def _deep_update(base, new):
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v


def load_config(verbose=True):
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    loaded = []
    for path in _SOURCES:
        if not os.path.exists(path):
            continue
        try:
            data = _read(path)
            if isinstance(data, dict):
                _deep_update(cfg, data)
                loaded.append(path)
        except Exception as e:
            print(f"  config: warning loading {path}: {e}")
    if verbose:
        print(f"  config: loaded {', '.join(loaded) if loaded else 'built-in defaults'}")
    # legacy top-level key (pre-privacy-block configs)
    if "include_examples" in cfg:
        cfg["privacy"]["include_examples"] = bool(cfg.pop("include_examples"))
    cfg["exclude_people"] = [str(x).strip() for x in (cfg.get("exclude_people") or []) if str(x).strip()]
    cfg["exclude_phrases"] = [str(x).strip().lower() for x in (cfg.get("exclude_phrases") or []) if str(x).strip()]
    cfg["sections"] = {str(k).strip().lower(): v for k, v in (cfg.get("sections") or {}).items()}
    return cfg
