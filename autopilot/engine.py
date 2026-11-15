# -*- coding: utf-8 -*-
"""成片装配引擎（这条流水线的核心）

设计要点（都是踩过坑换来的）：
1. **分段配音再对齐时间轴**：每个分镜单独 TTS，拿到逐词时间戳，段长 = 该段音频时长 + 气口。
   这样口播、画面、字幕天然同步，不需要手工对时长。
2. **图片走满屏 Ken Burns**，16:9 视频走「1080 宽前景 + 同帧模糊背景」，
   避免竖屏里出现大黑边。
3. **双层 ASS**：底部口播字幕 + 顶部大字卡，靠 libass 一次烧录。
4. **响度归一**：amix 默认 normalize 会把音量砍半，必须 normalize=0，再 loudnorm 到 -14 LUFS。
"""
import asyncio
import math
import os
import re
import shutil
import subprocess

from . import cards

W, H, FPS = 1080, 1920, 30


# ---------------------------------------------------------------- 基础
def _run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError("命令失败:\n%s\n%s" % (" ".join(cmd)[:800], (r.stderr or "")[-2000:]))
    return r


def _probe(cfg, path):
    r = subprocess.run([cfg["ffprobe"], "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float((r.stdout or "0").strip() or 0)


async def _tts(text, mp3, voice, rate):
    """返回 [{'t':词,'s':起,'d':时长}]"""
    import edge_tts  # 延迟导入，保证 doctor 在缺依赖时也能给出提示
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    audio, words = b"", []
    async for ch in comm.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append({"t": ch["text"], "s": ch["offset"] / 1e7, "d": ch["duration"] / 1e7})
    with open(mp3, "wb") as f:
        f.write(audio)
    return words


def _to_wav(cfg, src, dst):
    _run([cfg["ffmpeg"], "-y", "-v", "error", "-i", src, "-ar", "44100", "-ac", "2",
          "-c:a", "pcm_s16le", dst])
    return dst


def _silence(cfg, dur, dst):
    _run([cfg["ffmpeg"], "-y", "-v", "error", "-f", "lavfi", "-i",
          "anullsrc=channel_layout=stereo:sample_rate=44100", "-t", "%.3f" % dur,
          "-c:a", "pcm_s16le", dst])
    return dst


# ---------------------------------------------------------------- 字幕断句
def split_cues(words, max_len=13, min_dur=0.55):
    """按标点切句；超长句按字符数「均衡」切分；合并过短闪现句。

    max_len 取 13 是实测：58px 字号下 13 个汉字正好一行不换行，
    再长会折行；而简单粗暴地按上限截断会切出 0.3~0.5 秒的残句。
    """
    toks = [{"t": w["t"].strip(), "s": w["s"], "e": w["s"] + w["d"]}
            for w in words if w["t"].strip()]

    clauses, cur = [], []
    for tk in toks:
        cur.append(tk)
        if re.search(r"[，。！？、：；—…,.!?]$", tk["t"]):
            clauses.append(cur)
            cur = []
    if cur:
        clauses.append(cur)

    groups = []
    for cl in clauses:
        total = sum(len(x["t"]) for x in cl)
        if total <= max_len or len(cl) <= 1:
            groups.append(cl)
            continue
        n = int(math.ceil(total / float(max_len)))
        targets = [total * i / float(n) for i in range(1, n)]
        parts, prev, acc, idx = [], 0, 0, 0
        for tgt in targets:
            while idx < len(cl) - 1 and acc + len(cl[idx]["t"]) <= tgt + 0.51:
                acc += len(cl[idx]["t"])
                idx += 1
            parts.append(cl[prev:idx])
            prev = idx
        parts.append(cl[prev:])
        groups += [p for p in parts if p]

    cues = []
    for g in groups:
        st, en = g[0]["s"], g[-1]["e"]
        txt = "".join(x["t"] for x in g)
        if cues and (en - st) < min_dur:
            cues[-1]["text"] += txt
            cues[-1]["end"] = en
        else:
            cues.append({"text": txt, "start": st, "end": en})
    return cues


# ---------------------------------------------------------------- ASS
ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Microsoft YaHei,58,&H00FFFFFF,&H000000FF,&H00141414,&H78000000,-1,0,0,0,100,100,1,0,1,4,2,2,64,64,250,1
Style: Card,Microsoft YaHei,86,&H00FFFFFF,&H000000FF,&H00101010,&H00000000,-1,0,0,0,100,100,2,0,1,6,4,8,50,50,168,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_t(s):
    cs = int(round(max(s, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    sec, cs = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, sec, cs)


def write_ass(path, cues, cards_events):
    ev = []
    for st, en, txt in cues:
        ev.append("Dialogue: 0,%s,%s,Sub,,0,0,0,,{\\fad(120,80)}%s"
                  % (_ass_t(st), _ass_t(en), txt))
    for st, en, txt, color in cards_events:
        c = r"{\c&H00D7FF&}" if color == "gold" else r"{\c&HFFFFFF&}"   # &HBBGGRR
        ev.append("Dialogue: 1,%s,%s,Card,,0,0,0,,{\\fad(220,200)}%s%s"
                  % (_ass_t(st), _ass_t(en), c, txt.replace("\n", "\\N")))
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(ASS_HEAD + "\n".join(ev) + "\n")


# ---------------------------------------------------------------- 单段渲染
def _render_photo(cfg, img, out, dur, motion="in", zoom_max=1.12, contrast=1.05):
    n = max(1, int(round(dur * FPS)))
    rate = (zoom_max - 1.0) / n
    zexpr = ("max(%.4f-%.6f*in,1.0)" % (zoom_max, rate)) if motion == "out" \
        else ("min(1+%.6f*in,%.4f)" % (rate, zoom_max))
    xmap = {"in": "iw/2-(iw/zoom/2)", "left": "0", "right": "iw-iw/zoom",
            "out": "iw/2-(iw/zoom/2)"}
    x = xmap.get(motion, xmap["in"])
    y = "ih/2-(ih/zoom/2)"
    fc = ("[0:v]scale=1620:2880:force_original_aspect_ratio=increase:flags=lanczos,"
          "crop=1620:2880,setsar=1,"
          "zoompan=z='%s':d=1:x='%s':y='%s':s=%dx%d:fps=%d,"
          "eq=contrast=%.3f:saturation=1.05:brightness=-0.015,"
          "vignette=PI/4.6,format=yuv420p[v]"
          % (zexpr, x, y, W, H, FPS, contrast))
    _run([cfg["ffmpeg"], "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS),
          "-t", "%.3f" % dur, "-i", img, "-filter_complex", fc, "-map", "[v]",
          "-t", "%.3f" % dur, "-r", str(FPS), "-an", "-c:v", "libx264",
          "-preset", "veryfast", "-crf", "18", out])


def _render_video169(cfg, src, out, ss, to, dur, fg_h=700, fg_y=612):
    """16:9 素材：整宽前景 + 同帧模糊背景，速度按旁白长度自动拉伸/压缩。"""
    span = to - ss
    rate = span / dur
    fc = (
        "[0:v]setpts=PTS/%.4f,fps=%d,split=2[fg0][bgsrc];"
        "[fg0]scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=%d:%d,setsar=1[fg];"
        "[bgsrc]scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
        "crop=%d:%d,gblur=sigma=20,eq=brightness=-0.08:saturation=0.85[bg];"
        "[bg][fg]overlay=0:%d,"
        "eq=contrast=1.05:saturation=1.06,vignette=PI/4.6,format=yuv420p[v]"
        % (rate, FPS, W, fg_h, W, fg_h, W, H, W, H, fg_y))
    _run([cfg["ffmpeg"], "-y", "-v", "error", "-ss", "%.3f" % ss, "-to", "%.3f" % to,
          "-i", src, "-filter_complex", fc, "-map", "[v]", "-t", "%.3f" % dur,
          "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "18", out])


# ---------------------------------------------------------------- 主流程
def build(cfg, board, verbose=True):
    """board: 分镜表 dict，见 examples/storyboard.example.json

    返回 (输出路径, 总时长秒)
    """
    segs = board["segments"]
    voice = board.get("voice", "zh-CN-YunjianNeural")
    rate = board.get("rate", "+8%")
    tag = board.get("tag", "video")

    work = os.path.join(cfg["work_dir"], tag)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    os.makedirs(cfg["out_dir"], exist_ok=True)

    grad = cards.make_grad_overlay(os.path.join(work, "grad.png"))

    # 1) 分段配音
    if verbose:
        print("[%s] 配音 ..." % tag)
    aud = []
    for i, sg in enumerate(segs):
        if not sg.get("vo"):
            raise ValueError("segment %d 缺少 vo（口播稿）" % i)
        mp3 = os.path.join(work, "vo%02d.mp3" % i)
        words = asyncio.run(_tts(sg["vo"], mp3, voice, rate))
        wav = _to_wav(cfg, mp3, os.path.join(work, "vo%02d.wav" % i))
        aud.append({"wav": wav, "dur": _probe(cfg, wav), "words": words})
        if verbose:
            print("   vo%02d %5.2fs  %s" % (i, aud[-1]["dur"], sg["vo"][:26]))

    # 2) 时间轴
    pad, lead, tail = cfg["pad"], cfg["lead"], cfg["tail"]
    t = lead
    for i, sg in enumerate(segs):
        sg["_start"] = t
        sg["_dur"] = aud[i]["dur"] + pad + float(sg.get("extra", 0.0))
        if sg.get("kind") == "video":
            span = float(sg["to"]) - float(sg["ss"])
            sp = span / sg["_dur"]
            if sp < 0.55 or sp > 2.2:
                print("   !! seg%02d 速度 %.2f 超出建议区间(0.55~2.2)，画面会过快/过慢"
                      % (i, sp))
        t += sg["_dur"]
    total = t + tail
    if verbose:
        print("[%s] 总时长 %.2fs / %d 段" % (tag, total, len(segs)))

    # 3) 画面
    files = []
    for i, sg in enumerate(segs):
        out = os.path.join(work, "seg%02d.mp4" % i)
        d = sg["_dur"]
        kind = sg.get("kind", "photo")
        if kind == "video":
            _render_video169(cfg, sg["src"], out, float(sg["ss"]), float(sg["to"]), d)
        else:
            default_zoom = 1.12 if kind == "photo" else 1.035
            _render_photo(cfg, sg["src"], out, d, motion=sg.get("motion", "in"),
                          zoom_max=float(sg.get("zoom", default_zoom)))
        files.append(out)
        if verbose:
            print("   seg%02d %.2fs  %s" % (i, d, kind))

    # 4) 拼接 + 压暗
    lst = os.path.join(work, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in files:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    raw = os.path.join(work, "full_raw.mp4")
    _run([cfg["ffmpeg"], "-y", "-v", "error", "-f", "concat", "-safe", "0",
          "-i", lst, "-c", "copy", raw])

    full = os.path.join(work, "full.mp4")
    _run([cfg["ffmpeg"], "-y", "-v", "error", "-i", raw, "-loop", "1", "-i", grad,
          "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]",
          "-map", "[v]", "-t", "%.3f" % total, "-r", str(FPS),
          "-c:v", "libx264", "-preset", "medium", "-crf", "20", full])

    # 5) 音轨
    parts = [_silence(cfg, lead, os.path.join(work, "s_lead.wav"))]
    spad = _silence(cfg, pad, os.path.join(work, "s_pad.wav"))
    for i in range(len(segs)):
        parts.append(aud[i]["wav"])
        if i < len(segs) - 1:
            parts.append(spad)
    parts.append(_silence(cfg, tail, os.path.join(work, "s_tail.wav")))
    ins = []
    for p in parts:
        ins += ["-i", p]
    fc = "".join("[%d:a]" % i for i in range(len(parts)))
    fc += "concat=n=%d:v=0:a=1[a]" % len(parts)
    voice_wav = os.path.join(work, "voice.wav")
    _run([cfg["ffmpeg"], "-y", "-v", "error"] + ins +
         ["-filter_complex", fc, "-map", "[a]", "-c:a", "pcm_s16le", voice_wav])

    # 6) 字幕
    cues, cev = [], []
    for i, sg in enumerate(segs):
        off = sg["_start"]
        for c in split_cues(aud[i]["words"], max_len=int(sg.get("cue_max", 13))):
            cues.append((off + c["start"], off + c["end"], c["text"]))
        if sg.get("card"):
            cev.append((off + 0.12, off + sg["_dur"] - 0.10, sg["card"],
                        sg.get("card_color", "white")))
    ass = os.path.join(work, "sub.ass")
    write_ass(ass, cues, cev)

    # 7) BGM + 字幕烧录
    bgm_name = board.get("bgm")
    out_path = board.get("out") or os.path.join(cfg["out_dir"], "%s.mp4" % tag)
    if not os.path.isabs(out_path):
        out_path = os.path.join(cfg["_base"], out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    fade = max(0.0, total - 1.4)
    if bgm_name:
        bgm = bgm_name if os.path.isabs(bgm_name) else os.path.join(cfg["bgm_dir"], bgm_name)
        if not os.path.isfile(bgm):
            raise FileNotFoundError("BGM 不存在: %s（把音乐放进 assets/bgm/ 或改 storyboard.bgm）" % bgm)
        fc = ("[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.0[a1];"
              "[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=%s[a2];"
              "[a1][a2]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
              "loudnorm=I=-14:TP=-1.5:LRA=11,"
              "afade=t=out:st=%.2f:d=1.4[aout]" % (cfg["bgm_volume"], fade))
        _run([cfg["ffmpeg"], "-y", "-v", "error", "-i", full, "-i", voice_wav,
              "-stream_loop", "-1", "-i", bgm, "-filter_complex", fc,
              "-map", "0:v", "-map", "[aout]", "-vf", "subtitles=sub.ass",
              "-t", "%.3f" % total, "-r", str(FPS), "-c:v", "libx264",
              "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
              "-ar", "44100", "-movflags", "+faststart", out_path], cwd=work)
    else:
        fc = ("[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.0,"
              "loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st=%.2f:d=1.4[aout]" % fade)
        _run([cfg["ffmpeg"], "-y", "-v", "error", "-i", full, "-i", voice_wav,
              "-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
              "-vf", "subtitles=sub.ass", "-t", "%.3f" % total, "-r", str(FPS),
              "-c:v", "libx264", "-preset", "medium", "-crf", "20",
              "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
              "-movflags", "+faststart", out_path], cwd=work)

    if verbose:
        print("[%s] 完成 -> %s (%.1fs)" % (tag, out_path, total))
    return out_path, total
