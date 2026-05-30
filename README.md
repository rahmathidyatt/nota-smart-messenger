# Nota Smart Messenger

Aplikasi internal sederhana untuk membuat Nota Smart Messenger pemasangan banner. Aplikasi ini dibuat dengan Python dan Streamlit agar bisa langsung dijalankan secara lokal maupun di-deploy ke Streamlit Community Cloud melalui GitHub.

## Fitur

- Input data request: tanggal, nama agent, kantor, pembayaran, nomor rekening, dan estimasi pengerjaan.
- Input jumlah alamat/titik pekerjaan sampai 14 baris.
- Input jarak akumulasi perjalanan messenger.
- Perhitungan otomatis:
  - BBM = jarak akumulasi x tarif per KM.
  - Jika jarak kurang dari batas minimum, BBM memakai tarif minimum.
  - Biaya jasa = jumlah titik pekerjaan x biaya jasa per titik.
  - Total = BBM + biaya jasa.
- Preview nota dalam bentuk gambar.
- Download nota sebagai PDF.
- Download nota sebagai PNG/gambar.
- Tombol contoh 1 alamat dan 2 alamat untuk validasi rumus.

## Kenapa PDF dibuat dari gambar?

Template nota ini memiliki layout fixed seperti Excel. Pada versi sebelumnya, PDF dibuat langsung memakai tabel ReportLab sehingga bagian header, nomor rekening, dan brand bisa pecah atau bergeser saat di-download.

Di versi ini, aplikasi membuat satu gambar nota terlebih dahulu menggunakan Pillow. Gambar yang sama kemudian dipakai untuk:

1. preview di aplikasi,
2. download gambar PNG,
3. download PDF.

Dengan cara ini, hasil PDF akan sama seperti preview dan tidak pecah di bagian header.

## Struktur File

```text
nota-smart-messenger/
├── app.py
├── requirements.txt
├── README.md
└── .streamlit/
    └── config.toml
```

## Cara Menjalankan di Laptop/PC

### 1. Extract ZIP

Extract file project, lalu buka folder project melalui terminal atau VS Code.

```bash
cd nota-smart-messenger
```

### 2. Buat virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Jika `python` tidak terbaca, gunakan:

```bash
py -m venv .venv
.venv\Scripts\activate
```

Mac/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install library

```bash
pip install -r requirements.txt
```

### 4. Jalankan aplikasi

```bash
streamlit run app.py
```

Biasanya browser akan terbuka otomatis. Jika tidak, buka manual:

```text
http://localhost:8501
```

## Cara Deploy ke GitHub + Streamlit Community Cloud

1. Buat repository baru di GitHub, misalnya `nota-smart-messenger`.
2. Upload semua file/folder berikut:
   - `app.py`
   - `requirements.txt`
   - `README.md`
   - folder `.streamlit`
3. Buka Streamlit Community Cloud.
4. Login menggunakan GitHub.
5. Klik **New app**.
6. Pilih repository `nota-smart-messenger`.
7. Branch pilih `main`.
8. Main file path isi:

```text
app.py
```

9. Klik **Deploy**.

Setelah selesai, aplikasi akan memiliki link online dan bisa dipakai langsung dari browser.

## Catatan Penggunaan

- Jarak yang diisi adalah **jarak akumulasi**, bukan jarak per alamat.
- Biaya jasa dihitung dari jumlah titik/alamat yang terisi.
- Jika tarif kantor berubah, ubah dari sidebar aplikasi tanpa perlu mengedit kode.
- Untuk hasil paling rapi, gunakan tombol **Download PDF Nota** atau **Download Gambar Nota** dari preview aplikasi.


## Catatan penting V3

Versi ini menambahkan dependency `matplotlib` untuk memastikan font TrueType selalu tersedia saat nota dirender menjadi gambar/PDF. Tanpa font TrueType, Pillow dapat memakai font default yang terlalu kecil sehingga hasil download terlihat rusak.

Kalau hasil di Streamlit Cloud masih memakai versi lama, buka dashboard app lalu klik **Reboot app** atau **Redeploy** setelah push file terbaru ke GitHub.
