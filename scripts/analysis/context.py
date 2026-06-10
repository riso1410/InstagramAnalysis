"""AnalysisContext — loads the cleaned data once, applies user configuration
(exclusions, date window, phrase filtering, anonymization) and exposes the shared
frames every section module reads. Section modules may also stash cross-section
results here (e.g. ctx.chats from the people module is reused by clusters/sentiment).

Contract for section authors:
  * ctx.df / ctx.inbox / ctx.tx     message frames, already config-filtered
  * ctx.rx / ctx.th                 reactions / thread metadata, config-filtered
  * ctx.load_clean("x.parquet")    any other cleaned table (None if absent)
  * ctx.filter_people(df, cols)     drop rows naming an excluded person — call this
                                    on EVERY frame that carries contact names
  * ctx.disp(name)                  display name for output — respects
                                    privacy.anonymize_names ("Person 01", ...)
  * ctx.disp_title(title, is_group) same, for conversation titles
"""
import os, json, re
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
        self._exc = [e.lower() for e in self.CFG["exclude_people"]]
        self.anonymize = bool(self.CFG["privacy"]["anonymize_names"])
        self._anon_people = {}   # real name -> "Person NN" (stable, first-seen order)
        self._anon_groups = {}   # group title -> "Group NN"
        self._anon_tids = {}     # thread_id -> "t001" (IG thread ids embed usernames)

        # name tokens (accented + de-accented) of the owner and every participant —
        # used to scrub names out of emitted text/word lists when anonymizing
        self._name_tokens = set()
        self._scrub_re = None
        if self.anonymize:
            from unidecode import unidecode
            names = {self.self_name}
            for p in self.th["participants"].fillna(""):
                names.update(str(p).split("|"))
            for n in names:
                for tok in str(n).split():
                    tok = tok.strip().lower()
                    if len(tok) >= 3:
                        self._name_tokens.add(tok)
                        self._name_tokens.add(unidecode(tok))
            self._name_tokens.discard("")
            if self._name_tokens:
                pat = "|".join(re.escape(t) for t in sorted(self._name_tokens, key=len, reverse=True))
                self._scrub_re = re.compile(rf"\b({pat})\w*", re.IGNORECASE | re.UNICODE)

        if self._exc:
            dm_drop = set(self.th.loc[(self.th["n_participants"] <= 2) &
                          (self.th["participants"].fillna("").str.lower().apply(lambda p: any(e in p for e in self._exc))),
                          "thread_id"])
            before = len(self.df)
            mask = self.df["thread_id"].isin(dm_drop) | self.df["sender"].str.lower().apply(self._match_exc)
            self.df = self.df[~mask].copy()
            print(f"  excluded {before - len(self.df):,} messages matching {self.CFG['exclude_people']} "
                  f"({len(dm_drop)} DM thread(s) dropped)")
            # the exclusion is global: reactions and thread metadata too
            self.th = self.th[~self.th["thread_id"].isin(dm_drop)].copy()
            if not self.rx.empty:
                self.rx = self.rx[~self.rx["thread_id"].isin(dm_drop)]
                self.rx = self.filter_people(self.rx, ["reactor", "target_sender"])
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

    # ---------------------------------------------------------------- helpers
    def _match_exc(self, s):
        s = str(s).lower()
        return any(e in s for e in self._exc)

    def is_excluded(self, name):
        """True if `name` matches the exclude_people config (ci substring)."""
        return bool(self._exc) and self._match_exc(name)

    def filter_people(self, df, cols):
        """Drop rows where any of `cols` names an excluded person."""
        if df is None or df.empty or not self._exc:
            return df
        mask = pd.Series(False, index=df.index)
        for c in cols:
            if c in df.columns:
                mask |= df[c].fillna("").astype(str).str.lower().apply(self._match_exc)
        return df[~mask].copy()

    def disp(self, name):
        """Display name for emitted output. With privacy.anonymize_names the
        account owner becomes "Me" and every contact a stable "Person NN"."""
        name = str(name)
        if not self.anonymize:
            return name
        if name == self.self_name:
            return "Me"
        if name not in self._anon_people:
            self._anon_people[name] = f"Person {len(self._anon_people) + 1:02d}"
        return self._anon_people[name]

    def disp_tid(self, tid):
        """Display thread id. Instagram thread ids embed the contact's username
        (e.g. 'janedoe_1250817…'), so anonymized output uses stable 't001' keys.
        people.py and examples.py must use the SAME mapping (they do — it's shared)."""
        tid = str(tid)
        if not self.anonymize:
            return tid
        if tid not in self._anon_tids:
            self._anon_tids[tid] = f"t{len(self._anon_tids) + 1:03d}"
        return self._anon_tids[tid]

    def name_blocked(self, s):
        """True when a word/bigram/term contains a known contact-name token —
        used to keep names out of word charts when anonymizing."""
        if not self._name_tokens:
            return False
        return any(t in self._name_tokens for t in str(s).lower().split())

    def scrub_names(self, text):
        """Best-effort removal of known contact-name tokens from emitted text
        (Message Explorer samples). Nicknames not present in participant lists
        can survive — true share-safety also sets privacy.include_examples=false."""
        if self._scrub_re is None:
            return text
        return self._scrub_re.sub("***", str(text))

    def disp_title(self, title, is_group=False):
        """Display title for a conversation. DM titles are the contact's name ->
        anonymized via disp(); custom group titles become "Group NN"."""
        title = str(title)
        if not self.anonymize:
            return title
        if not is_group:
            return self.disp(title)
        if title not in self._anon_groups:
            self._anon_groups[title] = f"Group {len(self._anon_groups) + 1:02d}"
        return self._anon_groups[title]

    def load_clean(self, filename):
        """Load any cleaned table (parquet/json) or None when the export lacks it."""
        path = os.path.join(self.CLEAN, filename)
        if not os.path.exists(path):
            return None
        if filename.endswith(".json"):
            return json.load(open(path, encoding="utf-8"))
        df = pd.read_parquet(path)
        if "dt" in df.columns:
            df["dt"] = pd.to_datetime(df["dt"])
            if self.CFG.get("date_from"):
                df = df[df["dt"] >= pd.Timestamp(self.CFG["date_from"]).tz_localize(self.TZ)]
            if self.CFG.get("date_to"):
                df = df[df["dt"] <= pd.Timestamp(self.CFG["date_to"]).tz_localize(self.TZ)]
        return df

    def phrase_blocked(self, s):
        s = str(s).lower()
        return any(p in s for p in self._phrase_block)
