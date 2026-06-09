"""Shared text/NLP utilities and constants for the analysis package.

Centralises the (library-backed) language tooling so every section module uses the
same stopwords, lemmatizer, tokenizer, emoji/URL regexes and JSON helpers.
"""
import re
import numpy as np
import stopwordsiso
from unidecode import unidecode
import simplemma

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def deacc(s):
    """Transliterate to ASCII (de-accent) via unidecode."""
    return unidecode(str(s))


# Stopwords from the vetted stopwords-iso lists (Slovak + English + Czech loanwords),
# augmented with domain noise and diacritic-less variants (Slovak is often typed without accents).
STOP = set(stopwordsiso.stopwords(["sk", "en", "cs"]))
STOP |= {"https", "http", "www", "com", "instagram", "reel", "reels", "tt", "fbclid", "igsh", "amp", "story",
         "sent", "attachment", "message", "reacted", "liked", "contact", "added", "group", "photo", "video", "user",
         # common informal Slovak fillers the lists miss
         "hej", "joj", "jaj", "sak", "šak", "noo", "nooo", "aha", "aaa", "eee", "mmm", "hmm", "mhm", "ej", "eh", "ha",
         "ved", "veď", "fakt", "proste", "vlastne", "ano", "neviem", "ok", "okej", "cau", "čau", "ahoj", "dobre"}
STOP |= {deacc(w) for w in list(STOP)}

# Slovak lemmatizer (collapses heavy inflection: idem/ideš/ideme/išiel -> ísť), cached for speed.
_LEM = {}
def lemma(tok):
    v = _LEM.get(tok)
    if v is None:
        try:
            v = simplemma.lemmatize(tok, lang="sk")
        except Exception:
            v = tok
        _LEM[tok] = v
    return v

# Instagram system / auto-generated messages — exclude from linguistic & sentiment analysis
SYSTEM_RE = re.compile(
    r"(sent an attachment|reacted .* to your message|liked a message|to your message\s*$|"
    r"sent a photo|sent a video|sent a sticker|sent a gif|missed (a |your )?(video )?call|"
    r"video chat ended|started a (video )?call|named the group|changed the group|"
    r"added .* to the (group|chat)|left the group|this poll|created a poll|wasn't notified|"
    r"you are now connected|you sent an|changed the chat|changed the theme|set (the |your )?nickname|"
    r"pinned a message|turned (on|off)|removed .* from the group|created (a |the )?poll|joined|"
    r"shared a story|mentioned you|sent .* sticker)", re.I)

URL_RE = re.compile(r"https?://\S+|www\.\S+")
TOKEN_RE = re.compile(r"[a-zA-ZáäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ]+")
EMOJI_RE = re.compile(
    "[" "\U0001F300-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF" "\U00002B00-\U00002BFF" "\U0000FE00-\U0000FE0F"
    "\U0001F000-\U0001F0FF" "❤⭐✅❌‼⁉" "]+", flags=re.UNICODE)


def tokenize(txt):
    """Lowercase -> drop URLs -> word tokens -> drop stopwords/short -> lemmatize (Slovak)."""
    txt = URL_RE.sub(" ", str(txt).lower())
    out = []
    for t in TOKEN_RE.findall(txt):
        if len(t) <= 2 or t in STOP:
            continue
        l = lemma(t)
        if len(l) <= 2 or l in STOP:
            continue
        out.append(l)
    return out


def jnum(x):
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating,)): return float(x)
    if isinstance(x, (np.bool_,)): return bool(x)
    return x


def series_to_dict(s):
    return {str(k): jnum(v) for k, v in s.items()}
