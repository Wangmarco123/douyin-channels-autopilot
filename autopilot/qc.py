# -*- coding: utf-8 -*-
"""发布前音频质检门 —— 不通过就别发。

为什么需要它：两次真实返工都不是"画面难看"，而是**音频悄悄坏了**：

1. 每个切点塞了自合成噪声 whoosh，实测频谱重心 8.3kHz、62.7% 能量在 4kHz 以上，
   17 个切点叠起来，人声底下就是持续的"噗呲噗呲"——但采样峰值正常、没有削波，
   肉眼看波形根本发现不了。
2. 混音写成 `amix duration=first`（第一路是配音），配音一结束整条音轨就断了，
   35.5 秒的片子音频只有 33.4 秒，最后 2 秒静音。

5 项判定，任一不过返回码 1：

| 检查 | 阈值 | 拦截的事故 |
|---|---|---|
| 音视频时长一致 | ±0.30s | amix duration=first 造成的片尾静音 |
| 片尾非静音 | RMS > -60 dBFS | 黑屏/静音片尾被判低质 |
| 无削波 | 峰值 ≤ -1.0 dBFS，无连续削波 | 爆音 |
| 周期性瞬态 | ≤ 4 处 | 每个切点一条音效 |
| 瞬态频谱重心 | < 6 kHz | 高频噪声型 whoosh（"噗呲"元凶） |

用法：
    python -m autopilot qc out/final.mp4 --expect-duration 35.5
    python -m autopilot qc out/final.mp4 --json
"""
import argparse
import json
import subprocess
import sys

SR = 48000


def _run(cmd):
    return subprocess.run(cmd, capture_output=True)


def _probe_duration(path, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream]
    cmd += ["-show_entries", "format=duration:stream=duration", "-of", "json", str(path)]
    out = _run(cmd).stdout.decode("utf-8", "replace")
    data = json.loads(out or "{}")
    if stream:
        for s in data.get("streams", []):
            if s.get("duration"):
                return float(s["duration"])
    return float(data.get("format", {}).get("duration", 0.0))


def _decode(path, sr=SR):
    raw = _run(["ffmpeg", "-v", "error", "-i", str(path),
                "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"]).stdout
    if not raw:
        raise RuntimeError("解码失败或没有音轨: %s" % path)
    try:
        import numpy as np
    except ImportError:
        raise RuntimeError("缺 numpy：pip install numpy")
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def analyse(x, max_transients=4):
    """返回原始测量值。周期瞬态用 20ms 能量包络的差分 99.5 分位突刺统计。"""
    import numpy as np

    peak = float(np.abs(x).max()) if len(x) else 0.0
    peak_db = 20 * np.log10(peak + 1e-9)
    clip_runs = 0
    if len(x):
        mask = np.abs(x) > 0.985
        clip_runs = int((mask[1:] & ~mask[:-1]).sum())

    hop = int(SR * 0.02)
    n = len(x) // hop
    env = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2))
                    for i in range(n)]) if n else np.array([])
    d = np.diff(env) if len(env) > 2 else np.array([])
    spikes, centroid = [], 0.0
    if len(d) > 20:
        thr = np.percentile(np.abs(d), 99.5)
        idx = np.where(np.abs(d) > max(thr, 1e-4))[0]
        merged = []
        for i in idx:  # 0.2s 内的突刺算同一次
            if not merged or i - merged[-1] > 10:
                merged.append(int(i))
        spikes = merged
        cents = []
        for i in spikes[:8]:
            seg = x[max(0, i * hop - hop): i * hop + hop * 3]
            if len(seg) < 256:
                continue
            spec = np.abs(np.fft.rfft(seg))
            fr = np.fft.rfftfreq(len(seg), 1 / SR)
            if spec.sum() > 0:
                cents.append(float((spec * fr).sum() / spec.sum()))
        centroid = float(np.mean(cents)) if cents else 0.0

    tail = x[int(len(x) * 0.9):] if len(x) else x
    tail_db = 20 * np.log10(np.sqrt(np.mean(tail ** 2)) + 1e-9) if len(tail) else -99.0
    return {
        "peak_dbfs": round(peak_db, 2),
        "clip_runs": clip_runs,
        "transients": len(spikes),
        "transient_centroid_hz": round(centroid, 1),
        "tail_rms_dbfs": round(tail_db, 1),
        "max_transients": max_transients,
    }


def check(path, expect=None, max_transients=4, centroid_limit=6000.0):
    """跑完整质检，返回 {"passed": bool, "checks": [...]}。"""
    v_dur = _probe_duration(path, "v:0")
    a_dur = _probe_duration(path, "a:0")
    m = analyse(_decode(path), max_transients)
    total = expect if expect is not None else v_dur

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("音视频时长一致", abs(a_dur - total) <= 0.30,
        "audio=%.2fs expect=%.2fs" % (a_dur, total))
    add("片尾非静音", m["tail_rms_dbfs"] > -60.0,
        "tail_rms=%.1fdBFS" % m["tail_rms_dbfs"])
    add("无削波", m["peak_dbfs"] <= -1.0 and m["clip_runs"] == 0,
        "peak=%.1fdBFS clip_runs=%d" % (m["peak_dbfs"], m["clip_runs"]))
    add("瞬态数量受控", m["transients"] <= max_transients,
        "transients=%d (limit %d)" % (m["transients"], max_transients))
    add("瞬态不是高频噪声", m["transient_centroid_hz"] < centroid_limit,
        "centroid=%.0fHz" % m["transient_centroid_hz"])

    return {"file": str(path), "video_duration": round(v_dur, 2),
            "audio_duration": round(a_dur, 2), "passed": not any(not c["ok"] for c in checks),
            "checks": checks}


def report(res, as_json=False):
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("文件: %s" % res["file"])
    print("视频 %.2fs / 音频 %.2fs" % (res["video_duration"], res["audio_duration"]))
    for c in res["checks"]:
        print("  [%s] %s: %s" % ("PASS" if c["ok"] else "FAIL", c["check"], c["detail"]))
    if res["passed"]:
        print("\n全部通过")
    else:
        print("\n未通过 —— 不要发。常见修法：")
        print("  · 片尾静音/时长不符 → 混音加 apad=whole_dur=<成片时长> + amix duration=longest")
        print("  · 瞬态过多 → 删掉每个切点的合成音效，只留 1-2 个大段落转折")
        print("  · 瞬态高频 → 换 800-4000Hz 扫频带通，电平压到 -24dB 以下")


def run(path, expect=None, max_transients=4, centroid_limit=6000.0, as_json=False):
    res = check(path, expect=expect, max_transients=max_transients,
                centroid_limit=centroid_limit)
    report(res, as_json=as_json)
    return 0 if res["passed"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="autopilot qc", description="发布前音频质检门")
    ap.add_argument("video")
    ap.add_argument("--expect-duration", type=float, default=None)
    ap.add_argument("--max-transients", type=int, default=4)
    ap.add_argument("--centroid-limit", type=float, default=6000.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        return run(a.video, a.expect_duration, a.max_transients, a.centroid_limit, a.json)
    except Exception as e:
        print("质检失败: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
