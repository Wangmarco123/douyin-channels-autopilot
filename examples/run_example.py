# -*- coding: utf-8 -*-
"""最小可跑示例：不依赖任何外部素材，现场生成几张演示图再出片。

    python examples/run_example.py

产物：out/demo.mp4（约 15 秒竖版成片）
用途：确认 ffmpeg / edge-tts / 字体 / 字幕烧录这条链在你机器上是通的。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from autopilot import config, engine  # noqa: E402


def demo_image(path, text, c1, c2, font_path):
    W, H = 1080, 1920
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    f = ImageFont.truetype(font_path, 96)
    tw = d.textlength(text, font=f)
    d.text(((W - tw) / 2, H // 2 - 60), text, font=f, fill=(255, 255, 255))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
    return path


def main():
    cfg = config.load()
    if config.print_check(cfg):
        print("\n先解决上面标 FAIL 的项（见 docs/01-install.md），再跑这个示例。")
        return 1

    assets = os.path.join(cfg["work_dir"], "demo_assets")
    a1 = demo_image(os.path.join(assets, "a1.jpg"), "画面 A", (18, 22, 34), (48, 34, 18),
                    cfg["font_bold"])
    a2 = demo_image(os.path.join(assets, "a2.jpg"), "画面 B", (34, 12, 16), (12, 28, 40),
                    cfg["font_bold"])
    a3 = demo_image(os.path.join(assets, "a3.jpg"), "画面 C", (10, 10, 12), (40, 30, 14),
                    cfg["font_bold"])

    board = {
        "tag": "demo",
        "voice": "zh-CN-YunjianNeural",
        "rate": "+10%",
        "bgm": None,                      # 示例不配 BGM；有音乐就把文件名填这里
        "out": os.path.join(ROOT, "out", "demo.mp4"),
        "segments": [
            {"kind": "photo", "src": a1, "motion": "in", "zoom": 1.12,
             "vo": "这是一条演示视频，用来验证整条流水线是否跑得通。",
             "card": "演示 · 画面 A", "card_color": "gold"},
            {"kind": "photo", "src": a2, "motion": "right", "zoom": 1.10,
             "vo": "每一段口播都会自动配音、自动对齐时间轴，字幕跟着声音走。",
             "card": "自动对齐"},
            {"kind": "photo", "src": a3, "motion": "left", "zoom": 1.12,
             "vo": "最后输出一千零八十乘一千九百二十的竖版成片，抖音和视频号都能直接发。",
             "card": "1080×1920", "card_color": "gold"},
        ],
    }
    out, total = engine.build(cfg, board)
    print("\n示例完成：%s（%.1f 秒）" % (out, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
