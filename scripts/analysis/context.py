"""AnalysisContext — loads the cleaned data once, applies user configuration
(exclusions, date window, phrase filtering) and exposes the shared frames every
section module reads. Section modules may also stash cross-section results here
(e.g. ctx.chats from the people module is reused by clusters/sentiment).
"""
import os, json
import pandas as pd
from _config import load_config
from .text_utils import SYSTEM_RE


class AnalysisContext:
    def __init__(self, clean="data/clean", raw="data/raw"):
        self.CLEAN = clean
        self.RAW = raw
        print("loading data ...")
        self.df = pd.read_parquet(f"{clean}/messages.parquet")
        self.rx = pd.read_parquet(f"{clean}/reactions.parquet")
        self.th = pd.read_parquet(f"{clean}/threads.parquet")
        self.meta = json.load(open(f"{clean}/meta.json"))
        self.self_name = self.meta["self_name"]

        self.sent = None
        if os.path.exists(f"{clean}/sentiment.parquet"):
            sp = pd.read_parquet(f"{clean}/sentiment.parquet")
            if len(sp) == len(self.df):
                for c in ["neg", "neu", "pos", "compound", "sent_label"]:
                    self.df[c] = sp[c].values
                self.sent = True
                print("  sentiment merged")

        self.df["dt"] = pd.to_datetime(self.df["dt"])

        # ---- user configuration: exclusions, date window, tag filtering ----
        self.CFG = load_config()
        self.TZ = self.CFG.get("timezone") or self.meta.get("timezone", "Europe/Bratislava")
        EXC = [e.lower() for e in self.CFG["exclude_people"]]
        if EXC:
            dm_drop = set(self.th.loc[(self.th["n_participants"] <= 2) &
                          (self.th["participants"].fillna("").str.lower().apply(lambda p: any(e in p for e in EXC))),
                          "thread_id"])
            before = len(self.df)
            mask = self.df["thread_id"].isin(dm_drop) | self.df["sender"].str.lower().apply(lambda s: any(e in s for e in EXC))
            self.df = self.df[~mask].copy()
            print(f"  excluded {before - len(self.df):,} messages matching {self.CFG['exclude_people']} "
                  f"({len(dm_drop)} DM thread(s) dropped)")
        if self.CFG.get("date_from"):
            self.df = self.df[self.df["dt"] >= pd.Timestamp(self.CFG["date_from"]).tz_localize(self.TZ)]
        if self.CFG.get("date_to"):
            self.df = self.df[self.df["dt"] <= pd.Timestamp(self.CFG["date_to"]).tz_localize(self.TZ)]
        self._phrase_block = self.CFG["exclude_phrases"]

        # focus analysis on real conversations (inbox); requests counted separately
        self.inbox = self.df[self.df["kind"] == "inbox"].copy()
        self.inbox["dt"] = pd.to_datetime(self.inbox["dt"])
        self.inbox["is_system"] = self.inbox["content"].fillna("").str.contains(SYSTEM_RE, regex=True, na=False)
        n_system = int(self.inbox["is_system"].sum())
        print(f"  system/auto messages flagged: {n_system:,} ({100*n_system/max(len(self.inbox),1):.1f}% of inbox)")
        self.inbox["is_human_text"] = self.inbox["has_text"] & ~self.inbox["is_system"]
        self.tx = self.inbox[self.inbox["is_human_text"]]

        # cross-section results, populated by section modules
        self.chats = None        # set by sections.people
        self.title_map = None     # set by sections.people
        self.per_chat_resp = None  # set by sections.dynamics

    def phrase_blocked(self, s):
        s = str(s).lower()
        return any(p in s for p in self._phrase_block)
