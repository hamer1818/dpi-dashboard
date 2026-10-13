# DPI Dashboard

[English](README.md)

Engel aşma (DPI bypass) servisini **tek tıkla açıp kapatan** ve **gerçekten çalışıp
çalışmadığını test eden** küçük bir masaüstü penceresi. Terminale gerek yok.

![DPI Dashboard](docs/screenshot-tr.png)

Bazı internet sağlayıcıları siteleri derin paket incelemesiyle (DPI) engeller: site adı
görüldüğü anda TLS el sıkışmasının ortasında bağlantı kesilir.
[zapret](https://github.com/bol-van/zapret) ve
[GoodbyeDPI](https://github.com/ValdikSS/GoodbyeDPI) gibi araçlar bunu aşar, ama sistem
servisi olarak çalışırlar ve normalde komut satırından açılıp kapatılırlar. DPI
Dashboard o servisin arayüzüdür.

> **DPI Dashboard kendi başına hiçbir engeli aşmaz.** Önceden kurduğunuz engel aşma
> servisini yönetir. Bkz. [Gereksinimler](#gereksinimler).

## Özellikler

- Servisi tek düğmeyle açıp kapatma. Açılışta başlayıp başlamayacağını da birlikte ayarlar.
- Canlı durum: açık/kapalı ve açılışta başlayıp başlamadığı.
- Bir site listesine (varsayılan Discord) birkaç denemeyle bağlantı testi. Başarısız
  denemenin **nasıl** başarısız olduğunu söyler: bağlantı kesildi (DPI'ın tipik
  belirtisi), zaman aşımı, DNS hatası ya da reddedilen sertifika.
- Her seferinde yönetici şifresi sorar (Linux'ta polkit, Windows'ta UAC). Kalıcı
  "şifresiz" bir kural kurmaz.
- Türkçe ve İngilizce, sistem diline göre.
- Linux (systemd) ve Windows.

## Gereksinimler

| | Linux | Windows 10 / 11 |
|---|---|---|
| Engel aşma servisi | [zapret](https://github.com/bol-van/zapret)'in `zapret.service`'i (`install_easy.sh` ya da AUR `zapret` / `zapret-git`) | `zapret` adlı bir Windows servisi (örn. [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) `service.bat`) ya da `GoodbyeDPI` (GoodbyeDPI'ın `service_install_*.cmd` betikleri) |
| Servis yöneticisi | systemd | Windows servisleri |
| Şifre penceresi | Kimlik doğrulama ajanıyla polkit (KDE ve GNOME'da var) | UAC |
| Python (`.exe` kullanmıyorsanız) | 3.10+ ve PyQt6 | 3.10+ ve PyQt6 |

Servisinizin adı farklıysa [ayar dosyasına](#ayarlar) yazın.

Desteklenmeyenler: systemd kullanmayan Linux sistemleri (OpenRC, runit, s6), macOS.

## Kurulum

### Linux

```bash
git clone https://github.com/hamer1818/dpi-dashboard.git
cd dpi-dashboard
./scripts/install-linux.sh
```

Ardından uygulama menüsünde **DPI Dashboard** arayın (`dpi`, `zapret` ve `discord`
yazınca da çıkar). Her şey ev dizininize kurulur, root gerekmez. Dağıtımınızın PyQt6'sı
kuruluysa (`python-pyqt6`, `python3-pyqt6`) o kullanılır. Kaldırmak için:
`./scripts/uninstall-linux.sh`.

Debian/Ubuntu'da önce `sudo apt install python3-venv` gerekebilir.

### Windows

[Releases](https://github.com/hamer1818/dpi-dashboard/releases) sayfasından
`dpi-dashboard-<sürüm>-windows-x64.exe` dosyasını indirip çalıştırın. Kurulum adımı yok.

Dosya kod imzalı olmadığı için SmartScreen "bilinmeyen yayımcı" uyarısı verebilir:
**Ek bilgi → Yine de çalıştır**'ı seçin. Kendiniz de derleyebilirsiniz, bkz.
[Geliştirme](README.md#development).

## Ayarlar

**Ayarlar** düğmesi ayar dosyasını açar, ilk kullanımda varsayılanlarla oluşturur:

- Linux: `~/.config/dpi-dashboard/config.json`
- Windows: `%APPDATA%\dpi-dashboard\config.json`

| Anahtar | Anlamı |
|---|---|
| `backend` | `auto`, `systemd` ya da `windows-service` |
| `service` | Servis adı. `null` bilinen adları dener (Linux'ta `zapret.service`; Windows'ta önce `zapret`, sonra `GoodbyeDPI`). |
| `hosts` | Bağlantı testinde kullanılan siteler. Önem verdiğiniz siteleri yazın. |
| `tries` | Site başına deneme sayısı. DPI engeli çoğu zaman aralıklıdır, tek deneme yetmez. |
| `timeout` | Deneme başına saniye. |
| `language` | `auto`, `en` ya da `tr` |
| `refresh_seconds` | Durumun ne sıklıkla yeniden okunacağı. |

Geçersiz değerler yok sayılır ve pencerede bildirilir. Düzenledikten sonra uygulamayı
yeniden başlatın.

## Sorun giderme

**"BULUNAMADI".** Servis kurulu değil ya da adı farklı. Linux'ta
`systemctl list-unit-files | grep -i zapret`, Windows'ta
`sc query state= all | findstr /i "zapret goodbye"` ile bakın ve adı ayar dosyasına yazın.

**Düğmeye basınca hiçbir şey olmuyor (Linux).** Çalışan bir polkit kimlik doğrulama
ajanı yok. KDE ve GNOME gibi masaüstleri bunu kendisi başlatır. Sade pencere
yöneticilerinde eklenmesi gerekir (örn. `polkit-gnome` ya da `lxqt-policykit`).

**Servis açık ama siteler hâlâ "bağlantı kesildi" diyor.** Engel aşma stratejisi
sağlayıcınızın engelleme biçimine uymuyor. Bu, zapret/GoodbyeDPI'ın kendi ayarıdır
(zapret'in `blockcheck.sh`'ı uygun stratejiyi bulmaya yardım eder). DPI Dashboard sadece
servisi açıp kapatır.

**"ad çözülemedi (DNS)" ya da sadece bazı sitelerde yanlış sonuç.** Bazı sağlayıcılar
DNS cevaplarını da sahteler. Bunu DPI aşma düzeltmez. Şifreli DNS kullanın: Windows
11'in ağ ayarlarında ya da tarayıcıda DNS over HTTPS, Linux'ta systemd-resolved'da
`DNSOverTLS=yes`.

**"sertifika reddedildi".** Siteyle aranızdaki bir şey farklı bir sertifika sunuyor. O
bağlantıya güvenmeyin.

## Yasal not

Ağ filtrelemesini aşmanın yasal olup olmadığı bulunduğunuz yere göre değişir. Yazılımı
nasıl kullandığınızdan siz sorumlusunuz. Yazılım garantisiz sunulur, bkz.
[lisans](LICENSE).

## Lisans

[MIT](LICENSE)
