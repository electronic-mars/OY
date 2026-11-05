"""Translate the interface from English into the other languages (src/oyplayer/lang/<code>.json).

    python tools/translate.py                     # what each language is missing
    python tools/translate.py --only de,ja        # some languages
    python tools/translate.py --keys k1,k2        # these keys again, everywhere (their English changed)
    python tools/translate.py --review            # a second model reads every language
    python tools/translate.py --check             # the checks alone, no requests

Free models through NVIDIA NIM; the key is read from NVIDIA_NIM_API_KEY, in the environment or
in ~/.fcc/.env, and never written anywhere. English (i18n.EN) is the source; Ukrainian is
written by hand in i18n.py and never touched here.

- Only the keys a language is missing are sent, forty at a time, with the language's glossary
  (tools/glossary/<code>.json, made first), so a term reads the same in every chunk.
- Nothing is written until a value has passed fault(); a value that fails is asked for again
  with the reason, and one that still fails stays out of the file (the player shows English)
  and is named. Only a value too long for its place, or the same as the English, goes in after the
  last try: the window is checked by eye in the long languages anyway.
- The file is saved after every chunk: a stopped run loses one chunk, not a language.
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from oyplayer.i18n import EN, LANG_DIR, LANGUAGES, forms  # noqa: E402
from PySide6.QtCore import QLocale  # noqa: E402

API = "https://integrate.api.nvidia.com/v1/chat/completions"
NEMOTRON = "nvidia/nemotron-3-ultra-550b-a55b"
SUPER = "nvidia/nemotron-3.5-super-vl-120b-a12b"
MINIMAX = "minimaxai/minimax-m3.1-flash"
CHUNK = 40
REVIEW_CHUNK = 80
GLOSSARY = ROOT / "tools" / "glossary"      # each language's terms, kept for the next run
# the words the interface keeps in every language
KEEP = ["OY Player", "ffmpeg", "FFmpeg", "mpv", "mpv.conf", "H.264", "H.265", "NVIDIA", "GitHub", "PNG", "JPG",
        "BMP", "GIF", "WEBP", "EBU R128", "S/PDIF", "HDMI", "DTS", "GPL", "Windows", ".lau", "A-B"]
# the program in a few lines, for every request
ABOUT = """The program is OY Player, a video and audio player for Windows 11. Its window has a title bar,
the picture, and a panel at the foot with a timeline (a time scale with the fragments of the editor)
and one row of keys (play, stop, volume, subtitles, sound, speed, playlist, settings). Other parts:
a playlist panel with tabs (list, watch history, internet radio), a settings panel with pages, a
video panel (colour, aspect, zoom, filters), a file information panel, an editor for cutting
fragments out of a file and drawing on the frame (captions, arrows, rectangles, pencil), a
screenshot window, a scheduler (what to do and when), skipping of TV series openings and credits,
and an LCD on the panel showing the time. Key prefixes: act_* are the names of commands (in the key
editor and the tray menu), osd_* are short messages over the picture, s_* are setting names and
s_*_h the one-line hint under a setting, c_* are section captions (capitals), t_* are tooltips,
o_* are options of a segmented switch (very little room), m_* are menu rows and headers, es_* the
editor's strip, up_* the updater, err_* finish the sentence "Not saved: ...", info_* the file
information, tl_* the timeline, dial_* colour names on a dial, f_* video filters, d_* titles of
folder dialogs."""

PROMPT = """Translate the VALUES of the JSON object below from English into {lang}.

{about}

Rules:
- Return a JSON object with exactly the same keys. Translate every value.
- Keep the placeholders %1, %2, %3 exactly, each as often as in the English.
- A value with "|" holds several forms or units separated by "|": {forms_rule} Keep every other
  "|" list (units, sizes) at the same number of parts.
- Values written in CAPITALS in English are captions: write them in capitals too where {lang} has
  capital letters.
- Keep key names and these words unchanged: {keep}. Keep key combinations (Ctrl+Z, Shift+E, Alt,
  Space, Esc, Enter, PageUp, F12) as they are.
- Use the words Windows 11 itself uses in {lang} (settings, folder, file, full screen, clipboard,
  taskbar, sign in, drag) and address the person the way Windows 11 does in {lang}.
- Plain, short interface language, no marketing, no exclamation marks. Keys, options, tabs and
  menu rows: as short as the English.
- Use the glossary below for its terms, always the same word.
{extra}
Glossary (English: {lang}):
{glossary}

Return ONLY the JSON object.

{payload}
"""

GLOSSARY_PROMPT = """You are localizing a video player for Windows 11 into {lang}.

{about}

For each English term below give the one word or short phrase the interface will use in {lang},
as Windows 11 and well-known players (VLC, Windows Media Player) say it in {lang}. Return ONLY a
JSON object {{"term": "translation", ...}} with the same terms.

{terms}
"""
TERMS = ["player", "playlist", "list", "file", "folder", "settings", "subtitles", "audio track", "sound",
         "volume", "mute", "full screen", "window", "picture", "frame", "screenshot", "clipboard", "timeline",
         "time scale", "panel", "key (a button on the panel)", "skin (the panel's look)", "theme", "accent colour",
         "LCD (the time display on the panel)", "editing (cutting a video)", "fragment (a piece of the video)",
         "drawing (on the frame)", "caption (text drawn on the frame)", "opening (of a TV episode)", "credits",
         "episode", "series", "skip", "watch history", "internet radio", "radio station", "recording",
         "scheduler", "playback speed", "seek", "aspect ratio", "zoom", "filter", "brightness", "contrast",
         "saturation", "update", "download", "tray (notification area)", "tooltip", "shortcut (key combination)"]

REVIEW = """You are reviewing the {lang} translation of OY Player, a video player for Windows 11.

{about}

Each entry is KEY: [English source, current {lang} translation]. Read every translation as a native
{lang} speaker who uses Windows 11 in {lang} every day. Report ONLY entries that are wrong:
mistranslation or changed meaning, grammar or spelling errors, words Windows 11 does not use for
that term in {lang}, terms that differ from the glossary, a word-for-word rendering that reads
unnatural, a key or option much longer than needed, mixed formal and informal address, text that is
not in {lang} at all.

Keep %1 %2, the "|" separated forms and these words untouched: {keep}.
Do not report entries that are merely different from what you would write; only real faults.

Glossary (English: {lang}):
{glossary}

Return a JSON object {{"KEY": "corrected translation", ...}} with only the entries you correct.
If nothing is wrong, return {{}}. Return ONLY the JSON object.

{payload}
"""

_lock = threading.Lock()
# The free tier answers 429 to a dozen requests at once to one model: a few at a time per model,
# and a refusal is waited out rather than counted as a failure.
_gates = defaultdict(lambda: threading.Semaphore(5))


def say(*parts):
    with _lock:
        print(*parts, flush=True)


def key_for_nim():
    if os.environ.get("NVIDIA_NIM_API_KEY"):
        return os.environ["NVIDIA_NIM_API_KEY"]
    env = Path.home() / ".fcc" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "NVIDIA_NIM_API_KEY" and value.strip():
                return value.strip().strip('"').strip("'")
    raise SystemExit("NVIDIA_NIM_API_KEY is not set (environment or ~/.fcc/.env).")


def ask(nim, model, prompt, think=True):
    for wait in (30, 60, 90, 120, 180):
        try:
            with _gates[model]:
                return _ask(nim, model, prompt, think)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(wait)
    raise RuntimeError(f"{model} kept answering 429")


def _ask(nim, model, prompt, think=True):
    body = {
        "model": model,
        "messages": [{"role": "system", "content": "You are a professional software localizer. Output only valid JSON."},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 16000, "stream": True,
    }
    if not think and model.startswith("nvidia/"):
        # Nemotron without its reasoning: a chunk in 10 s instead of 40 (measured 05.11), the same answer
        body["chat_template_kwargs"] = {"enable_thinking": False}
    body = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {nim}", "Content-Type": "application/json", "Accept": "text/event-stream"})
    text = []
    with urllib.request.urlopen(req, timeout=900) as res:
        for raw in res:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            choices = json.loads(line[5:]).get("choices") or [{}]    # the last chunk may carry only usage
            text.append((choices[0].get("delta") or {}).get("content") or "")
    answer = re.sub(r"<think>.*?</think>", "", "".join(text), flags=re.S).strip()
    start, end = answer.find("{"), answer.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"no JSON in the answer ({len(answer)} chars)")
    return json.loads(answer[start:end + 1])


# ---- what a language is written in, for the check that a value is in it at all
SCRIPT = {"Arab": ("ar", "fa"), "Hebr": ("he",), "Cyrl": ("bg", "uk"), "Grek": ("el",), "Deva": ("hi",),
          "Thai": ("th",), "Hani": ("ja", "zh-Hans", "zh-Hant", "ko")}
SCRIPT_OF = {c: s for s, codes in SCRIPT.items() for c in codes}
# the Unicode name word each script's letters carry ("ARABIC LETTER BEH")
NAME_WORD = {"Arab": "ARABIC", "Hebr": "HEBREW", "Cyrl": "CYRILLIC", "Grek": "GREEK", "Deva": "DEVANAGARI",
             "Thai": "THAI"}


def script_letters(code, text):
    """How many letters of the language's own script the text has, and how many of others."""
    own = other = 0
    script = SCRIPT_OF.get(code, "Latn")
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        if script == "Hani":
            mine = any(w in name for w in ("CJK", "IDEOGRAPHIC", "HIRAGANA", "KATAKANA", "HANGUL"))
        elif script == "Latn":
            mine = "LATIN" in name or ch in "ʻʼ"
        else:
            mine = name.startswith(NAME_WORD[script])
        own, other = own + mine, other + (not mine and "LATIN" not in name)
    return own, other


def width(text):
    """Roughly how many Latin letters wide the text is on the screen."""
    w = 0
    for ch in text:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def placeholders(s):
    return sorted(re.findall(r"%\d", s))


def fault(code, key, english, value):
    """Why this value cannot go in, or None."""
    if not isinstance(value, str) or not value.strip():
        return "empty"
    if placeholders(value) != placeholders(english):
        return f"the placeholders must be exactly {placeholders(english) or 'none'}"
    if key.endswith("_forms"):
        if value.count("|") != forms(code) - 1:
            return f"{LANGUAGES[code][1]} needs exactly {forms(code)} forms separated by |"
    elif value.count("|") != english.count("|"):
        return f"exactly {english.count('|') + 1} parts separated by |" if "|" in english else "no | in this value"
    # a word cut short (Iskl.) keeps its point; a sentence ends as the English does
    if re.search(r"\w{6,}[.。।]$", value.rstrip()) and not english.rstrip().endswith((".", "…")):
        return "no full stop at the end, as in the English"
    for name in KEEP:
        if re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", english) and name not in value:
            return f'"{name}" must stay as it is'
    own, other = script_letters(code, value)
    letters = sum(ch.isalpha() for ch in re.sub(r"\b(%s)\b" % "|".join(map(re.escape, KEEP)), "", english))
    if other > 0:
        return "letters of another script"
    if SCRIPT_OF.get(code) in ("Cyrl", "Grek") and any(
            script_letters(code, w)[0] and re.search("[A-Za-z]", w) for w in re.findall(r"\w+", value)):
        return "a word mixes its letters with Latin ones"
    if own == 0 and letters >= 6 and re.search("[a-z]{3}", english) and SCRIPT_OF.get(code):
        return "not written in the language's own script"
    if value.strip() == english.strip() and re.search("[a-z]{4}", english) and not english.startswith("%"):
        return "left in English"
    if english.isupper() and value != value.upper():
        return "write it in capitals, like the English"
    room = max(12, round(2.2 * len(english)) + 4)
    if len(english) <= 24 and width(value) > room:
        return f"too long for its place: at most {room} characters"
    return None


def forms_rule(code):
    """How the plural forms go, with the counts each one takes."""
    from oyplayer.i18n import plural_table
    table = plural_table(code)
    if forms(code) == 1:
        return 'the "_forms" keys take ONE form only (the noun as it follows a number), no "|".'
    groups = [[n for n in range(0, 112) if table[n] == i][:6] for i in range(forms(code))]
    shown = "; ".join(f"form {i + 1} for {', '.join(map(str, g))}..." for i, g in enumerate(groups))
    return (f'the "_forms" keys hold the noun as it follows a number, in exactly {forms(code)} forms '
            f'in this order: {shown}.')


def decimal_point(code):
    """The language's decimal separator for Latin digits (CLDR, through Qt)."""
    point = QLocale(code).decimalPoint()
    return point if point in (".", ",") else "."


def read(code):
    path = LANG_DIR / f"{code}.json"
    return json.loads(path.read_text("utf-8")) if path.is_file() else {}


def write(code, values):
    """In English's order, through a temporary file."""
    out = {k: values[k] for k in EN if k in values}
    tmp = LANG_DIR / f".{code}.json.new"
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(LANG_DIR / f"{code}.json")


def glossary(nim, code, models):
    path = GLOSSARY / f"{code}.json"
    if path.is_file():
        return json.loads(path.read_text("utf-8"))
    lang = LANGUAGES[code][1]
    prompt = GLOSSARY_PROMPT.format(lang=lang, about=ABOUT, terms="\n".join(f"- {t}" for t in TERMS))
    for model in models + models:
        try:
            got = ask(nim, model, prompt)
            if len(got) >= len(TERMS) * 0.8:
                GLOSSARY.mkdir(exist_ok=True)
                path.write_text(json.dumps(got, ensure_ascii=False, indent=0) + "\n", encoding="utf-8", newline="\n")
                return got
        except Exception as e:
            say(f"  {code} glossary: {model} failed ({str(e)[:100]})")
            time.sleep(15)
    raise RuntimeError(f"{code}: no glossary")


def translate_language(nim, code, models, keys):
    lang = LANGUAGES[code][1]
    have = read(code)
    done = {k: v for k, v in have.items() if k in EN and k not in keys}
    done["dec"] = decimal_point(code)
    missing = [k for k in EN if k not in done]
    say(f"{code}: {len(missing)} to translate")
    if not missing:
        write(code, done)
        return []
    terms = glossary(nim, code, models)
    gloss = "\n".join(f"- {k}: {v}" for k, v in terms.items())
    left = []
    for start in range(0, len(missing), CHUNK):
        part = missing[start:start + CHUNK]
        notes, last = {}, {}
        for attempt in range(4):
            todo = list(notes) if notes else part
            fix = ("\nThese were rejected before; fix exactly this:\n" + "\n".join(f"- {k}: {why}" for k, why in notes.items())
                   if notes else "")
            # the first try without the model's reasoning, the retries with it, the last by the other model
            model = models[0 if attempt < 3 else -1]
            prompt = PROMPT.format(lang=lang, about=ABOUT, keep=", ".join(KEEP), forms_rule=forms_rule(code),
                                   extra=fix, glossary=gloss,
                                   payload=json.dumps({k: EN[k] for k in todo}, ensure_ascii=False, indent=1))
            try:
                got = ask(nim, model, prompt, think=attempt > 0)
            except Exception as e:
                say(f"  {code} {start + 1}: {model} failed ({str(e)[:100]})")
                time.sleep(15)
                continue
            notes = {}
            for k in todo:
                why = fault(code, k, EN[k], got.get(k))
                if why:
                    notes[k], last[k] = why, got.get(k)
                else:
                    done[k] = got[k].strip()
            if not notes:
                break
        # after the last try: too long is checked by eye in the window, and a word may well be the
        # same as in English (Contrast in Catalan, Video in German)
        for k in [k for k, why in notes.items() if why.startswith("too long") or why == "left in English"]:
            done[k] = last[k].strip()
            del notes[k]
        if notes:
            say(f"  {code} {start + 1}: still rejected {notes}")
            left += list(notes)
        write(code, done)
    say(f"{code}: written, {len(left)} left in English")
    return left


def review_language(nim, code, models, log):
    lang = LANGUAGES[code][1]
    have = read(code)
    terms = json.loads((GLOSSARY / f"{code}.json").read_text("utf-8")) if (GLOSSARY / f"{code}.json").is_file() else {}
    gloss = "\n".join(f"- {k}: {v}" for k, v in terms.items())
    keys = [k for k in EN if k in have and k != "dec"]
    changed, lines = 0, []
    for start in range(0, len(keys), REVIEW_CHUNK):
        part = keys[start:start + REVIEW_CHUNK]
        payload = {k: [EN[k], have[k]] for k in part}
        prompt = REVIEW.format(lang=lang, about=ABOUT, keep=", ".join(KEEP), glossary=gloss,
                               payload=json.dumps(payload, ensure_ascii=False, indent=1))
        got = None
        for model in models + models[:1]:
            try:
                got = ask(nim, model, prompt)
                break
            except Exception as e:
                say(f"  {code} review {start + 1}: {model} failed ({str(e)[:100]})")
                time.sleep(20)
        if got is None:
            say(f"  {code} review {start + 1}: not reviewed")
            continue
        for k, v in got.items():
            if k not in payload or not isinstance(v, str) or v.strip() == have[k]:
                continue
            why = fault(code, k, EN[k], v)
            if why:
                lines.append(f"REJECTED {k}: {have[k]!r} -> {v!r} ({why})")
                continue
            lines.append(f"{k}: {have[k]!r} -> {v.strip()!r}")
            have[k] = v.strip()
            changed += 1
        write(code, have)
        say(f"  {code} review: {min(start + REVIEW_CHUNK, len(keys))}/{len(keys)}, {changed} corrected")
    with _lock, log.open("a", encoding="utf-8") as f:
        f.write(f"## {code}: {changed} corrected\n" + "\n".join(lines) + "\n\n")
    return changed


def check(codes):
    """The faults in the files, as the self-test sees them; 0 when every language is whole."""
    bad = 0
    for code in codes:
        have = read(code)
        missing = [k for k in EN if k not in have]
        extra = [k for k in have if k not in EN]
        faults = {k: why for k in EN if k in have and k != "dec" and (why := fault(code, k, EN[k], have[k]))}
        if have.get("dec") != decimal_point(code):
            faults["dec"] = f"must be {decimal_point(code)!r}"
        hard = {k: w for k, w in faults.items() if not w.startswith("too long") and w != "left in English"}
        print(f"{code}: {len(have)} strings, {len(missing)} missing, {len(extra)} extra, "
              f"{len(hard)} faults, {len(faults) - len(hard)} long or as in English")
        for k, why in hard.items():
            print(f"   {k}: {why}: {have.get(k)!r}")
        bad += len(missing) + len(extra) + len(hard)
    return bad


# Who writes what (05.11): Nemotron 3.5 Super the big languages of western Europe as well as
# Ultra, five times as fast, but makes words up in the others; MiniMax the east Asian ones as
# well as Ultra; Ultra the rest. Three models at once, as each has its own limit of requests.
SUPER_WRITES = {"da", "de", "es", "es-419", "fr", "it", "nb", "nl", "pt-BR", "pt-PT", "sv"}
MINIMAX_WRITES = {"id", "ja", "ko", "th", "vi", "zh-Hans", "zh-Hant"}


def models_for(code):
    """The model that writes, then the one that takes over on a fault."""
    if code in SUPER_WRITES:
        return [SUPER, MINIMAX]
    return [MINIMAX, NEMOTRON] if code in MINIMAX_WRITES else [NEMOTRON, MINIMAX]


def reviewers_for(code):
    """Another model than the writer, with its reasoning on. Not MiniMax: weighing the Finnish
    and Greek corrections of 05.11 it put back two in five, typos and wrong words among them."""
    return [NEMOTRON, SUPER] if code in SUPER_WRITES else [SUPER, NEMOTRON]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--keys", default="")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--log", default=str(ROOT / "tests" / "out" / "translate-review.log"))
    args = ap.parse_args()
    codes = [c.strip() for c in args.only.split(",") if c.strip()] or [c for c in LANGUAGES if c not in ("en", "uk")]
    if args.check:
        return 1 if check(codes) else 0
    nim = key_for_nim()
    keys = {k.strip() for k in args.keys.split(",") if k.strip()}
    with ThreadPoolExecutor(max_workers=min(args.workers, len(codes))) as pool:
        if args.review:
            log = Path(args.log)
            log.parent.mkdir(parents=True, exist_ok=True)
            results = list(pool.map(lambda c: review_language(nim, c, reviewers_for(c), log), codes))
            print("corrected:", dict(zip(codes, results)))
        else:
            results = list(pool.map(lambda c: translate_language(nim, c, models_for(c), keys), codes))
            left = {c: len(r) for c, r in zip(codes, results) if r}
            if left:
                print("left in English:", left)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
