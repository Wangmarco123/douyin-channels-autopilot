# -*- coding: utf-8 -*-
"""命令行入口：python -m autopilot <子命令>

  doctor                      环境自检
  build <storyboard.json>     出成片
  cover <cover.json>          出 3:4 封面
  publish douyin|channels     发布（含前置校验）
  login  douyin|channels      扫码登录
  check  douyin|channels      检查登录态
"""
import argparse
import json
import os
import sys

from . import config, engine, publish
from . import cards as cardmod


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_doctor(cfg, a):
    return 1 if config.print_check(cfg) else 0


def cmd_build(cfg, a):
    board = _load_json(a.storyboard)
    # 相对路径按 storyboard 所在目录解析
    base = os.path.dirname(os.path.abspath(a.storyboard))
    for sg in board.get("segments", []):
        if sg.get("src") and not os.path.isabs(sg["src"]):
            sg["src"] = os.path.normpath(os.path.join(base, sg["src"]))
    cfg["_base"] = base if not os.path.isabs(board.get("out", "")) else cfg["_base"]
    out, total = engine.build(cfg, board)
    print("输出: %s (%.1fs)" % (out, total))
    return 0


def cmd_cover(cfg, a):
    spec = _load_json(a.cover)
    base = os.path.dirname(os.path.abspath(a.cover))

    def rp(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))

    out = cardmod.make_cover(
        base=rp(spec["base"]),
        out_jpg=rp(spec["out"]),
        tag=spec.get("tag", ""),
        main_lines=spec["main_lines"],
        sub=spec.get("sub", ""),
        sub2=spec.get("sub2"),
        font_bold=cfg["font_bold"],
        top_anchor=spec.get("top_anchor"),
    )
    print("封面: %s" % out)
    return 0


def cmd_publish(cfg, a):
    tags = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    publish.upload(cfg, a.platform, a.file, a.title, a.desc or "", tags,
                   short_title=a.short_title, schedule=a.schedule,
                   thumbnail=a.thumbnail, account=a.account, dry_run=a.dry_run)
    return 0


def cmd_login(cfg, a):
    return 0 if publish.login(cfg, a.platform, a.account, a.dry_run) == 0 else 1


def cmd_check(cfg, a):
    ok, out = publish.check(cfg, a.platform, a.account, a.dry_run)
    print(out)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="autopilot", description="抖音 / 视频号 竖版短视频自动化")
    ap.add_argument("-c", "--config", help="config.json 路径")
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("doctor", help="环境自检").set_defaults(fn=cmd_doctor)

    b = sp.add_parser("build", help="按分镜表出成片")
    b.add_argument("storyboard")
    b.set_defaults(fn=cmd_build)

    c = sp.add_parser("cover", help="按配置出 3:4 封面")
    c.add_argument("cover")
    c.set_defaults(fn=cmd_cover)

    for name, fn in (("publish", cmd_publish), ("login", cmd_login), ("check", cmd_check)):
        p = sp.add_parser(name, help=name)
        p.add_argument("platform", choices=["douyin", "channels"])
        p.add_argument("--account", default="main")
        p.add_argument("--dry-run", action="store_true")
        p.set_defaults(fn=fn)
        if name == "publish":
            p.add_argument("--file", required=True)
            p.add_argument("--title", required=True)
            p.add_argument("--desc", default="")
            p.add_argument("--tags", default="", help="逗号分隔，不要带 #")
            p.add_argument("--short-title", dest="short_title", default=None,
                           help="仅视频号，7~15 字")
            p.add_argument("--schedule", default=None,
                           help="仅抖音，'YYYY-MM-DD HH:MM'；视频号不支持")
            p.add_argument("--thumbnail", default=None, help="3:4 封面图")

    a = ap.parse_args(argv)
    cfg = config.load(a.config)
    try:
        return a.fn(cfg, a)
    except publish.PublishError as e:
        print("错误: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
