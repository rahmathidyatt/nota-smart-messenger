from __future__ import annotations


#Nota Smart Messenger - Versi V4
#================================
#Perbaikan utama versi ini:
#1. Menghapus garis bawah pada judul dan metadata kiri.
#2. Menggabungkan (merge) kolom Jarak / X / Tarif / Biaya Jasa / Total
#   pada baris pekerjaan yang terisi, agar rapi ketika jumlah alamat > 1.
#3. Preview gambar tetap dipertahankan, tetapi file PDF dibuat terpisah
#   secara vektor/editable menggunakan ReportLab (bukan sekadar gambar).
#4. No rekening dipaksa tampil 1 baris agar tidak terpotong.
#5. Struktur kode dirapikan agar mudah dirawat dan dikembangkan.


import io
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
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

# Kanvas dasar untuk preview PNG (dipakai seperti koordinat template).
BASE_WIDTH = 1400
BASE_HEIGHT = 990

MONTHS_EN = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Posisi tabel utama.
TABLE_X = [0, 40, 440, 610, 732, 764, 872, 1004, 1209, 1400]
Y_TOP = 264
HEADER_1_H = 38
HEADER_2_H = 78
HEADER_BOTTOM = Y_TOP + HEADER_1_H + HEADER_2_H
ROW_H = 29
TOTAL_H = 60
TOTAL_Y = HEADER_BOTTOM + (MAX_TEMPLATE_ROWS * ROW_H)
TABLE_BOTTOM = TOTAL_Y + TOTAL_H


@dataclass
class CalculationConfig:
    tariff_per_km: int = 900
    minimum_distance_km: float = 10.0
    minimum_bbm: int = 10_000
    service_fee_per_point: int = 5_000
    enable_minimum_bbm: bool = True


@dataclass
class CalculationResult:
    job_count: int
    distance_km: float
    raw_bbm_fee: int
    bbm_fee: int
    service_fee: int
    total: int
    minimum_note: str


# -----------------------------------------------------------------------------
# Helper format
# -----------------------------------------------------------------------------
def format_rupiah(value: float | int) -> str:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = 0
    return f"Rp {number:,}".replace(",", ".")


def format_number_id(value: float | int) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}".replace(".", ",")


def format_date_display(value: date | None) -> str:
    if not value:
        return "-"
    return f"{value.day:02d}-{MONTHS_EN[value.month - 1]}-{str(value.year)[-2:]}"


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip())
    return cleaned.strip("_") or "nota"


# -----------------------------------------------------------------------------
# Logika perhitungan
# -----------------------------------------------------------------------------
def calculate_total(distance_km: float, jobs: List[Dict[str, str]], config: CalculationConfig) -> CalculationResult:
    filled_jobs = [
        row for row in jobs
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
        f"Tarif minimum BBM {format_rupiah(config.minimum_bbm)} digunakan karena jarak kurang dari "
        f"{format_number_id(config.minimum_distance_km)} KM."
        if minimum_applied else "Tarif minimum BBM tidak digunakan."
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


def build_table_rows(jobs: List[Dict[str, str]], result: CalculationResult, config: CalculationConfig) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for index in range(MAX_TEMPLATE_ROWS):
        job = jobs[index] if index < len(jobs) else {"alamat": "", "tugas": "", "keterangan": ""}
        rows.append(
            {
                "No": str(index + 1),
                "Alamat": str(job.get("alamat", "")),
                "Tugas": str(job.get("tugas", "")),
                "Jarak": format_number_id(result.distance_km) if index == 0 and result.job_count else "",
                "X": "X",
                "Tarif": format_rupiah(config.tariff_per_km),
                "Biaya Jasa": format_rupiah(result.service_fee) if index == 0 and result.job_count else "",
                "Total": format_rupiah(result.total) if index == 0 and result.job_count else "Rp -",
                "Keterangan": str(job.get("keterangan", "")),
            }
        )
    return rows


# -----------------------------------------------------------------------------
# Font helper untuk preview PNG
# -----------------------------------------------------------------------------
def _font_path(bold: bool = False) -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    try:
        from matplotlib import font_manager
        prop = font_manager.FontProperties(family="DejaVu Sans", weight="bold" if bold else "normal")
        path = font_manager.findfont(prop, fallback_to_default=True)
        if path and os.path.exists(path):
            return path
    except Exception:
        pass
    return None


def load_font(size: int, scale: int = 2, bold: bool = False) -> ImageFont.ImageFont:
    path = _font_path(bold=bold)
    font_size = max(8, int(size * scale))
    if path:
        return ImageFont.truetype(path, font_size)
    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
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
    x1, y1, x2, y2 = [int(v * scale) for v in box]
    draw.rectangle((x1, y1, x2, y2), fill=fill, outline=outline, width=max(1, width * scale))
    if text and font:
        draw_text_box(draw, text, box, font, scale, align=align, valign=valign, padding=padding)


def draw_single_line_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: Tuple[int, int, int, int],
    font: ImageFont.ImageFont,
    scale: int,
    align: str = "left",
) -> None:
    x1, y1, x2, y2 = [int(v * scale) for v in box]
    text_w, text_h = _text_size(draw, text, font)
    if align == "center":
        x = x1 + ((x2 - x1) - text_w) // 2
    elif align == "right":
        x = x2 - text_w
    else:
        x = x1
    y = y1 + ((y2 - y1) - text_h) // 2
    draw.text((x, y), text, font=font, fill=BLACK)


def draw_metadata_line(draw: ImageDraw.ImageDraw, label: str, value: str, y: int, fonts: Dict[str, ImageFont.ImageFont], scale: int) -> None:
    draw.text((42 * scale, y * scale), label, font=fonts["meta"], fill=BLACK)
    draw.text((178 * scale, y * scale), ":", font=fonts["meta"], fill=BLACK)
    draw.text((193 * scale, y * scale), value, font=fonts["meta"], fill=BLACK)


def draw_split_rupiah_cell(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, scale: int) -> None:
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
    x = 825 * scale
    y = 58 * scale
    brand_font = fonts["brand"]
    tag_font = fonts["tagline"]
    yellow = BRIGHTON_YELLOW_RGB

    for text, color in [("Bright", BLACK), ("o", yellow), ("n", BLACK)]:
        draw.text((x, y), text, font=brand_font, fill=color)
        w, _ = _text_size(draw, text, brand_font)
        x += w

    sep_x = x + (16 * scale)
    draw.line((sep_x, y - (4 * scale), sep_x, y + (86 * scale)), fill=BLACK, width=4 * scale)
    tag_x = sep_x + (18 * scale)
    draw.text((tag_x, y + (2 * scale)), "Bringing", font=tag_font, fill=BLACK)
    draw.text((tag_x, y + (42 * scale)), "Dreams Beyond", font=tag_font, fill=BLACK)


def _draw_main_table_image(draw: ImageDraw.ImageDraw, jobs: List[Dict[str, str]], result: CalculationResult, config: CalculationConfig, fonts: Dict[str, ImageFont.ImageFont], scale: int) -> None:
    x = TABLE_X

    # Header
    draw_cell(draw, (x[0], Y_TOP, x[1], HEADER_BOTTOM), scale, "No", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[1], Y_TOP, x[2], HEADER_BOTTOM), scale, "Alamat", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[2], Y_TOP, x[3], HEADER_BOTTOM), scale, "Tugas", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[3], Y_TOP, x[6], Y_TOP + HEADER_1_H), scale, "Rumus BBM", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[6], Y_TOP, x[7], Y_TOP + HEADER_1_H), scale, "Biaya Jasa\n(Khusus Pasang)", fonts["header_small"], BRIGHTON_YELLOW_RGB, padding=2)
    draw_cell(
        draw,
        (x[7], Y_TOP, x[8], HEADER_BOTTOM),
        scale,
        f"TOTAL\n(Tarif minimum {format_rupiah(config.minimum_bbm)}\nberlaku jika jarak akumulasi\nkurang dari {format_number_id(config.minimum_distance_km)} KM)",
        fonts["header_small"],
        BRIGHTON_YELLOW_RGB,
        padding=3,
    )
    draw_cell(draw, (x[8], Y_TOP, x[9], HEADER_BOTTOM), scale, "Keterangan", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[3], Y_TOP + HEADER_1_H, x[4], HEADER_BOTTOM), scale, f"Jarak\nAkumulasi\n(Min {format_number_id(config.minimum_distance_km)} KM)", fonts["header_small"], BRIGHTON_YELLOW_RGB, padding=2)
    draw_cell(draw, (x[4], Y_TOP + HEADER_1_H, x[5], HEADER_BOTTOM), scale, "X", fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[5], Y_TOP + HEADER_1_H, x[6], HEADER_BOTTOM), scale, format_rupiah(config.tariff_per_km), fonts["header"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[6], Y_TOP + HEADER_1_H, x[7], HEADER_BOTTOM), scale, format_rupiah(config.service_fee_per_point), fonts["header"], BRIGHTON_YELLOW_RGB)

    # Body: kolom biasa (No, Alamat, Tugas, Keterangan)
    for idx in range(MAX_TEMPLATE_ROWS):
        y1 = HEADER_BOTTOM + (idx * ROW_H)
        y2 = y1 + ROW_H
        job = jobs[idx] if idx < len(jobs) else {"alamat": "", "tugas": "", "keterangan": ""}
        draw_cell(draw, (x[0], y1, x[1], y2), scale, str(idx + 1), fonts["body"], WHITE)
        draw_cell(draw, (x[1], y1, x[2], y2), scale, str(job.get("alamat", "")), fonts["body"], WHITE, align="left", padding=5)
        draw_cell(draw, (x[2], y1, x[3], y2), scale, str(job.get("tugas", "")), fonts["body"], WHITE, align="left", padding=5)
        draw_cell(draw, (x[8], y1, x[9], y2), scale, str(job.get("keterangan", "")), fonts["body"], WHITE, align="left", padding=5)

    # Merge pada kolom rumus untuk baris yang terisi.
    merge_count = max(1, result.job_count) if result.job_count else 1
    merge_count = min(merge_count, MAX_TEMPLATE_ROWS)
    merged_y1 = HEADER_BOTTOM
    merged_y2 = HEADER_BOTTOM + (merge_count * ROW_H)

    # Jika hanya 1 baris, tetap jadi 1 kotak normal; jika >1, benar-benar merged.
    draw_cell(draw, (x[3], merged_y1, x[4], merged_y2), scale, format_number_id(result.distance_km) if result.job_count else "", fonts["body"], WHITE)
    draw_cell(draw, (x[4], merged_y1, x[5], merged_y2), scale, "X", fonts["body"], WHITE)
    draw_cell(draw, (x[5], merged_y1, x[6], merged_y2), scale, format_rupiah(config.tariff_per_km), fonts["body"], WHITE)
    draw_cell(draw, (x[6], merged_y1, x[7], merged_y2), scale, format_rupiah(result.service_fee) if result.job_count else "", fonts["body"], WHITE)
    draw_split_rupiah_cell(draw, (x[7], merged_y1, x[8], merged_y2), format_rupiah(result.total) if result.job_count else "Rp -", fonts["body"], scale)

    # Sisa baris setelah merge.
    for idx in range(merge_count, MAX_TEMPLATE_ROWS):
        y1 = HEADER_BOTTOM + (idx * ROW_H)
        y2 = y1 + ROW_H
        draw_cell(draw, (x[3], y1, x[4], y2), scale, "", fonts["body"], WHITE)
        draw_cell(draw, (x[4], y1, x[5], y2), scale, "X", fonts["body"], WHITE)
        draw_cell(draw, (x[5], y1, x[6], y2), scale, format_rupiah(config.tariff_per_km), fonts["body"], WHITE)
        draw_cell(draw, (x[6], y1, x[7], y2), scale, "", fonts["body"], WHITE)
        draw_split_rupiah_cell(draw, (x[7], y1, x[8], y2), "Rp -", fonts["body"], scale)

    # Baris total bawah.
    draw_cell(draw, (x[0], TOTAL_Y, x[7], TABLE_BOTTOM), scale, "TOTAL", fonts["total_label"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[7], TOTAL_Y, x[8], TABLE_BOTTOM), scale, format_rupiah(result.total), fonts["total_amount"], BRIGHTON_YELLOW_RGB)
    draw_cell(draw, (x[8], TOTAL_Y, x[9], TABLE_BOTTOM), scale, "", fonts["body"], BRIGHTON_YELLOW_RGB)


def build_invoice_image_bytes(meta: Dict[str, Any], jobs: List[Dict[str, str]], result: CalculationResult, config: CalculationConfig, scale: int = 2) -> bytes:
    img = Image.new("RGB", (BASE_WIDTH * scale, BASE_HEIGHT * scale), WHITE)
    draw = ImageDraw.Draw(img)

    fonts = {
        "title": load_font(22, scale, bold=True),
        "meta": load_font(20, scale),
        "meta_small": load_font(13, scale),
        "brand": load_font(56, scale, bold=True),
        "tagline": load_font(30, scale, bold=True),
        "header": load_font(20, scale),
        "header_small": load_font(15, scale),
        "body": load_font(19, scale),
        "body_small": load_font(17, scale),
        "total_label": load_font(38, scale),
        "total_amount": load_font(33, scale, bold=True),
        "footer": load_font(20, scale),
        "footer_bold": load_font(20, scale, bold=True),
    }

    # Header atas - tanpa garis bawah.
    draw_text_box(draw, "NOTA SMART MESSENGER", (0, 20, BASE_WIDTH, 55), fonts["title"], scale)

    draw_metadata_line(draw, "Tgl Request", format_date_display(meta.get("tgl_request")), 83, fonts, scale)
    draw_metadata_line(draw, "Nama Agent", str(meta.get("nama_agent") or ""), 113, fonts, scale)
    draw_metadata_line(draw, "Kantor", str(meta.get("kantor") or ""), 143, fonts, scale)
    draw_metadata_line(draw, "Pembayaran", str(meta.get("pembayaran") or ""), 173, fonts, scale)

    draw.text((42 * scale, 203 * scale), "Estimasi Tanggal", font=fonts["meta_small"], fill=BLACK)
    draw.text((42 * scale, 225 * scale), "Pengerjaan", font=fonts["meta_small"], fill=BLACK)
    draw.text((178 * scale, 218 * scale), ":", font=fonts["meta"], fill=BLACK)
    draw.text((193 * scale, 218 * scale), format_date_display(meta.get("estimasi_tanggal")), font=fonts["meta"], fill=BLACK)

    if "transfer" in str(meta.get("pembayaran", "")).lower():
        rekening_text = f"No Rekening (Jika Transfer) : {meta.get('rekening') or ''}"
        draw_single_line_text(draw, rekening_text, (540, 160, 1060, 192), fonts["body_small"], scale, align="left")

    draw_brand(draw, fonts, scale)

    _draw_main_table_image(draw, jobs, result, config, fonts, scale)

    # Footer.
    footer_top = TABLE_BOTTOM
    draw.rectangle((0, footer_top * scale, BASE_WIDTH * scale, BASE_HEIGHT * scale), outline=BLACK, width=scale)
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
# Helper PDF editable / vector (bukan gambar)
# -----------------------------------------------------------------------------
def _wrap_lines_pdf(text: str, font_name: str, font_size: float, max_width: float) -> List[str]:
    text = str(text or "")
    all_lines: List[str] = []
    for original_line in text.split("\n"):
        words = original_line.split()
        if not words:
            all_lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    all_lines.append(current)
                current = word
        if current:
            all_lines.append(current)
    return all_lines


def draw_text_box_pdf(
    pdf: canvas.Canvas,
    page_h: float,
    scale: float,
    text: str,
    box: Tuple[int, int, int, int],
    font_name: str,
    font_size_base: float,
    align: str = "center",
    valign: str = "middle",
    padding: int = 4,
    line_spacing: float = 1.15,
    color=colors.black,
) -> None:
    x1, y1, x2, y2 = [v * scale for v in box]
    font_size = font_size_base * scale
    pad = padding * scale
    max_width = max(1.0, (x2 - x1) - (2 * pad))
    lines = _wrap_lines_pdf(text, font_name, font_size, max_width)
    line_h = font_size * line_spacing
    total_h = line_h * len(lines)

    if valign == "top":
        y_top = y1 + pad
    elif valign == "bottom":
        y_top = y2 - pad - total_h
    else:
        y_top = y1 + ((y2 - y1) - total_h) / 2

    pdf.setFont(font_name, font_size)
    pdf.setFillColor(color)

    current_top = y_top
    for line in lines:
        line_w = pdfmetrics.stringWidth(line, font_name, font_size)
        if align == "left":
            x = x1 + pad
        elif align == "right":
            x = x2 - pad - line_w
        else:
            x = x1 + ((x2 - x1) - line_w) / 2
        baseline_y = page_h - (current_top + font_size)
        pdf.drawString(x, baseline_y, line)
        current_top += line_h


def draw_rect_pdf(pdf: canvas.Canvas, page_h: float, scale: float, box: Tuple[int, int, int, int], fill_color=None, stroke_color=colors.black, stroke_width: float = 1.0) -> None:
    x1, y1, x2, y2 = box
    x = x1 * scale
    y = page_h - (y2 * scale)
    w = (x2 - x1) * scale
    h = (y2 - y1) * scale
    pdf.setLineWidth(stroke_width * scale)
    pdf.setStrokeColor(stroke_color)
    if fill_color is None:
        pdf.setFillColor(colors.white)
        pdf.rect(x, y, w, h, stroke=1, fill=0)
    else:
        pdf.setFillColor(fill_color)
        pdf.rect(x, y, w, h, stroke=1, fill=1)


def draw_cell_pdf(
    pdf: canvas.Canvas,
    page_h: float,
    scale: float,
    box: Tuple[int, int, int, int],
    text: str = "",
    font_name: str = "Helvetica",
    font_size_base: float = 12,
    fill_color=None,
    align: str = "center",
    valign: str = "middle",
    padding: int = 4,
) -> None:
    draw_rect_pdf(pdf, page_h, scale, box, fill_color=fill_color)
    if text:
        draw_text_box_pdf(pdf, page_h, scale, text, box, font_name, font_size_base, align=align, valign=valign, padding=padding)


def draw_split_rupiah_cell_pdf(pdf: canvas.Canvas, page_h: float, scale: float, box: Tuple[int, int, int, int], text: str, font_name: str = "Helvetica", font_size_base: float = 12) -> None:
    draw_rect_pdf(pdf, page_h, scale, box, fill_color=None)
    x1, y1, x2, y2 = box
    raw = str(text or "").strip()
    amount = raw.replace("Rp", "", 1).strip() if raw.startswith("Rp") else raw
    amount = amount or "-"
    draw_text_box_pdf(pdf, page_h, scale, "Rp", (x1 + 8, y1, x1 + 42, y2), font_name, font_size_base, align="left")
    draw_text_box_pdf(pdf, page_h, scale, amount, (x1 + 42, y1, x2 - 8, y2), font_name, font_size_base, align="right")


def draw_brand_pdf(pdf: canvas.Canvas, page_h: float, scale: float) -> None:
    x = 825 * scale
    y_top = 58 * scale
    font_size_brand = 56 * scale
    font_size_tag = 30 * scale

    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", font_size_brand)

    parts = [("Bright", colors.black), ("o", colors.Color(1, 192/255, 0)), ("n", colors.black)]
    cur_x = x
    for part, col in parts:
        pdf.setFillColor(col)
        baseline = page_h - (y_top + font_size_brand)
        pdf.drawString(cur_x, baseline, part)
        cur_x += pdfmetrics.stringWidth(part, "Helvetica-Bold", font_size_brand)

    sep_x = cur_x + (16 * scale)
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(4 * scale)
    pdf.line(sep_x, page_h - ((y_top - 4 * scale)), sep_x, page_h - ((y_top + 86 * scale)))

    tag_x = sep_x + (18 * scale)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", font_size_tag)
    pdf.drawString(tag_x, page_h - ((y_top + 2 * scale) + font_size_tag), "Bringing")
    pdf.drawString(tag_x, page_h - ((y_top + 42 * scale) + font_size_tag), "Dreams Beyond")


def _draw_main_table_pdf(pdf: canvas.Canvas, page_h: float, scale: float, jobs: List[Dict[str, str]], result: CalculationResult, config: CalculationConfig) -> None:
    x = TABLE_X
    yellow = colors.Color(*[c/255 for c in BRIGHTON_YELLOW_RGB])

    # Header
    draw_cell_pdf(pdf, page_h, scale, (x[0], Y_TOP, x[1], HEADER_BOTTOM), "No", "Helvetica", 20, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[1], Y_TOP, x[2], HEADER_BOTTOM), "Alamat", "Helvetica", 20, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[2], Y_TOP, x[3], HEADER_BOTTOM), "Tugas", "Helvetica", 20, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[3], Y_TOP, x[6], Y_TOP + HEADER_1_H), "Rumus BBM", "Helvetica", 20, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[6], Y_TOP, x[7], Y_TOP + HEADER_1_H), "Biaya Jasa\n(Khusus Pasang)", "Helvetica", 15, yellow, padding=2)
    draw_cell_pdf(
        pdf, page_h, scale, (x[7], Y_TOP, x[8], HEADER_BOTTOM),
        f"TOTAL\n(Tarif minimum {format_rupiah(config.minimum_bbm)}\nberlaku jika jarak akumulasi\nkurang dari {format_number_id(config.minimum_distance_km)} KM)",
        "Helvetica", 15, yellow, padding=3,
    )
    draw_cell_pdf(pdf, page_h, scale, (x[8], Y_TOP, x[9], HEADER_BOTTOM), "Keterangan", "Helvetica", 20, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[3], Y_TOP + HEADER_1_H, x[4], HEADER_BOTTOM), f"Jarak\nAkumulasi\n(Min {format_number_id(config.minimum_distance_km)} KM)", "Helvetica", 15, yellow, padding=2)
    draw_cell_pdf(pdf, page_h, scale, (x[4], Y_TOP + HEADER_1_H, x[5], HEADER_BOTTOM), "X", "Helvetica", 20, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[5], Y_TOP + HEADER_1_H, x[6], HEADER_BOTTOM), format_rupiah(config.tariff_per_km), "Helvetica", 20, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[6], Y_TOP + HEADER_1_H, x[7], HEADER_BOTTOM), format_rupiah(config.service_fee_per_point), "Helvetica", 20, yellow)

    # Kolom biasa di setiap row
    for idx in range(MAX_TEMPLATE_ROWS):
        y1 = HEADER_BOTTOM + (idx * ROW_H)
        y2 = y1 + ROW_H
        job = jobs[idx] if idx < len(jobs) else {"alamat": "", "tugas": "", "keterangan": ""}
        draw_cell_pdf(pdf, page_h, scale, (x[0], y1, x[1], y2), str(idx + 1), "Helvetica", 19)
        draw_cell_pdf(pdf, page_h, scale, (x[1], y1, x[2], y2), str(job.get("alamat", "")), "Helvetica", 19, align="left", padding=5)
        draw_cell_pdf(pdf, page_h, scale, (x[2], y1, x[3], y2), str(job.get("tugas", "")), "Helvetica", 19, align="left", padding=5)
        draw_cell_pdf(pdf, page_h, scale, (x[8], y1, x[9], y2), str(job.get("keterangan", "")), "Helvetica", 19, align="left", padding=5)

    merge_count = max(1, result.job_count) if result.job_count else 1
    merge_count = min(merge_count, MAX_TEMPLATE_ROWS)
    merged_y1 = HEADER_BOTTOM
    merged_y2 = HEADER_BOTTOM + (merge_count * ROW_H)

    draw_cell_pdf(pdf, page_h, scale, (x[3], merged_y1, x[4], merged_y2), format_number_id(result.distance_km) if result.job_count else "", "Helvetica", 19)
    draw_cell_pdf(pdf, page_h, scale, (x[4], merged_y1, x[5], merged_y2), "X", "Helvetica", 19)
    draw_cell_pdf(pdf, page_h, scale, (x[5], merged_y1, x[6], merged_y2), format_rupiah(config.tariff_per_km), "Helvetica", 19)
    draw_cell_pdf(pdf, page_h, scale, (x[6], merged_y1, x[7], merged_y2), format_rupiah(result.service_fee) if result.job_count else "", "Helvetica", 19)
    draw_split_rupiah_cell_pdf(pdf, page_h, scale, (x[7], merged_y1, x[8], merged_y2), format_rupiah(result.total) if result.job_count else "Rp -", "Helvetica", 19)

    for idx in range(merge_count, MAX_TEMPLATE_ROWS):
        y1 = HEADER_BOTTOM + (idx * ROW_H)
        y2 = y1 + ROW_H
        draw_cell_pdf(pdf, page_h, scale, (x[3], y1, x[4], y2), "", "Helvetica", 19)
        draw_cell_pdf(pdf, page_h, scale, (x[4], y1, x[5], y2), "X", "Helvetica", 19)
        draw_cell_pdf(pdf, page_h, scale, (x[5], y1, x[6], y2), format_rupiah(config.tariff_per_km), "Helvetica", 19)
        draw_cell_pdf(pdf, page_h, scale, (x[6], y1, x[7], y2), "", "Helvetica", 19)
        draw_split_rupiah_cell_pdf(pdf, page_h, scale, (x[7], y1, x[8], y2), "Rp -", "Helvetica", 19)

    draw_cell_pdf(pdf, page_h, scale, (x[0], TOTAL_Y, x[7], TABLE_BOTTOM), "TOTAL", "Helvetica", 38, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[7], TOTAL_Y, x[8], TABLE_BOTTOM), format_rupiah(result.total), "Helvetica-Bold", 33, yellow)
    draw_cell_pdf(pdf, page_h, scale, (x[8], TOTAL_Y, x[9], TABLE_BOTTOM), "", "Helvetica", 19, yellow)


def build_pdf_bytes(meta: Dict[str, Any], jobs: List[Dict[str, str]], result: CalculationResult, config: CalculationConfig) -> bytes:
    buffer = io.BytesIO()
    page_w, page_h = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    scale = page_w / BASE_WIDTH
    yellow = colors.Color(*[c/255 for c in BRIGHTON_YELLOW_RGB])

    # Judul.
    draw_text_box_pdf(pdf, page_h, scale, "NOTA SMART MESSENGER", (0, 20, BASE_WIDTH, 55), "Helvetica-Bold", 22)

    # Metadata kiri tanpa underline.
    pdf.setFillColor(colors.black)
    font_meta = 20 * scale
    font_meta_small = 13 * scale
    label_x = 42 * scale
    colon_x = 178 * scale
    value_x = 193 * scale

    def meta_line(label: str, value: str, y_base: int):
        yb = page_h - ((y_base * scale) + font_meta)
        pdf.setFont("Helvetica", font_meta)
        pdf.drawString(label_x, yb, label)
        pdf.drawString(colon_x, yb, ":")
        pdf.drawString(value_x, yb, value)

    meta_line("Tgl Request", format_date_display(meta.get("tgl_request")), 83)
    meta_line("Nama Agent", str(meta.get("nama_agent") or ""), 113)
    meta_line("Kantor", str(meta.get("kantor") or ""), 143)
    meta_line("Pembayaran", str(meta.get("pembayaran") or ""), 173)

    pdf.setFont("Helvetica", font_meta_small)
    pdf.drawString(label_x, page_h - ((203 * scale) + font_meta_small), "Estimasi Tanggal")
    pdf.drawString(label_x, page_h - ((225 * scale) + font_meta_small), "Pengerjaan")
    pdf.setFont("Helvetica", font_meta)
    pdf.drawString(colon_x, page_h - ((218 * scale) + font_meta), ":")
    pdf.drawString(value_x, page_h - ((218 * scale) + font_meta), format_date_display(meta.get("estimasi_tanggal")))

    # Rekening 1 baris.
    if "transfer" in str(meta.get("pembayaran", "")).lower():
        rekening_text = f"No Rekening (Jika Transfer) : {meta.get('rekening') or ''}"
        pdf.setFont("Helvetica", 17 * scale)
        pdf.drawString(540 * scale, page_h - ((160 * scale) + (17 * scale)), rekening_text)

    draw_brand_pdf(pdf, page_h, scale)
    _draw_main_table_pdf(pdf, page_h, scale, jobs, result, config)

    # Footer.
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(scale)
    footer_y = page_h - (TABLE_BOTTOM * scale)
    pdf.rect(0, 0, page_w, footer_y, stroke=1, fill=0)

    pdf.setFillColor(colors.black)
    footer_font = 20 * scale
    pdf.setFont("Helvetica", footer_font)
    start_x = 42 * scale
    line1_y = page_h - (((TABLE_BOTTOM + 8) * scale) + footer_font)
    gap = 30 * scale
    pdf.drawString(start_x, line1_y, "Tarif Smart Messenger berlaku Nasional seluruh Cabang Brighton, jika mendapatkan tarif diluar ketentuan diatas silahkan hubungi")
    pdf.drawString(start_x, line1_y - gap, "HRD Pusat: 0812-3051-3989")
    pdf.setFont("Helvetica-Bold", footer_font)
    pdf.drawString(start_x, line1_y - (gap * 2), "Biaya jasa disesuaikan dengan jumlah titik pekerjaan.")
    pdf.setFont("Helvetica", footer_font)
    pdf.drawString(start_x, line1_y - (gap * 3), "Salam #MimpiJadiNyata")

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


# -----------------------------------------------------------------------------
# Contoh data / state
# -----------------------------------------------------------------------------
def set_example_one_point() -> None:
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
# Streamlit UI
# -----------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🧾", layout="wide")
    st.markdown(
        """
        <style>
            .block-container { padding-top: 1.4rem; padding-bottom: 2rem; }
            div[data-testid="stMetricValue"] { font-size: 1.35rem; }
            .stDownloadButton button, .stButton button { width: 100%; }
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
            pembayaran = st.selectbox("Pembayaran", options=["Cash/Transfer", "Cash", "Transfer"], key="pembayaran")
            rekening = st.text_input("No Rekening jika Transfer", key="rekening", placeholder="Contoh: 7115343696 a/n APRIANSYAH ILYAS (BCA)")
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

        png_bytes = build_invoice_image_bytes(meta, jobs, result, config, scale=2)
        pdf_bytes = build_pdf_bytes(meta, jobs, result, config)

        st.markdown("#### Preview Nota (Gambar)")
        st.image(png_bytes, caption="Preview gambar untuk pengecekan tampilan. File PDF dibuat terpisah agar teks tetap editable/selectable.", use_container_width=True)

        file_suffix = sanitize_filename(f"{format_date_display(tgl_request)}_{nama_agent or 'agent'}")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button(
                "Download PDF Nota",
                data=pdf_bytes,
                file_name=f"nota_smart_messenger_{file_suffix}.pdf",
                mime="application/pdf",
            )
        with col_d2:
            st.download_button(
                "Download Gambar Nota",
                data=png_bytes,
                file_name=f"nota_smart_messenger_{file_suffix}.png",
                mime="image/png",
            )

        st.markdown("#### Data tabel")
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    st.markdown(
        """
        <hr style="margin-top: 40px; margin-bottom: 10px;">
        <div style="text-align: center; color: #777; font-size: 13px;">
            created by <b>rh</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

if __name__ == "__main__":
    main()
