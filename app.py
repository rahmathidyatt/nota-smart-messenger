"""
Aplikasi Nota Smart Messenger
====================================================
Dibuat untuk membantu Staff Operasional menghitung tagihan
Smart Messenger berdasarkan format nota Brighton.

Teknologi: Streamlit + Python + Pillow + ReportLab
Cara menjalankan lokal:
    streamlit run app.py

Catatan rumus utama:
    BBM  = jarak_akumulasi x tarif_per_km
    Jika jarak kurang dari batas minimum, BBM memakai tarif minimum.
    Jasa = jumlah_titik_pekerjaan x biaya_jasa_per_titik
    Total = BBM + Jasa

Contoh dari gambar:
    18,8 KM x Rp900 + Rp5.000 = Rp21.920
    50 KM x Rp900 + Rp10.000 = Rp55.000

Catatan teknis:
    PDF dibuat dari gambar nota yang sama dengan preview.
    Tujuannya agar hasil download PDF selalu rapi, tidak berubah karena masalah
    wrapping teks/logo pada ReportLab Table.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# -----------------------------------------------------------------------------
# Konstanta aplikasi
# -----------------------------------------------------------------------------
APP_TITLE = "Nota Smart Messenger"
MAX_TEMPLATE_ROWS = 14
BRIGHTON_YELLOW = "#ffc000"
BRIGHTON_YELLOW_RGB = (255, 192, 0)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Ukuran dasar mengikuti rasio A4 landscape agar saat masuk PDF tidak gepeng.
# 1400 x 990 = rasio ± 1.414, sama seperti A4 landscape.
BASE_WIDTH = 1400
BASE_HEIGHT = 990

MONTHS_EN = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


@dataclass
class CalculationConfig:
    """Aturan tarif yang bisa diubah dari sidebar aplikasi."""

    tariff_per_km: int = 900
    minimum_distance_km: float = 10.0
    minimum_bbm: int = 10_000
    service_fee_per_point: int = 5_000
    enable_minimum_bbm: bool = True


@dataclass
class CalculationResult:
    """Hasil akhir perhitungan nota."""

    job_count: int
    distance_km: float
    raw_bbm_fee: int
    bbm_fee: int
    service_fee: int
    total: int
    minimum_note: str


# -----------------------------------------------------------------------------
# Helper format angka, tanggal, dan rupiah
# -----------------------------------------------------------------------------
def format_rupiah(value: float | int) -> str:
    """Mengubah angka menjadi format Rupiah Indonesia, contoh: 21920 -> Rp 21.920."""
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = 0
    return f"Rp {number:,}".replace(",", ".")


def format_number_id(value: float | int) -> str:
    """Format angka Indonesia: 18.8 menjadi 18,8 dan 50.0 menjadi 50."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}".replace(".", ",")


def format_date_display(value: date | None) -> str:
    """Format tanggal seperti template nota: 19-May-26."""
    if not value:
        return "-"
    return f"{value.day:02d}-{MONTHS_EN[value.month - 1]}-{str(value.year)[-2:]}"


def sanitize_filename(text: str) -> str:
    """Membersihkan nama file agar aman di Windows/GitHub/Streamlit Cloud."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return cleaned.strip("_") or "nota"


# -----------------------------------------------------------------------------
# Logika bisnis perhitungan nota
# -----------------------------------------------------------------------------
def calculate_total(
    distance_km: float,
    jobs: List[Dict[str, str]],
    config: CalculationConfig,
) -> CalculationResult:
    """
    Menghitung tagihan Smart Messenger.

    Parameter:
    - distance_km: jarak akumulasi rute messenger, bukan jarak per alamat.
    - jobs: daftar pekerjaan/alamat yang diisi user.
    - config: aturan tarif yang dapat disesuaikan.

    Jumlah titik dihitung dari baris yang memiliki alamat atau tugas.
    """
    filled_jobs = [
        row
        for row in jobs
        if str(row.get("alamat", "")).strip() or str(row.get("tugas", "")).strip()
    ]
    job_count = len(filled_jobs)

    raw_bbm_fee = int(round(max(distance_km, 0) * config.tariff_per_km))
    minimum_applied = (
        config.enable_minimum_bbm
        and job_count > 0
        and max(distance_km, 0) < config.minimum_distance_km
    )
    bbm_fee = max(raw_bbm_fee, config.minimum_bbm) if minimum_applied else raw_bbm_fee
    service_fee = job_count * config.service_fee_per_point
    total = bbm_fee + service_fee

    minimum_note = (
        f"Tarif minimum BBM {format_rupiah(config.minimum_bbm)} digunakan karena jarak "
        f"kurang dari {format_number_id(config.minimum_distance_km)} KM."
        if minimum_applied
        else "Tarif minimum BBM tidak digunakan."
    )

    return CalculationResult(
        job_count=job_count,
        distance_km=distance_km,
        raw_bbm_fee=raw_bbm_fee,
        bbm_fee=bbm_fee,
        service_fee=service_fee,
        total=total,
        minimum_note=minimum_note,
    )


def normalize_jobs(job_count: int) -> List[Dict[str, str]]:
    """Mengambil data pekerjaan dari session_state sesuai jumlah titik."""
    jobs: List[Dict[str, str]] = []
    for i in range(job_count):
        jobs.append(
            {
                "alamat": st.session_state.get(f"alamat_{i}", ""),
                "tugas": st.session_state.get(f"tugas_{i}", "Pasang Banner"),
                "keterangan": st.session_state.get(f"keterangan_{i}", ""),
            }
        )
    return jobs


def build_table_rows(
    jobs: List[Dict[str, str]],
    result: CalculationResult,
    config: CalculationConfig,
) -> List[Dict[str, str]]:
    """
    Membuat 14 baris sesuai format template.
    Jarak, biaya jasa, dan total hanya ditampilkan di baris pertama seperti contoh nota.
    """
    rows: List[Dict[str, str]] = []
    for index in range(MAX_TEMPLATE_ROWS):
        job = jobs[index] if index < len(jobs) else {"alamat": "", "tugas": "", "keterangan": ""}
        is_first_row = index == 0
        rows.append(
            {
                "No": str(index + 1),
                "Alamat": str(job.get("alamat", "")),
                "Tugas": str(job.get("tugas", "")),
                "Jarak": format_number_id(result.distance_km) if is_first_row and result.job_count else "",
                "X": "X",
                "Tarif": format_rupiah(config.tariff_per_km),
                "Biaya Jasa": format_rupiah(result.service_fee) if is_first_row and result.job_count else "",
                "Total": format_rupiah(result.total) if is_first_row and result.job_count else "Rp -",
                "Keterangan": str(job.get("keterangan", "")),
            }
        )
    return rows


# -----------------------------------------------------------------------------
# Helper rendering gambar menggunakan Pillow
# -----------------------------------------------------------------------------
def _font_path(bold: bool = False) -> str | None:
    """
    Mencari file font TrueType yang tersedia di komputer/server.

    Kenapa dibuat panjang?
    Pada beberapa deployment, terutama Streamlit Cloud atau Windows tertentu,
    Pillow bisa gagal menemukan font sistem. Kalau Pillow memakai font default,
    hasil nota akan terlihat sangat kecil seperti gambar rusak. Karena itu kita
    cari font dari beberapa lokasi umum, lalu fallback ke font bawaan Matplotlib.
    """
    candidates = [
        # Linux/Streamlit Cloud umum
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        # Windows umum
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        # macOS umum
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]

    for path in candidates:
        if path and os.path.exists(path):
            return path

    # Fallback paling aman: Matplotlib membawa DejaVu Sans sendiri.
    # Tidak perlu menyertakan file font manual di project.
    try:
        from matplotlib import font_manager

        family = "DejaVu Sans"
        prop = font_manager.FontProperties(family=family, weight="bold" if bold else "normal")
        path = font_manager.findfont(prop, fallback_to_default=True)
        if path and os.path.exists(path):
            return path
    except Exception:
        pass

    return None


def load_font(size: int, scale: int = 2, bold: bool = False) -> ImageFont.ImageFont:
    """
    Load font TrueType dengan ukuran yang ikut skala gambar.

    Jika TrueType tidak ditemukan, aplikasi tetap berjalan dengan font default
    Pillow yang diperbesar. Namun normalnya fallback Matplotlib di atas sudah
    mencegah teks menjadi terlalu kecil.
    """
    font_size = max(8, int(size * scale))
    path = _font_path(bold=bold)
    if path:
        return ImageFont.truetype(path, font_size)

    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    """Mengukur lebar dan tinggi teks pada canvas aktual."""
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> List[str]:
    """Membungkus teks agar tidak keluar dari kotak."""
    text = str(text or "")
    final_lines: List[str] = []
    for original_line in text.split("\n"):
        words = original_line.split()
        if not words:
            final_lines.append("")
            continue

        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            candidate_width, _ = _text_size(draw, candidate, font)
            if candidate_width <= max_width:
                current = candidate
            else:
                if current:
                    final_lines.append(current)
                current = word
        if current:
            final_lines.append(current)
    return final_lines


def draw_text_box(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: Tuple[int, int, int, int],
    font: ImageFont.ImageFont,
    scale: int,
    fill: Tuple[int, int, int] = BLACK,
    align: str = "center",
    valign: str = "middle",
    padding: int = 4,
    line_spacing: float = 1.15,
) -> None:
    """Menulis teks di dalam kotak dengan wrapping, alignment, dan padding."""
    x1, y1, x2, y2 = [int(v * scale) for v in box]
    pad = padding * scale
    max_width = max(1, (x2 - x1) - (2 * pad))
    lines = _wrap_lines(draw, text, font, max_width)

    _, sample_h = _text_size(draw, "Ag", font)
    line_h = max(1, int(sample_h * line_spacing))
    total_h = line_h * len(lines)

    if valign == "top":
        y = y1 + pad
    elif valign == "bottom":
        y = y2 - pad - total_h
    else:
        y = y1 + ((y2 - y1) - total_h) // 2

    for line in lines:
        line_w, _ = _text_size(draw, line, font)
        if align == "left":
            x = x1 + pad
        elif align == "right":
            x = x2 - pad - line_w
        else:
            x = x1 + ((x2 - x1) - line_w) // 2
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h


def draw_cell(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    scale: int,
    text: str = "",
    font: ImageFont.ImageFont | None = None,
    fill: Tuple[int, int, int] | None = None,
    outline: Tuple[int, int, int] = BLACK,
    width: int = 1,
    align: str = "center",
    valign: str = "middle",
    padding: int = 4,
) -> None:
    """Menggambar satu cell tabel beserta isi teksnya."""
    x1, y1, x2, y2 = [int(v * scale) for v in box]
    draw.rectangle((x1, y1, x2, y2), fill=fill, outline=outline, width=max(1, width * scale))
    if text and font:
        draw_text_box(draw, text, box, font, scale, align=align, valign=valign, padding=padding)


def draw_underlined_value(
    draw: ImageDraw.ImageDraw,
    value: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    scale: int,
) -> None:
    """Menulis value metadata dengan underline seperti template Excel."""
    sx, sy = x * scale, y * scale
    draw.text((sx, sy), value, font=font, fill=BLACK)
    text_w, text_h = _text_size(draw, value, font)
    underline_y = sy + text_h + (2 * scale)
    draw.line((sx, underline_y, sx + text_w, underline_y), fill=BLACK, width=max(1, scale))


def draw_metadata_line(
    draw: ImageDraw.ImageDraw,
    label: str,
    value: str,
    y: int,
    fonts: Dict[str, ImageFont.ImageFont],
    scale: int,
) -> None:
    """Menggambar baris metadata kiri: label : value."""
    draw.text((42 * scale, y * scale), label, font=fonts["meta"], fill=BLACK)
    draw.text((178 * scale, y * scale), ":", font=fonts["meta"], fill=BLACK)
    draw_underlined_value(draw, value, 193, y, fonts["meta"], scale)


def draw_split_rupiah_cell(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    text: str,
    font: ImageFont.ImageFont,
    scale: int,
) -> None:
    """Menggambar kolom total: Rp di kiri, angka di kanan, mengikuti contoh template."""
    draw_cell(draw, box, scale, fill=WHITE)
    x1, y1, x2, y2 = box
    raw = str(text or "").strip()
    if raw.startswith("Rp"):
        amount = raw.replace("Rp", "", 1).strip() or "-"
    else:
        amount = raw or "-"

    draw_text_box(draw, "Rp", (x1 + 8, y1, x1 + 42, y2), font, scale, align="left")
    draw_text_box(draw, amount, (x1 + 42, y1, x2 - 8, y2), font, scale, align="right")


def draw_brand(draw: ImageDraw.ImageDraw, fonts: Dict[str, ImageFont.ImageFont], scale: int) -> None:
    """Menggambar teks brand Brighton di kanan atas secara manual agar tidak pecah di PDF."""
    x = 745 * scale
    y = 58 * scale

    brand_font = fonts["brand"]
    tag_font = fonts["tagline"]
    yellow = BRIGHTON_YELLOW_RGB

    # Tulis 'Brighton' dengan huruf o berwarna kuning.
    for text, color in [("Bright", BLACK), ("o", yellow), ("n", BLACK)]:
        draw.text((x, y), text, font=brand_font, fill=color)
        w, _ = _text_size(draw, text, brand_font)
        x += w

    sep_x = x + (22 * scale)
    draw.line((sep_x, y - (4 * scale), sep_x, y + (88 * scale)), fill=BLACK, width=4 * scale)

    tag_x = sep_x + (26 * scale)
    draw.text((tag_x, y + (1 * scale)), "Bringing", font=tag_font, fill=BLACK)
    draw.text((tag_x, y + (43 * scale)), "Dreams Beyond", font=tag_font, fill=BLACK)


def build_invoice_image_bytes(
    meta: Dict[str, Any],
    table_rows: List[Dict[str, str]],
    result: CalculationResult,
    config: CalculationConfig,
    scale: int = 2,
) -> bytes:
    """
    Membuat gambar nota PNG.

    Gambar ini menjadi sumber utama untuk:
    1. Preview di aplikasi.
    2. Download gambar PNG.
    3. Download PDF, agar layout PDF sama persis dengan preview.
    """
    img = Image.new("RGB", (BASE_WIDTH * scale, BASE_HEIGHT * scale), WHITE)
    draw = ImageDraw.Draw(img)

    fonts = {
        "title": load_font(22, scale, bold=True),
        "meta": load_font(20, scale),
        "meta_small": load_font(13, scale),
        "brand": load_font(62, scale, bold=True),
        "tagline": load_font(33, scale, bold=True),
        "header": load_font(20, scale),
        "header_small": load_font(15, scale),
        "body": load_font(20, scale),
        "body_small": load_font(18, scale),
        "total_label": load_font(38, scale),
        "total_amount": load_font(34, scale, bold=True),
        "footer": load_font(20, scale),
        "footer_bold": load_font(20, scale, bold=True),
    }

    # ------------------------------------------------------------------
    # Header nota
    # ------------------------------------------------------------------
    draw_text_box(draw, "NOTA SMART MESSENGER", (0, 20, BASE_WIDTH, 55), fonts["title"], scale)
    draw.line((581 * scale, 52 * scale, 819 * scale, 52 * scale), fill=BLACK, width=2 * scale)

    draw_metadata_line(draw, "Tgl Request", format_date_display(meta.get("tgl_request")), 83, fonts, scale)
    draw_metadata_line(draw, "Nama Agent", str(meta.get("nama_agent") or ""), 113, fonts, scale)
    draw_metadata_line(draw, "Kantor", str(meta.get("kantor") or ""), 143, fonts, scale)
    draw_metadata_line(draw, "Pembayaran", str(meta.get("pembayaran") or ""), 173, fonts, scale)

    # Estimasi tanggal memakai dua baris kecil seperti template.
    draw.text((42 * scale, 203 * scale), "Estimasi Tanggal", font=fonts["meta_small"], fill=BLACK)
    draw.text((42 * scale, 225 * scale), "Pengerjaan", font=fonts["meta_small"], fill=BLACK)
    draw.text((178 * scale, 218 * scale), ":", font=fonts["meta"], fill=BLACK)
    draw_underlined_value(draw, format_date_display(meta.get("estimasi_tanggal")), 193, 218, fonts["meta"], scale)

    # No rekening diposisikan di tengah supaya tidak tabrakan dengan logo.
    rekening_text = ""
    if "transfer" in str(meta.get("pembayaran", "")).lower():
        rekening_text = f"No Rekening (Jika Transfer) : {meta.get('rekening') or ''}"
    draw_text_box(draw, rekening_text, (528, 164, 980, 226), fonts["body_small"], scale, align="left", valign="middle")

    draw_brand(draw, fonts, scale)

    # ------------------------------------------------------------------
    # Tabel utama
    # ------------------------------------------------------------------
    x = [0, 40, 440, 610, 732, 764, 872, 1004, 1209, 1400]
    y_top = 264
    header_1_h = 38
    header_2_h = 78
    header_bottom = y_top + header_1_h + header_2_h
    row_h = 29
    total_h = 60
    total_y = header_bottom + (MAX_TEMPLATE_ROWS * row_h)
    table_bottom = total_y + total_h

    # Header row-spans dan col-spans.
    draw_cell(draw, (x[0], y_top, x[1], header_bottom), scale, "No", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[1], y_top, x[2], header_bottom), scale, "Alamat", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[2], y_top, x[3], header_bottom), scale, "Tugas", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[3], y_top, x[6], y_top + header_1_h), scale, "Rumus BBM", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[6], y_top, x[7], y_top + header_1_h), scale, "Biaya Jasa\n(Khusus Pasang)", fonts["header_small"], BRIGHTON_YELLOW_RGB, padding=2)
    draw_cell(
        draw,
        (x[7], y_top, x[8], header_bottom),
        scale,
        f"TOTAL\n(Tarif minimum {format_rupiah(config.minimum_bbm)}\nberlaku jika jarak akumulasi\nkurang dari {format_number_id(config.minimum_distance_km)} KM)",
        fonts["header_small"],
        BRIGHTON_YELLOW_RGB,
        padding=3,
    )
    draw_cell(draw, (x[8], y_top, x[9], header_bottom), scale, "Keterangan", fonts["header"], BRIGHTON_YELLOW_RGB)

    draw_cell(draw, (x[3], y_top + header_1_h, x[4], header_bottom), scale, f"Jarak\nAkumulasi\n(Min {format_number_id(config.minimum_distance_km)} KM)", fonts["header_small"], BRIGHTON_YELLOW_RGB, padding=2)
    draw_cell(draw, (x[4], y_top + header_1_h, x[5], header_bottom), scale, "X", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[5], y_top + header_1_h, x[6], header_bottom), scale, format_rupiah(config.tariff_per_km), fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[6], y_top + header_1_h, x[7], header_bottom), scale, format_rupiah(config.service_fee_per_point), fonts["header"], BRIGHTON_YELLOW_RGB)

    # Body 14 baris.
    for idx, row in enumerate(table_rows):
        y1 = header_bottom + (idx * row_h)
        y2 = y1 + row_h
        draw_cell(draw, (x[0], y1, x[1], y2), scale, row["No"], fonts["body"], WHITE)
        draw_cell(draw, (x[1], y1, x[2], y2), scale, row["Alamat"], fonts["body"], WHITE, align="left", padding=5)
        draw_cell(draw, (x[2], y1, x[3], y2), scale, row["Tugas"], fonts["body"], WHITE, align="left", padding=5)
        draw_cell(draw, (x[3], y1, x[4], y2), scale, row["Jarak"], fonts["body"], WHITE)
        draw_cell(draw, (x[4], y1, x[5], y2), scale, row["X"], fonts["body"], WHITE)
        draw_cell(draw, (x[5], y1, x[6], y2), scale, row["Tarif"], fonts["body"], WHITE)
        draw_cell(draw, (x[6], y1, x[7], y2), scale, row["Biaya Jasa"], fonts["body"], WHITE)
        draw_split_rupiah_cell(draw, (x[7], y1, x[8], y2), row["Total"], fonts["body"], scale)
        draw_cell(draw, (x[8], y1, x[9], y2), scale, row["Keterangan"], fonts["body"], WHITE, align="left", padding=5)

    # Baris TOTAL bawah.
    draw_cell(draw, (x[0], total_y, x[7], table_bottom), scale, "TOTAL", fonts["total_label"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[7], total_y, x[8], table_bottom), scale, format_rupiah(result.total), fonts["total_amount"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[8], total_y, x[9], table_bottom), scale, "", fonts["body"], BRIGHTON_YELLOW_RGB)

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    footer_top = table_bottom
    footer_bottom = BASE_HEIGHT
    draw.rectangle((0, footer_top * scale, BASE_WIDTH * scale, footer_bottom * scale), outline=BLACK, width=scale)

    footer_x = 42 * scale
    footer_y = (footer_top + 8) * scale
    line_gap = 30 * scale
    draw.text((footer_x, footer_y), "Tarif Smart Messenger berlaku Nasional seluruh Cabang Brighton, jika mendapatkan tarif diluar ketentuan diatas silahkan hubungi", font=fonts["footer"], fill=BLACK)
    draw.text((footer_x, footer_y + line_gap), "HRD Pusat: 0812-3051-3989", font=fonts["footer"], fill=BLACK)
    draw.text((footer_x, footer_y + (line_gap * 2)), "Biaya jasa disesuaikan dengan jumlah titik pekerjaan.", font=fonts["footer_bold"], fill=BLACK)
    draw.text((footer_x, footer_y + (line_gap * 3)), "Salam #MimpiJadiNyata", font=fonts["footer"], fill=BLACK)

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output.read()


# -----------------------------------------------------------------------------
# Renderer PDF
# -----------------------------------------------------------------------------
def build_pdf_bytes(
    meta: Dict[str, Any],
    table_rows: List[Dict[str, str]],
    result: CalculationResult,
    config: CalculationConfig,
) -> bytes:
    """
    Membuat PDF dari gambar nota.

    Pendekatan ini dipilih karena template nota berbentuk fixed layout seperti Excel.
    Jika dibuat langsung dengan Table ReportLab, teks brand/rekening bisa wrap dan bergeser.
    Dengan metode gambar -> PDF, hasil PDF sama persis dengan preview dan download PNG.
    """
    png_bytes = build_invoice_image_bytes(meta, table_rows, result, config, scale=2)

    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))

    # Gambar dipasang memenuhi halaman A4 landscape.
    # Ukuran gambar sudah mengikuti rasio A4, jadi tidak perlu preserveAspectRatio.
    image_reader = ImageReader(io.BytesIO(png_bytes))
    pdf.drawImage(image_reader, 0, 0, width=page_width, height=page_height)
    pdf.showPage()
    pdf.save()

    buffer.seek(0)
    return buffer.read()


# -----------------------------------------------------------------------------
# Session state dan contoh data
# -----------------------------------------------------------------------------
def set_example_one_point() -> None:
    """Mengisi form sesuai contoh gambar pertama: 1 alamat, jarak 18,8 KM."""
    st.session_state.job_count = 1
    st.session_state.distance_km = 18.8
    st.session_state.nama_agent = "RUDY"
    st.session_state.kantor = "HUB CIBUBUR"
    st.session_state.pembayaran = "Cash/Transfer"
    st.session_state.rekening = "7115343696 a/n APRIANSYAH ILYAS (BCA)"
    st.session_state.alamat_0 = "Workshop Multiteknik"
    st.session_state.tugas_0 = "Pasang Banner"
    st.session_state.keterangan_0 = ""


def set_example_two_points() -> None:
    """Mengisi form sesuai contoh gambar keempat: 2 alamat, jasa 2 titik."""
    st.session_state.job_count = 2
    st.session_state.distance_km = 50.0
    st.session_state.nama_agent = "RUDY"
    st.session_state.kantor = "HUB CIBUBUR"
    st.session_state.pembayaran = "Cash/Transfer"
    st.session_state.rekening = "7115343696 a/n APRIANSYAH ILYAS (BCA)"
    st.session_state.alamat_0 = "Workshop Multiteknik"
    st.session_state.tugas_0 = "Pasang Banner"
    st.session_state.keterangan_0 = ""
    st.session_state.alamat_1 = "alamat 2"
    st.session_state.tugas_1 = "Pasang Banner"
    st.session_state.keterangan_1 = ""


def reset_form() -> None:
    """Mengosongkan data pekerjaan dan mengembalikan form ke kondisi awal."""
    st.session_state.job_count = 1
    st.session_state.distance_km = 0.0
    st.session_state.nama_agent = ""
    st.session_state.kantor = "HUB CIBUBUR"
    st.session_state.pembayaran = "Cash/Transfer"
    st.session_state.rekening = "7115343696 a/n APRIANSYAH ILYAS (BCA)"
    for i in range(MAX_TEMPLATE_ROWS):
        st.session_state[f"alamat_{i}"] = ""
        st.session_state[f"tugas_{i}"] = "Pasang Banner"
        st.session_state[f"keterangan_{i}"] = ""


# -----------------------------------------------------------------------------
# Tampilan Streamlit
# -----------------------------------------------------------------------------
def main() -> None:
    """Entry point aplikasi Streamlit."""
    st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide")

    st.markdown(
        """
        <style>
            .block-container { padding-top: 1.4rem; padding-bottom: 2rem; }
            div[data-testid="stMetricValue"] { font-size: 1.35rem; }
            .stDownloadButton button { width: 100%; }
            .stButton button { width: 100%; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "job_count" not in st.session_state:
        set_example_one_point()

    st.title("🧾 Nota Smart Messenger")
    st.caption("Aplikasi internal sederhana untuk membuat nota pemasangan banner dan menghitung tagihan messenger secara otomatis.")

    with st.sidebar:
        st.header("⚙️ Aturan Perhitungan")
        tariff_per_km = st.number_input("Tarif BBM per KM", min_value=0, value=900, step=100)
        minimum_distance_km = st.number_input("Batas minimum jarak (KM)", min_value=0.0, value=10.0, step=0.5)
        minimum_bbm = st.number_input("Tarif minimum BBM", min_value=0, value=10_000, step=500)
        service_fee_per_point = st.number_input("Biaya jasa per titik", min_value=0, value=5_000, step=500)
        enable_minimum_bbm = st.checkbox("Aktifkan tarif minimum BBM", value=True)

        st.divider()
        st.subheader("🧪 Data Contoh")
        st.button("Contoh 1 alamat", on_click=set_example_one_point)
        st.button("Contoh 2 alamat", on_click=set_example_two_points)
        st.button("Kosongkan form", on_click=reset_form)

    config = CalculationConfig(
        tariff_per_km=tariff_per_km,
        minimum_distance_km=minimum_distance_km,
        minimum_bbm=minimum_bbm,
        service_fee_per_point=service_fee_per_point,
        enable_minimum_bbm=enable_minimum_bbm,
    )

    input_col, preview_col = st.columns([0.93, 1.35], gap="large")

    with input_col:
        st.subheader("1. Data Request")
        col_a, col_b = st.columns(2)
        with col_a:
            tgl_request = st.date_input("Tgl Request", value=date.today())
            nama_agent = st.text_input("Nama Agent", key="nama_agent", placeholder="Contoh: RUDY")
            kantor = st.text_input("Kantor", key="kantor", placeholder="Contoh: HUB CIBUBUR")
        with col_b:
            pembayaran = st.selectbox(
                "Pembayaran",
                options=["Cash/Transfer", "Cash", "Transfer"],
                key="pembayaran",
            )
            rekening = st.text_input(
                "No Rekening jika Transfer",
                key="rekening",
                placeholder="Contoh: 7115343696 a/n APRIANSYAH ILYAS (BCA)",
            )
            estimasi_tanggal = st.date_input("Estimasi Tanggal Pengerjaan", value=date.today())

        st.subheader("2. Data Pekerjaan")
        col_c, col_d = st.columns(2)
        with col_c:
            job_count = st.number_input(
                "Jumlah alamat/titik pekerjaan",
                min_value=1,
                max_value=MAX_TEMPLATE_ROWS,
                key="job_count",
                step=1,
                help="Biaya jasa otomatis dihitung dari jumlah titik yang terisi.",
            )
        with col_d:
            distance_km = st.number_input(
                "Jarak Akumulasi (KM)",
                min_value=0.0,
                key="distance_km",
                step=0.1,
                format="%.1f",
                help="Isi total jarak akumulasi perjalanan messenger, bukan jarak per alamat.",
            )

        with st.expander("Isi alamat, tugas, dan keterangan", expanded=True):
            for i in range(int(job_count)):
                st.markdown(f"**Titik {i + 1}**")
                row_col_1, row_col_2 = st.columns([1.3, 0.85])
                with row_col_1:
                    st.text_input("Alamat", key=f"alamat_{i}", placeholder="Contoh: Workshop Multiteknik", label_visibility="collapsed")
                with row_col_2:
                    st.text_input("Tugas", key=f"tugas_{i}", placeholder="Pasang Banner", label_visibility="collapsed")
                st.text_input("Keterangan", key=f"keterangan_{i}", placeholder="Opsional", label_visibility="collapsed")
                if i < int(job_count) - 1:
                    st.divider()

    jobs = normalize_jobs(int(st.session_state.job_count))
    result = calculate_total(st.session_state.distance_km, jobs, config)
    table_rows = build_table_rows(jobs, result, config)
    meta = {
        "tgl_request": tgl_request,
        "nama_agent": nama_agent,
        "kantor": kantor,
        "pembayaran": pembayaran,
        "rekening": rekening,
        "estimasi_tanggal": estimasi_tanggal,
    }

    with preview_col:
        st.subheader("3. Preview & Hasil")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Titik", result.job_count)
        m2.metric("BBM", format_rupiah(result.bbm_fee))
        m3.metric("Jasa", format_rupiah(result.service_fee))
        m4.metric("Total", format_rupiah(result.total))

        with st.expander("Detail rumus", expanded=True):
            st.write(f"Jarak Akumulasi: **{format_number_id(result.distance_km)} KM**")
            st.write(f"BBM awal: **{format_number_id(result.distance_km)} × {format_rupiah(config.tariff_per_km)} = {format_rupiah(result.raw_bbm_fee)}**")
            st.write(f"BBM dipakai: **{format_rupiah(result.bbm_fee)}**. {result.minimum_note}")
            st.write(f"Jasa pasang: **{result.job_count} titik × {format_rupiah(config.service_fee_per_point)} = {format_rupiah(result.service_fee)}**")
            st.success(f"Total tagihan: {format_rupiah(result.total)}")

        st.markdown("#### Preview Nota")
        png_bytes = build_invoice_image_bytes(meta, table_rows, result, config, scale=2)
        pdf_bytes = build_pdf_bytes(meta, table_rows, result, config)
        st.image(png_bytes, caption="Preview ini sama dengan hasil download PDF dan gambar.", use_container_width=True)

        file_suffix = sanitize_filename(f"{format_date_display(tgl_request)}_{nama_agent or 'agent'}")

        download_col_1, download_col_2 = st.columns(2)
        with download_col_1:
            st.download_button(
                "Download PDF Nota",
                data=pdf_bytes,
                file_name=f"nota_smart_messenger_{file_suffix}.pdf",
                mime="application/pdf",
            )
        with download_col_2:
            st.download_button(
                "Download Gambar Nota",
                data=png_bytes,
                file_name=f"nota_smart_messenger_{file_suffix}.png",
                mime="image/png",
            )

        st.markdown("#### Data tabel")
        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
