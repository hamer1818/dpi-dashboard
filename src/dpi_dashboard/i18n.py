"""English and Turkish UI strings."""

from __future__ import annotations

import locale
import os

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "DPI bypass",
        "on": "ON", "off": "OFF", "missing": "NOT FOUND",
        "boot_on": "starts at boot", "boot_off": "does not start at boot",
        "turn_on": "Turn on", "turn_off": "Turn off",
        "turning_on": "Turning on…", "turning_off": "Turning off…",
        "auth_hint": "An administrator password prompt will open…",
        "cancelled": "Cancelled, or the password was not accepted.",
        "error": "Error: {msg}",
        "test": "Test connection", "testing": "Testing…",
        "all_ok": "All test addresses are reachable.",
        "some_blocked": "Some addresses are being blocked.",
        "settings": "Settings",
        "no_backend": "This system has no supported service manager "
                      "(systemd on Linux, services on Windows).",
        "not_installed": "Service “{service}” was not found. Install zapret or GoodbyeDPI "
                         "as a service, or set its name in the settings file.",
        "config_warning": "Settings: {msg}",
        "reason_reset": "connection reset (typical for DPI)",
        "reason_timeout": "timed out",
        "reason_dns": "name not resolved (DNS)",
        "reason_cert": "certificate rejected (traffic may be intercepted)",
        "reason_tls": "TLS error",
        "reason_no-http": "no HTTP answer",
        "reason_error": "network error",
    },
    "tr": {
        "title": "Engel aşma (DPI)",
        "on": "AÇIK", "off": "KAPALI", "missing": "BULUNAMADI",
        "boot_on": "açılışta başlar", "boot_off": "açılışta başlamaz",
        "turn_on": "Aç", "turn_off": "Kapat",
        "turning_on": "Açılıyor…", "turning_off": "Kapatılıyor…",
        "auth_hint": "Yönetici şifresi penceresi açılacak…",
        "cancelled": "İptal edildi ya da şifre kabul edilmedi.",
        "error": "Hata: {msg}",
        "test": "Bağlantıyı test et", "testing": "Test ediliyor…",
        "all_ok": "Tüm test adreslerine erişiliyor.",
        "some_blocked": "Bazı adresler engelleniyor.",
        "settings": "Ayarlar",
        "no_backend": "Bu sistemde desteklenen bir servis yöneticisi yok "
                      "(Linux'ta systemd, Windows'ta servisler).",
        "not_installed": "“{service}” servisi bulunamadı. zapret ya da GoodbyeDPI'ı servis "
                         "olarak kurun veya adını ayar dosyasına yazın.",
        "config_warning": "Ayarlar: {msg}",
        "reason_reset": "bağlantı kesildi (DPI'ın tipik belirtisi)",
        "reason_timeout": "zaman aşımı",
        "reason_dns": "ad çözülemedi (DNS)",
        "reason_cert": "sertifika reddedildi (trafiğe müdahale olabilir)",
        "reason_tls": "TLS hatası",
        "reason_no-http": "HTTP yanıtı yok",
        "reason_error": "ağ hatası",
    },
}


def system_language() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        if os.environ.get(var, "").lower().startswith("tr"):
            return "tr"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return "tr" if loc.lower().startswith(("tr", "turkish")) else "en"


class Translator:
    def __init__(self, language: str = "auto"):
        self.lang = system_language() if language == "auto" else language
        if self.lang not in STRINGS:
            self.lang = "en"

    def __call__(self, key: str, **kw: str) -> str:
        text = STRINGS[self.lang].get(key) or STRINGS["en"][key]
        return text.format(**kw) if kw else text
