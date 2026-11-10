# labenv.zsh — persistent OSCP/HTB lab variables across zsh tabs, with /etc/hosts sync.
# Install:  echo 'source ~/oscp/scripts/labenv.zsh' >> ~/.zshrc   (then open a new tab)
# Usage:    setip 10.10.10.25 ; domain dc01.lab.local ; user admin ; password 'LabOnly!'
#           labinfo | labreload | labclear
#
# SECURITY: ~/.labenv holds creds in PLAINTEXT. Use AUTHORISED lab creds only, never real
# or reused passwords. The file is created mode 600; labinfo masks passwords on screen.
# This is a hardened rewrite: safe value-quoting, correct stale-/etc/hosts removal, no
# broad sudoers changes (you'll be prompted for your password on the hosts write).

LAB_ENV_FILE="${LAB_ENV_FILE:-$HOME/.labenv}"

# Load saved values when the shell starts.
[[ -f "$LAB_ENV_FILE" ]] && source "$LAB_ENV_FILE"

# --- persistence -----------------------------------------------------------
_lab_last_mtime=0
[[ -f "$LAB_ENV_FILE" ]] && _lab_last_mtime=$(stat -c %Y "$LAB_ENV_FILE" 2>/dev/null || echo 0)

# Re-source the file before each prompt if another tab changed it.
_check_labenv() {
    [[ -f "$LAB_ENV_FILE" ]] || return
    local m; m=$(stat -c %Y "$LAB_ENV_FILE" 2>/dev/null || echo 0)
    if [[ "$m" -gt "$_lab_last_mtime" ]]; then
        source "$LAB_ENV_FILE"
        _lab_last_mtime=$m
        print -r -- $'\n[lab] variables reloaded from another tab'
    fi
}
autoload -Uz add-zsh-hook
add-zsh-hook precmd _check_labenv

# Persist one variable to $LAB_ENV_FILE, safely single-quoting the value so a quote or
# shell metacharacter in it can never break or execute when the file is sourced.
_save_var() {
    local key="$1" value="$2"
    if [[ ! -f "$LAB_ENV_FILE" ]]; then : > "$LAB_ENV_FILE"; chmod 600 "$LAB_ENV_FILE"; fi
    sed -i "/^export ${key}=/d" "$LAB_ENV_FILE" 2>/dev/null
    local esc=${value//\'/\'\\\'\'}          # ' -> '\''
    printf "export %s='%s'\n" "$key" "$esc" >> "$LAB_ENV_FILE"
    chmod 600 "$LAB_ENV_FILE"
}

# --- /etc/hosts sync -------------------------------------------------------
# Map $ip -> $domain, removing any previous line for this domain AND the old domain
# (fixes the classic bug where switching domains left a stale mapping). Uses fixed-string
# matching (grep -wF) so a domain with regex metacharacters can't misbehave.
_update_hosts() {
    [[ -n "$ip" && -n "$domain" ]] || return
    local tmp; tmp=$(mktemp) || return
    cp /etc/hosts "$tmp" 2>/dev/null
    grep -vwF "$domain" "$tmp" > "$tmp.1" 2>/dev/null; mv "$tmp.1" "$tmp"
    if [[ -n "$_lab_prev_domain" && "$_lab_prev_domain" != "$domain" ]]; then
        grep -vwF "$_lab_prev_domain" "$tmp" > "$tmp.1" 2>/dev/null; mv "$tmp.1" "$tmp"
    fi
    printf '%s\t%s\n' "$ip" "$domain" >> "$tmp"
    if sudo cp "$tmp" /etc/hosts; then
        print -r -- "[+] /etc/hosts -> $ip  $domain"
        export _lab_prev_domain="$domain"; _save_var _lab_prev_domain "$domain"
    fi
    rm -f "$tmp" "$tmp.1" 2>/dev/null
}

# --- setters ---------------------------------------------------------------
setip()     { [[ -z "$1" ]] && { echo "usage: setip <IP>"; return 1; };     export ip="$1";       _save_var ip "$1";       echo "ip → $ip";             _update_hosts; }
domain()    { [[ -z "$1" ]] && { echo "usage: domain <domain>"; return 1; }; export domain="$1";   _save_var domain "$1";   echo "domain → $domain";     _update_hosts; }
user()      { [[ -z "$1" ]] && { echo "usage: user <name>"; return 1; };     export user="$1";     _save_var user "$1";     echo "user → $user"; }
password()  { [[ -z "$1" ]] && { echo "usage: password <pw>"; return 1; };   export password="$1"; _save_var password "$1"; echo "password set (hidden)"; }
dc()        { [[ -z "$1" ]] && { echo "usage: dc <host>"; return 1; };       export dc="$1";       _save_var dc "$1";       echo "dc → $dc"; }
user2()     { export user2="$1";     _save_var user2 "$1";     echo "user2 → $user2"; }
password2() { export password2="$1"; _save_var password2 "$1"; echo "password2 set (hidden)"; }
user3()     { export user3="$1";     _save_var user3 "$1";     echo "user3 → $user3"; }
password3() { export password3="$1"; _save_var password3 "$1"; echo "password3 set (hidden)"; }

# --- info / reload / clear -------------------------------------------------
_lab_mask() { [[ -z "$1" ]] && { printf '(unset)'; return; }; local n=${#1}; (( n <= 2 )) && printf '**' || printf '%s***%s' "${1[1]}" "${1[-1]}"; }
labinfo() {
    print -r -- "ip        → ${ip:-(unset)}"
    print -r -- "domain    → ${domain:-(unset)}"
    print -r -- "dc        → ${dc:-(unset)}"
    print -r -- "user      → ${user:-(unset)}"
    print -r -- "password  → $(_lab_mask "$password")"
    print -r -- "user2     → ${user2:-(unset)}"
    print -r -- "password2 → $(_lab_mask "$password2")"
    print -r -- "user3     → ${user3:-(unset)}"
    print -r -- "password3 → $(_lab_mask "$password3")"
    print -r -- "(run 'echo \$password' to see a value in full)"
}
labreload() { [[ -f "$LAB_ENV_FILE" ]] && source "$LAB_ENV_FILE"; echo "[+] lab variables reloaded"; }
labclear()  {
    unset ip domain user password dc user2 password2 user3 password3 _lab_prev_domain
    rm -f "$LAB_ENV_FILE"
    echo "[+] lab variables cleared (note: /etc/hosts entries are NOT removed — review 'tail /etc/hosts')"
}
