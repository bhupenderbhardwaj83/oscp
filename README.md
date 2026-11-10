# OSCP CLI Cheat-Sheet & Reference Hub

An offline command-line reference for OSCP exam preparation: a hand-curated
cheat-sheet, the full GTFOBins technique database, the 0xsyr0 OSCP cheat sheet,
and your own reference bookmarks — all searchable from the terminal, with
progressive help, paged output, and zsh tab-completion.

The tutorial is [howto.html](https://bhupenderbhardwaj83.github.io/oscp/howto.html).
`oscp howto page` opens the same file on this machine. GitHub Pages publishes
it from the `main` branch, and the site root opens that page.

> **Scope:** Educational use only. Run the commands here solely against systems
> you own or are explicitly authorized to test — your own labs, PWK/OSCP lab
> machines, and the exam environment. Replace the `TARGET` / `LHOST` / `LPORT` /
> `USER` placeholders with your own values before running anything.

## Requirements

- Python 3.8+ (standard library only — no `pip install` needed to run)

## Install

```bash
ln -sf "$(pwd)/oscp" ~/.local/bin/oscp     # put `oscp` on your PATH
```

Enable tab-completion (zsh) by adding one line to `~/.zshrc`, then reloading:

```bash
echo 'eval "$(command oscp shell-init zsh)"' >> ~/.zshrc && exec zsh
```

Now `oscp <Tab>`, `oscp show <Tab>`, `oscp gtfo <Tab>`, `oscp notes show <Tab>`
all complete. Bash is supported too: `eval "$(oscp shell-init bash)"`.

## Commands

```bash
oscp                      # the eight questions, in order
oscp help [command]       # how one command works

# the order you reach for them
oscp howto                # where you are in the exam (recon -> report)
oscp howto page           # this tutorial, in the default browser
oscp tmux                 # tmux keys and logging; default prefix is Ctrl-b, Ctrl-a is a custom example
oscp tmux logging         # live log rules (~/tmux_live.log)
oscp help technique       # how a command works
oscp technique            # three shelves: path, topics, notes
oscp technique path       # the exam in order
oscp technique windows    # one area
oscp technique show kerberos-flow
oscp technique notes post-exploitation
oscp atlas ffuf           # one tool in depth
oscp cmd privesc-linux    # the short numbered commands; a line number copies
oscp hacktools revshell 10.10.14.5 4444
oscp gtfo tar sudo
oscp search wireless      # when you do not know which command
oscp search atlas passwd  # the same search, only in one shelf

# older names still run: methods, manual, notes, list, show, copy

# your reference bookmarks  (alias: ref)
oscp bm list [group]
oscp bm open 18 [--browser safari]
oscp bm add https://gtfobins.org --group offsec --rate excellent
oscp bm import refs.json  # import a `ti ref export`, or a plain list of links

# install / move
oscp setup                # install/upgrade here: venv + PATH launcher + completion
oscp migrate              # package code+data into a portable tarball
```

## Move to another computer

On the current machine:

```bash
oscp migrate              # writes a .zip to your Desktop (code + data, no venv/videos)
```

On the new machine:

```bash
unzip oscp-migrate-*.zip
cd oscp && ./oscp setup   # creates its own venv, links oscp onto PATH, adds completion
exec $SHELL               # activate tab-completion
```

`oscp setup` is idempotent — safe to re-run to repair the install or upgrade.

## Copy a command straight from the output

Browse commands (`show`, `search`, `gtfo`, `notes`, `bm list/find`) number every
line. At the prompt:

- `N` or `N-M` — copy that line / range (indent and `$ ` prompt stripped), ready to paste.
- `o N` — open the link on line N in the browser (for the latest upstream content).
- `c` while paging — copy/open without reaching the end; Enter skips.

Set `OSCP_NO_PICK=1` to turn the prompt off. Notes render locally — markdown
tables are shown as aligned `Name   URL` (no pipes), so you read and copy
everything offline and only open a URL when you want the newest version.

> Note on data: `show`/`search` read the hand-curated `cheatsheet.json`
> (concise, ~103 entries). The **full 0xsyr0 cheat sheet** is under `oscp notes`
> (37 sections, ~complete import of the upstream README). GTFOBins is `oscp gtfo`.

```
$ oscp gtfo tar
 …
18    shell
19      $ tar cf /dev/null /dev/null --checkpoint=1 --checkpoint-action=exec=/bin/sh
 …
copy line(s) [N or N-M; Enter to skip]: 19
copied line 19 to clipboard (pbcopy)
```

Help has four-part cards (syntax / example / description), works at every depth,
and both `oscp help X` and `oscp X --help` are equivalent. Long output is paged
from the top — **Enter** = line, **Space/Tab** = page, **q** = quit. Set
`NO_COLOR=1` to disable colour (and the pager) when piping to a file.

## Data

All content lives under [`data/`](data/) and the CLI reads it at runtime:

- `cheatsheet.json` — the hand-written categories and your bookmarks (editable).
- `gtfobins.json` — generated from [GTFOBins](https://gtfobins.github.io/)
  (GPL-3.0). Reproduced for offline study; verify against the source.
- `notes.json` — generated from [0xsyr0/OSCP](https://github.com/0xsyr0/OSCP).

### Adding your own cheat-sheet commands

Add an entry to any category's `entries` list in `cheatsheet.json`:

```json
{ "title": "Short name", "cmd": "the command with PLACEHOLDERS",
  "desc": "what it does / when to use it", "notes": "gotchas, alternatives" }
```

The `tags` on a category are included in search, so tag generously. No code
changes are required — the CLI reads the JSON at runtime.

### Adding your own methods (methodology)

`data/methods.json` holds the `oscp methods` library. Add an entry to `methods`:

```json
{
  "id": "short-kebab-id",
  "topic": "privesc-linux",
  "title": "Human title",
  "brief": "One line shown in listings and search",
  "tags": ["privesc", "suid", "..."],
  "body": "Markdown. ## headings, | tables |, and\n    indented or ```fenced``` commands.\nExplain the WHY, not just the command."
}
```

`topic` should match one of the `topics` ids (add a new topic object to grow the
stages). The `body` renders with headings, aligned tables, highlighted code, and
inline `code`/**bold**/*emphasis* — and every line is copyable, links openable.

`data/manual.json` has the same shape (`topics` + `entries`) for `oscp manual`.

### Adding your own atlas commands

`data/atlas.json` → `commands` holds the `oscp atlas` reference. Each command:

```json
{
  "name": "awk",
  "syntax": "awk [OPTION]... PROGRAM [FILE...]",
  "description": "First sentence shows in the list; full text in the entry.",
  "tags": ["text"],
  "anatomy": [["Label", "what this part does"]],
  "origins": {"creators": "...", "when": "...", "where": "...", "why": "..."},
  "usecases": [["Title", "the command", "what it does", "a note"]]
}
```

These libraries ship with a starter set and grow over time — add entries in the JSON,
no code changes, and tab-completion picks up the new ids/names automatically.

## Files

- `oscp.py` — the CLI (argparse-based, stdlib only)
- `oscp` — shell wrapper (resolves symlinks, so it works from `~/.local/bin`)
- `completions/_oscp` — standalone zsh completion (alternative to `shell-init`)
- `data/*.json` — the knowledge base
