# -*- coding: utf-8 -*-
"""配置加载：所有本机路径都从 config.json / 环境变量来，仓库内不硬编码。"""
import json
import os
import shutil
import sys

DEFAULTS = {
    # 工具链
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
    # 字体（Windows 默认微软雅黑；其它系统请在 config.json 里改成自己的中文字体）
    "font_bold": r"C:\Windows\Fonts\msyhbd.ttc",
    "font_regular": r"C:\Windows\Fonts\msyh.ttc",
    # 素材与输出
    "bgm_dir": "./assets/bgm",
    "work_dir": "./work",
    "out_dir": "./out",
    # social-auto-upload 本地副本（发布用）
    "sau_dir": "",
    "sau_python": "",
    # 成片默认参数
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "pad": 0.26,
    "lead": 0.30,
    "tail": 0.85,
    "bgm_volume": 0.135,
}

_LINUX_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
]


class Config(dict):
    """dict + 属性访问"""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def path(self, key, base=None):
        v = self[key]
        if not v:
            return ""
        if os.path.isabs(v):
            return v
        base = base or self.get("_base") or os.getcwd()
        return os.path.normpath(os.path.join(base, v))


def load(path=None):
    """读取配置：命令行指定 > ./config.json > 默认值"""
    cfg = Config(DEFAULTS)
    if path is None:
        for cand in ("config.json", os.path.join(os.path.dirname(__file__), "..", "config.json")):
            if os.path.isfile(cand):
                path = cand
                break
    if path and os.path.isfile(path):
        cfg["_base"] = os.path.dirname(os.path.abspath(path))
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    else:
        cfg["_base"] = os.getcwd()

    # 环境变量覆盖
    if os.environ.get("FFMPEG"):
        cfg["ffmpeg"] = os.environ["FFMPEG"]
    if os.environ.get("FFPROBE"):
        cfg["ffprobe"] = os.environ["FFPROBE"]
    if os.environ.get("SAU_DIR"):
        cfg["sau_dir"] = os.environ["SAU_DIR"]

    # 字体兜底
    if not os.path.isfile(cfg["font_bold"]):
        for c in _LINUX_FONT_CANDIDATES:
            if os.path.isfile(c):
                cfg["font_bold"] = c
                cfg["font_regular"] = c
                break

    for k in ("work_dir", "out_dir", "bgm_dir"):
        cfg[k] = cfg.path(k)
    if cfg["sau_dir"]:
        cfg["sau_dir"] = cfg.path("sau_dir")
    return cfg


def check(cfg):
    """启动前自检。返回 [(ok, 说明, 是否必需)]"""
    rows = []
    rows.append((shutil.which(cfg["ffmpeg"]) is not None or os.path.isfile(cfg["ffmpeg"]),
                 "ffmpeg: %s" % cfg["ffmpeg"], True))
    rows.append((shutil.which(cfg["ffprobe"]) is not None or os.path.isfile(cfg["ffprobe"]),
                 "ffprobe: %s" % cfg["ffprobe"], True))
    rows.append((os.path.isfile(cfg["font_bold"]), "中文字体: %s" % cfg["font_bold"], True))
    rows.append((os.path.isdir(cfg["bgm_dir"]), "BGM 目录: %s" % cfg["bgm_dir"], True))
    sau_ok = bool(cfg["sau_dir"]) and os.path.isfile(os.path.join(cfg["sau_dir"], "sau_cli.py"))
    rows.append((sau_ok,
                 "social-auto-upload: %s" % (cfg["sau_dir"] or "未配置"),
                 False))                      # 只出片时不需要
    try:
        import edge_tts  # noqa: F401
        rows.append((True, "edge-tts: 已安装", True))
    except Exception:
        rows.append((False, "edge-tts: 未安装（pip install edge-tts）", True))
    try:
        import PIL  # noqa: F401
        rows.append((True, "Pillow: 已安装", True))
    except Exception:
        rows.append((False, "Pillow: 未安装（pip install pillow）", True))
    return rows


def print_check(cfg):
    bad = 0
    for ok, msg, required in check(cfg):
        if ok:
            print("  [OK]      " + msg)
        elif required:
            bad += 1
            print("  [FAIL]    " + msg)
        else:
            print("  [SKIP]    " + msg + "（仅发布时需要，见 docs/03-publish.md）")
    print()
    if bad:
        print("有 %d 项必需项未就绪，见 docs/01-install.md" % bad)
    else:
        print("环境自检通过。")
    return bad
