"""Generate assets/cpan.ico + assets/cpan.png (build-time only, needs Pillow)."""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
SIZE = 1024
MARGIN = 26
RADIUS = 218


def vertical_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    grad = Image.new("RGB", (1, SIZE))
    px = grad.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        px[0, y] = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
    return grad.resize((SIZE, SIZE), Image.Resampling.BICUBIC)


def star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill, inner=0.34):
    points = []
    for i in range(8):
        ang = -90 + i * 45
        radius = r if i % 2 == 0 else r * inner
        import math
        points.append((cx + radius * math.cos(math.radians(ang)),
                       cy + radius * math.sin(math.radians(ang))))
    draw.polygon(points, fill=fill)


def build() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [MARGIN, MARGIN, SIZE - MARGIN, SIZE - MARGIN],
        radius=RADIUS, fill=255)

    grad = vertical_gradient((86, 140, 255), (26, 62, 176))
    img.paste(grad, (0, 0), mask)

    # soft top-left sheen
    sheen = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    sd.ellipse([-280, -380, 900, 470], fill=(255, 255, 255, 22))
    sheen = sheen.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img, Image.composite(sheen, Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0)), mask))

    draw = ImageDraw.Draw(img)

    # gauge ring
    ring_box = [176, 176, SIZE - 176, SIZE - 176]
    draw.arc(ring_box, start=288, end=112, fill=(255, 255, 255, 64), width=16)
    draw.arc(ring_box, start=302, end=26, fill=(94, 234, 174, 255), width=30)

    # letter C with a soft shadow
    font_path = r"C:\Windows\Fonts\segoeuib.ttf"
    if not os.path.exists(font_path):
        font_path = r"C:\Windows\Fonts\msyhbd.ttc"
    font = ImageFont.truetype(font_path, 560)
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.text((SIZE / 2 + 4, SIZE / 2 + 26), "C", font=font,
               fill=(9, 24, 66, 130), anchor="mm")
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    draw.text((SIZE / 2, SIZE / 2 - 4), "C", font=font,
              fill=(248, 251, 255, 255), anchor="mm")

    # sparkle
    star(draw, 792, 232, 74, (255, 255, 255, 240), inner=0.3)
    star(draw, 838, 174, 34, (94, 234, 174, 255), inner=0.3)

    # crisp inner border
    border = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bd = ImageDraw.Draw(border)
    bd.rounded_rectangle([MARGIN, MARGIN, SIZE - MARGIN, SIZE - MARGIN],
                         radius=RADIUS, outline=(255, 255, 255, 36), width=4)
    return Image.alpha_composite(img, border)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    img = build()
    img.resize((512, 512), Image.Resampling.LANCZOS).save(
        os.path.join(ASSETS, "cpan.png"))
    img.save(os.path.join(ASSETS, "cpan.ico"), format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                    (64, 64), (128, 128), (256, 256)])
    print("wrote", os.path.join(ASSETS, "cpan.ico"))




def make_wizard_art():
    """Branded Inno Setup wizard images (BMP, no alpha)."""
    from PIL import Image, ImageDraw, ImageFont
    icon = build()
    # Small header images for Inno's 100/125/150/175/200/225/250% scales.
    for pct, size in zip((100, 125, 150, 175, 200, 225, 250),
                         (58, 77, 97, 116, 124, 143, 159)):
        small = Image.new("RGB", (size, size), "white")
        inner = max(24, int(size * 0.86))
        mark = icon.resize((inner, inner), Image.Resampling.LANCZOS)
        off = (size - inner) // 2
        small.paste(mark, (off, off), mark)
        small.save(os.path.join(ASSETS, f"wizard-small-{pct}.bmp"))

    # Classic/large wizard panel: 164x314.
    large = Image.new("RGB", (164, 314), "#0F1A2E")
    ld = ImageDraw.Draw(large)
    for y in range(314):
        t = y / 313
        color = (int(20 * (1 - t) + 9 * t),
                 int(32 * (1 - t) + 18 * t),
                 int(59 * (1 - t) + 38 * t))
        ld.line([(0, y), (164, y)], fill=color)
    mark = icon.resize((92, 92), Image.Resampling.LANCZOS)
    large.paste(mark, (36, 34), mark)
    try:
        bold = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 24)
        cn = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 11)
        tiny = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 9)
    except OSError:
        bold = cn = tiny = ImageFont.load_default()
    ld.text((82, 146), "Cpan", font=bold, fill="#FFFFFF", anchor="mm")
    ld.text((82, 169), "C 盘空间管家", font=cn, fill="#A9B9D6", anchor="mm")
    ld.line([(26, 195), (138, 195)], fill="#2A3A58", width=1)
    for i, line in enumerate(("安全清理白名单", "空间分析下钻", "软件联接搬家")):
        ld.text((82, 218 + i * 21), line, font=tiny, fill="#8FA2C2", anchor="mm")
    ld.text((82, 290), "纯本地运行", font=tiny, fill="#5E7194", anchor="mm")
    large.save(os.path.join(ASSETS, "wizard-large.bmp"))
    print("wrote wizard art")


if __name__ == "__main__":
    main()
    make_wizard_art()
