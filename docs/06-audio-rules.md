# 06 · 音频铁律（两次返工换来的）

画面难看还能改，**音频坏了往往整条片作废**，而且它不吵、不爆、波形也正常——
只有戴上耳机才知道完蛋了。这一页是硬规则，`python -m autopilot qc` 会逐条拦。

---

## 事故一：每个切点加 whoosh → 全片"噗呲噗呲"

**现象**：成片压着人声有周期性"呲"声。采样峰值 -1.8 dBFS，无削波，波形完全正常。

**测量**（这也是为什么必须做频谱检查）：

| 指标 | 实测值 | 结论 |
|---|---|---|
| 频谱重心 | **8335 Hz** | 不是"呼"的气流声 |
| >4 kHz 能量占比 | **62.7%** | 是高频噪声，听感就是"呲" |
| 触发次数 | 17 个切点 × 2 条叠放 | 34 次，密到像底噪 |

**规则**：

1. **默认不加切点音效。** 抖音/视频号的节奏靠画面和音乐，不靠 whoosh。
2. 必须加时：只放 **2–3 个大段落转折**（开场、反转、落版），**单条**，不叠。
3. 音色换成**扫频带通 800–4000 Hz（带共振）**，不要宽带噪声。
4. 电平 **≤ -24 dB**。
5. 合成后先自查频谱：重心落在 **2–6 kHz** 才允许上线。

```python
# 自查：频谱重心
import numpy as np, soundfile as sf   # 或解码成 float 数组
x, sr = sf.read("whoosh.wav")
spec = np.abs(np.fft.rfft(x)); fr = np.fft.rfftfreq(len(x), 1/sr)
print("centroid", (spec*fr).sum()/spec.sum())   # >6k 就是"呲"
```

## 事故二：`amix duration=first` → 片尾静音

**现象**：35.50 秒的片子，音频只有 **33.38 秒**，最后 2 秒完全没声（-99 dBFS）。
片尾正好是价格/落版卡，等于全片最重要的信息在静音里播完。

**原因**：`amix=inputs=N:duration=first` 以**第一路输入**的长度为准。第一路是配音，
配音一结束，整条音轨就断了——BGM 也跟着断。

**正确写法**：

```text
[1:a]aresample=48000,volume=<gain>,apad=whole_dur=<成片时长>[vo]
[2:a]atrim=0:<成片时长>,asetpts=PTS-STARTPTS,aresample=48000,volume=0.12[bgn]
[vo][bgn]amix=inputs=2:duration=longest:normalize=0[a]
```

再在输出端 `-t <成片时长>` 兜底。质检第 1 项就是查这个。

## 事故三：三层增益把动态压扁

`loudnorm` + 手动 `volume=+2.6dB` + `alimiter` 叠一起，声音忽大忽小、副歌发闷。

**规则**：两遍 `loudnorm`——第一次 `print_format=json` 测 `input_i / input_lra /
input_tp / input_thresh / target_offset`，第二次带 `measured_*` 应用；末尾只留一个
`alimiter` 防瞬时过载。不要额外 `volume`。

## 事故四：素材本身就是静音

`ffprobe ... -af volumedetect` 打出 `mean_volume: -91.0 dB` 就是没有有效音轨。
别指望"用原声"，直接走 BGM。开工前先检查一遍所有素材的音轨，能省一次返工。

---

## 发布前必须跑

```bash
python -m autopilot qc out/final.mp4 --expect-duration 35.5
```

5 项全 PASS 才发。它会告诉你：时长是否对齐、片尾是否静音、有没有削波、
有没有周期性瞬态、瞬态是不是高频噪声型。
