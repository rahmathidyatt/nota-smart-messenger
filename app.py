"""
Aplikasi Nota Smart Messenger
====================================================
Dibuat untuk membantu Staff Operasional menghitung tagihan
Smart Messenger berdasarkan format nota Brighton.

Teknologi: Streamlit + Python
Cara menjalankan lokal:
    streamlit run app.py

Catatan rumus utama:
    BBM  = max(jarak_akumulasi * tarif_per_km, minimum_bbm) jika minimum aktif
    Jasa = jumlah_titik_pekerjaan * biaya_jasa_per_titik
    Total = BBM + Jasa

Contoh dari gambar:
    18,8 KM x Rp900 + Rp5.000 = Rp21.920
    50 KM x Rp900 + Rp10.000 = Rp55.000
"""

from __future__ import annotations

import html
import io
from dataclasses import dataclass
from datetime import date
from typing import List, Dict, Any

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# -----------------------------------------------------------------------------
# Konstanta tampilan dan format dasar
# -----------------------------------------------------------------------------
APP_TITLE = "Nota Smart Messenger"
MAX_TEMPLATE_ROWS = 14
BRIGHTON_YELLOW = "#ffc000"
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
    """Menyimpan aturan perhitungan agar mudah diubah dari sidebar."""

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
    """Format tanggal seperti template: 19-May-26."""
    if not value:
        return "-"
    return f"{value.day:02d}-{MONTHS_EN[value.month - 1]}-{str(value.year)[-2:]}"


def safe_text(value: Any) -> str:
    """Escape teks agar aman saat dirender ke HTML."""
    return html.escape(str(value or ""), quote=True)


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
    - distance_km: jarak akumulasi rute messenger.
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
    Nilai jarak, jasa, dan total hanya diletakkan pada baris pertama seperti contoh nota.
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
# Renderer HTML untuk preview dan download HTML
# -----------------------------------------------------------------------------
def build_invoice_html(
    meta: Dict[str, Any],
    table_rows: List[Dict[str, str]],
    result: CalculationResult,
    config: CalculationConfig,
    standalone: bool = True,
) -> str:
    """Membuat tampilan nota dalam bentuk HTML yang mirip template gambar."""
    rekening_text = ""
    if str(meta.get("pembayaran", "")).lower().find("transfer") >= 0:
        rekening_text = f"No Rekening (Jika Transfer) : {safe_text(meta.get('rekening'))}"

    rows_html = "".join(
        f"""
        <tr>
            <td class="center narrow">{safe_text(row['No'])}</td>
            <td>{safe_text(row['Alamat'])}</td>
            <td>{safe_text(row['Tugas'])}</td>
            <td class="center">{safe_text(row['Jarak'])}</td>
            <td class="center narrow">{safe_text(row['X'])}</td>
            <td class="center">{safe_text(row['Tarif'])}</td>
            <td class="center">{safe_text(row['Biaya Jasa'])}</td>
            <td class="right total-col">{safe_text(row['Total'])}</td>
            <td>{safe_text(row['Keterangan'])}</td>
        </tr>
        """
        for row in table_rows
    )

    css = f"""
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            font-family: Arial, Helvetica, sans-serif;
            color: #000;
            background: #fff;
        }}
        .invoice-page {{
            width: 100%;
            max-width: 1280px;
            margin: 0 auto;
            padding: 18px 18px 10px 18px;
            background: #fff;
        }}
        .top-title {{
            text-align: center;
            font-weight: 800;
            text-decoration: underline;
            font-size: 20px;
            letter-spacing: .2px;
            margin-bottom: 4px;
        }}
        .brand {{
            text-align: right;
            font-weight: 900;
            font-size: 56px;
            line-height: 1;
            margin-top: -4px;
        }}
        .brand .yellow {{ color: {BRIGHTON_YELLOW}; }}
        .brand-sub {{
            font-size: 18px;
            font-weight: 700;
            color: #555;
            margin-left: 8px;
            vertical-align: middle;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: 420px 1fr;
            gap: 30px;
            margin: 4px 0 28px 0;
            font-size: 18px;
        }}
        .meta-line {{
            display: grid;
            grid-template-columns: 135px 10px 1fr;
            margin: 4px 0;
        }}
        .meta-small {{ font-size: 12px; line-height: 1.05; }}
        .underline {{ text-decoration: underline; }}
        .rekening {{
            align-self: end;
            padding-bottom: 36px;
            font-size: 18px;
        }}
        table.invoice {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            font-size: 18px;
        }}
        .invoice th, .invoice td {{
            border: 1px solid #000;
            padding: 3px 5px;
            vertical-align: middle;
            height: 27px;
            word-wrap: break-word;
        }}
        .invoice th {{
            background: {BRIGHTON_YELLOW};
            font-weight: 500;
            text-align: center;
        }}
        .invoice .subhead {{ font-size: 14px; line-height: 1.25; }}
        .center {{ text-align: center; }}
        .right {{ text-align: right; }}
        .narrow {{ width: 36px; }}
        .total-row td {{
            background: {BRIGHTON_YELLOW};
            font-weight: 900;
            font-size: 32px;
            height: 58px;
        }}
        .total-label {{ text-align: center; letter-spacing: 1px; }}
        .total-amount {{ text-align: center; }}
        .footnote {{
            border: 1px solid #000;
            border-top: none;
            padding: 6px 38px 2px 38px;
            font-size: 20px;
            line-height: 1.45;
        }}
        .footnote strong {{ font-weight: 800; }}
        .calc-info {{
            margin-top: 12px;
            padding: 12px 14px;
            border: 1px dashed #888;
            border-radius: 10px;
            font-size: 14px;
            background: #fffdf3;
        }}
        @media print {{
            .no-print {{ display: none !important; }}
            .invoice-page {{ max-width: none; padding: 6mm; }}
            @page {{ size: A4 landscape; margin: 7mm; }}
        }}
    </style>
    """

    body = f"""
    <div class="invoice-page">
        <div class="top-title">NOTA SMART MESSEGER</div>
        <div class="brand">Bright<span class="yellow">o</span>n <span class="brand-sub">| Bringing<br>Dreams Beyond</span></div>

        <div class="meta-grid">
            <div>
                <div class="meta-line"><span>Tgl Request</span><span>:</span><span class="underline">{safe_text(format_date_display(meta.get('tgl_request')))}</span></div>
                <div class="meta-line"><span>Nama Agent</span><span>:</span><span class="underline">{safe_text(meta.get('nama_agent'))}</span></div>
                <div class="meta-line"><span>Kantor</span><span>:</span><span class="underline">{safe_text(meta.get('kantor'))}</span></div>
                <div class="meta-line"><span>Pembayaran</span><span>:</span><span class="underline">{safe_text(meta.get('pembayaran'))}</span></div>
                <div class="meta-line meta-small"><span>Estimasi Tanggal<br>Pengerjaan</span><span>:</span><span class="underline" style="font-size:18px; align-self:end;">{safe_text(format_date_display(meta.get('estimasi_tanggal')))}</span></div>
            </div>
            <div class="rekening">{rekening_text}</div>
        </div>

        <table class="invoice">
            <colgroup>
                <col style="width:38px">
                <col style="width:29%">
                <col style="width:12.5%">
                <col style="width:9%">
                <col style="width:32px">
                <col style="width:8%">
                <col style="width:9.5%">
                <col style="width:15%">
                <col style="width:14.5%">
            </colgroup>
            <thead>
                <tr>
                    <th rowspan="2">No</th>
                    <th rowspan="2">Alamat</th>
                    <th rowspan="2">Tugas</th>
                    <th colspan="3">Rumus BBM</th>
                    <th>Biaya Jasa<br><span class="subhead">(Khusus Pasang)</span></th>
                    <th rowspan="2">TOTAL<br><span class="subhead">(Tarif minimum {safe_text(format_rupiah(config.minimum_bbm))} berlaku jika jarak akumulasi kurang dari {safe_text(format_number_id(config.minimum_distance_km))} KM)</span></th>
                    <th rowspan="2">Keterangan</th>
                </tr>
                <tr>
                    <th class="subhead">Jarak Akumulasi<br>(Min {safe_text(format_number_id(config.minimum_distance_km))} KM)</th>
                    <th>X</th>
                    <th>{safe_text(format_rupiah(config.tariff_per_km))}</th>
                    <th>{safe_text(format_rupiah(config.service_fee_per_point))}</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
                <tr class="total-row">
                    <td colspan="7" class="total-label">TOTAL</td>
                    <td class="total-amount">{safe_text(format_rupiah(result.total))}</td>
                    <td></td>
                </tr>
            </tbody>
        </table>

        <div class="footnote">
            Tarif Smart Messenger berlaku Nasional seluruh Cabang Brighton, jika mendapatkan tarif diluar ketentuan diatas silahkan hubungi<br>
            HRD Pusat: 0812-3051-3989<br>
            <strong>Biaya jasa disesuaikan dengan jumlah titik pekerjaan.</strong><br>
            Salam #MimpiJadiNyata
        </div>

        <div class="calc-info no-print">
            <strong>Ringkasan perhitungan:</strong><br>
            Jarak: {safe_text(format_number_id(result.distance_km))} KM × {safe_text(format_rupiah(config.tariff_per_km))} = {safe_text(format_rupiah(result.raw_bbm_fee))}<br>
            BBM dipakai: {safe_text(format_rupiah(result.bbm_fee))}. {safe_text(result.minimum_note)}<br>
            Jasa pasang: {safe_text(result.job_count)} titik × {safe_text(format_rupiah(config.service_fee_per_point))} = {safe_text(format_rupiah(result.service_fee))}<br>
            Total: {safe_text(format_rupiah(result.bbm_fee))} + {safe_text(format_rupiah(result.service_fee))} = <strong>{safe_text(format_rupiah(result.total))}</strong>
        </div>
    </div>
    """

    if standalone:
        return f"<!doctype html><html><head><meta charset='utf-8'>{css}</head><body>{body}</body></html>"
    return f"{css}{body}"


# -----------------------------------------------------------------------------
# Renderer PDF menggunakan ReportLab
# -----------------------------------------------------------------------------
def make_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    """Membuat paragraph ReportLab dengan HTML escaping sederhana."""
    return Paragraph(safe_text(text).replace("\n", "<br/>").replace("&lt;br/&gt;", "<br/>"), style)


def build_pdf_bytes(
    meta: Dict[str, Any],
    table_rows: List[Dict[str, str]],
    result: CalculationResult,
    config: CalculationConfig,
) -> bytes:
    """Membuat file PDF siap download dari data nota."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=0.5 * cm,
        leftMargin=0.5 * cm,
        topMargin=0.35 * cm,
        bottomMargin=0.35 * cm,
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("NormalSmall", parent=styles["Normal"], fontName="Helvetica", fontSize=8.7, leading=10)
    center = ParagraphStyle("CenterSmall", parent=normal, alignment=TA_CENTER)
    bold_center = ParagraphStyle("BoldCenter", parent=center, fontName="Helvetica-Bold", fontSize=16, leading=18)
    title_style = ParagraphStyle("Title", parent=bold_center, fontSize=11.5, underline=True)
    brand_style = ParagraphStyle("Brand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=31, leading=34, alignment=TA_LEFT)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=13)
    total_style = ParagraphStyle("Total", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=TA_CENTER)
    footer_style = ParagraphStyle("Footer", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)

    elements = []
    elements.append(Paragraph("NOTA SMART MESSEGER", title_style))

    meta_left = (
        f"Tgl Request&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <u>{format_date_display(meta.get('tgl_request'))}</u><br/>"
        f"Nama Agent&nbsp;&nbsp;&nbsp;&nbsp;: <u>{safe_text(meta.get('nama_agent'))}</u><br/>"
        f"Kantor&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <u>{safe_text(meta.get('kantor'))}</u><br/>"
        f"Pembayaran&nbsp;&nbsp;&nbsp;&nbsp;: <u>{safe_text(meta.get('pembayaran'))}</u><br/>"
        f"Estimasi Tanggal<br/>Pengerjaan&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <u>{format_date_display(meta.get('estimasi_tanggal'))}</u>"
    )
    rekening = ""
    if str(meta.get("pembayaran", "")).lower().find("transfer") >= 0:
        rekening = f"No Rekening (Jika Transfer) : {safe_text(meta.get('rekening'))}"

    header_table = Table(
        [
            [Paragraph(meta_left, meta_style), Paragraph(rekening, meta_style), Paragraph("Bright<font color='#ffc000'>o</font>n | Bringing<br/>Dreams Beyond", brand_style)]
        ],
        colWidths=[8.6 * cm, 9.1 * cm, 10.6 * cm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 0.35 * cm))

    table_data = [
        [
            make_paragraph("No", center),
            make_paragraph("Alamat", center),
            make_paragraph("Tugas", center),
            make_paragraph("Rumus BBM", center),
            "",
            "",
            make_paragraph("Biaya Jasa<br/>(Khusus Pasang)", center),
            make_paragraph(
                f"TOTAL<br/>(Tarif minimum {format_rupiah(config.minimum_bbm)} berlaku jika jarak akumulasi kurang dari {format_number_id(config.minimum_distance_km)} KM)",
                center,
            ),
            make_paragraph("Keterangan", center),
        ],
        [
            "",
            "",
            "",
            make_paragraph(f"Jarak Akumulasi<br/>(Min {format_number_id(config.minimum_distance_km)} KM)", center),
            make_paragraph("X", center),
            make_paragraph(format_rupiah(config.tariff_per_km), center),
            make_paragraph(format_rupiah(config.service_fee_per_point), center),
            "",
            "",
        ],
    ]

    for row in table_rows:
        table_data.append(
            [
                make_paragraph(row["No"], center),
                make_paragraph(row["Alamat"], normal),
                make_paragraph(row["Tugas"], normal),
                make_paragraph(row["Jarak"], center),
                make_paragraph(row["X"], center),
                make_paragraph(row["Tarif"], center),
                make_paragraph(row["Biaya Jasa"], center),
                make_paragraph(row["Total"], center),
                make_paragraph(row["Keterangan"], normal),
            ]
        )

    table_data.append(
        [
            "",
            make_paragraph("TOTAL", total_style),
            "",
            "",
            "",
            "",
            "",
            make_paragraph(format_rupiah(result.total), total_style),
            "",
        ]
    )

    col_widths = [0.75 * cm, 7.9 * cm, 3.4 * cm, 2.3 * cm, 0.65 * cm, 2.1 * cm, 2.6 * cm, 4.1 * cm, 4.2 * cm]
    invoice_table = Table(table_data, colWidths=col_widths, repeatRows=2)

    footer_index = len(table_data) - 1
    style_commands = [
        ("GRID", (0, 0), (-1, -1), 0.55, colors.black),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor(BRIGHTON_YELLOW)),
        ("BACKGROUND", (0, footer_index), (-1, footer_index), colors.HexColor(BRIGHTON_YELLOW)),
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),
        ("SPAN", (2, 0), (2, 1)),
        ("SPAN", (3, 0), (5, 0)),
        ("SPAN", (7, 0), (7, 1)),
        ("SPAN", (8, 0), (8, 1)),
        ("SPAN", (0, footer_index), (6, footer_index)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 2), (2, footer_index - 1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    invoice_table.setStyle(TableStyle(style_commands))
    elements.append(invoice_table)

    footer = (
        "Tarif Smart Messenger berlaku Nasional seluruh Cabang Brighton, jika mendapatkan tarif diluar ketentuan diatas silahkan hubungi<br/>"
        "HRD Pusat: 0812-3051-3989<br/>"
        "<b>Biaya jasa disesuaikan dengan jumlah titik pekerjaan.</b><br/>"
        "Salam #MimpiJadiNyata"
    )
    footer_table = Table([[Paragraph(footer, footer_style)]], colWidths=[28.0 * cm])
    footer_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.55, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 20),
            ]
        )
    )
    elements.append(footer_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


# -----------------------------------------------------------------------------
# Session state dan contoh data
# -----------------------------------------------------------------------------
def set_example_one_point() -> None:
    """Mengisi form sesuai contoh gambar pertama."""
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
        invoice_html = build_invoice_html(meta, table_rows, result, config, standalone=False)
        st.components.v1.html(invoice_html, height=820, scrolling=True)

        full_html = build_invoice_html(meta, table_rows, result, config, standalone=True)
        pdf_bytes = build_pdf_bytes(meta, table_rows, result, config)
        file_suffix = format_date_display(tgl_request).replace("-", "_")

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
                "Download HTML Nota",
                data=full_html.encode("utf-8"),
                file_name=f"nota_smart_messenger_{file_suffix}.html",
                mime="text/html",
            )

        st.markdown("#### Data tabel")
        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
