"""Ads & off-Meta footprint: which advertisers hold your data, how you're
targeted, the impression logs (ads/posts/videos/suggested profiles) and the
off-Meta website activity Instagram receives.

Outputs:
    impressions.parquet  one row per logged impression (ads_viewed, posts_viewed,
                         videos_watched, suggested_profiles_viewed)
    footprint.json       advertiser lists / targeting categories / hidden ads /
                         off-Meta site events / settings — the no-timestamp facts
"""
import json, os, re
from collections import Counter
import pandas as pd

from .common import fix, load_json, first_list, add_time

META = {"key": "ads", "outputs": ["impressions.parquet", "footprint.json"]}

A = "ads_information"
W = "apps_and_websites_off_of_instagram/apps_and_websites"

IMPRESSION_SOURCES = [
    (f"{A}/ads_and_topics/ads_viewed.json", "ad"),
    (f"{A}/ads_and_topics/posts_viewed.json", "post"),
    (f"{A}/ads_and_topics/videos_watched.json", "video"),
    (f"{A}/ads_and_topics/suggested_profiles_viewed.json", "suggested_profile"),
]

TOKEN_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)   # word tokens, >3 chars, no digits


# ---------------------------------------------------------------- extractors
def _find_label(o, lbl):
    """First {label: lbl, value: ...} leaf anywhere in the entry (handles the
    Owner / Media>Owner / Owner>Owner nesting variability)."""
    if isinstance(o, dict):
        if o.get("label") == lbl and o.get("value"):
            return o["value"]
        for v in o.values():
            r = _find_label(v, lbl)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_label(v, lbl)
            if r:
                return r
    return None


def _find_ts_label(o, lbl):
    """All timestamp_value leaves under {label: lbl} blocks."""
    out = []
    if isinstance(o, dict):
        if o.get("label") == lbl and o.get("timestamp_value"):
            out.append(o["timestamp_value"])
        for v in o.values():
            out += _find_ts_label(v, lbl)
    elif isinstance(o, list):
        for v in o:
            out += _find_ts_label(v, lbl)
    return out


def _find_titled(o, title):
    """First nested dict block with the given title (Owner / Hashtags ...)."""
    if isinstance(o, dict):
        if o.get("title") == title:
            return o
        for v in o.values():
            r = _find_titled(v, title)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_titled(v, title)
            if r is not None:
                return r
    return None


def _all_label_values(o, lbl):
    """All values of {label: lbl} leaves inside a block."""
    out = []
    if isinstance(o, dict):
        if o.get("label") == lbl and o.get("value"):
            out.append(o["value"])
        for v in o.values():
            out += _all_label_values(v, lbl)
    elif isinstance(o, list):
        for v in o:
            out += _all_label_values(v, lbl)
    return out


def _owner(entry):
    """(name, username): scoped to the title=='Owner' block — Hashtags blocks
    also carry {label:'Name'} leaves, so a global first-match is wrong. Falls
    back to top-level Name/Username leaves (suggested_profiles_viewed shape)."""
    blk = _find_titled(entry, "Owner")
    if blk is not None:
        return _find_label(blk, "Name"), _find_label(blk, "Username")
    name = username = None
    for lv in entry.get("label_values") or []:
        if lv.get("label") == "Name" and lv.get("value"):
            name = lv["value"]
        elif lv.get("label") == "Username" and lv.get("value"):
            username = lv["value"]
    return name, username


def _hashtags(entry):
    """Hashtag names inside the title=='Hashtags' nested block."""
    blk = _find_titled(entry, "Hashtags")
    if blk is None:
        return []
    return [fix(v) for v in _all_label_values(blk, "Name")]


def _titled_block(label_values, title):
    for lv in label_values or []:
        if lv.get("title") == title:
            return lv
    return None


# ---------------------------------------------------------------- impressions
def _parse_impressions(raw, out, tz):
    rows = []
    for path, kind in IMPRESSION_SOURCES:
        obj = load_json(path, raw)
        if obj is None:
            continue
        entries = first_list(obj)
        n = 0
        for e in entries:
            if not isinstance(e, dict):
                continue
            ts = e.get("timestamp") or 0
            if not ts:
                continue
            tags = _hashtags(e)
            name, username = _owner(e)
            rows.append({
                "ts": int(ts),
                "kind": kind,
                "owner_username": fix(username or ""),
                "owner_name": fix(name or ""),
                "n_hashtags": len(tags),
                "hashtags": "|".join(tags),
            })
            n += 1
        print(f"  impressions[{kind}]: {n:,}")
    if not rows:
        return None
    a = pd.DataFrame(rows)
    a = add_time(a, "ts", tz, unit="s").sort_values("dt").reset_index(drop=True)
    a.to_parquet(f"{out}/impressions.parquet", index=False)
    print(f"  impressions: {len(a):,} rows -> impressions.parquet")
    return a


# ---------------------------------------------------------------- footprint
def _advertisers(raw):
    obj = load_json(f"{A}/instagram_ads_and_businesses/advertisers_using_your_activity_or_information.json", raw)
    if obj is None:
        return None
    uploaded, interaction, store = set(), set(), set()
    for lv in (obj.get("label_values") if isinstance(obj, dict) else None) or []:
        lab = (lv.get("label") or "").lower()
        names = {fix(v.get("value")) for v in lv.get("vec") or [] if v.get("value")}
        if "containing entries" in lab:        # uploaded contact/audience list match
            uploaded = names
        elif "interactions" in lab:            # website/app/store interaction match
            interaction = names
        elif "store" in lab:
            store = names
    union = uploaded | interaction | store
    if not union:
        return None
    tok = Counter()
    for name in union:
        for t in TOKEN_RE.findall(name.lower()):
            tok[t] += 1
    return {
        "uploaded_n": len(uploaded),
        "interaction_n": len(interaction),
        "store_n": len(store),
        "both_n": len(uploaded & interaction),
        "union_n": len(union),
        "names_sample": sorted(union)[:100],
        "name_tokens": [{"token": t, "n": int(n)} for t, n in tok.most_common(40)],
    }


def _targeting(raw):
    obj = load_json(f"{A}/instagram_ads_and_businesses/other_categories_used_to_reach_you.json", raw)
    if obj is None:
        return []
    out = []
    for lv in (obj.get("label_values") if isinstance(obj, dict) else None) or []:
        out += [fix(v.get("value")) for v in lv.get("vec") or [] if v.get("value")]
    return out


def _hidden_ads(raw):
    obj = load_json(f"{A}/instagram_ads_and_businesses/ad_preferences.json", raw)
    if obj is None:
        return 0, {}
    block = _titled_block(obj.get("label_values") if isinstance(obj, dict) else None, "Hidden ads")
    if not block:
        return 0, {}
    years = Counter()
    n = 0
    for item in block.get("dict") or []:
        n += 1
        for ts in _find_ts_label(item, "Creation time"):
            years[str(pd.Timestamp(ts, unit="s").year)] += 1
    return n, dict(sorted(years.items()))


def _off_meta(raw):
    obj = load_json(f"{W}/your_activity_off_meta_technologies.json", raw)
    sites = []
    for e in first_list(obj) if obj is not None else []:
        if not isinstance(e, dict):
            continue
        tss = _find_ts_label(e, "Received on")
        n_ev = 0
        for lv in e.get("label_values") or []:
            if lv.get("label") == "Events":
                n_ev = len(lv.get("vec") or [])
        sites.append({"domain": fix(e.get("title") or ""),
                      "n_events": int(n_ev or len(tss)),
                      "last_ts": int(max(tss)) if tss else 0})
    return sorted(sites, key=lambda s: -s["last_ts"])


def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    stats = {}

    imp = _parse_impressions(raw, out, tz)
    if imp is not None:
        stats["n_impressions"] = int(len(imp))

    fp = {}
    adv = _advertisers(raw)
    if adv:
        fp["advertisers"] = adv
    fp["targeting_labels"] = _targeting(raw)
    fp["hidden_ads_n"], fp["hidden_ads_years"] = _hidden_ads(raw)

    sub = load_json(f"{A}/instagram_ads_and_businesses/subscription_for_no_ads.json", raw)
    status = _find_label(sub, "Your subscription status") if sub is not None else None
    fp["no_ads_subscription"] = fix(status) if status else ""

    fp["off_meta"] = _off_meta(raw)

    st = load_json(f"{W}/your_activity_off_meta_technologies_settings.json", raw)
    assoc = _find_label(st, "Profile association state") if st is not None else None
    fp["profile_association"] = fix(assoc) if assoc else ""

    if adv or fp["targeting_labels"] or fp["off_meta"]:
        json.dump(fp, open(os.path.join(out, "footprint.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"  footprint: {fp.get('advertisers', {}).get('union_n', 0):,} advertisers · "
              f"{len(fp['targeting_labels'])} targeting labels · {len(fp['off_meta'])} off-Meta sites "
              f"-> footprint.json")
        stats["n_advertisers"] = fp.get("advertisers", {}).get("union_n", 0)
        stats["n_off_meta_sites"] = len(fp["off_meta"])
    return stats
