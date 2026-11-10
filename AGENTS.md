# AGENTS.md — handoff guide for the `oscp` CLI

You are picking up work on **`oscp`**, an offline, stdlib-only Python CLI reference for
OSCP / OSWE / HTB / PG / CTF preparation. This document is written for an AI coding agent
(as capable as the one that built it) so you can continue without re-deriving the design.
It is operational detail, not marketing — the user-facing overview lives in `README.md`.

Everything here is for **authorized** security testing, labs, and exams only.

---

## 1. What this project is

A single-file Python 3 CLI (`oscp.py`, ~2.5k lines, **stdlib only** — argparse, json,
subprocess, termios/tty; no pip deps) that renders curated offensive-security reference
content held in `data/*.json`. It has zsh tab-completion, a pager, and a
"pick a line from the output to copy / open its URL" picker.

Design philosophy the user cares about most: **"WHEN YOU WANT TO… → command"** — the tool
must be *super predictable and intuitive*. Every not-found error should route the user
forward (to `oscp search` or a list), and `oscp search` is a universal cross-store find.
`oscp search <shelf> <term>` limits that find to one shelf: cheat-sheet, methods, manual, atlas, gtfo, or notes.
`oscp cmd web` is the enumeration page (`web basic` is the same page). `oscp cmd web <page>` opens php, wp, tomcat, jenkins, iis, joomla, drupal, or git. Tab on `oscp cmd` names those pages on the `web` row; Tab again after `web` lists them. `oscp cmd ssh` is its own category. Those web pages are hidden from the top-level category list.
`oscp tech`, `oscp tec`, and `oscp teq` are aliases of `oscp technique`. `oscp alias` lists every other name that still works. Tab on a decision menu marks only its three most-used next steps: ★★★ sober magenta, ★★ sober yellow, ★ soft amber. The long catalogs (every technique id, every atlas tool) are not ranked. `oscp technique show` with nothing typed pages that catalog: Enter one line, Space one page, q back. A few letters and Tab still filters it.

---

## 2. Layout

```
oscp.py                 # the whole CLI (data-driven; reads data/*.json at runtime)
data/*.json             # all content (see schemas below)
completions/_oscp       # generated zsh completion (regenerate when command STRUCTURE changes)
scripts/labenv.zsh      # shipped helper (lab env vars); referenced by `oscp lab-setup labenv`
README.md               # user-facing overview
howto.html              # tutorial; `oscp howto page` opens it in the default browser
AGENTS.md               # this file
lab resource/           # source docs (e.g. the Kali/VMware guide behind `oscp lab-setup`)
```

Key constants in `oscp.py`: `_DATA_DIR` and `<STORE>_FILE` (ATLAS_FILE, MANUAL_FILE,
HOWTO_FILE, LABSETUP_FILE, METHODS_FILE, …). Command resolution for atlas honours
`_ATLAS_ALIASES` and `find_atlas()` is **case-insensitive**. Lab-setup sections honour
`_LABSETUP_ALIASES`.

---

## 3. Data stores (top-level keys)

| File | Keys | `oscp` command |
|---|---|---|
| `atlas.json` | meta, commands | `oscp atlas <tool>` — per-tool syntax/anatomy/origins/use-cases |
| `manual.json` | meta, topics, entries | `oscp technique show <id>` — one write-up (hubs live here) |
| `methods.json` | meta, topics, methods | `oscp technique path` — the exam in order. `oscp methods` still runs |
| `cheatsheet.json` | meta, categories, bookmarks | `oscp cmd <category>`, `oscp bm`. `list` / `show` / `copy` still run |
| `howto.json` | meta, toolmap, phases | `oscp howto [phase]`, `oscp howto map`, `oscp howto page` |
| `labsetup.json` | meta, sections | `oscp lab-setup [section]` |
| `tmux.json` | meta, sections | `oscp tmux [section]` — this machine's prefix, keys, command mode, logging |
| `hacktools.json` | meta, categories | `oscp hacktools …` (payload gen; encode/decode/hash/obfuscate read stdin) |
| `gtfobins.json` | meta, binaries | `oscp gtfo <bin>` |
| `notes.json` | meta, sections | `oscp technique notes` — the 0xsyr0 sheet. `oscp notes` still runs |

### atlas command schema
```json
{
  "name": "ffuf",
  "syntax": "ffuf -u URL/FUZZ -w WORDLIST",
  "description": "one or two sentences …",
  "tags": ["web","fuzzing"],
  "anatomy": [["label","explanation"], ...],
  "origins": {"creators":"…","when":"…","where":"…","why":"…"},
  "docs": "https://…",                         // one URL, rendered as 'Docs', openable via `o N`
  "usecases": [ ["title","command","desc","note"], ... ]   // 4-tuples; command is copyable/openable
}
```

### manual entry schema
```json
{ "id":"kebab-id", "topic":"web", "title":"…", "brief":"…", "tags":[...], "body":"## md-ish\n…" }
```
`topic` must be one of the existing 20 (filesystem, files, text, permissions, processes,
storage, networking, packages, shell, services, kali, web, windows, creds, exploitation,
workflow, protocols, misc, cloud, wireless).

---

## 4. The renderer and its TWO hard rules

The manual body is a lightweight markdown-ish format: `## headings`, prose, 4-space-indented
code blocks, and `| a | b |` tables (rendered as aligned columns). `**bold**` and `` `code` ``
inline work **only in normal prose lines**. There are two rules you MUST follow or content
renders wrong:

1. **A `**bold**` span must stay on ONE physical line.** A bold span split across two array
   lines renders the literal `**`.
2. **No `**bold**` inside a 4-space-indented block** (code/list). Indented lines are treated
   as preformatted, so `**` stays literal there. Put bold only in prose.

Both failure modes are caught by the per-batch check `grep -c '\*\*'` on rendered output
(expected: 0). `/**/` inside an SQL-comment example is an intended false positive — eyeball it.

---

## 5. How content is added (the "batch" workflow)

Content grows in numbered **batches**: ~8 manual entries + ~9 atlas tool entries each.
Builders are **one-off idempotent Python scripts** kept in the scratchpad (NOT committed),
run against `data/`:

- **Atlas**: upsert by `name`. If the tool exists, append only *non-duplicate* use-cases
  (dedupe by use-case title); else insert the full command dict.
- **Manual**: upsert by `id` (`dict.update(entry)` if present, else append).
- After writing, `json.dump(..., indent=2, ensure_ascii=False)` then append a trailing `\n`.

Builder skeleton (atlas):
```python
NEW = { "toolname": (syntax, desc, tags, anatomy, origins, docs, usecases), ... }
for name, spec in NEW.items():
    if name in by:  # append only new use-cases by title
        ...
    else:
        d["commands"].append({...})
```
Build bodies with `NL = "\n"; NL.join([ ... ])` so each bold stays on its own physical line.

### Picking topics for a batch
Scan for "free" (not-yet-covered) topics by diffing a candidate list against existing
`name`s / `id`s (see any `append_atlas*.py` / `append_manual*.py` for the pattern). Favour
**distinct, exam-relevant** topics; avoid near-duplicates of existing entries. The pool is
now thin (batch 51+) — quality over padding.

---

## 6. Tool-selection HUBS (high-value pattern)

The strongest feature added late: a **hub** answers "which tool when?" for a category.
Pattern = one manual hub entry (a decision matrix + minimal-toolkit + workflow + tie-breakers)
PLUS a cross-link use-case inserted at **index 0** ("Use Case 01") on every related atlas
tool, whose `command` is `oscp technique show <hub-id>` (copyable/openable). `oscp manual show` still opens the same page. Built hubs:

- `web-content-discovery` — fuzz vs crawl vs params vs proxy (12 web tools linked)
- `pivoting-tool-selection` — port-forward vs SOCKS vs full-tunnel (17 tools linked)
- `cracking-tool-selection` — offline hash vs online brute; hashcat vs john (26 tools linked)
- `privesc-tool-selection` — "what you found → which technique" Linux+Windows (15 enumerators linked)
- `reverse-shell-selection` — foothold by service/tech, web + non-web; generate→catch→stabilise (8 shell tools linked)

Discovery note: the manual search caps shown matches (18), so the newest hub can fall outside a
very common search term. New hubs are reliably reached via a specific term and via the atlas
Use Case 01 cross-links. If a new hub should rank for a broad term, keep that word in the brief.

To add another hub, copy `scripts`-style `*_hub.py` logic: write the hub entry, then
`c["usecases"].insert(0, [title, "oscp technique show <hub-id>", desc, note])` for each core tool
(guard on the title to stay idempotent). Verify every `oscp manual show <id>` the matrix
points to actually exists.

---

## 7. Aliases

`_ATLAS_ALIASES` in `oscp.py` maps common names to canonical atlas entries, e.g.
`netcat→nc`, `netexec→nxc`, `ripgrep→rg`, `secretsdump→impacket-secretsdump`,
`ntlmrelayx→impacket-ntlmrelayx`, `miller→mlr`, `evilwinrm→evil-winrm`,
`nth→name-that-hash`. Add an alias instead of a duplicate entry when a tool has a
well-known alternate name. Do NOT alias a name that already has its own distinct entry
(e.g. `crackmapexec` has its own deprecated-pointer entry — leave it).

---

## 8. Safety / content boundaries (important)

A safety classifier reviews generated content. Keep everything **reference-level** — *what a
tool is and when to use it*, methodology, and standard named techniques/CVEs. It has blocked,
and you must AVOID:

- **Detection-evasion framing** — never describe a tool as "evade/bypass AV/EDR/detection".
  (A `nanodump` atlas desc with evasion wording was blocked mid-batch; it was dropped.)
- **Offensive C2 / phishing / evil-twin frameworks** (Empire, Sliver, Covenant, evilginx,
  SET, fluxion, …) — off-scope for OSCP and classifier-sensitive. Skip them.
- **Novel "become Domain Admin" self-escalation recipes** — standard documented AD
  techniques (Kerberoasting, DCSync, golden ticket, delegation) are fine at reference level
  (what/needs/tool/detect), not as step-by-step stealth-persistence guides.
- **Editing the user's `~/.zshrc` / sudoers yourself** — give the user the line to add;
  the classifier treats agent-written shell-rc persistence as unauthorized.

When something is blocked, drop it, substitute a safe equivalent, and tell the user plainly.

---

## 9. Verify EVERY change (run all of these)

```bash
cd ~/oscp
python3 -m py_compile oscp.py                                   # compiles
python3 -c "import json,os;[json.load(open('data/'+f)) for f in os.listdir('data') if f.endswith('.json')];print('json OK')"
# markdown leaks on new entries (expect 0 each):
OSCP_NO_PICK=1 python3 oscp.py manual show <id> | grep -c '\*\*'
OSCP_NO_PICK=1 python3 oscp.py atlas <tool>     | grep -c '\*\*'
# duplicates:
python3 -c "import json;from collections import Counter;m=json.load(open('data/manual.json'));print([k for k,v in Counter(e['id'] for e in m['entries']).items() if v>1])"
```
- `OSCP_NO_PICK=1` bypasses the interactive picker so output is capturable.
- Preferred interpreter if installed: `~/.local/share/oscp/venv/bin/python3` (falls back to `python3`).
- Regenerate completions **only when command STRUCTURE changes** (new subcommand/arg), not for
  data-only batches: `python3 oscp.py shell-init zsh > completions/_oscp` then `zsh -n completions/_oscp`.
- Never edit the user's `.zshrc`; they load completion via `eval "$(oscp shell-init zsh)"` themselves.

---

## 10. Current state (keep this and the memory file in sync)

As of the last session: **atlas = 454 commands / 5831 use-cases**, **manual = 425 entries**,
through **batch 51** plus 5 tool-selection hubs (web, pivoting, cracking, privesc, reverse-shell).
Thin tools were expanded with real exam commands only, including a later pass over the 15–19 band and the short exam tools in the middle (netsh, medusa, psql, cadaver, bettercap, and the same kind of gap). A tool stays under 20 when it does not have 20 distinct real invocations. `eaphammer` was left unchanged (evil-twin tool).
The authoritative running counts live in the user's memory file:
`~/.claude/projects/-Users-bhupenderbhardwaj-oscp/memory/oscp-content-progress.md`
(and `MEMORY.md` index beside it). Update it after every batch/hub.

Terminology note the user flagged: **"atlas commands" = tool entries** (~9/batch);
**"use-cases" = the examples inside each tool** (the original ~1,800 target was use-cases,
long since exceeded). Don't conflate them.

---

## 11. Typical next-step menu

- Another content batch (quality topics only — the pool is thin).
- Another selection hub if a category still lacks one (web/pivoting/cracking/privesc/reverse-shell done).
- A consolidation pass: dedupe/cross-link audit, verify every `docs` URL, fill small gaps.

Work in small, verified increments. Commit only if the user asks (and branch first if on the
default branch). Keep the tool predictable — that is the product.
