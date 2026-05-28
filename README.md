# Nota Smart Messenger

Aplikasi Python sederhana berbasis **Streamlit** untuk membuat nota Smart Messenger, menghitung tagihan pemasangan banner, menampilkan preview nota, dan mengunduh hasil dalam format PDF/HTML.

## Ringkasan Kebutuhan

Aplikasi ini dibuat berdasarkan format nota pada gambar referensi:

- Staff cukup mengisi data request: tanggal, nama agent, kantor, pembayaran, nomor rekening, dan estimasi pengerjaan.
- Staff mengisi data pekerjaan: alamat, tugas, keterangan, jumlah titik pekerjaan, dan jarak akumulasi.
- Sistem menghitung otomatis biaya BBM, biaya jasa, dan total tagihan.
- Output dibuat menyerupai format nota Smart Messenger.

## Rumus Perhitungan

Default aturan:

```text
Tarif BBM per KM       = Rp 900
Minimum jarak          = 10 KM
Tarif minimum BBM      = Rp 10.000
Biaya jasa per titik   = Rp 5.000
```

Rumus:

```text
BBM awal      = Jarak Akumulasi x Tarif per KM
BBM dipakai   = Rp 10.000 jika jarak < 10 KM dan minimum aktif
              = BBM awal jika jarak >= 10 KM
Biaya jasa    = Jumlah titik pekerjaan x Rp 5.000
Total tagihan = BBM dipakai + Biaya jasa
```

Contoh:

```text
18,8 KM x Rp 900 + Rp 5.000 = Rp 21.920
50 KM x Rp 900 + Rp 10.000 = Rp 55.000
```

## Struktur File

```text
nota-smart-messenger/
├── app.py                  # File utama aplikasi
├── requirements.txt        # Daftar library Python
├── README.md               # Dokumentasi penggunaan
└── .streamlit/
    └── config.toml         # Konfigurasi tema Streamlit
```

## Cara Menjalankan di Komputer Lokal

### 1. Install Python

Pastikan Python sudah terpasang. Disarankan memakai Python versi **3.10 sampai 3.12**.

Cek versi Python:

```bash
python --version
```

Jika perintah tersebut tidak berjalan di Windows, coba:

```bash
py --version
```

### 2. Masuk ke Folder Project

Buka terminal atau Command Prompt, lalu arahkan ke folder project:

```bash
cd nota-smart-messenger
```

### 3. Buat Virtual Environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Jika memakai `py`:

```bash
py -m venv .venv
.venv\Scripts\activate
```

Mac/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Library

```bash
pip install -r requirements.txt
```

### 5. Jalankan Aplikasi

```bash
streamlit run app.py
```

Browser akan terbuka otomatis. Jika tidak, buka alamat yang muncul di terminal, biasanya:

```text
http://localhost:8501
```

## Cara Upload ke GitHub

### 1. Buat Repository Baru

Buat repository baru di GitHub, misalnya:

```text
nota-smart-messenger
```

### 2. Upload File

Upload semua file berikut ke repository:

```text
app.py
requirements.txt
README.md
.streamlit/config.toml
```

Pastikan folder `.streamlit` ikut terupload.

## Cara Deploy Agar Bisa Dibuka Online

GitHub biasa hanya menyimpan kode. Untuk aplikasi Python seperti Streamlit, gunakan **Streamlit Community Cloud**.

Langkahnya:

1. Buka Streamlit Community Cloud.
2. Login menggunakan akun GitHub.
3. Klik **New app**.
4. Pilih repository `nota-smart-messenger`.
5. Branch: `main`.
6. Main file path: `app.py`.
7. Klik **Deploy**.

Setelah deploy selesai, aplikasi akan memiliki link online dan bisa langsung dipakai dari browser.

## Cara Pakai Aplikasi

1. Isi **Data Request**:
   - Tgl Request
   - Nama Agent
   - Kantor
   - Pembayaran
   - No Rekening jika Transfer
   - Estimasi Tanggal Pengerjaan

2. Isi **Data Pekerjaan**:
   - Jumlah alamat/titik pekerjaan
   - Jarak akumulasi total perjalanan
   - Alamat tiap titik
   - Tugas tiap titik
   - Keterangan jika ada

3. Cek bagian **Detail Rumus**.

4. Lihat **Preview Nota**.

5. Klik **Download PDF Nota** atau **Download HTML Nota**.

## Catatan Penting

- Jarak yang diinput adalah **jarak akumulasi total**, bukan jarak per alamat.
- Biaya jasa otomatis mengikuti jumlah titik pekerjaan.
- Untuk 2 alamat pemasangan banner, biaya jasa menjadi `2 x Rp 5.000 = Rp 10.000`.
- Aturan tarif dapat diubah dari sidebar jika kantor memperbarui ketentuan.
- Template menampilkan 14 baris seperti format nota asli.

## Troubleshooting

### Perintah `streamlit` tidak dikenali

Pastikan virtual environment aktif, lalu jalankan ulang:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Atau gunakan:

```bash
python -m streamlit run app.py
```

### PDF tidak terdownload

Pastikan `reportlab` sudah terinstall:

```bash
pip install reportlab
```

### Aplikasi error saat deploy

Cek hal berikut:

- File `requirements.txt` ada di repository.
- Main file path di Streamlit Cloud diisi `app.py`.
- Repository bersifat public atau sudah diberi akses oleh Streamlit Cloud.

