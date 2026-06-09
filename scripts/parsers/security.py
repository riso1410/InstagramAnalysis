"""Account security, identity & digital trail parser.

Sources:
  security_and_login_information/login_and_profile_creation/*.json
      profile_activity (richest event log), login/logout/password/privacy histories,
      signup_details
  personal_information/personal_information/{profile_changes,instagram_profile_information}.json
  personal_information/information_about_you/{locations_of_interest,profile_based_in}.json
  logged_information/link_history/link_history.json

Outputs:
  security_events.parquet  one row per security/identity event (deduped)
  identity.json            signup, milestones, profile changes, privacy toggles, locations
  links.parquet            in-app browser visit log (~30-day window)

PRIVACY: emails, phone numbers, profile names and full IPs are masked HERE, at
parse time, so no sensitive literal ever reaches data/clean/.
"""
import json
import re
from datetime import datetime

import pandas as pd

from .common import fix, load_json, first_list, smd_value, label_value, add_time

META = {"key": "security", "outputs": ["security_events.parquet", "identity.json", "links.parquet"]}

SEC = "security_and_login_information/login_and_profile_creation"
MASK = "•••"

# phone/tablet model tokens inside user agents (Samsung GT-/SM-, iPhone, common Androids)
MODEL_RE = re.compile(r"\b(GT-\w+|SM-\w+|iPhone[\d,]*|Pixel(?: \w+)?|Redmi \w+|moto \w+|ONEPLUS \w+)\b")
TYPE_NORM = {"Account privacy changed": "Privacy changed"}
SENSITIVE_FIELDS = {"email", "phone number", "profile name", "username", "name"}


def mask_ip(ip):
    """Keep coarse network info only: first 2 octets/hextets, rest masked."""
    if not ip or not isinstance(ip, str):
        return None
    ip = ip.strip()
    if ":" in ip:  # IPv6
        parts = [p for p in ip.split(":") if True]
        return ":".join(parts[:2]) + ":x:x" if len(parts) >= 2 else None
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:2]) + ".x.x"
    return None


def device_from_ua(ua):
    """Hardware model when present, else platform · browser family."""
    if not ua or not isinstance(ua, str):
        return None
    m = MODEL_RE.search(ua)
    if m:
        return m.group(1)
    plat = ("Mac" if "Macintosh" in ua else
            "Windows" if "Windows" in ua else
            "Linux" if "Linux" in ua else
            "iOS" if "iPad" in ua or "iPod" in ua else None)
    browser = ("Edge" if "Edg/" in ua or "Edge/" in ua else
               "Firefox" if "Firefox/" in ua else
               "Chrome" if "Chrome/" in ua else
               "Safari" if "Safari" in ua else
               "Instagram app" if "Instagram" in ua else None)
    if plat and browser:
        return f"{plat} · {browser}"
    if "THttpClient" in ua:
        return "Meta server"
    return plat or browser


def app_norm(app, ua):
    if app:
        app = fix(app)
        if app.startswith("Windows"):
            return "Windows"
        return app
    if not ua:
        return None
    if "Android" in ua:
        return "Android"
    if "Windows" in ua:
        return "Windows"
    return "Web"


# --------------------------------------------------------------- event sources
def _profile_activity_rows(raw):
    rows = []
    for e in first_list(load_json(f"{SEC}/profile_activity.json", raw)) or []:
        if not isinstance(e, dict):
            continue
        lv = {it.get("label"): it for it in e.get("label_values") or [] if isinstance(it, dict)}
        ts = e.get("timestamp") or (lv.get("Last Login") or {}).get("timestamp_value") or 0
        typ = TYPE_NORM.get((lv.get("Type") or {}).get("value") or "", None) \
            or (lv.get("Type") or {}).get("value") or "Other"
        ua = (lv.get("User Agent") or {}).get("value") or ""
        city = None
        for d in (lv.get("Details") or {}).get("dict") or []:
            if d.get("label") == "Location" and d.get("value"):
                city = fix(d["value"])
        rows.append({
            "ts": int(ts), "type": fix(typ),
            "app": app_norm((lv.get("App") or {}).get("value"), ua),
            "device": device_from_ua(ua),
            "language": fix((lv.get("Language") or {}).get("value")) or None,
            "city": city,
            "ip_masked": mask_ip((lv.get("IP address") or {}).get("value")),
        })
    return rows


def _smd_history_rows(raw, fname, key, typ):
    rows = []
    obj = load_json(f"{SEC}/{fname}", raw)
    if obj is None:
        return rows
    for e in obj.get(key) or []:
        ts = smd_value(e, "Time") or 0
        ua = smd_value(e, "User Agent") or ""
        rows.append({
            "ts": int(ts), "type": typ,
            "app": app_norm(None, ua),
            "device": device_from_ua(ua),
            "language": fix(smd_value(e, "Language Code") or "") or None,
            "city": None,
            "ip_masked": mask_ip(smd_value(e, "IP Address")),
        })
    return rows


def _privacy_toggles(raw):
    obj = load_json(f"{SEC}/profile_privacy_changes.json", raw)
    toggles = []
    for e in (obj or {}).get("account_history_account_privacy_history") or []:
        title = fix(e.get("title") or "")
        sld = e.get("string_list_data") or [{}]
        ts = sld[0].get("timestamp") or 0
        if ts:
            toggles.append({"ts": int(ts), "to": "Public" if "Public" in title else "Private"})
    return sorted(toggles, key=lambda t: t["ts"])


# --------------------------------------------------------------- identity bits
def _signup(raw, tz):
    obj = load_json(f"{SEC}/signup_details.json", raw)
    for e in (obj or {}).get("account_history_registration_info") or []:
        ts = smd_value(e, "Time") or 0
        dev = smd_value(e, "Device") or ""
        if dev == "m0":  # Samsung internal codename for the Galaxy S III
            dev = "Samsung Galaxy S III (GT-I9300)"
        if ts:
            return {"date": str(pd.Timestamp(ts, unit="s", tz="UTC").tz_convert(tz).date()),
                    "ts": int(ts), "device": fix(dev) or None}
    return None


def _milestones(raw, tz):
    obj = load_json("personal_information/personal_information/instagram_profile_information.json", raw)
    if obj is None:
        return []
    keep = {"First Story Time": "First story", "Last Story Time": "Last story",
            "Last Login": "Last login", "Last Logout": "Last logout"}
    out = []
    for it in obj.get("label_values") or []:
        lb = it.get("label")
        ts = it.get("timestamp_value") or 0
        if lb in keep and ts:
            out.append({"label": keep[lb],
                        "date": str(pd.Timestamp(ts, unit="s", tz="UTC").tz_convert(tz).date()),
                        "ts": int(ts)})
    return sorted(out, key=lambda m: m["ts"])


def _profile_changes(raw, tz):
    obj = load_json("personal_information/personal_information/profile_changes.json", raw)
    out = []
    for e in (obj or {}).get("profile_profile_change") or []:
        field = fix(smd_value(e, "Changed") or "")
        ts = (e.get("string_map_data") or {}).get("Change Date", {}).get("timestamp") or 0
        prev = fix((e.get("string_map_data") or {}).get("Previous Value", {}).get("value") or "")
        new = fix((e.get("string_map_data") or {}).get("New Value", {}).get("value") or "")
        if field.lower() in SENSITIVE_FIELDS:  # never emit emails/phones/real names
            prev = MASK if prev else ""
            new = MASK if new else ""
        out.append({"date": str(pd.Timestamp(ts, unit="s", tz="UTC").tz_convert(tz).date()) if ts else None,
                    "field": field, "prev": prev, "new": new})
    return out


def _based_in(raw):
    obj = load_json("personal_information/information_about_you/profile_based_in.json", raw)
    for it in (obj or {}).get("label_values") or []:
        if it.get("label") == "Location":
            d = {x.get("label"): fix(x.get("value")) for x in it.get("dict") or []}
            return {"country": d.get("Country"), "region": d.get("Region"), "city": d.get("City")}
    return None


def _locations_of_interest(raw):
    obj = load_json("personal_information/information_about_you/locations_of_interest.json", raw)
    for it in (obj or {}).get("label_values") or []:
        if it.get("label") == "Locations of interest":
            return [fix(v.get("value")) for v in it.get("vec") or [] if v.get("value")]
    return []


# --------------------------------------------------------------- link history
def _parse_locale_dt(s):
    """'Jun 05, 2026 1:51:18pm' — lowercase am/pm: uppercase first for %p."""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip().upper(), "%b %d, %Y %I:%M:%S%p")
    except ValueError:
        return None


def _links(raw):
    from urllib.parse import urlparse, parse_qs
    rows = []
    for e in first_list(load_json("logged_information/link_history/link_history.json", raw)) or []:
        if not isinstance(e, dict):
            continue
        url = label_value(e, "Website link you visited") or ""
        title = label_value(e, "Title of website page you visited")
        start = _parse_locale_dt(label_value(e, "Website session start time"))
        end = _parse_locale_dt(label_value(e, "Website session end time"))
        dur = (end - start).total_seconds() if (start and end) else None
        if dur is not None and dur < 0:
            dur = None
        try:
            p = urlparse(url)
            domain = (p.netloc or "").lower().removeprefix("www.") or None
            utm = (parse_qs(p.query).get("utm_medium") or [None])[0]
        except Exception:
            domain, utm = None, None
        rows.append({"ts": int(e.get("timestamp") or 0), "domain": domain,
                     "title": fix(title) if title else None,
                     "duration_s": float(dur) if dur is not None else None,
                     "utm_medium": fix(utm) if utm else None})
    return rows


# ------------------------------------------------------------------------ main
def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    stats = {}

    # -- security events (merged + deduped) --
    rows = _profile_activity_rows(raw)  # richest source first -> wins the dedupe
    rows += _smd_history_rows(raw, "login_activity.json", "account_history_login_history", "Login")
    rows += _smd_history_rows(raw, "logout_activity.json", "account_history_logout_history", "Logout")
    rows += _smd_history_rows(raw, "password_change_activity.json",
                              "account_history_password_change_history", "Password changed")
    rows += [{"ts": t["ts"], "type": "Privacy changed", "app": None, "device": None,
              "language": None, "city": None, "ip_masked": None} for t in _privacy_toggles(raw)]
    if rows:
        ev = pd.DataFrame(rows)
        ev = ev[ev["ts"] > 0].drop_duplicates(subset=["ts", "type"], keep="first")
        ev = add_time(ev, "ts", tz, unit="s").sort_values("ts").reset_index(drop=True)
        ev.to_parquet(f"{out}/security_events.parquet", index=False)
        stats["n_security_events"] = int(len(ev))
        print(f"  security events: {len(ev):,} (deduped from {len(rows):,}) -> security_events.parquet")
    else:
        print("  no security events found")

    # -- identity.json --
    identity = {
        "signup": _signup(raw, tz),
        "milestones": _milestones(raw, tz),
        "profile_changes": _profile_changes(raw, tz),
        "privacy_toggles": [{"date": str(pd.Timestamp(t["ts"], unit="s", tz="UTC").tz_convert(tz).date()),
                             "to": t["to"]} for t in _privacy_toggles(raw)],
        "based_in": _based_in(raw),
        "locations_of_interest": _locations_of_interest(raw),
    }
    if any(v for v in identity.values()):
        with open(f"{out}/identity.json", "w", encoding="utf-8") as fh:
            json.dump(identity, fh, ensure_ascii=False)
        stats["n_profile_changes"] = len(identity["profile_changes"])
        print(f"  identity: signup={bool(identity['signup'])}, "
              f"{len(identity['milestones'])} milestones, {len(identity['profile_changes'])} profile changes")

    # -- link history --
    links = _links(raw)
    if links:
        lk = pd.DataFrame(links)
        lk = lk[lk["ts"] > 0]
        lk = add_time(lk, "ts", tz, unit="s").sort_values("ts").reset_index(drop=True)
        lk.to_parquet(f"{out}/links.parquet", index=False)
        stats["n_link_visits"] = int(len(lk))
        print(f"  link history: {len(lk):,} visits -> links.parquet")

    return stats
