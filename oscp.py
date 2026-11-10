#!/usr/bin/env python3
"""
oscp - an offline CLI cheat-sheet and reference hub for OSCP exam preparation.

Educational reference only. Use the commands here against machines you own
or are explicitly authorized to test (your own labs, the exam environment).
The only network action is opening a saved bookmark in your browser.
No third-party dependencies - Python standard library only.
"""

import argparse
import contextlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_FILE = os.path.join(_DATA_DIR, "cheatsheet.json")
GTFO_FILE = os.path.join(_DATA_DIR, "gtfobins.json")
NOTES_FILE = os.path.join(_DATA_DIR, "notes.json")
METHODS_FILE = os.path.join(_DATA_DIR, "methods.json")
MANUAL_FILE = os.path.join(_DATA_DIR, "manual.json")
ATLAS_FILE = os.path.join(_DATA_DIR, "atlas.json")
HACKTOOLS_FILE = os.path.join(_DATA_DIR, "hacktools.json")
HOWTO_FILE = os.path.join(_DATA_DIR, "howto.json")
LABSETUP_FILE = os.path.join(_DATA_DIR, "labsetup.json")
TMUX_FILE = os.path.join(_DATA_DIR, "tmux.json")
SHELLSCRIPT_FILE = os.path.join(_DATA_DIR, "shellscript.json")

# ---- tiny ANSI colour helper (auto-disabled when not a TTY or NO_COLOR set) ----
_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def c(text, code):
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t):
    return c(t, "1")


def cyan(t):
    return c(t, "36")


def green(t):
    return c(t, "32")


def yellow(t):
    return c(t, "33")


def magenta(t):
    return c(t, "35")


def red(t):
    return c(t, "31")


def dim(t):
    return c(t, "2")


def vispad(s, n):
    extra = n - visible_len(s)
    if extra > 0:
        return s + " " * extra
    return s


def section(title):
    """Yellow group banner: ── everyday ──"""
    return yellow(f"── {title} ──")


def query_parts(term):
    """Tokens of a search term. 'feroxbuster php' -> ['feroxbuster', 'php']."""
    raw = (term or "").strip().lower()
    if not raw:
        return []
    parts = [p for p in re.split(r"\s+", raw) if len(p) >= 2]
    return parts or [raw]


def query_match(hay, term):
    """True when the phrase is in hay, or every token is (so quoted multi-word search works)."""
    hay = (hay or "").lower()
    raw = (term or "").strip().lower()
    if not raw:
        return False
    if raw in hay:
        return True
    parts = query_parts(raw)
    if len(parts) <= 1:
        return False
    return all(p in hay for p in parts)


def hl(text, needle=None):
    """Mark each search token in sober bold red so a hit is obvious in the line."""
    if text is None:
        return ""
    if not needle:
        return text
    parts = query_parts(str(needle))
    if not parts:
        return text
    parts = sorted(set(parts), key=len, reverse=True)
    pattern = "(" + "|".join(re.escape(p) for p in parts) + ")"
    return re.sub(pattern, lambda m: c(m.group(1), "1;31"), str(text), flags=re.I)


def visible_len(s):
    return len(_ANSI_RE.sub("", s))


def term_size():
    return shutil.get_terminal_size((80, 24))


def body_width():
    return min(term_size().columns, 96)


# ----------------------------------------------------------------- pager ----
def _read_key():
    """Read a single keypress from the terminal (raw mode), stdlib only."""
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def page_output(text):
    """Print text a page at a time, from the top.

    Enter -> one line, Space/Tab -> one page, q -> quit. Mirrors `ti`: it
    starts at the top and never jumps to the bottom. Falls back to a plain
    dump when output is not going to an interactive terminal.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    interactive = sys.stdout.isatty() and sys.stdin.isatty()
    rows = term_size().lines
    if not interactive or len(lines) < rows:
        sys.stdout.write("\n".join(lines) + "\n")
        return

    body = max(rows - 1, 1)
    footer = (bold(cyan("▾ more")) + dim("    ") + bold(cyan("Enter")) + dim(" next line    ")
              + bold(cyan("Space")) + dim(" next page    ") + bold(cyan("q")) + dim(" quit"))
    i = 0
    for _ in range(body):
        print(lines[i]); i += 1
    try:
        while i < len(lines):
            sys.stdout.write("\r\033[K" + footer); sys.stdout.flush()
            k = _read_key()
            sys.stdout.write("\r\033[K")
            if k in ("q", "Q", "\x03", "\x04"):      # q / Ctrl-C / Ctrl-D
                break
            elif k in (" ", "\t"):                    # page
                for _ in range(body):
                    if i >= len(lines):
                        break
                    print(lines[i]); i += 1
            elif k in ("\r", "\n"):                   # single line
                print(lines[i]); i += 1
            # any other key: ignore, reprompt
    except (KeyboardInterrupt, OSError):
        pass
    finally:
        sys.stdout.write("\r\033[K")


def run_paged(func, *fargs):
    """Capture a command's stdout and feed it to the pager."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(*fargs)
    page_output(buf.getvalue())


# ---------------------------------------------------- pick-a-line & copy ----
def clean_copy_line(plain):
    """Strip display decoration so the copied text is ready to paste.

    A command line may carry a note after it ('cmd    # why'). Only the command
    is copied. A line that is itself a comment, or has no note field, is copied whole.
    """
    s = _ANSI_RE.sub("", plain).rstrip().lstrip()
    s = re.sub(r"^[│├└─]+\s*", "", s)   # bookmark-tree branches
    s = re.sub(r"^\$\s+", "", s)         # the '$ ' command prompt marker
    if not s.lstrip().startswith("#"):
        s = re.sub(r"\s+#\s.*$", "", s)
    return s.rstrip()


def parse_selection(sel, maxn):
    """Parse '3', '3-5', '3,7', '3-5 8' into a bounded, de-duped line list."""
    nums = []
    for tok in re.split(r"[,\s]+", sel.strip()):
        if not tok:
            continue
        m = re.match(r"^(\d+)-(\d+)$", tok)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            nums.extend(range(a, b + 1))
        elif tok.isdigit():
            nums.append(int(tok))
        else:
            return None
    seen, out = set(), []
    for n in nums:
        if 1 <= n <= maxn and n not in seen:
            seen.add(n)
            out.append(n)
    return out


_URL_RE = re.compile(r"https?://[^\s|)\]]+")


def _pick_and_copy(content):
    maxn = max(content)
    try:
        prompt = (bold(cyan("Copy")) + dim(" a line → type ") + bold(green("N"))
                  + dim(" (or ") + bold(green("N-M")) + dim(" for a range)     ")
                  + bold(cyan("Open link")) + dim(" → ") + bold(green("o N"))
                  + dim("     Enter skips  "))
        sel = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not sel:
        return
    # open a URL from a line in the browser (for the latest upstream content)
    mo = re.match(r"^o\s*(\d+)$", sel, re.I)
    if mo:
        i = int(mo.group(1))
        if i not in content:
            print(dim(f"no line {i}."))
            return
        m = _URL_RE.search(content[i])
        if not m:
            print(dim(f"no link on line {i}."))
            return
        used = open_url(m.group(0))
        print(dim(f"opened {m.group(0)}  in {used}"))
        return
    nums = parse_selection(sel, maxn)
    if not nums:
        print(dim("nothing copied — type a line number like ") + bold(green("3"))
              + dim(", a range like ") + bold(green("3-5")) + dim(", or ") + bold(green("o 7"))
              + dim(" to open a link."))
        return
    out = "\n".join(clean_copy_line(content[i]) for i in nums)
    tool = clipboard_copy(out)
    if tool:
        label = sel if len(nums) > 1 else str(nums[0])
        print(dim(f"copied line {label} to clipboard ({tool})"))
        preview = out.replace("\n", " ⏎ ")
        if len(preview) > 90:
            preview = preview[:87] + "..."
        print(f"  {green('→')} {preview}")
    else:
        print(red("no clipboard helper found; could not copy"))


def page_and_pick(disp, content):
    """Page numbered output; allow copying a line/range mid-page (c) or at the end."""
    rows = term_size().lines
    n = len(disp)
    if n < rows:                        # fits on one screen
        print("\n".join(disp))
        if content:
            _pick_and_copy(content)
        return
    body = max(rows - 1, 1)
    footer = (bold(cyan("▾ more")) + dim("    ") + bold(cyan("Enter")) + dim(" next line    ")
              + bold(cyan("Space")) + dim(" next page    ") + bold(cyan("c")) + dim(" copy a line    ")
              + bold(cyan("q")) + dim(" quit"))
    i = 0
    for _ in range(body):
        print(disp[i]); i += 1
    try:
        while i < n:
            sys.stdout.write("\r\033[K" + footer); sys.stdout.flush()
            k = _read_key()
            sys.stdout.write("\r\033[K")
            if k in ("q", "Q", "\x03", "\x04"):
                return
            elif k in ("c", "C"):       # copy a visible line without reaching the end
                if content:
                    _pick_and_copy(content)
            elif k in (" ", "\t"):
                for _ in range(body):
                    if i >= n:
                        break
                    print(disp[i]); i += 1
            elif k in ("\r", "\n"):
                print(disp[i]); i += 1
    except (KeyboardInterrupt, OSError):
        return
    if content:
        _pick_and_copy(content)


def run_pickable(func, *fargs):
    """Run a display command, number its lines, then let the user copy line(s)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        func(*fargs)
    text = buf.getvalue()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    interactive = (sys.stdout.isatty() and sys.stdin.isatty()
                   and os.environ.get("OSCP_NO_PICK") is None)
    plain = [_ANSI_RE.sub("", ln) for ln in lines]
    total = sum(1 for p in plain if p.strip())
    if not interactive or total == 0:
        sys.stdout.write("\n".join(lines) + "\n")
        return
    w = len(str(total))
    content, disp, n = {}, [], 0
    for raw, p in zip(lines, plain):
        if p.strip():
            n += 1
            content[n] = p
            disp.append(f"{dim(str(n).rjust(w))}  {raw}")
        else:
            disp.append("")
    page_and_pick(disp, content)


# -------------------------------------------------------------------- data ----
def load_data():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.exit(f"error: data file not found at {DATA_FILE}")
    except json.JSONDecodeError as e:
        sys.exit(f"error: cheatsheet.json is not valid JSON ({e})")
    if not isinstance(data, dict) or "categories" not in data or "meta" not in data:
        sys.exit("error: cheatsheet.json must be an object with 'meta' and 'categories' keys")
    if not isinstance(data["categories"], list):
        sys.exit("error: 'categories' in cheatsheet.json must be a list")
    data.setdefault("bookmarks", [])
    return data


def save_data(data):
    """Write the knowledge base back to disk (used by bookmark add/rm)."""
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, DATA_FILE)


def find_category(data, cat_id):
    cat_id = cat_id.lower()
    for cat in data["categories"]:
        if cat["id"] == cat_id:
            return cat
    matches = [cat for cat in data["categories"] if cat_id in cat["id"]]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        opts = ", ".join(c["id"] for c in matches)
        sys.exit(f"'{cat_id}' is ambiguous - matches: {opts}")
    return None


def require_category(data, cat_id):
    cat = find_category(data, cat_id)
    if not cat:
        avail = ", ".join(c["id"] for c in data["categories"])
        sys.exit(f"unknown category '{cat_id}'.\navailable: {avail}")
    return cat


_DANGER_RE = (
    (re.compile(r"\brm\s+-[^\s]*r", re.I), "deletes files"),
    (re.compile(r"\bchmod\b", re.I), "changes permissions"),
    (re.compile(r"\bchown\b|\bchgrp\b", re.I), "changes ownership"),
    (re.compile(r"\b(killall|pkill|kill)\b", re.I), "stops a process"),
    (re.compile(r"\bdd\b", re.I), "overwrites a disk"),
    (re.compile(r"\bmkfs", re.I), "overwrites a disk"),
    (re.compile(r"\breset\s+--hard\b", re.I), "discards uncommitted work"),
    (re.compile(r"\bclean\s+-[^\s]*f", re.I), "deletes untracked files"),
    (re.compile(r"--force(?:-with-lease)?\b", re.I), "overwrites history or files"),
    (re.compile(r"\bgit\s+push\b[^\n]*\s-f\b", re.I), "overwrites remote history"),
    (re.compile(r"\bpush\s+[^\n]*--delete\b", re.I), "deletes a remote ref"),
)


def cmd_danger(cmd):
    """Short reason when argv can destroy work. Empty when the line is ordinary."""
    if not cmd:
        return ""
    for pat, reason in _DANGER_RE:
        if pat.search(cmd):
            return reason
    return ""


def print_dollar(cmd, highlight=None, indent="    "):
    shown = hl(cmd, highlight)
    reason = cmd_danger(cmd)
    if reason:
        print(f"{indent}{green('$')} {red('!')} {shown}  {red('! ' + reason)}")
        return
    print(f"{indent}{green('$')} {shown}")


def print_entry(entry, highlight=None, num=None):
    prefix = f"{dim(str(num) + '.'):<3} " if num is not None else "  "
    print(f"{prefix}{bold(hl(entry.get('title', '(untitled)'), highlight))}")
    if entry.get("cmd"):
        print_dollar(entry["cmd"], highlight)
    if entry.get("desc"):
        print(f"    {dim(hl(entry['desc'], highlight))}")
    if entry.get("notes"):
        print(f"    {yellow('note:')} {dim(hl(entry['notes'], highlight))}")
        if re.search(r"ctrl-a", entry["notes"], re.I):
            print(f"    {_tmux_prefix_note()}")
    print()


# ------------------------------------------------------------- clipboard ----
def clipboard_copy(text):
    if platform.system() == "Darwin":
        candidates = [["pbcopy"]]
    else:
        candidates = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for argv in candidates:
        try:
            if subprocess.run(argv, input=text.encode("utf-8"), check=True).returncode == 0:
                return argv[0]
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return None


# --------------------------------------------------------------- browser ----
_MAC_APPS = {
    "chrome": "Google Chrome", "safari": "Safari", "firefox": "Firefox",
    "edge": "Microsoft Edge", "brave": "Brave Browser", "arc": "Arc",
    "chromium": "Chromium", "opera": "Opera", "vivaldi": "Vivaldi",
}


def open_url(url, browser=None):
    want = (browser or "").lower()
    if platform.system() == "Darwin":
        if want and want != "system":
            app = _MAC_APPS.get(want)
            if app and subprocess.run(["open", "-a", app, url],
                                      stderr=subprocess.DEVNULL).returncode == 0:
                return app
            print(dim(f"{browser} not available; falling back to the default browser"))
        elif not want:
            if subprocess.run(["open", "-a", "Google Chrome", url],
                              stderr=subprocess.DEVNULL).returncode == 0:
                return "Google Chrome"
        subprocess.run(["open", url])
        return "default browser"
    import webbrowser
    if want and want != "system":
        try:
            webbrowser.get(want).open(url)
            return want
        except webbrowser.Error:
            print(dim(f"{browser} not available; falling back to the default browser"))
    webbrowser.open(url)
    return "default browser"


def entry_by_number(cat, n):
    if n < 1 or n > len(cat["entries"]):
        sys.exit(f"'{cat['id']}' has entries 1-{len(cat['entries'])}; got {n}")
    return cat["entries"][n - 1]


# ------------------------------------------------------------- bookmarks ----
RATINGS = {"good": 1, "very good": 2, "excellent": 3, "1": 1, "2": 2, "3": 3}


def parse_rating(value):
    key = str(value).strip().lower()
    if key not in RATINGS:
        sys.exit("rating must be one of: good, very good, excellent (or 1, 2, 3)")
    return RATINGS[key]


def stars(rate):
    """Filled stars use the same three colours as the Tab menus. Empty stars stay dim."""
    rate = int(rate or 0)
    if rate >= 3:
        filled = c("★" * rate, "38;5;132")       # sober magenta
    elif rate == 2:
        filled = c("★★", "38;5;185")             # sober yellow
    elif rate == 1:
        filled = c("★", "38;5;179")              # soft amber
    else:
        filled = ""
    empty = max(0, 3 - min(rate, 3))
    return filled + (dim("☆" * empty) if empty else "")


def bookmark_by_id(data, bid):
    for bm in data["bookmarks"]:
        if bm.get("id") == bid:
            return bm
    sys.exit(f"no bookmark #{bid}. try: oscp bm list")


def next_bookmark_id(data):
    return max((bm.get("id", 0) for bm in data["bookmarks"]), default=0) + 1


def host_of(url):
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


def print_bookmark_tree(bookmarks):
    groups = {}
    for bm in bookmarks:
        groups.setdefault(bm.get("group", "misc"), []).append(bm)
    for gname in sorted(groups):
        items = sorted(groups[gname], key=lambda b: (-int(b.get("rate", 0)), b.get("name", "").lower()))
        print(f"{bold(gname)}  {dim('(' + str(len(items)) + ')')}")
        for i, bm in enumerate(items):
            branch = "└─" if i == len(items) - 1 else "├─"
            line = (f"  {dim(branch)} {cyan(str(bm.get('id')).rjust(3))}  "
                    f"{stars(bm.get('rate'))}  {bm.get('name', '(unnamed)')}")
            print(f"{line}  {dim(host_of(bm.get('url', '')))}")
            if bm.get("note"):
                print(f"       {dim(bm['note'])}")
        print()


# ---------------------------------------------------------------- commands ----
# Second word of `oscp cmd web <page>`. `basic` is the enumeration page.
# The ids are real categories, hidden from the top-level list so Tab stays short.
_WEB_PAGES = (
    ("basic", "web", "the enumeration page"),
    ("php", "web-php", "LFI, wrappers, upload"),
    ("wp", "web-wp", "WordPress users, plugins, xmlrpc"),
    ("tomcat", "web-tomcat", "manager and a WAR deploy"),
    ("jenkins", "web-jenkins", "script console"),
    ("iis", "web-iis", "WebDAV and aspx"),
    ("joomla", "web-joomla", "admin and version files"),
    ("drupal", "web-drupal", "changelog and login"),
    ("git", "web-git", "an exposed .git"),
)
_WEB_PAGE_IDS = {name: cid for name, cid, _desc in _WEB_PAGES}
_WEB_PAGE_IDS["wordpress"] = "web-wp"
_CMD_HIDDEN = {cid for _name, cid, _desc in _WEB_PAGES if cid != "web"}


def _resolve_cmd_words(words):
    """One category word, or `web` plus a page name."""
    if len(words) > 2:
        sys.exit("usage: oscp cmd [<category> [<page>]]")
    if len(words) == 2:
        head, page = words[0].lower(), words[1].lower()
        if head != "web":
            sys.exit(f"usage: oscp cmd {words[0]}\n"
                     f"a second word is only for web:  oscp cmd web php")
        cid = _WEB_PAGE_IDS.get(page)
        if not cid:
            names = " ".join(name for name, _cid, _desc in _WEB_PAGES)
            sys.exit(f"no web page '{words[1]}'.\n"
                     f"pages: {names}\n"
                     f"try: oscp cmd web")
        return cid
    word = words[0]
    # `php` / `wp` open that page. `basic` does not, it only means something after `web`.
    if word.lower() != "basic":
        alias = _WEB_PAGE_IDS.get(word.lower())
        if alias and alias != "web":
            return alias
    return word


def cmd_list(data, args):
    print(bold(data["meta"]["title"]))
    print(dim(data["meta"]["note"]))
    print()
    print(bold("Categories:"))
    for cat in data["categories"]:
        if cat["id"] in _CMD_HIDDEN:
            continue
        count = len(cat["entries"])
        print(f"  {vispad(bold(cat['id']), 28)} {dim(cat['name'])} {dim(f'({count})')}")
        if cat["id"] == "web":
            pages = " ".join(name for name, _cid, _desc in _WEB_PAGES)
            print(dim(f"    pages: {pages}"))
    nb = len(data["bookmarks"])
    print()
    print(dim("open one:  oscp cmd <category>     web page:  oscp cmd web php"))
    print(dim(f"find:  oscp search <term>     links:  oscp bm list  ({nb})"))


def cmd_show(data, args):
    cat = require_category(data, args.category)
    print(bold(cat["name"]) + "  " + dim(f"[{cat['id']}]"))
    if cat["id"] == "tmux":
        print(_tmux_prefix_note())
    tags = cat.get("tags", [])
    if tags:
        print(dim("tags: " + ", ".join(tags)))
    print()
    for i, entry in enumerate(cat["entries"], 1):
        print_entry(entry, num=i)
    print(dim("a line number copies the command"))


def _search_store_index(term, cap=18, skip_atlas=False):
    """Search methods/manual/atlas/gtfo/notes; return [(label, [(opencmd, title)])]."""
    out = []

    def _sec(label, opencmd_fn, items, text_fn, title_fn, key_fn):
        matched = [it for it in items if query_match(text_fn(it), term)]
        if matched:
            rows = [(opencmd_fn(key_fn(it)), title_fn(it)) for it in matched[:cap]]
            out.append((f"{label}  ·  {len(matched)} match(es)", rows,
                        len(matched) - len(rows)))

    try:
        md = load_json_file(METHODS_FILE, "methods")
        _sec("PATH   (the exam, in order)", lambda k: f"oscp technique show {k}",
             md.get("methods", []),
             lambda m: " ".join([m["id"], m["title"], m.get("brief", ""),
                                 m.get("body", "")] + m.get("tags", [])).lower(),
             lambda m: m.get("brief", m["title"]), lambda m: m["id"])
    except SystemExit:
        pass
    try:
        man = load_json_file(MANUAL_FILE, "manual")
        _sec("TECHNIQUE   (one write-up)", lambda k: f"oscp technique show {k}",
             man.get("entries", []),
             lambda m: " ".join([m["id"], m["title"], m.get("brief", ""),
                                 m.get("body", "")] + m.get("tags", [])).lower(),
             lambda m: m.get("brief", m["title"]), lambda m: m["id"])
    except SystemExit:
        pass
    if not skip_atlas:
        try:
            at = load_json_file(ATLAS_FILE, "atlas")
            def _atlas_text(c):
                parts = [c["name"], c.get("description", ""), " ".join(c.get("tags", []))]
                parts += [a[0] + " " + a[1] for a in c.get("anatomy", [])]
                for u in c.get("usecases", []):
                    parts.extend(_uc_fields(u))
                return " ".join(str(p) for p in parts)
            _sec("ATLAS   (one command in depth)", lambda k: f"oscp atlas {k}",
                 sorted(at.get("commands", []), key=lambda x: x["name"]),
                 _atlas_text, lambda c: c.get("description", "").split(". ")[0], lambda c: c["name"])
        except SystemExit:
            pass
    try:
        g = load_json_file(GTFO_FILE, "GTFOBins")
        bins = [(n, b) for n, b in sorted(g["binaries"].items())]
        def _gtfo_text(nb):
            n, b = nb
            cmds = " ".join(e.get("command", "") for v in b["functions"].values() for e in v)
            return (n + " " + " ".join(b["functions"].keys()) + " " + cmds).lower()
        _sec("GTFOBINS   (abuse a binary)", lambda k: f"oscp gtfo {k}", bins,
             _gtfo_text, lambda nb: ", ".join(nb[1]["functions"].keys()), lambda nb: nb[0])
    except SystemExit:
        pass
    try:
        n = load_json_file(NOTES_FILE, "notes")
        _sec("NOTES   (0xsyr0 cheat sheet)", lambda k: f"oscp technique show {k}",
             n.get("sections", []),
             lambda s: " ".join([s["id"], s["title"], s.get("body", "")]).lower(),
             lambda s: s["title"], lambda s: s["id"])
    except SystemExit:
        pass
    try:
        tx = load_json_file(TMUX_FILE, "tmux")

        def _tmux_text(s):
            parts = [s.get("id", ""), s.get("name", ""), s.get("goal", ""),
                     s.get("why", ""), s.get("gotcha", "")]
            for step in s.get("steps") or []:
                parts.extend(str(x) for x in step)
            tbl = s.get("table") or {}
            parts.extend(tbl.get("headers") or [])
            for row in tbl.get("rows") or []:
                parts.extend(str(x) for x in row)
            return " ".join(parts).lower()

        _sec("TMUX   (this machine's terminal)", lambda k: f"oscp tmux {k}",
             tx.get("sections", []), _tmux_text,
             lambda s: s.get("goal") or s.get("name", ""), lambda s: s["id"])
    except SystemExit:
        pass
    try:
        sh = load_json_file(SHELLSCRIPT_FILE, "shell-script")

        def _sh_text(s):
            parts = [s.get("id", ""), s.get("name", ""), s.get("goal", ""),
                     s.get("why", ""), s.get("gotcha", "")]
            for step in s.get("steps") or []:
                parts.extend(str(x) for x in step)
            tbl = s.get("table") or {}
            parts.extend(tbl.get("headers") or [])
            for row in tbl.get("rows") or []:
                parts.extend(str(x) for x in row)
            return " ".join(parts).lower()

        _sec("BASH   (shell-script library)", lambda k: f"oscp shell-script {k}",
             sh.get("sections", []), _sh_text,
             lambda s: s.get("goal") or s.get("name", ""), lambda s: s["id"])
    except SystemExit:
        pass
    return out


# First word of `oscp search <shelf> <term>`. The names are the ones the
# search prompt lists. A few short aliases are accepted on purpose.
_SEARCH_SHELVES = {
    "cheat-sheet": "cheatsheet",
    "cheatsheet": "cheatsheet",
    "cmd": "cheatsheet",
    "methods": "methods",
    "method": "methods",
    "path": "methods",
    "manual": "manual",
    "atlas": "atlas",
    "gtfo": "gtfo",
    "gtfobins": "gtfo",
    "notes": "notes",
    "note": "notes",
    "bash": "bash",
    "shell-script": "bash",
    "shellscript": "bash",
}

# Section title in the wide index -> the shelf name used to open the rest.
_SEARCH_MORE = {
    "PATH": "methods",
    "TECHNIQUE": "manual",
    "ATLAS": "atlas",
    "GTFOBINS": "gtfo",
    "NOTES": "notes",
    "BASH": "bash",
}


def _shell_word(term):
    """A term safe to paste back into the shell."""
    if term and not any(c.isspace() for c in term):
        return term
    return "'" + term.replace("'", "'\\''") + "'"


def _cheatsheet_hits(data, term):
    found = []
    for cat in data["categories"]:
        matched = []
        for entry in cat["entries"]:
            entry_hay = " ".join([
                entry.get("title", ""),
                entry.get("cmd", ""),
                entry.get("desc", ""),
                entry.get("notes", ""),
            ])
            tagged = entry_hay + " " + " ".join(cat.get("tags", []))
            if query_match(entry_hay, term) or (
                    len(query_parts(term)) == 1 and query_match(tagged, term)):
                matched.append(entry)
        if matched:
            found.append((cat, matched))
    return found


def _print_cheatsheet_hits(found, highlight):
    hits = 0
    print(bold(magenta("CHEAT-SHEET")) + dim("   (copy-ready commands)"))
    print()
    for cat, matched in found:
        print(bold(cat["name"]) + "  " + dim(f"[{cat['id']}]"))
        print()
        for entry in matched:
            print_entry(entry, highlight=highlight)
            hits += 1
    return hits


def _search_shelf(data, shelf, term_raw):
    """One shelf. The output is the same search that shelf's own command runs."""
    shown = _shell_word(term_raw)
    if shelf == "cheatsheet":
        found = _cheatsheet_hits(data, term_raw.lower())
        if not found:
            sys.exit(f"no cheat-sheet entry matches '{term_raw}'. "
                     f"try: oscp search {shown}   (searches everything)")
        hits = _print_cheatsheet_hits(found, term_raw)
        print(dim(f"{hits} result(s) in the cheat-sheet  ·  "
                  f"everywhere:  oscp search {shown}"))
        return
    if shelf == "methods":
        _kb_browse(METHODS_FILE, "methods", "oscp methods", "search", None, None, term_raw)
        return
    if shelf == "manual":
        _kb_browse(MANUAL_FILE, "manual", "oscp manual", "search", None, None, term_raw)
        return
    if shelf == "atlas":
        cmd_atlas(data, argparse.Namespace(atlas_arg="search", atlas_arg2=term_raw))
        return
    if shelf == "gtfo":
        cmd_gtfo(data, argparse.Namespace(binary="search", filter=term_raw))
        return
    if shelf == "bash":
        sh = load_json_file(SHELLSCRIPT_FILE, "shell-script")
        term = term_raw.lower()
        hits = 0
        for s in sh.get("sections", []):
            parts = [s.get("id", ""), s.get("name", ""), s.get("goal", ""),
                     s.get("why", ""), s.get("gotcha", "")]
            for step in s.get("steps") or []:
                parts.extend(str(x) for x in step)
            blob = " ".join(parts)
            if not query_match(blob, term):
                continue
            hits += 1
            print(bold(hl(s["id"], term_raw)) + "  " + dim(hl(s.get("name", ""), term_raw)))
            print(f"    {green('$')} {hl('oscp shell-script ' + s['id'], term_raw)}")
            for step in s.get("steps") or []:
                cmd = step[1] if len(step) > 1 else ""
                if cmd and term in cmd.lower():
                    first = cmd.split("\n")[0]
                    print(f"    {green('$')} {hl(first, term_raw)}")
            print()
        if hits == 0:
            sys.exit(f"no shell-script section matches '{term_raw}'. "
                     f"try: oscp search {shown}   (searches everything)")
        print(dim(f"{hits} section(s) in shell-script  ·  "
                  f"everywhere:  oscp search {shown}"))
        return
    cmd_notes(data, argparse.Namespace(notes_command="search", term=term_raw))


def cmd_search(data, args):
    words = list(args.term)
    shelf = _SEARCH_SHELVES.get(words[0].lower()) if len(words) >= 2 else None
    if shelf:
        _search_shelf(data, shelf, " ".join(words[1:]))
        return

    term_raw = " ".join(words)
    term = term_raw.lower()
    found = _cheatsheet_hits(data, term)
    hits = _print_cheatsheet_hits(found, term_raw) if found else 0

    atlas_hits = []
    try:
        at = load_json_file(ATLAS_FILE, "atlas")
        atlas_hits = atlas_command_hits(at.get("commands", []), term)
    except SystemExit:
        pass
    atlas_count = len(atlas_hits)
    if atlas_hits:
        if hits:
            print()
        print(bold(magenta("ATLAS")) + dim("   (command + why)"))
        print()
        print_atlas_search_hits(atlas_hits, term_raw, cap_cmds=8, cap_cards=4)

    # methods / manual / gtfo / notes / tmux / bash (atlas is printed above)
    sections = _search_store_index(term, skip_atlas=True)
    idx_hits = sum(len(rows) + extra for _, rows, extra in sections)
    if sections:
        if hits or atlas_hits:
            print()
        print(bold(magenta("ALSO IN")) + dim("   (open any line)"))
        for label, rows, extra in sections:
            print(bold(label))
            width = max((len(c) for c, _ in rows), default=0)
            for opencmd, title in rows:
                print(f"    {green('$')} {hl(opencmd.ljust(width), term_raw)}   {dim('# ' + hl(title, term_raw))}")
            if extra:
                more = _SEARCH_MORE.get(label.split()[0])
                if more:
                    print(f"    {dim(f'... +{extra} more:  oscp search {more} {_shell_word(term_raw)}')}")
            print()

    total = hits + atlas_count + idx_hits
    if total == 0:
        print(f"no matches for {bold(term_raw)} anywhere.")
        print(dim("oscp search looks across cheat-sheet · methods · manual · atlas · gtfo · notes · bash"))
        print(dim("one shelf:  oscp search cheat-sheet <term>   ·   methods  manual  atlas  gtfo  notes  bash"))
        print(dim("try a broader term, or:  oscp howto map   (which command does what)"))
    else:
        print(dim(f"{total} result(s) for '{term_raw}'  ·  "
                  f"cheat-sheet {hits} · atlas {atlas_count} · elsewhere {idx_hits}"))


def cmd_copy(data, args):
    cat = require_category(data, args.category)
    entry = entry_by_number(cat, args.number)
    cmd = entry.get("cmd")
    if not cmd:
        sys.exit(f"entry {args.number} in '{cat['id']}' has no command to copy")
    tool = clipboard_copy(cmd)
    print(f"  {bold(entry.get('title', ''))}")
    print(f"    {green('$')} {cmd}")
    if tool:
        print(dim(f"copied to clipboard ({tool})"))
    else:
        helper = "pbcopy" if platform.system() == "Darwin" else "xclip / xsel / wl-copy"
        print(red(f"no clipboard helper found (install {helper}); command printed above"))


# -- bookmark subcommands --
def cmd_bm_list(data, args):
    bms = data["bookmarks"]
    if getattr(args, "group", None):
        g = args.group.lower()
        bms = [b for b in bms if b.get("group", "").lower() == g]
        if not bms:
            sys.exit(f"no bookmarks in group '{args.group}'. try: oscp bm list")
    if not bms:
        print("no bookmarks yet.")
        print(dim("add one: oscp bm add URL --group offsec --rate excellent"))
        return
    print_bookmark_tree(bms)
    print(dim("open N · add URL --group G --rate R · rm N · find TEXT · oscp help bm"))


def cmd_bm_open(data, args):
    bm = bookmark_by_id(data, args.number)
    used = open_url(bm["url"], browser=args.browser)
    print(f"Opened #{bm['id']}  {bold(bm.get('name', ''))}  in {used}  {dim('(' + bm['url'] + ')')}")


def cmd_bm_find(data, args):
    term = args.term.lower()
    matched = []
    for bm in data["bookmarks"]:
        hay = " ".join([bm.get("name", ""), bm.get("url", ""), bm.get("note", ""),
                        bm.get("group", "")] + bm.get("tags", [])).lower()
        if query_match(hay, term):
            matched.append(bm)
    if not matched:
        sys.exit(f"no bookmarks match '{args.term}'. try: oscp bm list")
    print_bookmark_tree(matched)
    print(dim(f"{len(matched)} match(es) for '{args.term}'"))


def cmd_bm_add(data, args):
    url = args.url.strip()
    md = re.match(r"\[([^\]]+)\]\((\S+)\)", url)
    name = args.name
    if md:
        name = name or md.group(1)
        url = md.group(2)
    if not re.match(r"https?://", url):
        url = "https://" + url
    if not name:
        name = host_of(url).replace(".", " ")
    for bm in data["bookmarks"]:
        if bm.get("url", "").rstrip("/") == url.rstrip("/"):
            sys.exit(f"already saved as #{bm['id']}  {bm.get('name', '')}")
    bm = {
        "id": next_bookmark_id(data),
        "name": name,
        "url": url,
        "group": (args.group or "misc").lower(),
        "rate": parse_rating(args.rate) if args.rate else 0,
        "note": args.note or "",
        "tags": [],
    }
    data["bookmarks"].append(bm)
    save_data(data)
    print(f"Saved #{bm['id']}  {bold(bm['name'])}  {stars(bm['rate'])}  {dim('[' + bm['group'] + ']')}")


def cmd_bm_rate(data, args):
    bm = bookmark_by_id(data, args.number)
    bm["rate"] = parse_rating(args.rating)
    save_data(data)
    print(f"Re-rated #{bm['id']}  {bold(bm.get('name', ''))}  {stars(bm['rate'])}")


def cmd_bm_rm(data, args):
    bm = bookmark_by_id(data, args.number)
    data["bookmarks"] = [b for b in data["bookmarks"] if b.get("id") != args.number]
    save_data(data)
    print(f"Removed #{bm['id']}  {bm.get('name', '')}")


def cmd_bm_import(data, args):
    try:
        with open(args.file, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        sys.exit(f"cannot read {args.file}: {e}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    incoming = []
    if isinstance(parsed, dict) and ("bookmarks" in parsed or "links" in parsed):
        incoming = parsed.get("bookmarks") or parsed.get("links") or []
    elif isinstance(parsed, list):
        incoming = parsed
    else:
        for line in raw.splitlines():
            line = line.strip().lstrip("-*• ").strip()
            if not line:
                continue
            md = re.match(r"\[([^\]]+)\]\((\S+)\)", line)
            if md:
                incoming.append({"name": md.group(1), "url": md.group(2)})
            elif re.search(r"\S+\.\S+", line):
                incoming.append({"url": line.split()[0]})
    existing = {b.get("url", "").rstrip("/") for b in data["bookmarks"]}
    added = 0
    for item in incoming:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        if not re.match(r"https?://", url):
            url = "https://" + url
        if url.rstrip("/") in existing:
            continue
        name = item.get("name") or host_of(url).replace(".", " ")
        rate = item.get("rate", 0)
        if isinstance(rate, str):
            rate = RATINGS.get(rate.lower(), 0)
        data["bookmarks"].append({
            "id": next_bookmark_id(data),
            "name": name,
            "url": url,
            "group": (args.group or item.get("group") or "misc").lower(),
            "rate": int(rate or 0),
            "note": item.get("note", ""),
            "tags": item.get("tags", []) if isinstance(item.get("tags"), list) else [],
        })
        existing.add(url.rstrip("/"))
        added += 1
    save_data(data)
    print(dim(f"imported {added} new bookmark(s); {len(incoming) - added} skipped (already saved / blank)"))


def cmd_bm_root(data, args):
    args.group = None
    cmd_bm_list(data, args)


# -------------------------------------------------------- gtfobins / notes ----
def load_json_file(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"{what} data not found at {path}.\n(rebuild it from the upstream source, or reinstall oscp)")
    except json.JSONDecodeError as e:
        sys.exit(f"{what} data is not valid JSON ({e})")


def render_gtfo(name, b, filt):
    print(f"{bold(name)}  {dim('— GTFOBins')}")
    if b.get("description"):
        print(dim(b["description"]))
    print()
    shown = 0
    for ftype, entries in b["functions"].items():
        rows = []
        for e in entries:
            ctx = [x.lower() for x in e.get("contexts", [])]
            if filt and filt not in ftype.lower() and filt not in ctx:
                continue
            rows.append(e)
        if not rows:
            continue
        print(f"  {bold(ftype)}")
        for e in rows:
            if e.get("contexts"):
                print(f"    {dim('[' + ' '.join(e['contexts']) + ']')}")
            for line in e["code"].split("\n"):
                print(f"    {green('$')} {line}")
            if e.get("comment"):
                for cl in e["comment"].split("\n"):
                    print(f"    {dim(cl)}")
            print()
            shown += 1
    if filt and shown == 0:
        print(dim(f"no '{filt}' technique listed for {name}."))
    print(dim(f"source: https://gtfobins.github.io/gtfobins/{name}/"))


def cmd_gtfo(data, args):
    g = load_json_file(GTFO_FILE, "GTFOBins")
    bins = g["binaries"]
    name = args.binary
    if not name:
        print(bold("GTFOBins") + "  " + dim(f"({len(bins)} binaries)"))
        print(dim("Unix binaries that can break out of a restricted shell or escalate privileges."))
        print()
        print(dim("  oscp gtfo <binary> [sudo|suid|shell|file-read|...]   techniques for a binary"))
        print(dim("  oscp gtfo search <term>                              search names and commands"))
        print(dim("  oscp gtfo list                                       list every binary"))
        return
    key = name.lower()
    if key == "list":
        for n in sorted(bins):
            print(f"  {n}")
        print()
        print(dim(f"{len(bins)} binaries · oscp gtfo <name> · oscp gtfo search <term>"))
        return
    if key == "search":
        term = (args.filter or "").lower()
        if not term:
            sys.exit("usage: oscp gtfo search <term>")
        hits = []
        for n in sorted(bins):
            hay = n + " " + " ".join(
                e.get("code", "") + " " + e.get("comment", "")
                for fns in bins[n]["functions"].values() for e in fns)
            if query_match(hay, term):
                funcs = ", ".join(bins[n]["functions"].keys())
                hits.append((n, funcs))
        if not hits:
            sys.exit(f"no GTFOBins entry matches '{term}'. try: oscp search {term}   (searches everything)")
        for n, funcs in hits:
            print(f"  {vispad(bold(hl(n, args.filter)), 20)} {dim(funcs)}")
        print()
        print(dim(f"{len(hits)} match(es) · show one: oscp gtfo <name>"))
        return
    # a specific binary (exact, else unambiguous partial)
    if key not in bins:
        matches = [n for n in bins if key in n]
        if len(matches) == 1:
            key = matches[0]
        elif len(matches) > 1:
            sys.exit(f"'{name}' matches {len(matches)}: " + ", ".join(sorted(matches)[:15])
                     + (" ..." if len(matches) > 15 else ""))
        else:
            sys.exit(f"no GTFOBins entry for '{name}'. try: oscp gtfo search {name}")
    render_gtfo(key, bins[key], (args.filter or "").lower())


def _is_table_row(line):
    return line.lstrip().startswith("|") and "|" in line.strip()[1:]


def _table_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _inline_md(s):
    """Render inline markdown in prose: `code`, **bold**, *emphasis*.

    Code spans are stashed first so a literal * or _ inside them (e.g. `*`)
    is never mistaken for emphasis.
    """
    spans = []

    def stash(m):
        spans.append(m.group(1))
        return f"\x00{len(spans) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, s)
    s = re.sub(r"\*\*(.+?)\*\*", lambda m: bold(m.group(1)), s)
    s = re.sub(r"(?<![\w*])[*_](\S.*?\S|\S)[*_](?![\w*])", lambda m: m.group(1), s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: cyan(spans[int(m.group(1))]), s)
    return s


def _render_markdown(body):
    """Yield display lines: code highlighted, headings bold, tables aligned, pipes gone."""
    lines = body.split("\n")
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            i += 1
            continue
        if in_fence:
            yield f"  {green(line)}"
            i += 1
            continue
        if _is_table_row(line):
            # gather the whole table block, drop separator rows, align columns
            block = []
            while i < len(lines) and (_is_table_row(lines[i]) or not lines[i].strip()):
                if lines[i].strip():
                    cells = _table_cells(lines[i])
                    if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
                        block.append(cells)
                    i += 1
                else:
                    break
            if block:
                # style each cell first (inline md / url / header), then align on visible width
                styled = []
                for ridx, row in enumerate(block):
                    srow = []
                    for cell in row:
                        if _URL_RE.fullmatch(cell):
                            srow.append(dim(cell))
                        elif ridx == 0:
                            srow.append(bold(cell))
                        else:
                            srow.append(_inline_md(cell))
                    styled.append(srow)
                ncol = max(len(r) for r in styled)
                widths = [max(visible_len(r[c]) for r in styled if c < len(r)) for c in range(ncol)]
                for srow in styled:
                    parts = [srow[c] + " " * (widths[c] - visible_len(srow[c])) for c in range(len(srow))]
                    yield "  " + "   ".join(parts).rstrip()
            continue
        if re.match(r"^#{1,6}\s", line):
            yield bold(_inline_md(re.sub(r"^#{1,6}\s+", "", line)))
        elif line[:4] == "    " and line.strip():   # indented code block
            yield green(line)
        else:
            yield _inline_md(line)
        i += 1


def _render_notes_body(sec):
    print(bold(sec["title"]) + "  " + dim(f"[{sec['id']}]"))
    print()
    for dl in _render_markdown(sec["body"]):
        print(dl)
    print()


def find_section(sections, sid):
    sid = sid.lower()
    for s in sections:
        if s["id"] == sid:
            return s
    matches = [s for s in sections if sid in s["id"] or sid in s["title"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        opts = ", ".join(s["id"] for s in matches)
        sys.exit(f"'{sid}' is ambiguous - matches: {opts}")
    return None


def cmd_notes(data, args):
    n = load_json_file(NOTES_FILE, "notes")
    secs = n["sections"]
    sub = getattr(args, "notes_command", None)
    if sub in (None, "list"):
        print(bold("0xsyr0 — OSCP Cheat Sheet") + "  " + dim("[notes]"))
        print(dim(n["meta"]["url"]))
        print()
        for s in secs:
            ln = s["body"].count("\n") + 1
            print(f"  {vispad(bold(s['id']), 34)} {dim(f'({ln} ln)')}")
        print()
        print(dim("show: oscp notes show <id>   ·   search: oscp notes search <term>"))
        return
    if sub == "show":
        sec = find_section(secs, args.section)
        if not sec:
            sys.exit(f"no notes section '{args.section}'. try: oscp notes list")
        _render_notes_body(sec)
        print(dim(f"source: {n['meta']['url']}"))
        return
    if sub == "search":
        term = args.term.lower()
        hits = 0
        secs_hit = 0
        for s in secs:
            matched = [ln for ln in s["body"].split("\n") if query_match(ln, term)]
            if not matched:
                continue
            secs_hit += 1
            print(bold(hl(s["title"], args.term)) + "  " + dim(f"[{s['id']}]"))
            for ln in matched:
                disp = "  ".join(_table_cells(ln)) if _is_table_row(ln) else ln.strip()
                print(f"    {hl(disp, args.term)}")
                hits += 1
            print()
        if hits == 0:
            sys.exit(f"no notes line matches '{args.term}'. try: oscp search {args.term}   (searches everything)")
        print(dim(f"{hits} line(s) in {secs_hit} section(s) match '{args.term}'  ·  "
                  f"open a whole section: oscp notes show <id>"))


# ----------------------------------------------------------------- methods ----
def find_method(methods, mid):
    mid = mid.lower()
    for m in methods:
        if m["id"] == mid:
            return m
    matches = [m for m in methods if mid in m["id"] or mid in m["title"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        opts = ", ".join(m["id"] for m in matches)
        sys.exit(f"'{mid}' is ambiguous - matches: {opts}")
    return None


def _kb_browse(path, label, hint, sub, item, topic, term):
    """Shared list/show/search for topic+markdown knowledge bases (methods, manual)."""
    md = load_json_file(path, label)
    entries = md.get("entries") or md.get("methods") or []
    topics = md.get("topics", [])
    tnames = {t["id"]: t["name"] for t in topics}

    if sub == "show":
        m = find_method(entries, item)
        if not m:
            sys.exit(f"no entry '{item}'. try: {hint} search <term>  ·  {hint} list")
        print(bold(m["title"]) + "  " + dim(f"[{m['id']}]"))
        meta = tnames.get(m.get("topic"), m.get("topic", ""))
        if m.get("tags"):
            meta += f"  ·  tags: {', '.join(m['tags'])}"
        print(dim(meta))
        print()
        for dl in _render_markdown(m.get("body", "")):
            print(dl)
        print()
        print(dim(f"copy a command from any line · {hint} search <term>"))
        return

    if sub == "search":
        t = term.lower()
        hits = 0
        for m in entries:
            hay = " ".join([m["id"], m["title"], m.get("brief", ""),
                            m.get("body", "")] + m.get("tags", []))
            if not query_match(hay, t):
                continue
            hits += 1
            print(bold(hl(m["title"], term)) + "  " + dim(f"[{m['id']}]"))
            if m.get("brief"):
                print(f"  {dim(hl(m['brief'], term))}")
            for ln in m.get("body", "").split("\n"):
                if query_match(ln, t):
                    disp = "  ".join(_table_cells(ln)) if _is_table_row(ln) else ln.strip()
                    if disp:
                        print(f"    {hl(disp, term)}")
            print()
        if hits == 0:
            sys.exit(f"no {hint} entry matches '{term}'. try: oscp search {term}   (searches everything)")
        print(dim(f"{hits} entry(ies) match '{term}' · read one: {hint} show <id>"))
        return

    # list, grouped by topic
    print(bold(md["meta"]["title"]) + "  " + dim(f"[{label}]"))
    print(dim(md["meta"]["note"]))
    print()
    shown = 0
    order = [t["id"] for t in topics] + sorted({m.get("topic") for m in entries} - {t["id"] for t in topics})
    for tid in order:
        if topic and topic.lower() not in tid:
            continue
        group = [m for m in entries if m.get("topic") == tid]
        if not group:
            continue
        print(bold(tnames.get(tid, tid)))
        for m in group:
            print(f"  {vispad(bold(m['id']), 24)} {dim(m.get('brief', m['title']))}")
            shown += 1
        print()
    if shown == 0:
        sys.exit(f"nothing in topic '{topic}'. try: {hint} list")
    print(dim(f"read: {hint} show <id>   ·   search: {hint} search <term>"))


def cmd_methods(data, args):
    _kb_browse(METHODS_FILE, "methods", "oscp methods",
               getattr(args, "methods_command", None), getattr(args, "method", None),
               getattr(args, "topic", None), getattr(args, "term", None))


_HOWTO_ALIASES = {
    "setup": "recon", "scan": "recon", "nmap": "recon",
    "services": "service", "exploit": "service", "web": "service",
    "shell": "foothold", "access": "foothold", "revshell": "foothold",
    "stabilize": "stabilise", "tty": "stabilise",
    "enum": "enumerate", "enumeration": "enumerate", "post": "enumerate",
    "privesc": "escalate", "escalation": "escalate", "root": "escalate",
    "loot": "proof", "flag": "proof", "flags": "proof", "pivot": "proof",
    "reporting": "report", "write-up": "report",
}


_HOWTO_MAP_ALIASES = {"map", "tool", "tools", "utility", "utilities",
                      "commands", "cmds", "overview"}


def _render_toolmap(tm):
    """Render the oscp utility self-map: which command does what, and when."""
    print(bold(tm.get("title", "oscp utility map")) + "  " + dim("[howto map]"))
    if tm.get("note"):
        print(dim(tm["note"]))
    print()
    flow = tm.get("flow", [])
    if flow:
        print(bold(magenta("HOW THE COMMANDS CONNECT")))
        for line in flow:
            print(f"  {dim(line)}" if line else "")
        print()
    for g in tm.get("groups", []):
        print(bold(magenta(g["name"])))
        width = max((len(c) for c, _ in g["items"]), default=0)
        for cmd, what in g["items"]:
            print(f"  {green(cmd.ljust(width))}  {dim(what)}")
        print()
    when = tm.get("when", [])
    if when:
        print(bold(magenta("WHEN YOU WANT TO…")))
        width = max((len(s) for s, _ in when), default=0)
        for situation, cmd in when:
            print(f"  {situation.ljust(width)}  {dim('->')}  {green(cmd)}")
        print()
    print(dim("the kill-chain map (what to run when):  oscp howto"))


_LABSETUP_ALIASES = {
    "setup": "vm", "create": "vm", "vmware": "vm", "fusion": "vm",
    "installation": "install", "kali": "install",
    "guest": "guest-tools", "tools-guest": "guest-tools", "shared": "guest-tools",
    "upgrade": "update", "apt": "update",
    "toolset": "tools", "install-tools": "tools",
    "snap": "snapshot",
    "openvpn": "vpn", "offsec": "vpn", "htb": "vpn",
    "network": "mtu", "net": "mtu",
    "profile": "profiles", "exam": "profiles",
    "gotcha": "gotchas", "troubleshoot": "gotchas", "fixes": "gotchas",
    "check": "checks", "verify": "checks",
    "vars": "labenv", "env": "labenv", "variables": "labenv", "labvars": "labenv",     "hosts": "labenv",
}

_TMUX_ALIASES = {
    "conf": "config", "file": "config", "rc": "config",
    "log": "logging", "logs": "logging", "pipe": "logging",
    "key": "keys", "bind": "keys", "binds": "keys",
    "colon": "command", "prompt": "command",
    "reload": "shell", "source": "shell", "source-file": "shell",
    "session": "shell", "sessions": "shell",
    "window": "keys", "windows": "keys", "pane": "keys", "panes": "keys",
    "scroll": "copy", "copy-mode": "copy", "paste": "copy",
    "paste-buffer": "copy", "buffer": "copy", "buffers": "copy",
    "clipboard": "copy", "emacs": "copy", "vi": "copy",
}


def _tmux_prefix_note():
    """One line, wherever Ctrl-a is shown as a prefix: stock tmux is Ctrl-b."""
    return (c("default prefix is Ctrl-b", "1;33")
            + dim("  ·  Ctrl-a is a custom setting, for ease, in ~/.tmux.conf"))


def _tmux_mentions_custom_prefix(s):
    parts = [s.get("name", ""), s.get("goal", ""), s.get("why", ""), s.get("gotcha", "")]
    for step in s.get("steps") or []:
        parts.extend(str(x) for x in step)
    tbl = s.get("table") or {}
    parts.extend(tbl.get("headers") or [])
    for row in tbl.get("rows") or []:
        parts.extend(str(x) for x in row)
    return "ctrl-a" in " ".join(parts).lower()


def _print_tmux_section(s):
    print(bold(cyan(s["name"])))
    if _tmux_mentions_custom_prefix(s):
        print(f"  {_tmux_prefix_note()}")
    if s.get("goal"):
        print(f"  {dim(s['goal'])}")
    for step in s.get("steps", []):
        label, cmd = (step + ["", ""])[:2]
        if label and cmd:
            print(f"    {green('$')} {cmd}   {dim('# ' + label)}")
        elif cmd:
            print(f"    {green('$')} {cmd}")
        elif label:
            print(f"    {dim('- ' + label)}")
    tbl = s.get("table")
    if tbl:
        rows = [tbl.get("headers", [])] + tbl.get("rows", [])
        w = max((len(r[0]) for r in rows), default=0)
        for i, r in enumerate(rows):
            left = r[0].ljust(w)
            right = r[1] if len(r) > 1 else ""
            print(f"  {bold(left) if i == 0 else dim(left)}   {dim(right)}")
    if s.get("why"):
        print(f"  {dim(s['why'])}")
    if s.get("gotcha"):
        print(f"  {yellow('gotcha:')} {dim(s['gotcha'])}")
    print()


def cmd_tmux(data, args):
    """This machine's tmux: prefix Ctrl-a, keys, command mode, and the live log."""
    td = load_json_file(TMUX_FILE, "tmux")
    meta = td.get("meta", {})
    secs = td["sections"]
    byid = {s["id"]: s for s in secs}
    arg = getattr(args, "section", None)

    selected = secs
    if arg:
        key = arg.lower()
        sid = _TMUX_ALIASES.get(key, key)
        s = byid.get(sid)
        if not s:
            m = [x for x in secs if x["id"].startswith(sid)]
            s = m[0] if len(m) == 1 else None
        if not s:
            sys.exit(f"no tmux section '{arg}'. sections: " + ", ".join(x["id"] for x in secs))
        selected = [s]

    print(bold(meta.get("title", "oscp tmux")) + "  " + dim("[tmux]"))
    print(_tmux_prefix_note())
    if meta.get("note"):
        print(dim(meta["note"]))
    if meta.get("flow"):
        print(dim(meta["flow"]))
    print()
    for s in selected:
        _print_tmux_section(s)
    if not arg:
        print(dim("one section:  oscp tmux <section>   (config · logging · prefix · keys · "
                  "command · shell · copy)"))
        print(dim("short commands:  oscp cmd tmux     one tool:  oscp atlas tmux"))


_SHELL_ALIASES = {
    "shebang": "start", "bash": "start", "intro": "start", "first": "start",
    "comment": "start", "comments": "start", "hello": "start",
    "strict": "safety", "set": "safety", "pipefail": "safety", "umask": "safety",
    "deps": "safety", "require": "safety",
    "var": "variables", "vars": "variables", "assign": "variables",
    "assignment": "variables", "export": "variables", "capture": "variables",
    "quote": "quoting", "quotes": "quoting", "expansion": "quoting",
    "expand": "quoting", "default": "quoting", "substring": "quoting",
    "condition": "if", "conditions": "if", "ifelse": "if", "if-else": "if",
    "elif": "if", "else": "if", "test": "if", "tests": "if",
    "case": "if", "regex": "if",
    "loop": "loops", "for": "loops", "while": "loops", "break": "loops",
    "continue": "loops", "select": "loops", "read": "loops",
    "arg": "args", "arguments": "args", "positional": "args",
    "getopts": "args", "shift": "args",
    "function": "functions", "fn": "functions", "func": "functions",
    "local": "functions", "main": "functions", "source": "functions",
    "library": "functions",
    "array": "arrays", "list": "arrays", "map": "arrays", "mapfile": "arrays",
    "associative": "arrays", "hash": "arrays", "heredoc": "arrays",
    "herestring": "arrays", "input": "arrays",
    "file": "files", "path": "files", "paths": "files", "mkdir": "files",
    "mktemp": "files", "trap": "files", "find": "files", "glob": "files",
    "cd": "files",
    "redir": "redirect", "redirection": "redirect", "pipe": "redirect",
    "pipeline": "redirect", "tee": "redirect", "fd": "redirect",
    "job": "redirect", "jobs": "redirect", "background": "redirect",
    "wait": "redirect", "flock": "redirect", "timeout": "redirect",
    "retry": "redirect", "exec": "redirect",
    "secure": "security", "eval": "security", "validate": "security",
    "secret": "security", "secrets": "security", "locale": "security",
    "shellcheck": "security", "lint": "security",
}


def _print_shell_section(s):
    print(bold(cyan(s["name"])))
    if s.get("goal"):
        print(f"  {dim(s['goal'])}")
    for step in s.get("steps", []):
        label, cmd = (step + ["", ""])[:2]
        if label:
            print(f"    {dim('# ' + label)}")
        if cmd:
            for ln in cmd.split("\n"):
                print(f"    {green(ln)}")
    tbl = s.get("table")
    if tbl:
        rows = [tbl.get("headers", [])] + tbl.get("rows", [])
        w = max((len(r[0]) for r in rows if r), default=0)
        print()
        for i, r in enumerate(rows):
            left = (r[0] if r else "").ljust(w)
            right = r[1] if len(r) > 1 else ""
            print(f"  {bold(left) if i == 0 else dim(left)}   {dim(right)}")
    if s.get("why"):
        print(f"  {dim(s['why'])}")
    if s.get("gotcha"):
        print(f"  {yellow('gotcha:')} {dim(s['gotcha'])}")
    print()


def cmd_shell_script(data, args):
    """Bash you can copy into a file: shebang, quoting, if, loops, and the rest."""
    td = load_json_file(SHELLSCRIPT_FILE, "shell-script")
    meta = td.get("meta", {})
    secs = td["sections"]
    byid = {s["id"]: s for s in secs}
    arg = getattr(args, "section", None)

    print(bold(meta.get("title", "oscp shell-script")) + "  " + dim("[shell-script]"))
    if meta.get("note"):
        print(dim(meta["note"]))
    if meta.get("flow"):
        print(dim(meta["flow"]))
    print()
    if not arg:
        print(yellow("-- what a script is --"))
        print(dim("  A script is a file. bash reads it top to bottom. The live prompt is not a script."))
        print(dim("  Quote \"$var\". Prefer [[ ]] in bash. Do not parse ls. Do not eval."))
        print()
        print(yellow("-- section (Tab lists these) --"))
        width = max(len(s["id"]) for s in secs)
        for s in secs:
            print(f"  {vispad(bold(s['id']), width)}   {dim(s.get('goal', s.get('name', '')))}")
        print()
        ids = " · ".join(s["id"] for s in secs)
        print(dim(f"one section:  oscp shell-script <section>   ({ids})"))
        print(dim("copy a line:  type N     a block:  N-M"))
        return

    key = arg.lower()
    sid = _SHELL_ALIASES.get(key, key)
    s = byid.get(sid)
    if not s:
        m = [x for x in secs if x["id"].startswith(sid)]
        s = m[0] if len(m) == 1 else None
    if not s:
        sys.exit(f"no shell-script section '{arg}'. sections: " + ", ".join(x["id"] for x in secs))
    _print_shell_section(s)


def cmd_lab_setup(data, args):
    """Walk Kali-on-VMware lab setup for OSCP/OSWE/HTB: install -> tools -> VPN -> MTU."""
    ld = load_json_file(LABSETUP_FILE, "lab-setup")
    meta = ld.get("meta", {})
    secs = ld["sections"]
    byid = {s["id"]: s for s in secs}
    arg = getattr(args, "section", None)

    selected = secs
    if arg:
        key = arg.lower()
        sid = _LABSETUP_ALIASES.get(key, key)
        s = byid.get(sid)
        if not s:
            m = [x for x in secs if x["id"].startswith(sid)]
            s = m[0] if len(m) == 1 else None
        if not s:
            sys.exit(f"no lab-setup section '{arg}'. sections: " + ", ".join(x["id"] for x in secs))
        selected = [s]

    print(bold(meta.get("title", "oscp lab-setup")) + "  " + dim("[lab-setup]"))
    if meta.get("note"):
        for dl in _render_markdown(meta["note"]):
            print(dim(dl))
    if meta.get("flow"):
        print(dim("flow:  " + meta["flow"]))
    print()

    for s in selected:
        print(bold(s["name"]))
        if s.get("goal"):
            print(f"  {dim(s['goal'])}")
        for step in s.get("steps", []):
            label, cmd = (step + ["", ""])[:2]
            if label and cmd:
                print(f"    {green('$')} {cmd}   {dim('# ' + label)}")
            elif cmd:
                print(f"    {green('$')} {cmd}")
            elif label:
                print(f"    {dim('- ' + label)}")
        tbl = s.get("table")
        if tbl:
            rows = [tbl.get("headers", [])] + tbl.get("rows", [])
            w = max((len(r[0]) for r in rows), default=0)
            for i, r in enumerate(rows):
                left = r[0].ljust(w)
                right = r[1] if len(r) > 1 else ""
                print(f"  {bold(left) if i == 0 else dim(left)}   {dim(right)}")
        if s.get("why"):
            print(f"  {dim('why: ' + s['why'])}")
        if s.get("gotcha"):
            print(f"  {yellow('⚠ gotcha:')} {dim(s['gotcha'])}")
        if s.get("resource"):
            ru = s.get("resource_url", "")
            extra = f"   {dim(ru)}" if ru else ""
            print(f"  {dim('resource:')} {dim(s['resource'])}{extra}")
        print()

    if not arg:
        print(dim("one section at a time:  oscp lab-setup <section>   (vm · install · guest-tools · "
                  "update · tools · snapshot · vpn · mtu · profiles · gotchas · checks)"))


def _open_howto_page():
    """Open howto.html in the system default browser. Local file only."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "howto.html")
    if not os.path.isfile(path):
        sys.exit(f"no tutorial page at {path}")
    import webbrowser
    if not webbrowser.open("file://" + path):
        sys.exit(f"could not open a browser. the page is at {path}")
    print(f"opened {path}", file=sys.stderr)


def cmd_howto(data, args):
    """The phase-by-phase command map: which oscp command to run at each stage."""
    phase_arg = getattr(args, "phase", None)
    if phase_arg and phase_arg.lower() == "page":
        _open_howto_page()
        return
    hd = load_json_file(HOWTO_FILE, "howto")
    meta = hd.get("meta", {})
    phases = hd["phases"]
    byid = {p["id"]: p for p in phases}

    if phase_arg and phase_arg.lower() in _HOWTO_MAP_ALIASES:
        tm = hd.get("toolmap")
        if not tm:
            sys.exit("no toolmap in howto.json")
        _render_toolmap(tm)
        return

    selected = phases
    if phase_arg:
        key = phase_arg.lower()
        pid = _HOWTO_ALIASES.get(key, key)
        p = byid.get(pid)
        if not p:                       # unambiguous prefix match
            m = [x for x in phases if x["id"].startswith(pid)]
            p = m[0] if len(m) == 1 else None
        if not p:
            sys.exit(f"no howto phase '{phase_arg}'. phases: "
                     + ", ".join(x["id"] for x in phases))
        selected = [p]

    print(bold(meta.get("title", "oscp howto")) + "  " + dim("[howto]"))
    if meta.get("loop"):
        print(dim("the loop:  " + meta["loop"]))
    print(dim("the path:  oscp technique show full-workflow"))
    print()
    if not phase_arg and meta.get("setup"):
        print(bold(magenta("0. Set up once")))
        print(f"    {green('$')} {meta['setup']}")
        print()

    for p in selected:
        print(bold(p["name"]))
        if p.get("goal"):
            print(f"  {dim(p['goal'])}")
        for step in p.get("steps", []):
            cmd, note = (step + ["", ""])[:2]
            line = f"    {green('$')} {cmd}"
            if note:
                line += f"   {dim('# ' + note)}"
            print(line)
        if p.get("resource"):
            ru = p.get("resource_url", "")
            extra = f"   {dim(ru)}" if ru else ""
            print(f"  {dim('resource:')} {dim(p['resource'])}{extra}")
        if phase_arg and p.get("next"):
            print(f"  {dim('↳ next phase:  oscp howto ' + p['next'])}")
        print()

    if not phase_arg:
        if meta.get("metarule"):
            print(dim(meta["metarule"]))
        print(dim("one phase at a time:  oscp howto <phase>   (recon · service · foothold · "
                  "stabilise · enumerate · escalate · proof · report)"))
        print(dim("the oscp tool itself:  oscp howto map   (which command does what, and when)"))
        print(dim("the tutorial in a browser:  oscp howto page"))


def cmd_manual(data, args):
    a = getattr(args, "manual_arg", None)
    a2 = getattr(args, "manual_arg2", None)
    if a in (None, "list"):
        _kb_browse(MANUAL_FILE, "manual", "oscp manual", None, None, a2, None)
        return
    if a == "show":
        if not a2:
            sys.exit("usage: oscp manual show <id>")
        _kb_browse(MANUAL_FILE, "manual", "oscp manual", "show", a2, None, None)
        return
    if a == "search":
        if not a2:
            sys.exit("usage: oscp manual search <term>")
        _kb_browse(MANUAL_FILE, "manual", "oscp manual", "search", None, None, a2)
        return
    # bare arg: a topic to list, or an entry id to show
    md = load_json_file(MANUAL_FILE, "manual")
    topic_ids = {t["id"] for t in md.get("topics", [])}
    if a in topic_ids:
        _kb_browse(MANUAL_FILE, "manual", "oscp manual", None, None, a, None)
    elif find_method(md.get("entries", []), a):
        _kb_browse(MANUAL_FILE, "manual", "oscp manual", "show", a, None, None)
    else:
        sys.exit(f"no manual topic or entry '{a}'. try: oscp manual search {a}  ·  oscp manual list")


def _technique_stores():
    methods = load_json_file(METHODS_FILE, "methods")
    manual = load_json_file(MANUAL_FILE, "manual")
    notes = load_json_file(NOTES_FILE, "notes")
    return methods, manual, notes


def _print_technique(entry, shelf):
    print(bold(entry["title"]) + "  " + dim(f"[{shelf} · {entry['id']}]"))
    meta = entry.get("topic", "") or ""
    if entry.get("tags"):
        meta += ("  ·  " if meta else "") + "tags: " + ", ".join(entry["tags"])
    if meta:
        print(dim(meta))
    print()
    for dl in _render_markdown(entry.get("body", "")):
        print(dl)
    print()
    print(dim("copy a command from any line · oscp technique search <term>"))


def _list_shelf(title, topics, entries, only):
    names = {t["id"]: t.get("name") or t["id"] for t in topics}
    group = [m for m in entries if m.get("topic") == only]
    if not group:
        return False
    print(bold(magenta(title)) + "  " + dim(names.get(only, only)))
    for m in group:
        print(f"  {vispad(bold(m['id']), 28)} {dim(m.get('brief', m['title']))}")
    print()
    return True


def _technique_index(methods, manual, notes):
    print(bold("technique") + "  " + dim("path · topic · notes"))
    print(dim("path is the exam in order. A topic is one area. notes is the 0xsyr0 sheet."))
    print()
    print(bold(magenta("PATH")))
    for t in methods.get("topics", []):
        n = sum(1 for m in methods.get("methods", []) if m.get("topic") == t["id"])
        print(f"  {vispad(bold(t['id']), 22)} {dim(t.get('name', t['id']))} {dim(f'({n})')}")
    print(dim("    oscp technique path"))
    print()
    print(bold(magenta("TOPICS")))
    for t in manual.get("topics", []):
        n = sum(1 for m in manual.get("entries", []) if m.get("topic") == t["id"])
        print(f"  {vispad(bold(t['id']), 22)} {dim(t.get('name') or t['id'])} {dim(f'({n})')}")
    print(dim("    oscp technique <topic>     e.g. oscp technique windows"))
    print()
    nsec = len(notes.get("sections", []))
    print(bold(magenta("NOTES")))
    print(f"  {vispad(bold('notes'), 22)} {dim('0xsyr0 OSCP cheat sheet')} {dim(f'({nsec})')}")
    print(dim("    oscp technique notes"))
    print()
    print(dim("one write-up:  oscp technique show <id>"))
    print(dim("search:        oscp technique search <term>"))


def _collect_technique(mid, methods, manual, notes, partial):
    mid_l = mid.lower()
    found = []

    def take(shelf, entry, kind, blob):
        if partial:
            if mid_l in blob:
                found.append((shelf, entry, kind))
        elif entry["id"] == mid_l:
            found.append((shelf, entry, kind))

    for e in methods.get("methods", []):
        take("path", e, "kb", (e["id"] + " " + e["title"]).lower())
    for e in manual.get("entries", []):
        take("topic", e, "kb", (e["id"] + " " + e["title"]).lower())
    for s in notes.get("sections", []):
        take("notes", s, "notes", (s["id"] + " " + s["title"]).lower())
    return found


def _emit_technique(found):
    if len(found) > 1:
        print(dim(f"{len(found)} shelves use this — each one follows"))
        print()
    for shelf, entry, kind in found:
        if kind == "notes":
            print(dim(f"[notes · {entry['id']}]"))
            _render_notes_body(entry)
        else:
            _print_technique(entry, shelf)


def _technique_show(mid, methods, manual, notes):
    found = _collect_technique(mid, methods, manual, notes, partial=False)
    if not found:
        partial = _collect_technique(mid, methods, manual, notes, partial=True)
        if len(partial) == 1:
            found = partial
        elif len(partial) > 1:
            opts = ", ".join(f"{shelf}:{entry['id']}" for shelf, entry, _ in partial[:12])
            sys.exit(f"'{mid}' is ambiguous — {opts}\n"
                     f"open one:  oscp technique show <id>    or    oscp technique search {mid}")
        else:
            sys.exit(f"no technique '{mid}'. try: oscp technique search {mid}  ·  oscp technique")
    _emit_technique(found)


def _technique_search(term, methods, manual, notes):
    t = term.lower()
    hits = 0

    def scan(label, entries):
        nonlocal hits
        for m in entries:
            hay = " ".join([m["id"], m.get("title", ""), m.get("brief", ""),
                            m.get("body", "")] + m.get("tags", []))
            if not query_match(hay, t):
                continue
            hits += 1
            print(bold(hl(m["title"], term)) + "  " + dim(f"[{label} · {m['id']}]"))
            if m.get("brief"):
                print(f"  {dim(hl(m['brief'], term))}")
            print(f"    {green('$')} {hl('oscp technique show ' + m['id'], term)}")
            print()

    scan("path", methods.get("methods", []))
    scan("topic", manual.get("entries", []))
    for s in notes.get("sections", []):
        hay = " ".join([s["id"], s.get("title", ""), s.get("body", "")])
        if not query_match(hay, t):
            continue
        hits += 1
        print(bold(hl(s["title"], term)) + "  " + dim(f"[notes · {s['id']}]"))
        print(f"    {green('$')} {hl('oscp technique show ' + s['id'], term)}")
        print()
    if hits == 0:
        sys.exit(f"no technique matches '{term}'. try: oscp search {term}")
    print(dim(f"{hits} match(es) · open one: oscp technique show <id>"))


def _technique_notes(notes, section):
    secs = notes.get("sections", [])
    if not section:
        print(bold("0xsyr0 — OSCP cheat sheet") + "  " + dim("[technique notes]"))
        print(dim(notes.get("meta", {}).get("url", "")))
        print()
        for s in secs:
            print(f"  {vispad(bold(s['id']), 34)} {dim(s['title'])}")
        print()
        print(dim("one section:  oscp technique notes <id>"))
        return
    sec = find_section(secs, section)
    if not sec:
        sys.exit(f"no notes section '{section}'. try: oscp technique notes")
    print(dim(f"[notes · {sec['id']}]"))
    _render_notes_body(sec)


def _technique_path(methods, topic):
    topics = methods.get("topics", [])
    entries = methods.get("methods", [])
    ids = [t["id"] for t in topics]
    chosen = ids
    if topic:
        key = topic.lower()
        chosen = [i for i in ids if key == i or key in i]
        if not chosen:
            sys.exit(f"no path stage '{topic}'. stages: " + ", ".join(ids))
    print(bold("path") + "  " + dim("the exam, in order"))
    print()
    for tid in chosen:
        _list_shelf("PATH", topics, entries, tid)
    print(dim("one write-up:  oscp technique show <id>"))


def cmd_technique(data, args):
    """path (the exam), a topic, or the 0xsyr0 notes — one command."""
    methods, manual, notes = _technique_stores()
    a = getattr(args, "technique_arg", None)
    a2 = getattr(args, "technique_arg2", None)
    method_topics = {t["id"] for t in methods.get("topics", [])}
    manual_topics = {t["id"] for t in manual.get("topics", [])}
    note_ids = {s["id"] for s in notes.get("sections", [])}

    if a in (None, "list"):
        _technique_index(methods, manual, notes)
        return
    if a == "path":
        _technique_path(methods, a2)
        return
    if a == "notes":
        _technique_notes(notes, a2)
        return
    if a == "show":
        if not a2:
            sys.exit("usage: oscp technique show <id>")
        _technique_show(a2, methods, manual, notes)
        return
    if a == "search":
        if not a2:
            sys.exit("usage: oscp technique search <term>")
        _technique_search(a2, methods, manual, notes)
        return
    if a in method_topics or a in manual_topics:
        if a in method_topics:
            _list_shelf("PATH", methods.get("topics", []), methods.get("methods", []), a)
        if a in manual_topics:
            _list_shelf("TOPIC", manual.get("topics", []), manual.get("entries", []), a)
        if a in note_ids:
            print(dim(f"also a notes section:  oscp technique notes {a}"))
            print()
        print(dim("one write-up:  oscp technique show <id>"))
        return
    _technique_show(a, methods, manual, notes)


def cmd_commands(data, args):
    """Short numbered commands for one cheat-sheet category. No category lists them."""
    words = list(getattr(args, "cmd_arg", None) or [])
    if not words or words == ["list"]:
        cmd_list(data, args)
        return
    args.category = _resolve_cmd_words(words)
    cmd_show(data, args)


# ------------------------------------------------------------------- atlas ----
# common aliases -> canonical atlas command name
_ATLAS_ALIASES = {
    "netcat": "nc",
    "netexec": "nxc",
    "linux-smart-enumeration": "lse", "ripgrep": "rg",
    "secretsdump": "impacket-secretsdump", "samrdump": "impacket-samrdump",
    "ntlmrelayx": "impacket-ntlmrelayx", "hcat": "hashcat",
    "miller": "mlr", "getallurls": "gau",
    "evilwinrm": "evil-winrm", "certipy-find": "certipy", "nth": "name-that-hash",
}


def cmd_alias(data, args):
    """Every other name that still opens a page. The Tab menu keeps the main names."""
    print(bold("oscp alias") + "  " + dim("every other name that still works"))
    print(dim("Tab shows the main name. Any name on the left opens the command on the right."))
    print()

    def emit(title, note, rows):
        print(bold(title))
        if note:
            print(f"  {dim(note)}")
        width = max(len(left) for left, _right in rows)
        for left, right in rows:
            print(f"  {green(left.ljust(width))}  {dim('->')}  {right}")
        print()

    def grouped(mapping, prefix):
        by = {}
        for alias, target in mapping.items():
            if alias == target:
                continue
            by.setdefault(target, []).append(alias)
        rows = []
        for target in sorted(by):
            names = ", ".join(sorted(by[target]))
            rows.append((names, f"{prefix} {target}"))
        return rows

    emit("Commands", "Type these instead of the menu name.", [
        ("tech, tec, teq", "oscp technique"),
        ("ref, reference, bookmark", "oscp bm"),
        ("ht", "oscp hacktools"),
        ("shellscript, bash-script", "oscp shell-script"),
        ("install", "oscp setup"),
    ])
    emit("Older commands", "These still run. The menu name is on the right.", [
        ("methods", "oscp technique path"),
        ("manual", "oscp technique"),
        ("notes", "oscp technique notes"),
        ("list", "oscp cmd"),
        ("show", "oscp cmd <category>"),
        ("copy", "the line number on a page"),
    ])
    emit("Search shelves", "oscp search <shelf> <term> limits the find to one shelf.",
         grouped(_SEARCH_SHELVES, "oscp search"))
    web_rows = []
    for name in sorted(n for n in _WEB_PAGE_IDS if n != "basic"):
        page = "wp" if name == "wordpress" else name
        web_rows.append((f"cmd {name}", f"oscp cmd web {page}"))
    web_rows.append(("cmd web basic", "oscp cmd web"))
    emit("Web pages", "A framework name works on its own, or after web.", web_rows)
    emit("Tool names", "oscp atlas <alias> opens the tool's usual page.",
         grouped(_ATLAS_ALIASES, "oscp atlas"))
    emit("Howto", "oscp howto <name> opens that phase.",
         grouped(_HOWTO_ALIASES, "oscp howto")
         + [(", ".join(sorted(_HOWTO_MAP_ALIASES - {"map"})), "oscp howto map")])
    emit("Lab setup", "oscp lab-setup <name> opens that section.",
         grouped(_LABSETUP_ALIASES, "oscp lab-setup"))
    emit("tmux", "oscp tmux <name> opens that section.",
         grouped(_TMUX_ALIASES, "oscp tmux"))
    emit("Shell script", "oscp shell-script <name> opens that section.",
         grouped(_SHELL_ALIASES, "oscp shell-script"))


def find_atlas(commands, name):
    name = name.lower()
    name = _ATLAS_ALIASES.get(name, name)
    for c in commands:
        if c["name"].lower() == name:
            return c
    matches = [c for c in commands if name in c["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        sys.exit(f"'{name}' matches: " + ", ".join(c["name"] for c in matches))
    return None


ATLAS_CARD_CAP = 8


def _uc_fields(uc):
    if isinstance(uc, list):
        title = uc[0] if len(uc) > 0 else ""
        cmd = uc[1] if len(uc) > 1 else ""
        desc = uc[2] if len(uc) > 2 else ""
        note = uc[3] if len(uc) > 3 else ""
        return title, cmd, desc, note
    return (
        uc.get("title", ""),
        uc.get("cmd") or uc.get("command") or "",
        uc.get("desc") or uc.get("what") or "",
        uc.get("notes") or uc.get("note") or "",
    )


def _uc_blob(title, cmd, desc, note):
    return f"{title} {cmd} {desc} {note}".lower()


def _print_atlas_card(title, cmd, desc, note, highlight=None, indent="    "):
    if title:
        print(f"{indent}{bold(hl(title, highlight))}")
    if cmd:
        print_dollar(cmd, highlight, indent=indent)
    if desc:
        print(f"{indent}  {dim(hl(desc, highlight))}")
    if note:
        print(f"{indent}  {yellow('note:')} {dim(hl(note, highlight))}")


def _atlas_jump(name, term_raw):
    t = (term_raw or "").strip()
    if not t or t.lower() == name.lower():
        return f"oscp atlas {name}"
    parts = t.split()
    if parts and parts[0].lower() == name.lower() and len(parts) > 1:
        rest = " ".join(parts[1:])
        return f"oscp atlas {name} {_shell_word(rest)}"
    return f"oscp atlas {name} {_shell_word(t)}"


def atlas_command_hits(commands, term):
    """[(command, matching use-case tuples)]. Exact command names stay on that page."""
    t = (term or "").strip().lower()
    if not t:
        return []
    exact = any(c["name"].lower() == t for c in commands)
    parts = query_parts(t)
    scored = []
    for c in commands:
        name = c["name"]
        if exact and name.lower() != t:
            continue
        matched = []
        for uc in c.get("usecases", []):
            fields = _uc_fields(uc)
            if query_match(_uc_blob(*fields), t):
                matched.append(fields)
        if exact:
            scored.append((200, name.lower(), c, matched))
            continue
        head = " ".join([name, c.get("syntax", ""), c.get("description", ""),
                         " ".join(c.get("tags", []))])
        if not (matched or query_match(head, t)):
            continue
        sc = 0
        nl = name.lower()
        if nl == t or nl in parts:
            sc += 100
        scored.append((sc, nl, c, matched))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [(c, matched) for _, _, c, matched in scored]


def print_atlas_search_hits(hits, term_raw, cap_cmds=None, cap_cards=None):
    """Teach matching atlas use-cases. Returns how many commands were printed."""
    if cap_cmds is None:
        cap_cmds = 80
    if cap_cards is None:
        cap_cards = ATLAS_CARD_CAP
    shown = hits[:cap_cmds]
    n = 0
    for c, matched in shown:
        n += 1
        name = c["name"]
        print(bold(hl(name, term_raw)) + "  " + dim(hl(c.get("syntax", ""), term_raw)))
        first = c.get("description", "").split(". ")[0]
        if first:
            print(f"    {dim(hl(first, term_raw))}")
        extra = 0
        cards = matched
        if len(cards) > cap_cards:
            extra = len(cards) - cap_cards
            cards = cards[:cap_cards]
        for title, cmd, desc, note in cards:
            _print_atlas_card(title, cmd, desc, note, term_raw)
        if extra:
            print("    " + dim(f"{extra} more:  oscp atlas {name}"))
        elif matched:
            print("    " + dim(f"read: oscp atlas {name}   ·   one use:  {_atlas_jump(name, term_raw)}"))
        else:
            print("    " + dim(f"read: oscp atlas {name}"))
        print()
    extra_cmds = len(hits) - len(shown)
    if extra_cmds > 0:
        print(dim(f"{extra_cmds} more:  oscp search atlas {_shell_word(term_raw)}"))
        print()
    return n, extra_cmds


def render_atlas_command(c):
    print(bold(c["name"]))
    print(f"{magenta('Syntax')}   {green(c.get('syntax', ''))}")
    print()
    print(bold(magenta("Description")))
    for dl in _render_markdown(c.get("description", "")):
        print(f"  {dl}")
    if c.get("name") == "tmux":
        print(f"  {_tmux_prefix_note()}")
    anat = c.get("anatomy", [])
    if anat:
        print()
        print(bold(magenta("Anatomy")))
        for label, text in anat:
            print(f"  {bold(yellow(label))}")
            for dl in _render_markdown(text):
                print(f"    {dl}")
    org = c.get("origins")
    if org:
        print()
        print(bold(magenta("Origins")))
        for key, lbl in (("creators", "Creators"), ("when", "When"),
                         ("where", "Where"), ("why", "Why it emerged")):
            if org.get(key):
                print(f"  {bold(yellow(lbl))}  {dim(org[key])}")
    if c.get("docs"):
        print()
        print(bold(magenta("Docs")))
        print(f"  {c['docs']}   {dim('(open with: o <this line number>)')}")
    ucs = c.get("usecases", [])
    if c.get("name") == "tmux" and ucs:
        print()
        print(f"  {_tmux_prefix_note()}")
    for i, uc in enumerate(ucs, 1):
        title = uc[0] if isinstance(uc, list) else uc.get("title", "")
        cmd = uc[1] if isinstance(uc, list) else uc.get("cmd", "")
        desc = uc[2] if len(uc) > 2 else ""
        note = uc[3] if len(uc) > 3 else ""
        print()
        print(bold(magenta(f"Use Case {i:02d}: {title}")))
        print_dollar(cmd, indent="  ")
        if desc:
            print(f"  {dim(desc)}")
        if note:
            print(f"  {yellow('note:')} {dim(note)}")
    print()
    print(dim(f"copy any line (use-case command, option, field) · oscp atlas search <term>"))


def cmd_atlas(data, args):
    ad = load_json_file(ATLAS_FILE, "atlas")
    commands = ad["commands"]
    arg = getattr(args, "atlas_arg", None)
    arg2 = getattr(args, "atlas_arg2", None)

    if not arg or arg == "list":
        print(bold(ad["meta"]["title"]) + "  " + dim(f"[atlas · {len(commands)} commands]"))
        print(dim(ad["meta"]["note"]))
        print()
        for c in sorted(commands, key=lambda x: x["name"]):
            first = c.get("description", "").split(". ")[0]
            print(f"  {vispad(bold(c['name']), 14)} {dim(first)}")
        print()
        print(dim("read: oscp atlas <command>   ·   search: oscp atlas search <term>"))
        return

    if arg == "search":
        if not arg2:
            sys.exit("usage: oscp atlas search <term>")
        hits = atlas_command_hits(commands, arg2)
        if not hits:
            sys.exit(f"no atlas command matches '{arg2}'. try: oscp search {arg2}   (searches everything)")
        n, _ = print_atlas_search_hits(hits, arg2)
        print(dim(f"{n} command(s) match '{arg2}' · read one: oscp atlas <command> [word]"))
        return

    c = find_atlas(commands, arg)
    if not c:
        sys.exit(f"no atlas entry for '{arg}'. try: oscp atlas search {arg}  ·  oscp atlas list")
    if arg2:
        t = arg2.lower()
        matched = []
        for uc in c.get("usecases", []):
            fields = _uc_fields(uc)
            if query_match(_uc_blob(*fields), t):
                matched.append(fields)
        if not matched:
            sys.exit(f"no use-case in '{c['name']}' matches '{arg2}'. try: oscp atlas {c['name']}")
        print(bold(c["name"]) + "  " + dim(f"{len(matched)} matching use-case(s)"))
        shown = matched[:ATLAS_CARD_CAP]
        for title, cmd, desc, note in shown:
            print()
            _print_atlas_card(title, cmd, desc, note, arg2, indent="  ")
        extra = len(matched) - len(shown)
        print()
        if extra:
            print(dim(f"{extra} more:  oscp atlas {c['name']}"))
        else:
            print(dim("the chapter:  oscp atlas " + c["name"]))
        return
    render_atlas_command(c)


# --------------------------------------------------------------- hacktools ----
def _ht_compute(cat, text):
    import base64 as _b64
    import hashlib
    import urllib.parse as _up
    if not text:
        sys.exit(f"usage: oscp hacktools {cat} <text>   "
                 f"(or pipe it:  echo -n '<text>' | oscp hacktools {cat})")

    def _t(fn):
        try:
            return fn()
        except Exception:
            return "(not decodable)"

    pairs = []  # (label, value); the first is auto-copied to the clipboard
    if cat == "encode":
        pairs = [("base64", _b64.b64encode(text.encode()).decode()),
                 ("url", _up.quote(text, safe="")),
                 ("hex", text.encode().hex())]
    elif cat == "decode":
        pad = text.strip() + "=" * (-len(text.strip()) % 4)
        pairs = [("base64 -d", _t(lambda: _b64.b64decode(pad).decode(errors="replace"))),
                 ("url-decode", _up.unquote(text)),
                 ("hex-decode", _t(lambda: bytes.fromhex(text.strip()).decode(errors="replace")))]
    elif cat == "hash":
        pairs = [(a, hashlib.new(a, text.encode()).hexdigest())
                 for a in ("md5", "sha1", "sha256", "sha512")]
    elif cat == "obfuscate":
        b = _b64.b64encode(text.encode()).decode()
        pw = _b64.b64encode(text.encode("utf-16-le")).decode()
        pairs = [("bash (base64 loader)", f"echo -n '{b}' | base64 -d | bash"),
                 ("sh via eval", f"eval \"$(echo -n '{b}' | base64 -d)\""),
                 ("powershell -enc", f"powershell -enc {pw}")]

    for label, val in pairs:
        print(f"  {bold(label)}")
        print(f"    {green('$')} {val}")
    if pairs:
        tool = clipboard_copy(pairs[0][1])
        if tool:
            print()
            print(dim(f"· copied {pairs[0][0]} to clipboard ({tool})"))


def _ht_read_text(rest):
    """Full TEXT for encode/decode/hash/obfuscate — inline args, a pipe, or paste.

    Inline args are joined with single spaces (the shell already stripped quotes).
    For big strings with special characters, pipe or redirect them in — that path
    preserves bytes exactly:  echo -n '<payload>' | oscp hacktools encode
    """
    parts = [x for x in (rest or []) if x not in (None, "-")]
    if parts:
        return " ".join(parts)
    if not sys.stdin.isatty():          # piped / redirected: read it all
        return sys.stdin.read().rstrip("\n")
    try:                                 # interactive: paste, then Ctrl-D
        sys.stderr.write(dim("paste text, then press Ctrl-D:\n"))
        sys.stderr.flush()
        return sys.stdin.read().rstrip("\n")
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def cmd_hacktools(data, args):
    cat = getattr(args, "ht_cat", None)
    rest = getattr(args, "ht_rest", None) or []
    a = (list(rest) + [None, None, None])[:3]

    if cat in ("encode", "decode", "hash", "obfuscate"):
        _ht_compute(cat, _ht_read_text(rest))
        return

    ht = load_json_file(HACKTOOLS_FILE, "hacktools")
    cats = ht["categories"]
    cmap = {c["id"]: c for c in cats}

    if not cat or cat == "list":
        print(bold(ht["meta"]["title"]) + "  " + dim("[hacktools]"))
        print(dim(ht["meta"]["note"]))
        print()
        for c in cats:
            needs = " ".join("<" + n.lower() + ">" for n in c.get("needs", []))
            print(f"  {vispad(bold(c['id']), 12)} {dim(c['name'])}  {dim(needs)}")
        print(f"  {vispad(bold('encode'), 12)} {dim('base64/url/hex encode')}  {dim('<text>')}")
        print(f"  {vispad(bold('decode'), 12)} {dim('base64/url/hex decode')}  {dim('<text>')}")
        print(f"  {vispad(bold('hash'), 12)} {dim('md5/sha1/sha256/sha512')}  {dim('<text>')}")
        print(f"  {vispad(bold('obfuscate'), 12)} {dim('base64 bash loader / powershell -enc')}  {dim('<text>')}")
        print()
        print(dim("e.g. oscp hacktools revshell 10.10.14.5 4444  ·  oscp hacktools tty  ·  oscp hacktools hash apple"))
        return

    c = cmap.get(cat)
    if not c:
        m = [x for x in cats if cat in x["id"]]
        c = m[0] if len(m) == 1 else None
    if not c:
        sys.exit(f"no hacktools category '{cat}'. try: oscp hacktools")

    needs = c.get("needs", [])
    subs = {}
    for i, n in enumerate(needs):
        if i < len(a) and a[i] is not None:
            subs[n] = a[i]
    print(bold(c["name"]) + "  " + dim(f"[hacktools/{c['id']}]"))
    if c.get("desc"):
        print(dim(c["desc"]))
    missing = [n for n in needs if n not in subs]
    if missing:
        print(dim("fill in: " + ", ".join(missing) + "  (left as placeholders below)"))
    print()
    last_section = None
    for it in c["items"]:
        sec = it.get("section")
        if sec and sec != last_section:
            print(section(sec))
            last_section = sec
        t = it["template"]
        for n in ("LHOST", "LPORT", "FILE", "TEXT"):
            t = t.replace("{" + n + "}", subs.get(n, n))
        print(f"  {bold(it['title'])}")
        for line in t.split("\n"):
            print(f"    {green('$')} {line}")
        if it.get("desc"):
            print(f"    {dim(it['desc'])}")
        if it.get("note"):
            nt = it["note"]
            for n in ("LHOST", "LPORT", "FILE"):
                nt = nt.replace("{" + n + "}", subs.get(n, n))
            print(f"    {dim('· ' + nt)}")
        print()
    if c.get("resources"):
        print(dim("resources: " + "  ·  ".join(c["resources"])))


# -------------------------------------------------------- setup / migrate ----
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "oscp", "venv")
BIN_DIR = os.path.join(os.path.expanduser("~"), ".local", "bin")
BUNDLE_ITEMS = ["oscp.py", "oscp", "README.md", "completions", "data"]


def _step(name, status, detail=""):
    mark = green("✓") if not status.startswith("FAILED") else red("✗")
    print(f"  {mark} {cyan(name):<12} {status}  {dim(detail)}")


def cmd_setup(data, args):
    """Install/upgrade oscp on this machine: venv, PATH launcher, completion."""
    import venv as _venv
    print(bold("oscp setup") + "  " + dim(f"[{REPO_DIR}]"))

    # 1. isolated venv
    if os.path.isdir(VENV_DIR):
        _step("runtime", "venv already present", VENV_DIR)
    else:
        os.makedirs(os.path.dirname(VENV_DIR), exist_ok=True)
        _venv.create(VENV_DIR, with_pip=True)
        _step("runtime", "venv created", VENV_DIR)

    # 2. launcher on PATH
    os.makedirs(BIN_DIR, exist_ok=True)
    link = os.path.join(BIN_DIR, "oscp")
    target = os.path.join(REPO_DIR, "oscp")
    try:
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(target, link)
        _step("launcher", "linked", f"{link} -> {target}")
    except OSError as e:
        _step("launcher", f"FAILED: {e}", link)

    # 3. shell completion in the rc file
    shell = os.environ.get("SHELL", "")
    is_zsh = "zsh" in shell or not shell
    rc = os.path.join(os.path.expanduser("~"), ".zshrc" if is_zsh else ".bashrc")
    initline = f'eval "$(command oscp shell-init {"zsh" if is_zsh else "bash"})"'
    try:
        existing = open(rc, encoding="utf-8").read() if os.path.exists(rc) else ""
    except OSError:
        existing = ""
    if "oscp shell-init" in existing:
        _step("completion", f"already in {os.path.basename(rc)}", rc)
    else:
        block = "\n# oscp CLI completion\n"
        if BIN_DIR not in os.environ.get("PATH", "").split(os.pathsep):
            block += 'export PATH="$HOME/.local/bin:$PATH"\n'
        block += initline + "\n"
        try:
            with open(rc, "a", encoding="utf-8") as f:
                f.write(block)
            _step("completion", f"added to {os.path.basename(rc)}", rc)
        except OSError as e:
            _step("completion", f"FAILED: {e}", rc)

    print()
    print(dim("done. open a new shell (or run: exec $SHELL) to activate completion."))


def cmd_migrate(data, args):
    """Package oscp (code + data) into a portable .zip for another machine."""
    import datetime
    import zipfile
    action = (args.migrate_arg or "export").lower()
    if action != "export" and not action.endswith(".zip"):
        sys.exit("usage: oscp migrate [export] [OUTFILE.zip]")
    out = args.outfile
    if action.endswith(".zip"):
        out = action
    if not out:
        now = datetime.datetime.now().astimezone()
        # e.g. oscp-migrate-20-19_IST_Sun_25_OCT_2026.zip
        stamp = (now.strftime("%H-%M_%Z_%a_%d_") + now.strftime("%b").upper()
                 + now.strftime("_%Y"))
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        out = os.path.join(desktop, f"oscp-migrate-{stamp}.zip")
    out = os.path.abspath(os.path.expanduser(out))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in BUNDLE_ITEMS:
            p = os.path.join(REPO_DIR, item)
            if os.path.isfile(p):
                zf.write(p, arcname=os.path.join("oscp", item))
            elif os.path.isdir(p):
                for root, dirs, files in os.walk(p):
                    dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".scratch"}]
                    for fn in files:
                        if fn in {".DS_Store"} or fn.endswith(".pyc"):
                            continue
                        fp = os.path.join(root, fn)
                        rel = os.path.relpath(fp, REPO_DIR)
                        zf.write(fp, arcname=os.path.join("oscp", rel))
    size = os.path.getsize(out)
    print(bold("oscp migrate") + "  " + dim("portable bundle (code + data, no venv/videos)"))
    _step("bundle", "created", f"{out}  ({size // 1024} KB)")
    print()
    print(dim("on the NEW machine:"))
    print(f"    {green('$')} unzip {os.path.basename(out)}")
    print(f"    {green('$')} cd oscp && ./oscp setup")
    print(f"    {green('$')} exec $SHELL        {dim('# activate completion')}")
    print()
    print(dim("same three steps as bhuppi:  unzip  ·  ./TOOL setup  ·  exec $SHELL"))


# ------------------------------------------------------------------- help ----
# Each card: (name, syntax, example, description)
CHEAT_CARDS = [
    ("list", "oscp list", "oscp list",
     "Lists every category with how many commands it holds."),
    ("show", "oscp show CATEGORY", "oscp show privesc-linux",
     "Shows every entry in a category, numbered so you can copy one. A partial "
     "category name works when it is unambiguous."),
    ("copy", "oscp copy CATEGORY N", "oscp copy privesc-linux 3",
     "Copies entry N's command to the clipboard (pbcopy on macOS; xclip / xsel / "
     "wl-copy on Linux). The numbers come from 'oscp show'."),
    ("search", "oscp search [SHELF] TERM", "oscp search wireless",
     "Find a term across the short commands, technique (path, topics, notes), "
     "atlas, and GTFOBins. Each hit prints the command that opens it. "
     "Put a shelf first to look in only one place: the cheat sheet, methods, "
     "manual, atlas, gtfo, or notes. Example: oscp search atlas passwd."),
]

CMD_CARDS = [
    ("cmd", "oscp cmd [CATEGORY] [PAGE]", "oscp cmd web php",
     "The short numbered commands for one category. With no category, lists them. "
     "oscp cmd web is the enumeration page, and oscp cmd web basic is that same page. "
     "A second word opens one framework: php, wp, tomcat, jenkins, iis, joomla, drupal, git. "
     "oscp cmd ssh is the SSH category. Type the line number at the prompt to copy."),
]

TECHNIQUE_CARDS = [
    ("technique", "oscp technique [path | TOPIC | notes | ID]", "oscp technique windows",
     "Three shelves. path is the exam in order (27 write-ups). A topic such as windows "
     "or web is one area. notes is the 0xsyr0 sheet. A bare id opens that write-up."),
    ("technique show", "oscp technique show ID", "oscp technique show kerberos-flow",
     "One write-up, from the path, a topic, or the notes. The same id on two shelves "
     "prints both."),
    ("technique search", "oscp technique search TERM", "oscp technique search kerberos",
     "Search the path, the topics, and the notes. oscp search also covers atlas, "
     "the short commands, and GTFOBins."),
    ("technique path", "oscp technique path [STAGE]", "oscp technique path",
     "The exam in stage order: foundations, recon, each service, foothold, privesc, "
     "proof, report, and what to do when stuck."),
    ("technique notes", "oscp technique notes [SECTION]", "oscp technique notes post-exploitation",
     "The 0xsyr0 sheet. No section lists them. A section id prints that section."),
]

BM_CARDS = [
    ("list", "oscp bm list [GROUP]", "oscp bm list offsec",
     "Shows bookmarks as a tree, best-rated first. Give a GROUP to narrow it."),
    ("open", "oscp bm open N [--browser NAME]", "oscp bm open 18 --browser safari",
     "Opens a bookmark by its number. Google Chrome when installed, else the "
     "system default. Names: chrome, safari, firefox, edge, brave, arc, system."),
    ("find", "oscp bm find TEXT", "oscp bm find youtube",
     "Searches names, addresses, notes, tags and group names."),
    ("add", "oscp bm add URL [--group G] [--rate R] [--name N] [--note TEXT]",
     "oscp bm add https://gtfobins.org --group offsec --rate excellent",
     "Saves a link. A bare host or a pasted [name](url) both work. "
     "Ratings: good, very good, excellent (or 1, 2, 3). Duplicates are refused."),
    ("rate", "oscp bm rate N good|very good|excellent", "oscp bm rate 18 excellent",
     "Re-rates a bookmark by its number. The tree shows excellent first."),
    ("rm", "oscp bm rm N", "oscp bm rm 9",
     "Forgets a bookmark."),
    ("import", "oscp bm import FILE [--group G]", "oscp bm import refs.json",
     "Imports a `ti ref export` JSON, or a plain list of links one per line "
     "(bullets and markdown links are fine). Links already saved are skipped."),
]

GTFO_CARDS = [
    ("gtfo", "oscp gtfo BINARY [sudo|suid|shell|file-read|...]", "oscp gtfo tar sudo",
     "Shows a binary's GTFOBins techniques (break out of restricted shells, read/write "
     "files, escalate via sudo/suid/capabilities). Add a function or context to filter."),
    ("gtfo search", "oscp gtfo search TERM", "oscp gtfo search LD_PRELOAD",
     "Searches binary names and their commands across all 458 GTFOBins entries."),
    ("gtfo list", "oscp gtfo list", "oscp gtfo list",
     "Lists every GTFOBins binary."),
]

NOTES_CARDS = [
    ("notes list", "oscp notes [list]", "oscp notes",
     "Lists the sections of the 0xsyr0 OSCP cheat sheet."),
    ("notes show", "oscp notes show SECTION", "oscp notes show post-exploitation",
     "Prints a cheat-sheet section. A partial id or title works when unambiguous."),
    ("notes search", "oscp notes search TERM", "oscp notes search kerberos",
     "Searches section titles and bodies and shows a matching snippet."),
]

HACKTOOLS_CARDS = [
    ("hacktools", "oscp hacktools [CATEGORY [LHOST LPORT FILE]]", "oscp hacktools revshell 10.10.14.5 4444",
     "HackTools-style payload generator: fill LHOST/LPORT/FILE and copy a ready payload — reverse "
     "shells, PHP/webshells, TTY, MSFVenom, file transfer, LFI/XSS/SQLi, quick enum. Alias: ht."),
    ("hacktools encode/hash", "oscp hacktools (encode|decode|hash|obfuscate) [TEXT]", "oscp hacktools hash apple",
     "Computed helpers: base64/url/hex encode & decode, md5/sha1/sha256/sha512 hashing, and "
     "obfuscate (base64 bash loader / powershell -enc). The result is auto-copied to the clipboard. "
     "For big strings with special characters, single-quote the TEXT, pipe it "
     "(echo -n '...' | oscp hacktools encode), redirect a file (< payload.txt), or run with no TEXT "
     "and paste + Ctrl-D."),
]

METHODS_CARDS = [
    ("methods", "oscp methods [list [TOPIC]]", "oscp methods",
     "The methodology library: the logic behind each step, grouped as a progressive path "
     "(foundations · full-workflow · recon · per-service attack plans · foothold · enumerate · "
     "privesc · proof · reporting · when-stuck). Start: oscp methods show full-workflow — or "
     "oscp howto for the command map. Explains the why, not just commands."),
    ("methods show", "oscp methods show ID", "oscp methods show gtfobins-logic",
     "Read one method in full (background, reasoning, commands you can copy)."),
    ("methods search", "oscp methods search TERM", "oscp methods search privesc",
     "Search methods by title, brief, body and tags."),
]

LABSETUP_CARDS = [
    ("lab-setup", "oscp lab-setup [SECTION]", "oscp lab-setup vpn",
     "Set up a Kali attacker box on VMware Fusion (Apple Silicon) for OSCP/OSWE/HTB/CTF: VM + ISO, "
     "install, guest tools (shared folder/clipboard), update, toolset, snapshot, VPN (OffSec/HTB), and "
     "MTU tuning — with the gotchas and fixes. `oscp lab-setup <section>` zooms to one."),
]

TMUX_CARDS = [
    ("tmux", "oscp tmux [SECTION]", "oscp tmux logging",
     "Examples use a custom prefix, Ctrl-a, chosen for ease. The default is Ctrl-b. "
     "Sections: config, logging, prefix, keys, command (prefix then :), shell, copy. "
     "oscp cmd tmux is the short list. oscp atlas tmux is the tool page."),
]

SHELLSCRIPT_CARDS = [
    ("shell-script", "oscp shell-script [SECTION]", "oscp shell-script loops",
     "Bash you can copy into a .sh file: shebang, quoting, if, loops, functions, files. "
     "Tab lists sections. Type a line number to copy, or N-M for a block. "
     "Snippets are not executed from this page."),
]

HOWTO_CARDS = [
    ("howto", "oscp howto [PHASE]", "oscp howto recon",
     "The phase-by-phase command map: which oscp command to run at each stage, in order "
     "(recon -> service -> foothold -> stabilise -> enumerate -> escalate -> proof -> report). "
     "`oscp howto` shows the whole map; `oscp howto <phase>` zooms to one; `oscp howto map` shows "
     "the oscp utility map (which command does what, and when). `oscp howto page` opens the "
     "tutorial in the default browser. The why is in `oscp technique show full-workflow`."),
]

ATLAS_CARDS = [
    ("atlas", "oscp atlas [COMMAND [WORD]]", "oscp atlas awk",
     "Command reference: each entry has syntax, description, anatomy, origins and use-cases. "
     "`oscp atlas` lists; `oscp atlas <command>` reads one; "
     "`oscp atlas git log` jumps to matching use-cases."),
    ("atlas search", "oscp atlas search TERM", "oscp atlas search passwd",
     "Search commands and their use-cases. Each hit shows the command, why, and a danger mark when argv can destroy work."),
]

MANUAL_CARDS = [
    ("manual", "oscp manual [TOPIC | ID]", "oscp manual filesystem",
     "Linux/Kali fundamentals by category, explained as patterns. `oscp manual` lists; "
     "`oscp manual <topic>` filters; `oscp manual show <id>` reads one."),
    ("manual search", "oscp manual search TERM", "oscp manual search inode",
     "Search fundamentals by title, brief, body and tags."),
]

SETUP_CARDS = [
    ("setup", "oscp setup", "oscp setup",
     "Installs/upgrades oscp on this machine: creates its own venv, links `oscp` "
     "onto your PATH, and adds tab-completion to your shell rc. Safe to re-run."),
    ("migrate", "oscp migrate [export] [OUTFILE.zip]", "oscp migrate",
     "Packages the code and data (your categories, bookmarks, GTFOBins, notes) into "
     "a portable .zip on your Desktop — no venv or videos. On the new machine: "
     "unzip, then `cd oscp && ./oscp setup`, then `exec $SHELL`. Same three steps as bhuppi."),
]

TOP_COMMANDS = {k: v for v in CHEAT_CARDS for k in [v[0]]}
BM_COMMANDS = {k: v for v in BM_CARDS for k in [v[0]]}
SETUP_COMMANDS = {k: v for v in SETUP_CARDS for k in [v[0]]}


def _label(lbl, val):
    return f"    {dim(lbl.ljust(7))}  {val}"


def render_card(card, width):
    name, syntax, example, desc = card
    out = [f"  {bold(cyan(name))}"]
    out.append(_label("syntax", cyan(syntax)))
    out.append(_label("example", yellow(example)))
    wrapped = textwrap.wrap(desc, max(width - 15, 24)) or [""]
    for i, line in enumerate(wrapped):
        out.append(_label("what" if i == 0 else "", line))
    out.append("")
    return out


def render_help(topic, width):
    legend = dim("Shape: UPPERCASE = you supply it · [brackets] = optional · a|b = pick one")
    if topic in ("tech", "tec", "teq"):
        topic = "technique"

    # ---- deep help for a single top-level command ----
    if topic in TOP_COMMANDS:
        out = [bold(magenta(f"oscp {topic}")), ""]
        out += render_card(TOP_COMMANDS[topic], width)
        out.append(legend)
        return "\n".join(out)

    if topic in SETUP_COMMANDS:
        out = [bold(magenta(f"oscp {topic}")), ""]
        out += render_card(SETUP_COMMANDS[topic], width)
        out.append(legend)
        return "\n".join(out)

    # ---- GTFOBins ----
    if topic == "gtfo":
        out = [bold(magenta("oscp gtfo — GTFOBins techniques")),
               dim("Unix binaries abused to break out of restricted shells or escalate privileges."), ""]
        for card in GTFO_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    # ---- lab-setup (Kali/VMware lab build) ----
    if topic in ("lab-setup", "labsetup", "lab"):
        out = [bold(magenta("oscp lab-setup — Kali / VMware lab build")),
               dim("Install Kali and your toolkit, connect the VPN, fix the gotchas. For OSCP/OSWE/HTB/CTF."), ""]
        for card in LABSETUP_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic == "tmux":
        out = [bold(magenta("oscp tmux — this machine's terminal")),
               _tmux_prefix_note(), ""]
        for card in TMUX_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic in ("shell-script", "shellscript", "bash-script"):
        out = [bold(magenta("oscp shell-script — bash you can copy into a file")), ""]
        for card in SHELLSCRIPT_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    # ---- howto (the phase-by-phase command map) ----
    if topic == "howto":
        out = [bold(magenta("oscp howto — the phase-by-phase command map")),
               dim("Which oscp command to run at each stage. Pairs with: oscp technique show full-workflow."), ""]
        for card in HOWTO_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    # ---- methods (methodology library) ----
    if topic == "methods":
        out = [bold(magenta("oscp methods — methodology & fundamentals")),
               dim("Understand the why behind each step; browse by stage, read in full, search."), ""]
        for card in METHODS_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic == "manual":
        out = [bold(magenta("oscp manual — still works")),
               dim("Same write-ups as oscp technique. The menu name is technique."), ""]
        for card in MANUAL_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic == "technique":
        out = [bold(magenta("oscp technique — the path, one technique, or the notes")),
               dim("Three shelves. path is the exam in order. A topic is one area. notes is the 0xsyr0 sheet."),
               dim("Same command: oscp tech, oscp tec, oscp teq."), ""]
        for card in TECHNIQUE_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic == "cmd":
        out = [bold(magenta("oscp cmd — the short command for a category")),
               dim("Numbered lines. Type the line number to copy. list and show still work."), ""]
        for card in CMD_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic == "atlas":
        out = [bold(magenta("oscp atlas — command reference")),
               dim("Syntax, description, anatomy, origins and use-cases, per command."), ""]
        for card in ATLAS_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic in ("hacktools", "ht"):
        out = [bold(magenta("oscp hacktools — payload generators")),
               dim("Modelled on the HackTools extension. Fill LHOST/LPORT/FILE; copy the payload."), ""]
        for card in HACKTOOLS_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    # ---- notes (0xsyr0) ----
    if topic == "notes":
        out = [bold(magenta("oscp notes — 0xsyr0 OSCP cheat sheet")),
               dim("Imported from github.com/0xsyr0/OSCP, browsable as sections."), ""]
        for card in NOTES_CARDS:
            out += render_card(card, width)
        out.append(legend)
        return "\n".join(out)

    if topic == "alias":
        out = [bold(magenta("oscp alias")),
               dim("Every other name that still works. The menu keeps the main name."),
               "",
               dim("oscp alias"),
               ""]
        return "\n".join(out)

    # ---- the whole bookmark group ----
    if topic in ("bm", "ref", "reference", "bookmark") or topic in BM_COMMANDS:
        out = [bold(magenta("oscp bm — the links you keep coming back to")),
               dim("A reference hub. Links in groups, shown as a tree, each rated so the best is a number away."),
               dim("Aliases:  oscp bm  =  oscp ref  =  oscp reference  =  oscp bookmark"), ""]
        for card in BM_CARDS:
            out += render_card(card, width)
        out.append(legend)
        out.append(dim("more: oscp help · oscp help copy"))
        return "\n".join(out)

    # ---- landing / overview ----
    rows = [
        ("howto", "where you are in the exam"),
        ("help", "how a command works"),
        ("technique", "the path, one technique, or the notes"),
        ("atlas", "one tool in depth"),
        ("cmd", "the short command for a category"),
        ("hacktools", "build a payload"),
        ("gtfo", "abuse a binary"),
        ("search", "when you do not know which of those"),
        ("shell-script", "bash you can copy into a file"),
    ]
    out = [
        bold(cyan("oscp") + "  —  offline exam reference"),
        dim("one command per question. a line number copies."),
        "",
        bold(magenta("WHEN YOU WANT TO")),
    ]
    for name, what in rows:
        out.append(f"  {green(name.ljust(12))} {what}")
    out += [
        "",
        dim("oscp technique              the three shelves"),
        dim("oscp technique path         the exam in order"),
        dim("oscp technique show <id>    one write-up"),
        dim("oscp cmd <category>         numbered commands"),
        dim("oscp tmux                   keys and logging; default prefix is Ctrl-b"),
        dim("oscp shell-script           bash library; Tab lists loops, if, quoting, …"),
        "",
        dim("older names still run:  methods  manual  notes  list  show  copy"),
        dim("every other name:  oscp alias     deeper:  oscp help <command>     map:  oscp howto"),
        "",
        legend,
    ]
    return "\n".join(out)


# ------------------------------------------------------------- completion ----
GTFO_FUNC_DESC = {
    "shell": "spawn an interactive shell",
    "command": "run a command / break out",
    "reverse-shell": "connect back for a shell",
    "bind-shell": "listen for an incoming shell",
    "file-read": "read files as the target user",
    "file-write": "write files as the target user",
    "file-upload": "upload a file to the target",
    "file-download": "download a file to the target",
    "upload": "upload a file to the target",
    "download": "download a file to the target",
    "library-load": "load a shared library",
    "privilege-escalation": "escalate privileges directly",
    "inherit": "inherit a privileged fd/capability",
    "sudo": "abuse when runnable via sudo",
    "suid": "abuse the suid bit",
    "capabilities": "abuse a file capability",
    "limited-suid": "suid with a limited shell",
    "unprivileged": "works without privileges",
}


def _cd(value, desc):
    """Format one `value:description` pair for zsh _describe (sanitise colons)."""
    return f"{value}:{desc.replace(':', ' -')}"


def do_complete(rest):
    """Emit completion candidates for the shell widget.

    Plain names (one per line) for bash; `value:description` pairs for zsh's
    _describe (the '-desc' variants), so Tab shows a description per option.
    """
    what = rest[0] if rest else ""
    arg = rest[1] if len(rest) > 1 else None

    # ---- plain name lists (bash / fallback) ----
    if what == "commands":
        print("\n".join(["howto", "lab-setup", "tmux", "shell-script", "help", "alias", "technique", "atlas", "cmd",
                         "hacktools", "gtfo", "search", "bm", "ref", "setup", "migrate",
                         "list", "show", "copy", "methods", "manual", "notes"]))
        return
    if what == "techniquetopics-desc":
        methods = load_json_file(METHODS_FILE, "methods")
        manual = load_json_file(MANUAL_FILE, "manual")
        rows = []
        manual_ids = set()
        for t in manual.get("topics", []):
            manual_ids.add(t["id"])
            n = sum(1 for e in manual.get("entries", []) if e.get("topic") == t["id"])
            rows.append(_cd(t["id"], f"{t.get('name') or t['id']} ({n})"))
        for t in methods.get("topics", []):
            if t["id"] in manual_ids:
                continue
            n = sum(1 for e in methods.get("methods", []) if e.get("topic") == t["id"])
            rows.append(_cd(t["id"], f"path — {t.get('name') or t['id']} ({n})"))
        print("\n".join(rows))
        return
    if what == "techniqueids-desc":
        methods = load_json_file(METHODS_FILE, "methods")
        manual = load_json_file(MANUAL_FILE, "manual")
        notes = load_json_file(NOTES_FILE, "notes")
        seen = {}
        for shelf, items, brief in (
            ("path", methods.get("methods", []), lambda e: e.get("brief", e["title"])),
            ("topic", manual.get("entries", []), lambda e: e.get("brief", e["title"])),
            ("notes", notes.get("sections", []), lambda e: e.get("title", "")),
        ):
            for e in items:
                seen.setdefault(e["id"], []).append(f"{shelf}: {brief(e)}")
        print("\n".join(_cd(i, " · ".join(parts)[:180]) for i, parts in seen.items()))
        return
    if what == "labsetupsecs-desc":
        ld = load_json_file(LABSETUP_FILE, "lab-setup")
        print("\n".join(_cd(s["id"], s.get("goal", s.get("name", ""))) for s in ld["sections"]))
        return
    if what == "tmuxsecs-desc":
        td = load_json_file(TMUX_FILE, "tmux")
        print("\n".join(_cd(s["id"], s.get("goal", s.get("name", ""))) for s in td["sections"]))
        return
    if what == "shellscriptsecs-desc":
        td = load_json_file(SHELLSCRIPT_FILE, "shell-script")
        print("\n".join(_cd(s["id"], s.get("goal", s.get("name", ""))) for s in td["sections"]))
        return
    if what == "howtophases-desc":
        hd = load_json_file(HOWTO_FILE, "howto")
        rows = [_cd(p["id"], p.get("goal", p.get("name", ""))) for p in hd["phases"]]
        rows.append(_cd("map", "the oscp utility map — which command does what, and when"))
        rows.append(_cd("page", "open the tutorial in the default browser"))
        print("\n".join(rows))
        return
    if what == "hacktoolscats":
        ht = load_json_file(HACKTOOLS_FILE, "hacktools")
        print("\n".join([_cd(c["id"], c["name"]) for c in ht["categories"]]
                        + [_cd("encode", "base64/url/hex encode"), _cd("decode", "base64/url/hex decode"),
                           _cd("hash", "md5/sha1/sha256/sha512"),
                           _cd("obfuscate", "base64 bash loader / powershell -enc")]))
        return
    if what == "manualids-desc":
        md = load_json_file(MANUAL_FILE, "manual")
        print("\n".join(_cd(m["id"], m.get("brief", m["title"])) for m in md.get("entries", [])))
        return
    if what == "manualtopics-desc":
        md = load_json_file(MANUAL_FILE, "manual")
        print("\n".join(_cd(t["id"], t["name"]) for t in md.get("topics", [])))
        return
    if what == "atlasnames-desc":
        ad = load_json_file(ATLAS_FILE, "atlas")
        print("\n".join(_cd(c["name"], c.get("description", "").split(". ")[0])
                        for c in sorted(ad["commands"], key=lambda x: x["name"])))
        return
    if what == "methodsub":
        print("\n".join(["list", "show", "search"]))
        return
    if what == "methodids":
        md = load_json_file(METHODS_FILE, "methods")
        print("\n".join(m["id"] for m in md["methods"]))
        return
    if what == "methodids-desc":
        md = load_json_file(METHODS_FILE, "methods")
        print("\n".join(_cd(m["id"], m.get("brief", m["title"])) for m in md["methods"]))
        return
    if what == "methodtopics-desc":
        md = load_json_file(METHODS_FILE, "methods")
        print("\n".join(_cd(t["id"], t["name"]) for t in md.get("topics", [])))
        return
    if what == "bmsub":
        print("\n".join(["list", "open", "add", "rm", "rate", "find", "import"]))
        return
    if what == "notessub":
        print("\n".join(["list", "show", "search"]))
        return
    if what == "gtfobins":
        g = load_json_file(GTFO_FILE, "GTFOBins")
        print("\n".join(sorted(g["binaries"])))
        return
    if what == "gtfofuncs":
        g = load_json_file(GTFO_FILE, "GTFOBins")
        b = g["binaries"].get((arg or "").lower())
        if b:
            fns = set(b["functions"].keys())
            for e in (e for v in b["functions"].values() for e in v):
                fns.update(e.get("contexts", []))
            print("\n".join(sorted(fns)))
        return
    if what == "notesids":
        n = load_json_file(NOTES_FILE, "notes")
        print("\n".join(s["id"] for s in n["sections"]))
        return

    # ---- `value:description` pairs for zsh _describe ----
    if what == "categories-desc":
        data = load_data()
        rows = []
        pages = " ".join(name for name, _cid, _desc in _WEB_PAGES)
        for c in data["categories"]:
            if c["id"] in _CMD_HIDDEN:
                continue
            desc = f"{c['name']} ({len(c['entries'])})"
            if c["id"] == "web":
                desc += f" — next Tab is {pages}"
            rows.append(_cd(c["id"], desc))
        print("\n".join(rows))
        return
    if what == "webpages-desc":
        rows = []
        for name, _cid, desc in _WEB_PAGES:
            example = "oscp cmd web" if name == "basic" else f"oscp cmd web {name}"
            rows.append(_cd(name, f"{desc}  ·  e.g. {example}"))
        print("\n".join(rows))
        return
    if what == "copynums-desc":
        data = load_data()
        cat = find_category(data, arg) if arg else None
        if cat:
            print("\n".join(_cd(str(i), e.get("title", ""))
                            for i, e in enumerate(cat["entries"], 1)))
        return
    if what == "gtfobins-desc":
        g = load_json_file(GTFO_FILE, "GTFOBins")
        out = []
        for name in sorted(g["binaries"]):
            fns = ", ".join(g["binaries"][name]["functions"].keys())
            out.append(_cd(name, fns))
        print("\n".join(out))
        return
    if what == "gtfofuncs-desc":
        g = load_json_file(GTFO_FILE, "GTFOBins")
        b = g["binaries"].get((arg or "").lower())
        if b:
            fns = set(b["functions"].keys())
            for e in (e for v in b["functions"].values() for e in v):
                fns.update(e.get("contexts", []))
            print("\n".join(_cd(f, GTFO_FUNC_DESC.get(f, f)) for f in sorted(fns)))
        return
    if what == "notesids-desc":
        n = load_json_file(NOTES_FILE, "notes")
        print("\n".join(_cd(s["id"], f"{s['title']} ({s['body'].count(chr(10)) + 1} ln)")
                        for s in n["sections"]))
        return
    if what == "bmids-desc":
        data = load_data()
        print("\n".join(_cd(str(b["id"]),
                            f"{b.get('name', '')} [{b.get('group', '')}]")
                        for b in data["bookmarks"]))
        return
    if what == "groups-desc":
        data = load_data()
        counts = {}
        for b in data["bookmarks"]:
            g = b.get("group", "")
            if g:
                counts[g] = counts.get(g, 0) + 1
        print("\n".join(_cd(g, f"{n} bookmark(s)") for g, n in sorted(counts.items())))
        return

    # ---- plain data lists (bash / fallback) ----
    data = load_data()
    if what == "categories":
        print("\n".join(c["id"] for c in data["categories"] if c["id"] not in _CMD_HIDDEN))
    elif what == "copynums":
        cat = find_category(data, arg) if arg else None
        if cat:
            print("\n".join(str(i) for i in range(1, len(cat["entries"]) + 1)))
    elif what == "groups":
        print("\n".join(sorted({b.get("group", "") for b in data["bookmarks"] if b.get("group")})))
    elif what == "bmids":
        print("\n".join(str(b["id"]) for b in data["bookmarks"]))


# Depth-aware zsh completion + a hook to load it. Mirrors `ti`'s
#   eval "$(command ticu shell-init zsh)"
# Add to ~/.zshrc:  eval "$(oscp shell-init zsh)"
_ZSH_INIT = r'''# oscp shell integration (completion). Generated by: oscp shell-init zsh
if ! whence compinit >/dev/null 2>&1; then
  autoload -Uz compinit && compinit -C
fi
# Colour ONLY the 'map' option (it extends to 'oscp howto map') bold magenta; everything else
# keeps its normal colour. '=map=...' matches only the literal value "map".
zstyle ':completion:*:oscp:*' list-colors '=map=01;35'
zstyle ':completion:*:*:oscp:*' list-colors '=map=01;35'
zstyle ':completion:*:phases' list-colors '=map=01;35'
zstyle ':completion:*:*:oscp:*' group-name ''
if [[ -z ${NO_COLOR:-} ]]; then
  zstyle ':completion:*:*:oscp:*:descriptions' format $'\e[33m── %d ──\e[0m'
else
  zstyle ':completion:*:*:oscp:*:descriptions' format '── %d ──'
fi
_oscp_runhint() { _message -r "· press ↵ to run now ($1) — or pick an option below"; }
_oscp_endhint() { _message -r "· nothing more to complete — press ↵ to run"; }

# Top 3 on a decision menu only. Catalogs (every technique, every tool) are not ranked.
# ★★★ sober magenta, ★★ sober yellow, ★ soft amber. Marks are padded to the same width.
if [[ -z ${NO_COLOR:-} ]]; then
  _oscp_s3=$'\e[38;5;132m★★★\e[0m'
  _oscp_s2=$'\e[38;5;185m★★\e[0m '
  _oscp_s1=$'\e[38;5;179m★\e[0m  '
else
  _oscp_s3='★★★'
  _oscp_s2='★★ '
  _oscp_s1='★  '
fi
# _oscp_rank TAG name rank name rank ...
# Rewrites the descriptions in $_c and colours those match names. Anything not named is left as-is.
_oscp_rank() {
  local tag="$1"; shift
  local -a cols
  cols=( '=map=01;35' )
  local name rank mark col i
  while (( $# >= 2 )); do
    name="$1"; rank="$2"; shift 2
    case $rank in
      3) mark="$_oscp_s3"; col='38;5;132' ;;
      2) mark="$_oscp_s2"; col='38;5;185' ;;
      1) mark="$_oscp_s1"; col='38;5;179' ;;
      *) continue ;;
    esac
    cols+=( "=${name}=${col}" )
    i=1
    while (( i <= ${#_c} )); do
      if [[ "${_c[i]%%:*}" == "$name" ]]; then
        _c[i]="${name}:${mark}  ${_c[i]#*:}"
        break
      fi
      (( i++ ))
    done
  done
  [[ -n ${NO_COLOR:-} ]] && return
  zstyle ":completion:${curcontext}:${tag}" list-colors "${cols[@]}"
}

_oscp() {
  local -a _c
  # top level: same six headings, commands in the order you use them.
  # -V keeps that order (zsh otherwise alphabetises and the groups collapse).
  # `copy` is intentionally absent: every browsed line already copies with N.
  # The command still works if typed.
  if (( CURRENT == 2 )); then
    zstyle ":completion:${curcontext}:*" list-grouped true
    zstyle ":completion:${curcontext}:*" sort false
    local -a guide hlp cheat refs links setupg
    guide=(
      'howto:the map — which command at each stage  ·  e.g. oscp howto recon'
      'lab-setup:build the Kali box (once)  ·  e.g. oscp lab-setup vpn'
      'tmux:keys, command mode, logging  ·  default prefix Ctrl-b; Ctrl-a is custom  ·  e.g. oscp tmux logging'
      'shell-script:bash you can copy  ·  loops, if, quoting, functions  ·  e.g. oscp shell-script loops'
    )
    hlp=(
      'help:how a command works  ·  e.g. oscp help technique'
      'alias:every other name that still works  ·  e.g. oscp alias'
    )
    refs=(
      "technique:${_oscp_s3}  the path, one technique, or the notes  ·  e.g. oscp technique windows"
      "atlas:${_oscp_s1}  one tool in depth  ·  e.g. oscp atlas ffuf"
    )
    cheat=(
      "cmd:${_oscp_s2}  the short command for a category  ·  e.g. oscp cmd privesc-linux"
      'hacktools:build a payload  ·  e.g. oscp hacktools revshell'
      'gtfo:abuse a binary  ·  e.g. oscp gtfo tar sudo'
      'search:find a term anywhere, or in one shelf  ·  e.g. oscp search wireless'
    )
    links=(
      'bm:your reference bookmarks  ·  e.g. oscp bm list offsec'
      'ref:alias of bm'
      'reference:alias of bm'
      'bookmark:alias of bm'
    )
    setupg=(
      'setup:install / upgrade oscp here  ·  e.g. oscp setup'
      'migrate:package oscp for another machine  ·  e.g. oscp migrate'
    )
    if [[ -z ${NO_COLOR:-} ]]; then
      zstyle ":completion:${curcontext}:references" list-colors '=technique=38;5;132' '=atlas=38;5;179' '=map=01;35'
      zstyle ":completion:${curcontext}:cheatsheet" list-colors '=cmd=38;5;185' '=map=01;35'
    fi
    _describe -V -t guide 'start here' guide
    _describe -V -t help 'help' hlp
    _describe -V -t references 'external references' refs
    _describe -V -t cheatsheet 'cheat-sheet' cheat
    _describe -V -t links 'your links' links
    _describe -V -t setup 'setup' setupg
    # teq is not a prefix of technique, so it is offered only once typed.
    # tech and tec already complete to technique. The menu above stays unchanged.
    if [[ $PREFIX == teq* ]]; then
      local -a _teq
      _teq=( 'teq:alias of technique' )
      _describe -V -t aliases 'alias' _teq
    fi
    return
  fi
  case $words[2] in
    howto)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'shows the whole recon -> report map'
        _c=( ${(f)"$(command oscp __complete howtophases-desc)"} )
        _oscp_rank phases recon 3 foothold 2 escalate 1
        _describe -t phases 'phase' _c
      else _oscp_endhint; fi
      ;;
    lab-setup)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'walks the whole install -> tools -> VPN -> MTU setup'
        _c=( ${(f)"$(command oscp __complete labsetupsecs-desc)"} )
        _oscp_rank sections vpn 3 mtu 2 tools 1
        _describe -t sections 'section' _c
      else _oscp_endhint; fi
      ;;
    tmux)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'prefix, keys, command mode, and the live log'
        _c=( ${(f)"$(command oscp __complete tmuxsecs-desc)"} ); _describe -V -t sections 'section' _c
      else _oscp_endhint; fi
      ;;
    shell-script|shellscript|bash-script)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'bash snippets you can copy into a .sh file'
        _c=( ${(f)"$(command oscp __complete shellscriptsecs-desc)"} ); _describe -V -t sections 'section' _c
      else _oscp_endhint; fi
      ;;
    list)
      _oscp_endhint
      ;;
    alias)
      _oscp_endhint
      ;;
    technique|tech|tec|teq)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists the three shelves: path, topics, notes'
        local -a tsub
        tsub=(
          "path:${_oscp_s1}  the exam in order  ·  e.g. oscp technique path"
          'notes:the 0xsyr0 sheet  ·  e.g. oscp technique notes post-exploitation'
          "show:${_oscp_s3}  one write-up  ·  e.g. oscp technique show kerberos-flow"
          "search:${_oscp_s2}  search path, topics, and notes  ·  e.g. oscp technique search kerberos"
          'list:the three shelves  ·  e.g. oscp technique'
        )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:techshelves" list-colors '=show=38;5;132' '=search=38;5;185' '=path=38;5;179' '=map=01;35'
        fi
        _describe -V -t techshelves 'shelf' tsub
        _c=( ${(f)"$(command oscp __complete techniquetopics-desc)"} )
        _describe -V -t techtopics 'topic' _c
      elif (( CURRENT == 4 )); then
        case $words[3] in
          show) _c=( ${(f)"$(command oscp __complete techniqueids-desc)"} ); _describe -V -t techniques 'technique' _c ;;
          notes) _c=( ${(f)"$(command oscp __complete notesids-desc)"} ); _describe -V -t sections 'section' _c ;;
          path) _c=( ${(f)"$(command oscp __complete methodtopics-desc)"} ); _describe -V -t stages 'stage (optional)' _c ;;
          search) _message -r 'a term to find in path, topics, and notes' ;;
          *) _oscp_endhint ;;
        esac
      else _oscp_endhint; fi
      ;;
    cmd)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists the short-command categories'
        _c=( ${(f)"$(command oscp __complete categories-desc)"} )
        _oscp_rank categories web 3 privesc-linux 2 privesc-windows 1
        _describe -V -t categories 'category' _c
      elif (( CURRENT == 4 )) && [[ $words[3] == web ]]; then
        _oscp_runhint 'the enumeration page'
        _c=( ${(f)"$(command oscp __complete webpages-desc)"} ); _describe -V -t pages 'web page' _c
      else _oscp_endhint; fi
      ;;
    setup)
      _oscp_endhint
      ;;
    show)
      if (( CURRENT == 3 )); then _c=( ${(f)"$(command oscp __complete categories-desc)"} ); _describe -t categories 'category (required)' _c
      else _oscp_endhint; fi
      ;;
    copy)
      if (( CURRENT == 3 )); then _c=( ${(f)"$(command oscp __complete categories-desc)"} ); _describe -t categories 'category (required)' _c
      elif (( CURRENT == 4 )); then _c=( ${(f)"$(command oscp __complete copynums-desc $words[3])"} ); _describe -t entries 'entry to copy (required)' _c
      else _oscp_endhint; fi
      ;;
    search)
      if (( CURRENT == 3 )); then
        _message -r 'a term to find ANYWHERE — or pick a shelf, then the term'
        local -a shelves
        shelves=(
          "cheat-sheet:${_oscp_s1}  only the short commands"
          'methods:only the exam path'
          "manual:${_oscp_s3}  only the write-ups"
          "atlas:${_oscp_s2}  only the tool pages"
          'gtfo:only GTFOBins'
          'notes:only the 0xsyr0 sheet'
          'bash:only the shell-script library'
        )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:shelves" list-colors '=manual=38;5;132' '=atlas=38;5;185' '=cheat-sheet=38;5;179' '=map=01;35'
        fi
        _describe -V -t shelves 'shelf (optional)' shelves
      elif (( CURRENT >= 4 )); then
        case $words[3] in
          cheat-sheet|cheatsheet|cmd|methods|method|path|manual|atlas|gtfo|gtfobins|notes|note|bash|shell-script|shellscript)
            _message -r "a term to find in $words[3]" ;;
          *) _oscp_endhint ;;
        esac
      fi
      ;;
    gtfo)
      if (( CURRENT == 3 )); then
        _message -r '· press ↵ to show usage — or pick a binary / list / search'
        local -a actions
        actions=( "list:${_oscp_s2}  list every GTFOBins binary" "search:${_oscp_s3}  search names and commands" )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:actions" list-colors '=search=38;5;132' '=list=38;5;185' '=map=01;35'
        fi
        _describe -t actions 'action' actions
        _c=( ${(f)"$(command oscp __complete gtfobins-desc)"} ); _describe -t binaries 'binary' _c
      elif (( CURRENT == 4 )); then
        _oscp_runhint "all ${words[3]} techniques"
        _c=( ${(f)"$(command oscp __complete gtfofuncs-desc $words[3])"} ); _describe -t functions 'filter: function / context' _c
      else _oscp_endhint; fi
      ;;
    methods)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists all methods by stage'
        local -a msub
        msub=(
          "list:${_oscp_s1}  browse methods by stage  ·  e.g. oscp methods"
          "show:${_oscp_s3}  read one method in full  ·  e.g. oscp methods show gtfobins-logic"
          "search:${_oscp_s2}  search methods  ·  e.g. oscp methods search privesc"
        )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:methodsub" list-colors '=show=38;5;132' '=search=38;5;185' '=list=38;5;179' '=map=01;35'
        fi
        _describe -t methodsub 'methods command' msub
      elif (( CURRENT == 4 )); then
        case $words[3] in
          show) _c=( ${(f)"$(command oscp __complete methodids-desc)"} ); _describe -t methods 'method' _c ;;
          list) _c=( ${(f)"$(command oscp __complete methodtopics-desc)"} ); _describe -t topics 'topic (optional)' _c ;;
        esac
      else _oscp_endhint; fi
      ;;
    manual)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists all fundamentals by category'
        local -a msub
        msub=(
          "list:${_oscp_s1}  browse fundamentals by category  ·  e.g. oscp manual"
          "show:${_oscp_s3}  read one in full  ·  e.g. oscp manual show passwd-file"
          "search:${_oscp_s2}  search fundamentals  ·  e.g. oscp manual search inode"
        )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:manualsub" list-colors '=show=38;5;132' '=search=38;5;185' '=list=38;5;179' '=map=01;35'
        fi
        _describe -t manualsub 'manual command' msub
        _c=( ${(f)"$(command oscp __complete manualtopics-desc)"} ); _describe -t topics 'topic' _c
        _c=( ${(f)"$(command oscp __complete manualids-desc)"} ); _describe -t entries 'entry' _c
      elif (( CURRENT == 4 )) && [[ $words[3] == show ]]; then
        _c=( ${(f)"$(command oscp __complete manualids-desc)"} ); _describe -t entries 'entry' _c
      elif (( CURRENT == 4 )) && [[ $words[3] == list ]]; then
        _c=( ${(f)"$(command oscp __complete manualtopics-desc)"} ); _describe -t topics 'topic' _c
      else _oscp_endhint; fi
      ;;
    hacktools|ht)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists all payload categories'
        _c=( ${(f)"$(command oscp __complete hacktoolscats)"} )
        _oscp_rank categories revshell 3 listener 2 msfvenom 1
        _describe -t categories 'category' _c
      else
        case "${words[3]}" in
          encode|decode|hash|obfuscate)
            _message -r "· <text> to ${words[3]} — the shell mangles ; ( ) \" ', so quote, redirect, or paste:"
            _message -r "  quote:  oscp hacktools ${words[3]} 'python -c \"import pty;pty.spawn('\''/bin/bash'\'')\"'"
            _message -r "  file:   oscp hacktools ${words[3]} < payload.txt"
            _message -r "  paste:  oscp hacktools ${words[3]}      (then paste text and press Ctrl-D)"
            ;;
          *) _message -r '· fill LHOST / LPORT / FILE for this category' ;;
        esac
      fi
      ;;
    atlas)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists all commands'
        local -a asub
        asub=( "list:${_oscp_s2}  list every command" "search:${_oscp_s3}  search commands and use-cases" )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:atlassub" list-colors '=search=38;5;132' '=list=38;5;185' '=map=01;35'
        fi
        _describe -t atlassub 'action' asub
        _c=( ${(f)"$(command oscp __complete atlasnames-desc)"} ); _describe -t commands 'command' _c
      else _oscp_endhint; fi
      ;;
    notes)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists all sections'
        local -a nsub
        nsub=(
          "list:${_oscp_s1}  list cheat-sheet sections  ·  e.g. oscp notes"
          "show:${_oscp_s3}  print a section  ·  e.g. oscp notes show post-exploitation"
          "search:${_oscp_s2}  search section titles and bodies  ·  e.g. oscp notes search kerberos"
        )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:notesub" list-colors '=show=38;5;132' '=search=38;5;185' '=list=38;5;179' '=map=01;35'
        fi
        _describe -t notesub 'notes command' nsub
      elif (( CURRENT == 4 )) && [[ $words[3] == show ]]; then
        _c=( ${(f)"$(command oscp __complete notesids-desc)"} ); _describe -t sections 'section (required)' _c
      else _oscp_endhint; fi
      ;;
    migrate)
      if (( CURRENT == 3 )); then
        _message -r '· press ↵ to write a default bundle to the Desktop — or name an output .zip'
        local -a ma; ma=( 'export:write the portable bundle' ); _describe -t migrate 'action' ma
        _files -g '*.zip'
      else _oscp_endhint; fi
      ;;
    help)
      (( CURRENT == 3 )) && { _c=( ${(f)"$(command oscp __complete commands)"} ); _describe -t topics 'help topic' _c }
      ;;
    bm|ref|reference|bookmark)
      if (( CURRENT == 3 )); then
        _oscp_runhint 'lists your bookmarks'
        local -a bsub
        bsub=(
          "list:${_oscp_s3}  show bookmarks as a tree  ·  e.g. oscp bm list offsec"
          "open:${_oscp_s2}  open a bookmark in the browser  ·  e.g. oscp bm open 18"
          'add:save a new bookmark  ·  e.g. oscp bm add URL --rate excellent'
          'rm:forget a bookmark  ·  e.g. oscp bm rm 9'
          'rate:re-rate a bookmark  ·  e.g. oscp bm rate 18 excellent'
          "find:${_oscp_s1}  search your bookmarks  ·  e.g. oscp bm find youtube"
          'import:import a ti ref export or link list  ·  e.g. oscp bm import refs.json'
        )
        if [[ -z ${NO_COLOR:-} ]]; then
          zstyle ":completion:${curcontext}:bmsub" list-colors '=list=38;5;132' '=open=38;5;185' '=find=38;5;179' '=map=01;35'
        fi
        _describe -t bmsub 'bookmark command' bsub
      else
        case $words[3] in
          open|rm|rate)
            if (( CURRENT == 4 )); then _c=( ${(f)"$(command oscp __complete bmids-desc)"} ); _describe -t bookmarks 'bookmark' _c
            else _oscp_endhint; fi ;;
          list)
            if (( CURRENT == 4 )); then _message -r '· press ↵ to list all — or narrow to a group'; _c=( ${(f)"$(command oscp __complete groups-desc)"} ); _describe -t groups 'group (optional)' _c
            else _oscp_endhint; fi ;;
          add)          local -a _f; _f=( '--group:file it under a group' '--rate:good | very good | excellent' '--name:override the saved name' '--note:a line of context' ); _describe -t flags 'option' _f ;;
          import)       _files ;;
          *)            _oscp_endhint ;;
        esac
      fi
      ;;
  esac
}
compdef _oscp oscp

# Some tools (e.g. TACU/ticu) rebind Tab to their own ZLE widget, which only
# knows their command and falls back to file completion for everything else.
# Chain it: on an `oscp ...` line run standard completion (-> _oscp); otherwise
# hand off to whatever owned Tab before us, so their ghost/Tab keeps working.
() {
  local _p="${$(bindkey '^I')##* }"
  if [[ "$_p" != _oscp_tab && "$_p" != expand-or-complete && "$_p" != complete-word ]]; then
    typeset -g _OSCP_PREV_TAB="$_p"
  fi
}
_oscp_tab() {
  # A bare `oscp technique show` is hundreds of ids. Page them with the same keys
  # as every other oscp page. A typed prefix (`oscp technique show sqli`) still
  # uses normal Tab, so it filters instead of paging.
  local buf="${${BUFFER%%[[:space:]]##}##[[:space:]]#}"
  if [[ "$buf" == "oscp technique show" || "$buf" == "oscp tech show" || "$buf" == "oscp tec show" || "$buf" == "oscp teq show" ]]; then
    zle -I
    command oscp __page techniqueids-desc
    zle reset-prompt
    return
  fi
  if [[ "$BUFFER" == oscp || "$BUFFER" == oscp\ * ]]; then
    zle expand-or-complete
  elif [[ -n "$_OSCP_PREV_TAB" && "$_OSCP_PREV_TAB" != undefined-key ]]; then
    zle "$_OSCP_PREV_TAB"
  else
    zle expand-or-complete
  fi
}
zle -N _oscp_tab 2>/dev/null
bindkey '^I' _oscp_tab 2>/dev/null
bindkey -M emacs '^I' _oscp_tab 2>/dev/null
bindkey -M viins '^I' _oscp_tab 2>/dev/null
'''

_BASH_INIT = r'''# oscp shell integration (completion). Add to ~/.bashrc:  eval "$(oscp shell-init bash)"
_oscp_complete() {
  local cur prev words cword
  _init_completion 2>/dev/null || { cur="${COMP_WORDS[COMP_CWORD]}"; cword=$COMP_CWORD; words=("${COMP_WORDS[@]}"); }
  local cmds="howto help alias technique tech tec teq atlas cmd tmux shell-script hacktools gtfo search bm ref list show copy methods manual notes"
  if (( cword == 1 )); then COMPREPLY=($(compgen -W "$cmds" -- "$cur")); return; fi
  case "${words[1]}" in
    show)  (( cword == 2 )) && COMPREPLY=($(compgen -W "$(oscp __complete categories)" -- "$cur")) ;;
    cmd)   if (( cword == 2 )); then COMPREPLY=($(compgen -W "$(oscp __complete categories)" -- "$cur"));
           elif (( cword == 3 )) && [[ ${words[2]} == web ]]; then COMPREPLY=($(compgen -W "basic php wp wordpress tomcat jenkins iis joomla drupal git" -- "$cur")); fi ;;
    copy)  if (( cword == 2 )); then COMPREPLY=($(compgen -W "$(oscp __complete categories)" -- "$cur"));
           elif (( cword == 3 )); then COMPREPLY=($(compgen -W "$(oscp __complete copynums ${words[2]})" -- "$cur")); fi ;;
    help)  (( cword == 2 )) && COMPREPLY=($(compgen -W "$cmds" -- "$cur")) ;;
    search) (( cword == 2 )) && COMPREPLY=($(compgen -W "cheat-sheet methods manual atlas gtfo notes bash" -- "$cur")) ;;
    shell-script|shellscript|bash-script)
      (( cword == 2 )) && COMPREPLY=($(compgen -W "$(oscp __complete shellscriptsecs-desc | cut -d: -f1)" -- "$cur")) ;;
    bm|ref|reference|bookmark)
      if (( cword == 2 )); then COMPREPLY=($(compgen -W "list open add rm rate find import" -- "$cur"));
      else case "${words[2]}" in
        open|rm|rate) COMPREPLY=($(compgen -W "$(oscp __complete bmids)" -- "$cur")) ;;
        list)         COMPREPLY=($(compgen -W "$(oscp __complete groups)" -- "$cur")) ;;
      esac; fi ;;
  esac
}
complete -F _oscp_complete oscp
'''


def do_shell_init(rest):
    shell = (rest[0] if rest else "zsh").lower()
    if shell in ("bash",):
        sys.stdout.write(_BASH_INIT)
    else:
        sys.stdout.write(_ZSH_INIT)


# ------------------------------------------------------------------ parser ----
def build_parser():
    p = argparse.ArgumentParser(prog="oscp", add_help=False)
    sub = p.add_subparsers(dest="command")

    sub.add_parser("list", add_help=False).set_defaults(func=cmd_list)

    sp_show = sub.add_parser("show", add_help=False)
    sp_show.add_argument("category")
    sp_show.set_defaults(func=cmd_show)

    sp_search = sub.add_parser("search", add_help=False)
    sp_search.add_argument("term", nargs="+")
    sp_search.set_defaults(func=cmd_search)

    sp_copy = sub.add_parser("copy", add_help=False)
    sp_copy.add_argument("category")
    sp_copy.add_argument("number", type=int)
    sp_copy.set_defaults(func=cmd_copy)

    sp_gtfo = sub.add_parser("gtfo", add_help=False)
    sp_gtfo.add_argument("binary", nargs="?")
    sp_gtfo.add_argument("filter", nargs="?")
    sp_gtfo.set_defaults(func=cmd_gtfo)

    notes = sub.add_parser("notes", add_help=False)
    notes.set_defaults(func=cmd_notes, notes_command=None)
    nsub = notes.add_subparsers(dest="notes_command")
    nsub.add_parser("list", add_help=False).set_defaults(func=cmd_notes)
    n_show = nsub.add_parser("show", add_help=False)
    n_show.add_argument("section")
    n_show.set_defaults(func=cmd_notes)
    n_search = nsub.add_parser("search", add_help=False)
    n_search.add_argument("term")
    n_search.set_defaults(func=cmd_notes)

    sp_howto = sub.add_parser("howto", add_help=False)
    sp_howto.add_argument("phase", nargs="?")
    sp_howto.set_defaults(func=cmd_howto)

    sp_lab = sub.add_parser("lab-setup", add_help=False)
    sp_lab.add_argument("section", nargs="?")
    sp_lab.set_defaults(func=cmd_lab_setup)

    sp_tmux = sub.add_parser("tmux", add_help=False)
    sp_tmux.add_argument("section", nargs="?")
    sp_tmux.set_defaults(func=cmd_tmux)

    sp_sh = sub.add_parser("shell-script", aliases=["shellscript", "bash-script"], add_help=False)
    sp_sh.add_argument("section", nargs="?")
    sp_sh.set_defaults(func=cmd_shell_script)

    methods = sub.add_parser("methods", add_help=False)
    methods.set_defaults(func=cmd_methods, methods_command=None, topic=None)
    msub = methods.add_subparsers(dest="methods_command")
    m_list = msub.add_parser("list", add_help=False)
    m_list.add_argument("topic", nargs="?")
    m_list.set_defaults(func=cmd_methods)
    m_show = msub.add_parser("show", add_help=False)
    m_show.add_argument("method")
    m_show.set_defaults(func=cmd_methods)
    m_search = msub.add_parser("search", add_help=False)
    m_search.add_argument("term")
    m_search.set_defaults(func=cmd_methods)

    sp_manual = sub.add_parser("manual", add_help=False)
    sp_manual.add_argument("manual_arg", nargs="?")
    sp_manual.add_argument("manual_arg2", nargs="?")
    sp_manual.set_defaults(func=cmd_manual)

    sub.add_parser("alias", add_help=False).set_defaults(func=cmd_alias)

    sp_tech = sub.add_parser("technique", aliases=["tech", "tec", "teq"], add_help=False)
    sp_tech.add_argument("technique_arg", nargs="?")
    sp_tech.add_argument("technique_arg2", nargs="?")
    sp_tech.set_defaults(func=cmd_technique)

    sp_cmd = sub.add_parser("cmd", add_help=False)
    sp_cmd.add_argument("cmd_arg", nargs="*")
    sp_cmd.set_defaults(func=cmd_commands)

    sp_atlas = sub.add_parser("atlas", add_help=False)
    sp_atlas.add_argument("atlas_arg", nargs="?")
    sp_atlas.add_argument("atlas_arg2", nargs="?")
    sp_atlas.set_defaults(func=cmd_atlas)

    sp_ht = sub.add_parser("hacktools", aliases=["ht"], add_help=False)
    sp_ht.add_argument("ht_cat", nargs="?")
    sp_ht.add_argument("ht_rest", nargs=argparse.REMAINDER)
    sp_ht.set_defaults(func=cmd_hacktools)

    sub.add_parser("setup", aliases=["install"], add_help=False).set_defaults(func=cmd_setup)

    sp_mig = sub.add_parser("migrate", add_help=False)
    sp_mig.add_argument("migrate_arg", nargs="?")
    sp_mig.add_argument("outfile", nargs="?")
    sp_mig.set_defaults(func=cmd_migrate)

    bm = sub.add_parser("bm", aliases=["ref", "reference", "bookmark"], add_help=False)
    bm.set_defaults(func=cmd_bm_root, group=None)
    bmsub = bm.add_subparsers(dest="bm_command")

    b_list = bmsub.add_parser("list", add_help=False)
    b_list.add_argument("group", nargs="?")
    b_list.set_defaults(func=cmd_bm_list)

    b_open = bmsub.add_parser("open", add_help=False)
    b_open.add_argument("number", type=int)
    b_open.add_argument("--browser")
    b_open.set_defaults(func=cmd_bm_open)

    b_find = bmsub.add_parser("find", add_help=False)
    b_find.add_argument("term")
    b_find.set_defaults(func=cmd_bm_find)

    b_add = bmsub.add_parser("add", add_help=False)
    b_add.add_argument("url")
    b_add.add_argument("--group")
    b_add.add_argument("--rate")
    b_add.add_argument("--name")
    b_add.add_argument("--note")
    b_add.set_defaults(func=cmd_bm_add)

    b_rate = bmsub.add_parser("rate", add_help=False)
    b_rate.add_argument("number", type=int)
    b_rate.add_argument("rating")
    b_rate.set_defaults(func=cmd_bm_rate)

    b_rm = bmsub.add_parser("rm", add_help=False)
    b_rm.add_argument("number", type=int)
    b_rm.set_defaults(func=cmd_bm_rm)

    b_import = bmsub.add_parser("import", add_help=False)
    b_import.add_argument("file")
    b_import.add_argument("--group")
    b_import.set_defaults(func=cmd_bm_import)

    return p


HELP_TOKENS = {"help", "-h", "--help"}
TOP_NAMES = {"list", "show", "copy", "search", "bm", "ref", "reference", "bookmark"}


def do_page(rest):
    """Page one completion catalog. Enter = line, Space = page, q = back.

    Used when Tab would otherwise dump hundreds of technique ids at once.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        do_complete(rest)
    width = body_width()
    room = max(24, width - 40)
    lines = []
    for raw in buf.getvalue().splitlines():
        if ":" not in raw:
            continue
        name, desc = raw.split(":", 1)
        lines.append(f"  {name:<36}  {desc[:room]}")
    if not lines:
        return
    page_output(f"{len(lines)} matches. Type a few letters and Tab again to narrow.\n"
                + "\n".join(lines) + "\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    width = body_width()

    if argv and argv[0] == "__complete":
        do_complete(argv[1:])
        return

    if argv and argv[0] == "__page":
        do_page(argv[1:])
        return

    if argv and argv[0] == "shell-init":
        do_shell_init(argv[1:])
        return

    # help / --help, at any level, both spellings
    if not argv or any(t in HELP_TOKENS for t in argv):
        topic = None
        for t in argv:
            if t in HELP_TOKENS:
                continue
            topic = t
            break
        page_output(render_help(topic, width))
        return

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        page_output(render_help(None, width))
        return
    # browse commands get the number-a-line + copy picker; actions just page
    pickable = {cmd_list, cmd_show, cmd_commands, cmd_search, cmd_gtfo, cmd_notes, cmd_methods,
                cmd_howto, cmd_lab_setup, cmd_tmux, cmd_shell_script, cmd_manual, cmd_technique, cmd_atlas, cmd_hacktools,
                cmd_bm_list, cmd_bm_find, cmd_bm_root}
    # encode/decode/hash/obfuscate may read stdin (pipe or paste) and auto-copy —
    # run them directly so the picker doesn't capture output or fight for stdin.
    if args.func is cmd_hacktools and getattr(args, "ht_cat", None) in ("encode", "decode", "hash", "obfuscate"):
        cmd_hacktools(load_data(), args)
        return
    if args.func is cmd_howto and str(getattr(args, "phase", "") or "").lower() == "page":
        cmd_howto(None, args)
        return
    runner = run_pickable if args.func in pickable else run_paged
    runner(args.func, load_data(), args)


if __name__ == "__main__":
    main()
