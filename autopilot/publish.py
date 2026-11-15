# -*- coding: utf-8 -*-
"""发布层：包装 social-auto-upload 的 CLI，把踩过的坑固化成校验。

依赖：https://github.com/dreammis/social-auto-upload （MIT）
本模块只做三件事：拼命令 / 前置校验 / 把输出原样透传给你。
"""
import os
import re
import subprocess
import sys

DOUYIN_TITLE_MAX = 30          # 上游 fill_title_and_description 里是 title[:30]
SHORT_TITLE_MIN, SHORT_TITLE_MAX = 7, 15   # 视频号短标题区间

PLATFORM = {"douyin": "douyin", "channels": "tencent"}


class PublishError(Exception):
    pass


def _resolve(cfg):
    sau = cfg.get("sau_dir") or ""
    if not sau or not os.path.isfile(os.path.join(sau, "sau_cli.py")):
        raise PublishError(
            "未配置 social-auto-upload。请先:\n"
            "  git clone https://github.com/dreammis/social-auto-upload\n"
            "  cd social-auto-upload && python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt\n"
            "然后在 config.json 里填 sau_dir / sau_python"
        )
    py = cfg.get("sau_python") or ""
    if not py or not os.path.isfile(py):
        cand = os.path.join(sau, ".venv", "Scripts", "python.exe")
        if os.path.isfile(cand):
            py = cand
        else:
            py = sys.executable
    return sau, py


def run(cfg, platform, action, **opts):
    """调用 sau_cli.py。返回 (returncode, stdout+stderr 文本)"""
    sau, py = _resolve(cfg)
    plat = PLATFORM[platform]
    cmd = [py, os.path.join(sau, "sau_cli.py"), plat, action]

    if action in ("upload-video", "upload-note"):
        cmd += ["--account", opts.get("account", "main")]
        if opts.get("file"):
            cmd += ["--file", opts["file"]]
        if opts.get("title"):
            cmd += ["--title", opts["title"]]
        if opts.get("desc"):
            cmd += ["--desc", opts["desc"]]
        if opts.get("tags"):
            tags = opts["tags"]
            cmd += ["--tags", ",".join(tags) if isinstance(tags, (list, tuple)) else tags]
        if opts.get("thumbnail"):
            cmd += ["--thumbnail", opts["thumbnail"]]
        if opts.get("short_title") and platform == "channels":
            cmd += ["--short-title", opts["short_title"]]
        if opts.get("schedule"):
            cmd += ["--schedule", opts["schedule"]]
        if opts.get("headed"):
            cmd += ["--headed"]
        if opts.get("headless"):
            cmd += ["--headless"]
    elif action == "login":
        cmd += ["--account", opts.get("account", "main")]
        cmd += ["--headed"]           # 扫码必须看得见浏览器
    elif action == "check":
        cmd += ["--account", opts.get("account", "main")]

    if opts.get("dry_run"):
        return 0, "DRY-RUN: " + " ".join(cmd)

    p = subprocess.run(cmd, cwd=sau, text=True, encoding="utf-8", errors="replace",
                       capture_output=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------- 前置校验
def validate(platform, title, desc="", tags=None, short_title=None,
             schedule=None, file=None, thumbnail=None):
    """把平台硬约束提前拦截，别等跑完 2 分钟浏览器才发现被拒。"""
    probs = []

    if file and not os.path.isfile(file):
        probs.append("视频文件不存在: %s" % file)
    if thumbnail and not os.path.isfile(thumbnail):
        probs.append("封面文件不存在: %s" % thumbnail)

    if platform == "douyin":
        if not title:
            probs.append("抖音 title 必填")
        elif len(title) > DOUYIN_TITLE_MAX:
            probs.append("抖音标题 %d 字，超过 %d 字上限（上游会静默截断到 30 字）"
                         % (len(title), DOUYIN_TITLE_MAX))
        if schedule and not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", schedule):
            probs.append("--schedule 格式应为 'YYYY-MM-DD HH:MM'，当前: %s" % schedule)

    if platform == "channels":
        if schedule:
            probs.append(
                "视频号不要用定时发布！上游的定时选择器会把表单点乱，"
                "导致「发表」按钮点不动、卡满 4 分钟后失败。请直接立即发布，"
                "需要定时就发完再在手机端调整。")
        if short_title:
            n = len(short_title)
            if n < SHORT_TITLE_MIN or n > SHORT_TITLE_MAX:
                probs.append("视频号短标题 %d 字，要求 %d~%d 字" %
                             (n, SHORT_TITLE_MIN, SHORT_TITLE_MAX))
        if title and len(title) > 1000:
            probs.append("视频号描述过长")

    if tags:
        bad = [t for t in tags if t.startswith("#")]
        if bad:
            probs.append("tags 不要带 # 号，工具会自己加（当前: %s）" % ",".join(bad))
    return probs


def upload(cfg, platform, file, title, desc="", tags=None, short_title=None,
           schedule=None, thumbnail=None, account="main", dry_run=False, echo=True):
    probs = validate(platform, title, desc, tags, short_title, schedule, file, thumbnail)
    if probs:
        raise PublishError("前置校验未通过:\n  - " + "\n  - ".join(probs))

    rc, out = run(cfg, platform, "upload-video", file=file, title=title, desc=desc,
                  tags=tags, short_title=short_title, schedule=schedule,
                  thumbnail=thumbnail, account=account, dry_run=dry_run)
    if echo:
        print(out)
    if rc != 0:
        raise PublishError("发布失败（退出码 %d），完整日志见上" % rc)
    return rc, out


def login(cfg, platform, account="main", dry_run=False):
    rc, out = run(cfg, platform, "login", account=account, dry_run=dry_run)
    print(out)
    return rc


def check(cfg, platform, account="main", dry_run=False):
    rc, out = run(cfg, platform, "check", account=account, dry_run=dry_run)
    return rc == 0, out.strip()
