#!/bin/bash
# DPI Dashboard setup helper for Linux. Runs as root (started through pkexec).
#
#   setup-linux.sh install   LOG --source DIR --strategies FILE --hosts "a b" [--tries N] [--dns-dot]
#   setup-linux.sh tune      LOG --strategies FILE --hosts "a b" [--tries N] [--dns-dot]
#   setup-linux.sh uninstall LOG
#
# install: copies an extracted, already verified zapret release to /opt/zapret, links the
#          binaries for this CPU, writes the config and the systemd unit, then runs tune.
# tune:    measures the blocking with zapret off, tries each strategy until one reaches
#          every test site, keeps the best and enables the service. If no strategy helps,
#          the previous config and service state are restored.
# Progress goes to LOG using the @@ protocol described in runner.py.
set -u
umask 022
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

ZDIR=/opt/zapret
UNIT=/etc/systemd/system/zapret.service
MARK=$ZDIR/.installed-by-dpi-dashboard
DOT_CONF=/etc/systemd/resolved.conf.d/dpi-dashboard-dot.conf
SAFE_STRATEGY='^--[A-Za-z0-9 =,._+:/-]+$'
SAFE_HOST='^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$'

MODE=${1:-}
LOG=${2:-}
[ $# -ge 2 ] && shift 2
SOURCE='' STRATS='' HOSTS='discord.com' TRIES=3 DNSDOT=0
while [ $# -gt 0 ]; do
    case $1 in
        --source) SOURCE=$2; shift 2 ;;
        --strategies) STRATS=$2; shift 2 ;;
        --hosts) HOSTS=$2; shift 2 ;;
        --tries) TRIES=$2; shift 2 ;;
        --dns-dot) DNSDOT=1; shift ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

[ -n "$LOG" ] || { echo "usage: $0 install|tune|uninstall LOG [options]" >&2; exit 2; }
log()  { printf '%s\n' "$*" >>"$LOG"; printf '%s\n' "$*"; }
fail() { log "@@ERROR $*"; log "@@DONE fail"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

[ "$(id -u)" = 0 ] || fail "must run as root"
[[ $TRIES =~ ^[1-9][0-9]?$ ]] || fail "invalid --tries"
for h in $HOSTS; do [[ $h =~ $SAFE_HOST ]] || fail "invalid host: $h"; done
NHOSTS=$(wc -w <<<"$HOSTS")
MAX=$((NHOSTS * TRIES))

install_pkgs() {
    log "@@STEP deps"
    log "installing: $*"
    if have pacman; then pacman -S --needed --noconfirm "$@"
    elif have apt-get; then apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y -q "$@"
    elif have dnf; then dnf install -y "$@"
    elif have zypper; then zypper --non-interactive install "$@"
    else return 1
    fi >>"$LOG" 2>&1
}

ensure_prereqs() {
    [ -d /run/systemd/system ] || fail "systemd is required"
    have curl || install_pkgs curl || true
    have curl || fail "curl is required and could not be installed"
    if ! have nft && ! have iptables; then install_pkgs nftables || true; fi
    have nft || have iptables || fail "nftables or iptables is required and could not be installed"
}

read_strategies() {
    [ -f "$STRATS" ] || fail "strategy file not found"
    mapfile -t LIST < <(grep -v '^[[:space:]]*$' "$STRATS")
    [ ${#LIST[@]} -gt 0 ] || fail "no strategies"
    local s
    for s in "${LIST[@]}"; do [[ $s =~ $SAFE_STRATEGY ]] || fail "unsafe strategy: $s"; done
}

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
                c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "https://$h/" 2>/dev/null)
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

service_running() {
    systemctl restart zapret.service >>"$LOG" 2>&1 || return 1
    sleep 2
    systemctl is-active -q zapret.service && pgrep -x nfqws >/dev/null
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
    systemctl restart systemd-resolved
    sleep 2
}

do_tune() {
    if [ ! -f "$ZDIR/config" ] || [ ! -x "$ZDIR/init.d/sysv/zapret" ]; then
        fail "zapret is not installed in $ZDIR"
    fi
    systemctl cat zapret.service >/dev/null 2>&1 || fail "zapret.service not found"
    read_strategies
    [ "$DNSDOT" = 1 ] && setup_dot

    local was_active=0 was_enabled=0 best=-1 bi=0 i=0 s
    systemctl is-active -q zapret.service && was_active=1
    systemctl is-enabled -q zapret.service && was_enabled=1
    cp -p "$ZDIR/config" "$ZDIR/config.dpi-dashboard.bak"
    set_conf NFQWS_ENABLE 1
    set_conf NFQWS_PORTS_UDP ""

    log "@@STEP baseline"
    systemctl stop zapret.service >>"$LOG" 2>&1
    log "@@BASELINE $(probe_all)/$MAX"

    for s in "${LIST[@]}"; do
        i=$((i + 1))
        log "@@STEP try $i"
        log "strategy $i: $s"
        set_strategy "$s"
        if ! service_running; then
            log "@@TRY $i fail"
            journalctl -u zapret.service -n 5 --no-pager >>"$LOG" 2>&1
            continue
        fi
        local ok
        ok=$(probe_all)
        log "@@TRY $i $ok/$MAX"
        if [ "$ok" -gt "$best" ]; then best=$ok; bi=$i; fi
        [ "$ok" -eq "$MAX" ] && break
    done

    if [ "$best" -le 0 ]; then
        cp -p "$ZDIR/config.dpi-dashboard.bak" "$ZDIR/config"
        systemctl stop zapret.service >>"$LOG" 2>&1
        [ "$was_enabled" = 1 ] || systemctl disable zapret.service >>"$LOG" 2>&1
        [ "$was_active" = 1 ] && systemctl start zapret.service >>"$LOG" 2>&1
        fail "no strategy worked; previous settings restored"
    fi
    set_strategy "${LIST[$((bi - 1))]}"
    systemctl enable zapret.service >>"$LOG" 2>&1
    service_running || fail "zapret did not start with the chosen strategy"
    log "@@CHOSEN $bi $best/$MAX"
    log "@@DONE ok"
}

do_install() {
    if [ -z "$SOURCE" ] || [ ! -f "$SOURCE/install_bin.sh" ] || [ ! -f "$SOURCE/config.default" ]; then
        fail "not a zapret release: $SOURCE"
    fi
    [ -e "$ZDIR" ] && fail "$ZDIR already exists"
    systemctl cat zapret.service >/dev/null 2>&1 && fail "a zapret.service already exists"
    ensure_prereqs

    log "@@STEP copy"
    cp -a "$SOURCE" "$ZDIR" || fail "copy failed"
    chown -R root:root "$ZDIR"
    chmod -R go-w "$ZDIR"
    echo "installed by DPI Dashboard on $(date -Is)" >"$MARK"
    cleanup() { rm -rf "$ZDIR" "$UNIT"; systemctl daemon-reload; }

    log "@@STEP binaries"
    if ! "$ZDIR/install_bin.sh" >>"$LOG" 2>&1; then cleanup; fail "no zapret binaries for this CPU"; fi

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
    systemctl disable --now zapret.service >>"$LOG" 2>&1
    rm -f "$UNIT"
    systemctl daemon-reload
    rm -rf "$ZDIR"
    if [ -f "$DOT_CONF" ]; then rm -f "$DOT_CONF"; systemctl restart systemd-resolved; fi
    log "@@DONE ok"
}

case $MODE in
    install) do_install ;;
    tune) do_tune ;;
    uninstall) do_uninstall ;;
    *) fail "unknown mode: $MODE" ;;
esac
