# Google Pixel UI / GoogleBook Desktop Suite for Linux

> **Material Design 3 (Android 15 / 16 / 17 & ChromeOS Pixelbook) Desktop Environment for Linux Mint (Cinnamon / X11)**  
> Fast, native vector-rendered desktop suite written in Python 3, GTK+ 3, and Cairo with pure event-driven architecture (0.0% CPU when idle).

---

## 🌟 Fitur Utama (Key Features)

### 1. Floating Shelf Dock (`pixel_dock.py`)
* **Material 3 Squircle Design**: Pil melayang (*floating pill*) dengan bayangan elevasi halus dan sudut melengkung khas Google Pixel.
* **Integrasi Launcher & Kontrol**:
  * Tombol **App Drawer (`⸬`)** di sisi kiri untuk membuka laci aplikasi.
  * Tombol **Multitasking Overview (`▢`)** untuk melihat aplikasi yang sedang terbuka.
  * **Bilah Pencarian Google**: Desain kapsul terpusat dengan logo warna-warni Google 'G'.
* **Aplikasi Tersemat (*Pinned*) & Berjalan (*Running*)**:
  * Dilengkapi indikator titik aktif (*running dot*).
  * Pengaturan posisi ikon bebas via **Drag & Drop** (tersimpan otomatis).
  * **Klik Kiri Cerdas**: Meminimalkan jendela aktif, memulihkan (*unminimize*) jendela yang diminimalkan, dan siklus bergantian jika ada banyak jendela pada aplikasi yang sama.
  * **Klik Kanan Profil Aplikasi**: Menu profil terisolasi (WhatsApp Kantor/Admin/Pribadi, Google Chrome Jendela Baru & Incognito, Nemo Folder Home/Unduhan, Terminal, kontrol musik MPRIS, dsb.), serta toggle *"Sematkan ke Dock"* / *"Tutup Jendela"*.
* **Auto-Hide / Auto-Dodge Cerdas**: Dock otomatis meluncur turun bersembunyi saat ada jendela aktif berstatus *Fullscreen*, *Maximized*, atau menutupi area dock bawah, dan muncul kembali seketika saat kursor menyentuh batas bawah layar.

### 2. Fullscreen App Drawer (`pixel_app_drawer.py`)
* **Laci Aplikasi Modern**: Kartu Material 3 solid berlatar belakang teredup lembut (*frosted glass backdrop*).
* **Pencarian Instan**: Pencarian aplikasi cepat berbasis fuzzy matching dengan fallback Google Web Search.
* **Kategori Tab Chip**: Pemfilteran aplikasi berdasarkan kategori (*Semua, Kantor & Kerja, Komunikasi, Multimedia, Utilitas*).
* **Tombol Daya Sistem (`⏻`)**: Akses cepat ke dialog matikan, mulai ulang, atau tidur (*shutdown / restart / suspend*).

### 3. Recent Apps Switcher / Alt+Tab Replacement (`pixel_recent_apps.py`)
* **Karosel Kartu Tumpang-Tindih (*Overlapping Card Deck*)**: Menggantikan switcher jendela bawaan Cinnamon secara penuh.
* **Siklus Alami Alt+Tab**: Tahan `Alt`, tekan `Tab` untuk memilih aplikasi, dan begitu tombol `Alt` dilepas, jendela terpilih seketika diaktifkan ke depan.
* **Pratinjau Jendela Real-Time**: Tangkapan layar live window preview via `GdkX11` & `libwnck`.
* **Telemetri Header & Clear All**: Menampilkan penggunaan RAM real-time di bilah atas dan tombol bulat *"Tutup Semua"* di bagian bawah.

### 4. Interactive Desktop Canvas (`pixel_desktop.py`)
* **Widget Google Pixel Asli**:
  * Jam Digital & Kalender besar dengan tipografi *Google Sans*.
  * Cuaca Real-Time Open-Meteo dengan deteksi lokasi otomatis via IP geolokasi.
  * Telemetri Suhu & Baterai ThinkPad.
  * Pemutar Musik MPRIS dengan bilah gelombang audio bergerak (*squiggly progress wave*).
  * Quick Folder Launchers (*Downloads, Documents, Pictures, Music*).
  * Control Center interaktif dengan slider volume live dan tombol pintas (Dark Mode, Wi-Fi, Bluetooth).
  * Quick Notes dengan pemantau berkas otomatis (*live watcher* `~/.config/quick-notes.txt`).
* **Input Shape Click-Through**: Area transparan tembus klik ke wallpaper tanpa menghalangi desktop.
* **0.0% CPU Idle**: Tidak ada loop polling aktif. Menggunakan DBus UPower, DBus MPRIS, dan minute-boundary tick.

---

## 🚀 Panduan Instalasi (Quick Start)

### Kebutuhan Sistem (Prerequisites)
* **Distro**: Linux Mint (Cinnamon) 21.x / 22.x, Ubuntu, atau Debian-based distro dengan sesi X11.
* **Python**: Python 3.10 ke atas.

### Pemasangan 1-Klik via Skrip

1. Clone repositori ini:
   ```bash
   git clone https://github.com/<username>/pixel-desktop.git ~/Applications/pixel-desktop
   cd ~/Applications/pixel-desktop
   ```

2. Jalankan skrip installer:
   ```bash
   ./install.sh
   ```
   *(Gunakan `./install.sh -y` jika ingin melewati konfirmasi paket otomatis).*

Skrip installer akan secara otomatis:
* Memeriksa dan memasang paket dependensi sistem (`python3-gi`, `gir1.2-wnck-3.0`, `python3-xlib`, `wmctrl`, dsb.).
* Memasang font resmi *Google Sans* ke `~/.local/share/fonts/`.
* Mendaftarkan dan mengaktifkan 4 layanan background `systemd --user`.
* Mengonfigurasi shortcut `Alt+Tab` Cinnamon ke Pixel Recent Apps Switcher.

---

## ⌨️ Pintasan Keyboard (Keybindings)

| Pintasan Keyboard | Aksi / Fungsi |
| :--- | :--- |
| **`Alt + Tab`** / **`Super + Tab`** | Membuka Recent Apps Switcher (Tahan Alt, tekan Tab untuk navigasi, lepas Alt untuk memilih). |
| **`Shift + Alt + Tab`** | Menavigasi Recent Apps Switcher ke arah belakang (*reverse*). |
| **`Enter`** / **`Spasi`** | Mengaktifkan jendela yang sedang dipilih pada Recent Apps. |
| **`Esc`** | Menutup overlay App Drawer atau Recent Apps tanpa memilih. |
| **`Delete`** / **`Backspace`** | Menutup jendela yang sedang dipilih pada Recent Apps. |

---

## 🛠️ Kustomisasi & Berkas Konfigurasi

Semua berkas konfigurasi disimpan rapi dalam format JSON / teks standar di `~/.config/`:

| Berkas Konfigurasi | Deskripsi |
| :--- | :--- |
| **`~/.config/pixel-launcher-apps.json`** | Daftar aplikasi yang disematkan di Dock (`name`, `icon`, `cmd`, `bg`, `shape`). Perubahan langsung ter-update di layar tanpa perlu restart. |
| **`~/.config/pixel-widgets-pos.json`** | Koordinat posisi widget desktop (otomatis tersimpan saat widget digeser menggunakan mouse drag). |
| **`~/.config/quick-notes.txt`** | Isi teks catatan cepat pada widget desktop. |
| **`~/.config/weather-config.json`** | Setelan manual koordinat cuaca (kota, latitude, longitude) jika tidak menggunakan auto-detect IP. |

---

## ⚙️ Manajemen Layanan (Systemd Services)

Seluruh komponen desktop berjalan mandiri di latar belakang di bawah kontrol `systemd --user`:

```bash
# Memeriksa status semua komponen
systemctl --user status pixel-dock pixel-desktop pixel-recent-apps pixel-app-drawer

# Memulai ulang dock jika baru mengubah pengaturan
systemctl --user restart pixel-dock.service

# Mematikan sementara
systemctl --user stop pixel-dock pixel-desktop pixel-recent-apps pixel-app-drawer
```

---

## 🗑️ Penghapusan (Uninstallation)

Jika ingin menghapus suite ini dan mengembalikan pintasan desktop Cinnamon ke setelan bawaan:
```bash
cd ~/Applications/pixel-desktop
./uninstall.sh
```

---

## 📄 Lisensi
Didistribusikan di bawah lisensi MIT. Silakan gunakan, modifikasi, dan bagikan secara bebas!
