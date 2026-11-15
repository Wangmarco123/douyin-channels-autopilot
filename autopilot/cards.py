# -*- coding: utf-8 -*-
"""卡片与封面渲染（PIL）：截图悬浮卡、数据卡、片尾卡、上下压暗渐变、3:4 封面。

所有尺寸按 1080x1920 竖版设计；封面单独走 1080x1440（3:4）。
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


# ---------------------------------------------------------------- 素材预处理
def clean_photo(src, out, threshold=14):
    """EXIF 转正 + 裁掉纯黑边（手机截图/录屏常见上下黑边）。"""
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    g = im.convert("L")
    w, h = g.size
    px = g.load()

    def row_dark(y):
        vals = [px[x, y] for x in range(0, w, 8)]
        return sum(vals) / max(1, len(vals)) < threshold

    def col_dark(x):
        vals = [px[x, y] for y in range(0, h, 8)]
        return sum(vals) / max(1, len(vals)) < threshold

    top = 0
    while top < h // 3 and row_dark(top):
        top += 1
    bot = h - 1
    while bot > h * 2 // 3 and row_dark(bot):
        bot -= 1
    left = 0
    while left < w // 3 and col_dark(left):
        left += 1
    right = w - 1
    while right > w * 2 // 3 and col_dark(right):
        right -= 1
    crop = (left, top, right + 1, bot + 1)
    if crop != (0, 0, w, h) and (bot - top) > h * 0.4:
        im = im.crop(crop)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    return out


def make_grad_overlay(out, w=1080, h=1920, top_alpha=150, bot_alpha=205):
    """上下压暗渐变：保证任何画面上字幕与花字都可读。"""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    th = int(h * 0.323)
    for i in range(th):
        a = int(top_alpha * (1 - i / th) ** 1.35)
        d.line([(0, i), (w, i)], fill=(0, 0, 0, a))
    bh = int(h * 0.365)
    for i in range(bh):
        a = int(bot_alpha * (i / bh) ** 1.25)
        d.line([(0, h - bh + i), (w, h - bh + i)], fill=(0, 0, 0, a))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    return out


# ---------------------------------------------------------------- 通用绘制
def _round_shadow(img, radius=26, shadow=42):
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    card.paste(img, (0, 0), mask)
    edge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=radius, outline=(255, 255, 255, 90), width=3)
    card = Image.alpha_composite(card, edge)

    pad = shadow * 2
    canvas = Image.new("RGBA", (w + pad, h + pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", (w + pad, h + pad), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [shadow, shadow, shadow + w, shadow + h], radius=radius, fill=(0, 0, 0, 165))
    sh = sh.filter(ImageFilter.GaussianBlur(shadow * 0.55))
    canvas = Image.alpha_composite(canvas, sh)
    canvas.paste(card, (shadow, shadow), card)
    return canvas


def _bg_gradient(size, c1=(12, 14, 20), c2=(30, 20, 12)):
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(size[1]):
        t = y / size[1]
        d.line([(0, y), (size[0], y)],
               fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return im


def make_inset_card(src, out, font_bold, crop=None, box=(980, 1230), center_y=965,
                    bg_blur=46, w=1080, h=1920):
    """截图类素材：模糊压暗底 + 圆角悬浮卡（比直接拉伸截图好看得多）。"""
    im = Image.open(src).convert("RGB")
    bg = im
    if crop:
        im = im.crop(crop)
        bg = bg.crop(crop)

    s = max(w / bg.width, h / bg.height)
    bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
    bw, bh = bg.size
    bg = bg.crop(((bw - w) // 2, (bh - h) // 2, (bw - w) // 2 + w, (bh - h) // 2 + h))
    bg = Image.eval(bg.filter(ImageFilter.GaussianBlur(bg_blur)), lambda v: int(v * 0.42))

    sc = min(box[0] / im.width, box[1] / im.height)
    fg = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
    card = _round_shadow(fg)
    canvas = bg.convert("RGBA")
    canvas.alpha_composite(card, ((w - card.width) // 2, center_y - card.height // 2))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    canvas.convert("RGB").save(out)
    return out


def make_data_card(out, rows, font_bold, foot=None, w=1080, h=1920,
                   accent=(255, 206, 74)):
    """数据卡：rows = [(大数字, 说明), ...]，可加 foot 备注行。"""
    im = _bg_gradient((w, h))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([w // 2 - 620, 380, w // 2 + 620, 1180],
                                 fill=(210, 150, 45, 46))
    glow = glow.filter(ImageFilter.GaussianBlur(170))
    im = Image.alpha_composite(im.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")

    block = 300
    y = (h - len(rows) * block) // 2 - 60
    for val, label in rows:
        f1 = ImageFont.truetype(font_bold, 132 if len(val) <= 5 else 108)
        f2 = ImageFont.truetype(font_bold, 50)
        tw = d.textlength(val, font=f1)
        d.text(((w - tw) / 2 + 5, y + 5), val, font=f1, fill=(0, 0, 0, 200))
        d.text(((w - tw) / 2, y), val, font=f1, fill=accent + (255,),
               stroke_width=3, stroke_fill=(0, 0, 0, 180))
        tw2 = d.textlength(label, font=f2)
        d.text(((w - tw2) / 2, y + 168), label, font=f2, fill=(238, 238, 238, 255))
        y += block

    if foot:
        lines = foot if isinstance(foot, (list, tuple)) else [foot]
        f3 = ImageFont.truetype(font_bold, 52)
        yb = h - 430
        for ln in lines:
            tw3 = d.textlength(ln, font=f3)
            d.text(((w - tw3) / 2, yb), ln, font=f3, fill=(242, 242, 242, 255),
                   stroke_width=3, stroke_fill=(0, 0, 0, 170))
            yb += 74

    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    return out


def make_end_card(out, main, sub, font_bold, font_regular, foot="",
                  w=1080, h=1920):
    """片尾卡：主标题 + 金色副标 + 细金线 + 可选脚注。"""
    im = _bg_gradient((w, h), (8, 10, 14), (26, 18, 10))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([w // 2 - 700, 660, w // 2 + 700, 1320],
                                 fill=(200, 145, 40, 52))
    glow = glow.filter(ImageFilter.GaussianBlur(200))
    im = Image.alpha_composite(im.convert("RGBA"), glow).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")

    f1 = ImageFont.truetype(font_bold, 150)
    f2 = ImageFont.truetype(font_bold, 66)
    tw = d.textlength(main, font=f1)
    d.text(((w - tw) / 2 + 6, 806), main, font=f1, fill=(0, 0, 0, 190))
    d.text(((w - tw) / 2, 800), main, font=f1, fill=(255, 255, 255, 255))
    tw2 = d.textlength(sub, font=f2)
    d.text(((w - tw2) / 2, 1010), sub, font=f2, fill=(255, 206, 74, 255))
    if foot:
        f3 = ImageFont.truetype(font_regular, 40)
        tw3 = d.textlength(foot, font=f3)
        d.text(((w - tw3) / 2, 1140), foot, font=f3, fill=(175, 175, 175, 255))
    d.line([(w // 2 - 190, 990), (w // 2 + 190, 990)], fill=(210, 165, 70, 160), width=3)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    return out


# ---------------------------------------------------------------- 3:4 封面
def make_cover(base, out_jpg, tag, main_lines, sub, font_bold,
               sub2=None, size=(1080, 1440), top_anchor=None, quality=94):
    """抖音/视频号竖版封面：1080x1440（3:4）。

    - tag：左上角小标签（如「真实事故」「官方测试」）
    - main_lines：主标（多行）
    - sub：金色副标
    - sub2：更小的灰色第三行
    """
    W, H = size
    im = Image.open(base).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    bw, bh = im.size
    im = im.crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W, (bh - H) // 2 + H))
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    d = ImageDraw.Draw(im, "RGBA")

    gh = int(H * 0.458)
    for i in range(gh):
        a = int(228 * (i / gh) ** 1.25)
        d.line([(0, H - gh + i), (W, H - gh + i)], fill=(0, 0, 0, a))
    th = int(H * 0.292)
    for i in range(th):
        a = int(165 * (1 - i / th) ** 1.3)
        d.line([(0, i), (W, i)], fill=(0, 0, 0, a))

    f_tag = ImageFont.truetype(font_bold, 40)
    f_main = ImageFont.truetype(font_bold, 132)
    f_sub = ImageFont.truetype(font_bold, 50)

    tw = d.textlength(tag, font=f_tag)
    d.rounded_rectangle([44, 52, 44 + tw + 52, 130], radius=14, fill=(0, 0, 0, 165))
    d.text((70, 68), tag, font=f_tag, fill=(255, 255, 255, 240))

    y = top_anchor if top_anchor else H - gh + 96
    for line in main_lines:
        tw = d.textlength(line, font=f_main)
        x = (W - tw) / 2
        d.text((x + 5, y + 6), line, font=f_main, fill=(0, 0, 0, 215))
        d.text((x, y), line, font=f_main, fill=(255, 255, 255, 255),
               stroke_width=9, stroke_fill=(0, 0, 0, 255))
        y += 158
    tw = d.textlength(sub, font=f_sub)
    d.text(((W - tw) / 2, y + 10), sub, font=f_sub, fill=(255, 208, 76, 255),
           stroke_width=5, stroke_fill=(0, 0, 0, 235))
    if sub2:
        f2 = ImageFont.truetype(font_bold, 38)
        tw = d.textlength(sub2, font=f2)
        d.text(((W - tw) / 2, y + 82), sub2, font=f2, fill=(226, 226, 226, 245),
               stroke_width=4, stroke_fill=(0, 0, 0, 220))
    d.line([(W // 2 - 150, y - 18), (W // 2 + 150, y - 18)],
           fill=(214, 168, 72, 190), width=3)

    os.makedirs(os.path.dirname(out_jpg), exist_ok=True)
    im.save(out_jpg, quality=quality)
    return out_jpg
