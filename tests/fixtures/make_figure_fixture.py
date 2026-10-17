"""A20 用の図とPDFを作る(架空・公開開発例)。Pillow と標準ライブラリのみ。

図1: 左に「開始」、右に「承認」、間に破線の矢印。右上の凡例に「破線：未承認」。
PDF: 1ページ。図の画像を貼り、凡例の文字を不可視の文字層として重ねた「検索可能な画像PDF」。
文字層は抽出の試験用で、図の意味(破線=未承認)の確認には視覚確認が必要。
"""
from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
W, H = 1200, 680           # 画像のピクセル
PW, PH = 600, 340          # PDFのポイント(1px = 0.5pt)


def draw_png(path: Path) -> dict:
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 44)
    small = ImageFont.truetype(FONT, 36)
    d.text((40, 30), "図1", font=f, fill="black")
    d.rectangle([80, 260, 360, 420], outline="black", width=6)
    d.text((165, 315), "開始", font=f, fill="black")
    d.rectangle([840, 260, 1120, 420], outline="black", width=6)
    d.text((925, 315), "承認", font=f, fill="black")
    x = 380
    while x < 790:                         # 破線の矢印
        d.line([x, 340, min(x + 40, 790), 340], fill="black", width=8)
        x += 70
    d.polygon([(830, 340), (790, 318), (790, 362)], fill="black")
    legend = (700, 40, 1160, 150)          # 右上の凡例
    d.rectangle(legend, outline="black", width=3)
    for sx in (720, 760):                  # 凡例の見本も破線で描く
        d.line([sx, 95, sx + 24, 95], fill="black", width=6)
    d.text((820, 70), "破線：未承認", font=small, fill="black")
    img.save(path)
    return {"legend_text_px": (815, 66, 1150, 130), "legend_box_px": legend}


def write_pdf(path: Path, png: Path, legend_text: str, legend_box_px) -> None:
    img = Image.open(png).convert("RGB")
    raw = zlib.compress(img.tobytes())
    x0, y0, x1, y1 = legend_box_px
    tx, ty = x0 / 2 + 60, PH - (y0 + 75) / 2        # 凡例の文字付近(PDF座標: 下が原点)
    hexs = "".join(f"{ord(c):04X}" for c in legend_text)
    content = f"q {PW} 0 0 {PH} 0 0 cm /Im0 Do Q BT 3 Tr /F1 18 Tf {tx:.1f} {ty:.1f} Td <FEFF{hexs}> Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PW} {PH}] /Contents 4 0 R /Resources << /XObject << /Im0 5 0 R >> /Font << /F1 6 0 R >> >> >>".encode(),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (W, H, len(raw)) + raw + b"\nendstream",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiKakuGo-W5 /Encoding /UniJIS-UCS2-H /DescendantFonts [7 0 R] >>",
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiKakuGo-W5 /CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 2 >> /DW 1000 >>",
    ]
    out, offs = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def main(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    info = draw_png(outdir / "figure1.png")
    write_pdf(outdir / "figure1.pdf", outdir / "figure1.png", "破線：未承認", info["legend_box_px"])
    (outdir / "figure1.meta.json").write_text(json.dumps({
        "page": 1, "figure_label": "図1", "legend_region": "右上の凡例",
        "legend_bbox_pdf_pt": [info["legend_box_px"][0] / 2, info["legend_box_px"][1] / 2,
                               info["legend_box_px"][2] / 2, info["legend_box_px"][3] / 2],
        "note": "bbox は描画時の指定値(PDFの左上原点換算)。座標系は x0,top,x1,bottom"}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
