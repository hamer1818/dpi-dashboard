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
        "not_installed": "Service “{service}” was not found. Use “Setup” to install zapret, "
                         "or set the name of your service in the settings file.",
        "config_warning": "Settings: {msg}",
        "reason_reset": "connection reset (typical for DPI)",
        "reason_timeout": "timed out",
        "reason_dns": "name not resolved (DNS)",
        "reason_cert": "certificate rejected (traffic may be intercepted)",
        "reason_tls": "TLS error",
        "reason_no-http": "no HTTP answer",
        "reason_error": "network error",
        "setup_btn": "Setup",
        "close": "Close",
        "setup_title": "Setup and repair",
        "setup_checking": "Checking this computer…",
        "setup_dns_option": "Also turn on encrypted DNS (DNS-over-TLS in systemd-resolved)",
        "setup_remove": "Remove",
        "setup_service_found": "Service “{service}” is installed.",
        "setup_service_missing": "Service “{service}” is not installed.",
        "setup_files_ours": "zapret files are present (installed by DPI Dashboard).",
        "setup_files_other": "zapret files are present (installed by another installer or "
                             "package).",
        "setup_missing_required": "Missing and required: {items}",
        "setup_missing_auto": "Missing, will be installed during setup: {items}",
        "setup_dns_ok": "DNS answers for {host} look genuine.",
        "setup_dns_mismatch": "DNS answers for {host} differ from encrypted DNS: your provider may "
                              "be falsifying them. A DPI bypass does not fix that.",
        "setup_dns_unknown": "Could not check DNS for {host}.",
        "setup_dns_windows_hint": "Windows 11: Settings → Network & internet → your connection → "
                                  "DNS server assignment → Edit, enter 1.1.1.1 and turn on "
                                  "DNS over HTTPS.",
        "setup_install": "Install zapret and find a working setting",
        "setup_tune": "Find the best setting again",
        "setup_foreign_windows": "This service was installed by another tool. DPI Dashboard turns "
                                 "it on and off, but its settings must be changed with the tool "
                                 "that installed it.",
        "setup_confirm_install": "DPI Dashboard will:\n\n"
                                 "• download the latest zapret release from "
                                 "github.com/bol-van/zapret and verify its checksums,\n"
                                 "• install it to {path} as a system service,\n"
                                 "• try up to {tries} settings and keep the best one.\n\n"
                                 "The administrator password is asked once. Web connections may "
                                 "drop for a few seconds while settings are tried. “Remove” "
                                 "undoes all of it.\n\nContinue?",
        "setup_confirm_tune": "DPI Dashboard will try up to {tries} settings on the installed "
                              "zapret and keep the best one. If none of them works, the current "
                              "settings are put back.\n\nThe administrator password is asked "
                              "once. Web connections may drop for a few seconds.\n\nContinue?",
        "setup_confirm_remove": "Stop and delete the zapret service and remove {path}?",
        "setup_download_failed": "Download failed: {msg}",
        "step_download": "Downloading zapret from GitHub…",
        "step_verified": "zapret {version}: checksums verified.",
        "step_deps": "Installing missing system packages…",
        "step_copy": "Copying files…",
        "step_binaries": "Selecting the programs for this processor…",
        "step_config": "Writing the configuration…",
        "step_unit": "Creating the service…",
        "step_dns": "Turning on encrypted DNS…",
        "step_baseline": "Measuring with zapret off…",
        "step_remove": "Removing zapret…",
        "setup_baseline": "Without zapret: {score} attempts reached the sites.",
        "setup_try": "Setting {n}: {score}",
        "setup_try_fail": "Setting {n}: zapret did not start",
        "setup_chosen": "Chosen: setting {n} ({score}).",
        "warn_dns-no-resolved": "systemd-resolved is not running; encrypted DNS was not set up.",
        "setup_success": "Done. zapret is on and starts at boot.",
        "setup_removed": "zapret was removed.",
        "setup_failed": "Setup did not finish. See the messages above.",
        "setup_no_output": "The administrator step ended without any message (exit code {code}). "
                           "Please report this with your Windows/Linux version.",
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
        "not_installed": "“{service}” servisi bulunamadı. zapret'i kurmak için “Kurulum”u "
                         "kullanın ya da servisinizin adını ayar dosyasına yazın.",
        "config_warning": "Ayarlar: {msg}",
        "reason_reset": "bağlantı kesildi (DPI'ın tipik belirtisi)",
        "reason_timeout": "zaman aşımı",
        "reason_dns": "ad çözülemedi (DNS)",
        "reason_cert": "sertifika reddedildi (trafiğe müdahale olabilir)",
        "reason_tls": "TLS hatası",
        "reason_no-http": "HTTP yanıtı yok",
        "reason_error": "ağ hatası",
        "setup_btn": "Kurulum",
        "close": "Kapat",
        "setup_title": "Kurulum ve onarım",
        "setup_checking": "Bilgisayar kontrol ediliyor…",
        "setup_dns_option": "Şifreli DNS'i de aç (systemd-resolved'da DNS-over-TLS)",
        "setup_remove": "Kaldır",
        "setup_service_found": "“{service}” servisi kurulu.",
        "setup_service_missing": "“{service}” servisi kurulu değil.",
        "setup_files_ours": "zapret dosyaları mevcut (DPI Dashboard kurdu).",
        "setup_files_other": "zapret dosyaları mevcut (başka bir kurulum ya da paket).",
        "setup_missing_required": "Eksik ve zorunlu: {items}",
        "setup_missing_auto": "Eksik, kurulum sırasında kurulacak: {items}",
        "setup_dns_ok": "{host} için DNS cevapları doğru görünüyor.",
        "setup_dns_mismatch": "{host} için DNS cevapları şifreli DNS'ten farklı: sağlayıcınız "
                              "sahte cevap veriyor olabilir. Bunu DPI aşma düzeltmez.",
        "setup_dns_unknown": "{host} için DNS kontrol edilemedi.",
        "setup_dns_windows_hint": "Windows 11: Ayarlar → Ağ ve internet → bağlantınız → DNS "
                                  "sunucusu ataması → Düzenle; 1.1.1.1 girip HTTPS üzerinden "
                                  "DNS'i açın.",
        "setup_install": "zapret'i kur ve çalışan ayarı bul",
        "setup_tune": "En iyi ayarı yeniden bul",
        "setup_foreign_windows": "Bu servis başka bir araçla kurulmuş. DPI Dashboard onu açıp "
                                 "kapatabilir, ama ayarları onu kuran araçtan değiştirilmeli.",
        "setup_confirm_install": "DPI Dashboard şunları yapacak:\n\n"
                                 "• github.com/bol-van/zapret'ten son zapret sürümünü indirip "
                                 "özetlerini doğrulayacak,\n"
                                 "• {path} konumuna sistem servisi olarak kuracak,\n"
                                 "• en fazla {tries} ayar deneyip en iyisini bırakacak.\n\n"
                                 "Yönetici şifresi bir kez sorulur. Ayarlar denenirken web "
                                 "bağlantıları birkaç saniye kopabilir. “Kaldır” hepsini geri "
                                 "alır.\n\nDevam edilsin mi?",
        "setup_confirm_tune": "DPI Dashboard kurulu zapret üzerinde en fazla {tries} ayar deneyip "
                              "en iyisini bırakacak. Hiçbiri işe yaramazsa mevcut ayarlar geri "
                              "konur.\n\nYönetici şifresi bir kez sorulur. Web bağlantıları "
                              "birkaç saniye kopabilir.\n\nDevam edilsin mi?",
        "setup_confirm_remove": "zapret servisi durdurulup silinsin ve {path} kaldırılsın mı?",
        "setup_download_failed": "İndirme başarısız: {msg}",
        "step_download": "zapret GitHub'dan indiriliyor…",
        "step_verified": "zapret {version}: özetler doğrulandı.",
        "step_deps": "Eksik sistem paketleri kuruluyor…",
        "step_copy": "Dosyalar kopyalanıyor…",
        "step_binaries": "Bu işlemciye uygun programlar seçiliyor…",
        "step_config": "Ayar dosyası yazılıyor…",
        "step_unit": "Servis oluşturuluyor…",
        "step_dns": "Şifreli DNS açılıyor…",
        "step_baseline": "zapret kapalıyken ölçülüyor…",
        "step_remove": "zapret kaldırılıyor…",
        "setup_baseline": "zapret olmadan: {score} deneme sitelere ulaştı.",
        "setup_try": "Ayar {n}: {score}",
        "setup_try_fail": "Ayar {n}: zapret başlamadı",
        "setup_chosen": "Seçilen: ayar {n} ({score}).",
        "warn_dns-no-resolved": "systemd-resolved çalışmıyor; şifreli DNS kurulmadı.",
        "setup_success": "Tamam. zapret açık ve açılışta başlıyor.",
        "setup_removed": "zapret kaldırıldı.",
        "setup_failed": "Kurulum tamamlanmadı. Yukarıdaki mesajlara bakın.",
        "setup_no_output": "Yönetici adımı hiçbir mesaj vermeden bitti (çıkış kodu {code}). "
                           "Lütfen Windows/Linux sürümünüzle birlikte bildirin.",
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

    def keys(self) -> set[str]:
        return set(STRINGS["en"])

    def __call__(self, key: str, **kw: str) -> str:
        text = STRINGS[self.lang].get(key) or STRINGS["en"][key]
        return text.format(**kw) if kw else text
