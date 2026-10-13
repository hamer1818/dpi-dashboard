#!/bin/bash
# DPI Dashboard setup helper for Linux. Runs as root.
#
# The app does not run this file from disk: it pipes the script into
#     pkexec /bin/bash -c 'script=$(cat) && exec /bin/bash -c "$script" ... </dev/null' ...
# so nothing a normal user can write is ever executed as root. For the same reason this
# helper downloads and verifies zapret itself, in a directory only root can write, and
# reports progress on stdout instead of writing to a file.
#
#   install   [--strategy S]... --hosts "a b" [--tries N] [--dns-dot]
#   tune      [--strategy S]... --hosts "a b" [--tries N] [--dns-dot]
#   uninstall
#
# install: downloads the latest bol-van/zapret release, checks the archive against the
#          SHA-256 published by GitHub and every program against upstream's sha256sum.txt,
#          installs it to /opt/zapret with a systemd unit, then runs tune.
# tune:    measures the blocking with zapret off, tries each strategy until one reaches
#          every test site, keeps the best and enables the service. If no strategy helps,
#          the previous config and service state are restored.
# Progress lines use the @@ protocol described in runner.py.
set -u
umask 022
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

ZDIR=/opt/zapret
UNIT=/etc/systemd/system/zapret.service
MARK=$ZDIR/.installed-by-dpi-dashboard
DOT_CONF=/etc/systemd/resolved.conf.d/dpi-dashboard-dot.conf
API=https://api.github.com/repos/bol-van/zapret/releases/latest
SAFE_STRATEGY='^--[A-Za-z0-9 =,._+:/-]+$'
SAFE_HOST='^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$'

log()  { printf '%s\n' "$*"; }
fail() { log "@@ERROR $*"; log "@@DONE fail"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

MODE=${1:-}
[ $# -ge 1 ] && shift
LIST=() HOSTS='discord.com' TRIES=3 DNSDOT=0
while [ $# -gt 0 ]; do
    case $1 in
        --strategy) LIST+=("${2:-}"); shift 2 ;;
        --hosts) HOSTS=${2:-}; shift 2 ;;
        --tries) TRIES=${2:-}; shift 2 ;;
        --dns-dot) DNSDOT=1; shift ;;
        *) fail "unknown option: $1" ;;
    esac
done

[ "$(id -u)" = 0 ] || fail "must run as root"
[[ $TRIES =~ ^[1-9][0-9]?$ ]] || fail "invalid --tries"
for h in $HOSTS; do [[ $h =~ $SAFE_HOST ]] || fail "invalid host"; done
NHOSTS=$(wc -w <<<"$HOSTS")
MAX=$((NHOSTS * TRIES))

WORK=$(mktemp -d /tmp/dpi-dashboard-root.XXXXXXXX) || fail "cannot create a work directory"
trap 'rm -rf "$WORK"' EXIT

# Commands below never read the terminal: stdin is /dev/null.
run() { "$@" </dev/null; }

install_pkgs() {
    log "@@STEP deps"
    log "installing: $*"
    if have pacman; then run pacman -S --needed --noconfirm "$@"
    elif have apt-get; then run apt-get update -q && DEBIAN_FRONTEND=noninteractive run apt-get install -y -q "$@"
    elif have dnf; then run dnf install -y "$@"
    elif have zypper; then run zypper --non-interactive install "$@"
    else return 1
    fi
}

ensure_prereqs() {
    [ -d /run/systemd/system ] || fail "systemd is required"
    have python3 || fail "python3 is required"
    have sha256sum || fail "sha256sum is required"
    have curl || install_pkgs curl || true
    have curl || fail "curl is required and could not be installed"
    have awk || install_pkgs gawk || true
    have awk || fail "awk is required and could not be installed"
    if ! have nft && ! have iptables; then install_pkgs nftables || true; fi
    have nft || have iptables || fail "nftables or iptables is required and could not be installed"
}

check_strategies() {
    [ ${#LIST[@]} -gt 0 ] || fail "no strategies"
    local s
    for s in "${LIST[@]}"; do [[ $s =~ $SAFE_STRATEGY ]] || fail "unsafe strategy"; done
}

# --- download and verification (all inside $WORK, which only root can write) ----------

fetch() {  # fetch URL FILE [header]
    local code
    code=$(curl -sSL --proto '=https' --tlsv1.2 --max-time 120 -o "$2" -w '%{http_code}' \
        -H 'User-Agent: dpi-dashboard' ${3:+-H "$3"} "$1") || return 1
    case $code in
        200) return 0 ;;
        403|429) fail "GitHub's request limit was reached for this network; try again in an hour" ;;
        *) return 1 ;;
    esac
}

# Prints "tag archive_url sha256 sums_url" for the Linux archive of a release JSON.
read_release() {
    python3 -I - "$1" <<'PY'
import json, re, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
tag = d["tag_name"]
if not re.fullmatch(r"v[0-9][0-9A-Za-z.\-]{0,30}", tag):
    sys.exit("unexpected tag")
a = {x["name"]: x for x in d.get("assets", [])}
arc, sums = a.get(f"zapret-{tag}.tar.gz"), a.get("sha256sum.txt")
if not arc or not sums:
    sys.exit("release has no Linux archive or sha256sum.txt")
digest = arc.get("digest") or ""
if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
    sys.exit("GitHub did not publish a checksum")
prefix = "https://github.com/bol-van/zapret/releases/download/"
for u in (arc["browser_download_url"], sums["browser_download_url"]):
    if not u.startswith(prefix):
        sys.exit("unexpected download URL")
print(tag, arc["browser_download_url"], digest[7:], sums["browser_download_url"])
PY
}

verify_digest() {  # FILE HEX
    [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$2" ]
}

# Refuse absolute paths, "..", and links or devices that point outside the archive.
check_archive() {
    python3 -I - "$1" <<'PY'
import posixpath, sys, tarfile
with tarfile.open(sys.argv[1]) as t:
    for m in t.getmembers():
        if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
            sys.exit(f"unexpected member type: {m.name}")
        names = [m.name]
        if m.issym():
            names.append(posixpath.join(posixpath.dirname(m.name), m.linkname))
        elif m.islnk():
            names.append(m.linkname)
        for n in names:
            p = posixpath.normpath(n)
            if n.startswith("/") or p == ".." or p.startswith("../"):
                sys.exit(f"unsafe path: {n}")
PY
}

download_release() {
    log "@@STEP download"
    local auth='' tag url hex sums
    [ -n "${GITHUB_TOKEN:-}" ] && auth="Authorization: Bearer $GITHUB_TOKEN"
    fetch "$API" "$WORK/release.json" "$auth" || fail "could not reach GitHub"
    local info
    info=$(read_release "$WORK/release.json" 2>&1) || fail "release information: $info"
    read -r tag url hex sums <<<"$info"
    log "release $tag: $url"
    fetch "$url" "$WORK/zapret.tar.gz" || fail "download failed"
    fetch "$sums" "$WORK/sha256sum.txt" || fail "download failed"
    verify_digest "$WORK/zapret.tar.gz" "$hex" || fail "archive checksum does not match GitHub's"
    check_archive "$WORK/zapret.tar.gz" >/dev/null 2>&1 || fail "archive contains unsafe paths"
    mkdir "$WORK/src"
    tar -xzf "$WORK/zapret.tar.gz" -C "$WORK/src" --no-same-owner || fail "could not unpack the archive"
    (cd "$WORK/src" && sha256sum --quiet --strict -c "$WORK/sha256sum.txt") >/dev/null 2>&1 \
        || fail "a program in the archive does not match upstream's sha256sum.txt"
    SOURCE="$WORK/src/zapret-$tag"
    if [ ! -f "$SOURCE/install_bin.sh" ] || [ ! -f "$SOURCE/config.default" ]; then
        fail "unexpected archive layout"
    fi
    log "@@STEP verified $tag"
}

# --- configuration --------------------------------------------------------------------

# Replace KEY=... (single-line values only).
set_conf() {
    local f=$ZDIR/config
    if grep -q "^$1=" "$f"; then sed -i "s|^$1=.*|$1=$2|" "$f"; else printf '%s=%s\n' "$1" "$2" >>"$f"; fi
}

# Replace the multi-line NFQWS_OPT="..." block (or add it).
set_strategy() {
    local f=$ZDIR/config tmp
    tmp=$(mktemp)
    awk -v s="$1" '
        function block() {
            print "NFQWS_OPT=\""
            print "--filter-tcp=80 --hostcase <HOSTLIST> --new"
            print "--filter-tcp=443 " s " <HOSTLIST>"
            print "\""
            done = 1
        }
        /^NFQWS_OPT="/ { block(); rest = substr($0, 12); if (rest !~ /"[[:space:]]*$/) skip = 1; next }
        skip { if ($0 ~ /^"/) skip = 0; next }
        { print }
        END { if (!done) block() }
    ' "$f" >"$tmp" && cat "$tmp" >"$f"
    rm -f "$tmp"
}

probe_all() {
    local h dir ok=0
    dir=$(mktemp -d)
    for h in $HOSTS; do
        (
            n=0
            for _ in $(seq "$TRIES"); do
                c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "https://$h/" </dev/null 2>/dev/null)
                [ -n "$c" ] && [ "$c" != 000 ] && n=$((n + 1))
            done
            echo "$n" >"$dir/$h"
        ) &
    done
    wait
    for h in $HOSTS; do ok=$((ok + $(cat "$dir/$h" 2>/dev/null || echo 0))); done
    rm -rf "$dir"
    echo "$ok"
}

# Without pgrep: procps is not installed on every system.
nfqws_running() {
    grep -qx nfqws /proc/[0-9]*/comm 2>/dev/null
}

service_running() {
    run systemctl restart zapret.service 2>&1 || return 1
    sleep 2
    systemctl is-active -q zapret.service && nfqws_running
}

setup_dot() {
    log "@@STEP dns"
    if ! systemctl is-active -q systemd-resolved; then log "@@WARN dns-no-resolved"; return; fi
    mkdir -p "$(dirname "$DOT_CONF")"
    cat >"$DOT_CONF" <<'CONF'
# Written by DPI Dashboard: encrypted DNS against forged answers.
[Resolve]
DNS=9.9.9.9#dns.quad9.net 1.1.1.1#cloudflare-dns.com
DNSOverTLS=yes
Domains=~.
CONF
    run systemctl restart systemd-resolved
    sleep 2
}

do_tune() {
    if [ ! -f "$ZDIR/config" ] || [ ! -x "$ZDIR/init.d/sysv/zapret" ]; then
        fail "zapret is not installed in $ZDIR"
    fi
    systemctl cat zapret.service >/dev/null 2>&1 || fail "zapret.service not found"
    check_strategies
    [ "$DNSDOT" = 1 ] && setup_dot

    local was_active=0 was_enabled=0 best=-1 bi=0 i=0 s ok
    systemctl is-active -q zapret.service && was_active=1
    systemctl is-enabled -q zapret.service && was_enabled=1
    cp -p "$ZDIR/config" "$ZDIR/config.dpi-dashboard.bak"
    set_conf NFQWS_ENABLE 1
    set_conf NFQWS_PORTS_UDP ""

    log "@@STEP baseline"
    run systemctl stop zapret.service 2>&1
    log "@@BASELINE $(probe_all)/$MAX"

    for s in "${LIST[@]}"; do
        i=$((i + 1))
        log "@@STEP try $i"
        log "strategy $i: $s"
        set_strategy "$s"
        if ! service_running; then
            log "@@TRY $i fail"
            journalctl -u zapret.service -n 5 --no-pager 2>&1
            continue
        fi
        ok=$(probe_all)
        log "@@TRY $i $ok/$MAX"
        if [ "$ok" -gt "$best" ]; then best=$ok; bi=$i; fi
        [ "$ok" -eq "$MAX" ] && break
    done

    if [ "$best" -le 0 ]; then
        cp -p "$ZDIR/config.dpi-dashboard.bak" "$ZDIR/config"
        run systemctl stop zapret.service 2>&1
        [ "$was_enabled" = 1 ] || run systemctl disable zapret.service 2>&1
        [ "$was_active" = 1 ] && run systemctl start zapret.service 2>&1
        fail "no strategy worked; previous settings restored"
    fi
    set_strategy "${LIST[$((bi - 1))]}"
    run systemctl enable zapret.service 2>&1
    service_running || fail "zapret did not start with the chosen strategy"
    log "@@CHOSEN $bi $best/$MAX"
    log "@@DONE ok"
}

do_install() {
    [ -e "$ZDIR" ] && fail "$ZDIR already exists"
    systemctl cat zapret.service >/dev/null 2>&1 && fail "a zapret.service already exists"
    check_strategies
    ensure_prereqs
    download_release

    log "@@STEP copy"
    cp -a "$SOURCE" "$ZDIR" || fail "copy failed"
    chown -R root:root "$ZDIR"
    chmod -R go-w "$ZDIR"
    # SELinux (Fedora, RHEL): give the files the normal label for /opt.
    if have restorecon && have selinuxenabled && selinuxenabled; then
        restorecon -R "$ZDIR" 2>&1
    fi
    echo "installed by DPI Dashboard on $(date -Is)" >"$MARK"
    cleanup() { rm -rf "$ZDIR" "$UNIT"; systemctl daemon-reload; }

    log "@@STEP binaries"
    if ! run "$ZDIR/install_bin.sh" 2>&1; then cleanup; fail "no zapret binaries for this CPU"; fi

    log "@@STEP config"
    cp "$ZDIR/config.default" "$ZDIR/config"
    log "@@STEP unit"
    install -m 0644 "$ZDIR/init.d/systemd/zapret.service" "$UNIT"
    systemctl daemon-reload
    do_tune
}

do_uninstall() {
    [ -f "$MARK" ] || fail "zapret in $ZDIR was not installed by DPI Dashboard; use its own uninstaller"
    log "@@STEP remove"
    run systemctl disable --now zapret.service 2>&1
    rm -f "$UNIT"
    systemctl daemon-reload
    rm -rf "$ZDIR"
    if [ -f "$DOT_CONF" ]; then rm -f "$DOT_CONF"; run systemctl restart systemd-resolved; fi
    log "@@DONE ok"
}

case $MODE in
    install) do_install ;;
    tune) do_tune ;;
    uninstall) do_uninstall ;;
    *) fail "unknown mode" ;;
esac
