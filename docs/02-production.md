# 02 · 出成片

## 核心思路：先有稿子，再有画面

传统剪辑是「先排画面再配音」，改一句口播就要重排整条时间轴。
这条流水线反过来：**每个分镜先写口播稿 → 单独配音 → 用音频时长反推画面时长**。
口播、画面、字幕天然同步，改稿子只影响那一段。

```
分镜表(JSON) ──> 分段 TTS(带逐词时间戳) ──> 段长 = 音频长 + 气口
                    │
                    ├─> 图片: 满屏 KenBurns
                    ├─> 16:9 视频: 前景 + 同帧模糊背景(自动变速)
                    └─> 截图: 预渲染悬浮卡
                              │
                              ▼
                   拼接 → 上下压暗 → 烧 ASS 字幕 → 混 BGM → loudnorm -14 LUFS
```

## 分镜表字段

```jsonc
{
  "tag":   "作品A",                  // 工作目录名
  "voice": "zh-CN-YunjianNeural",    // edge-tts 音色
  "rate":  "+10%",                   // 语速（+6% ~ +12% 是中文短视频常用区间）
  "bgm":   "bgm01.mp3",              // assets/bgm/ 下的文件名；null 表示不要 BGM
  "out":   "../out/作品A.mp4",
  "segments": [ ... ]
}
```

每个 segment：

| 字段 | 适用 | 说明 |
|---|---|---|
| `kind` | 全部 | `photo` 图片 / `video` 16:9 视频 / `card` 已预渲染的 1080×1920 卡片 |
| `src` | 全部 | 素材路径（相对分镜表文件） |
| `vo` | 全部 | **必填**，这一段的口播稿 |
| `card` | 全部 | 顶部大字（花字），可空 |
| `card_color` | 全部 | `gold` / `white` |
| `motion` | photo | `in` / `out` / `left` / `right` |
| `zoom` | photo/card | 推近倍率，图片 1.10~1.25，卡片 1.035（几乎不动） |
| `ss` / `to` | video | 取源片区间（秒）。**引擎会自动变速**去匹配旁白长度 |
| `extra` | 全部 | 额外多留的秒数，给情绪留呼吸 |
| `cue_max` | 全部 | 该段字幕单行上限，默认 13 字 |

## 音色

`edge-tts` 免 API Key，常用中文音色：

| 音色 | 感觉 | 适合 |
|---|---|---|
| `zh-CN-YunjianNeural` | 低沉、新闻腔 | 严肃叙事、安全/技术向 |
| `zh-CN-YunxiNeural` | 年轻、偏快 | 技术罗列、清单体 |
| `zh-CN-XiaoxiaoNeural` | 亲和女声 | 生活化、口播带货 |
| `zh-CN-YunyangNeural` | 播音员 | 品牌片、官方口径 |

查看全部：`edge-tts --list-voices | findstr zh-CN`

## 素材预处理

三类素材的处理方式不同，别混用：

```python
from autopilot import cards

# 1) 手机截图/录屏：先裁掉黑边，避免满屏出现黑框
cards.clean_photo("raw/现场.jpg", "work/cards/clean_site.png")

# 2) 截图/聊天记录：做成圆角悬浮卡（直接拉伸会变形、也不好看）
cards.make_inset_card("raw/截图.jpg", "work/cards/card_shot.png",
                      font_bold=cfg["font_bold"],
                      crop=(0, 60, 620, 1060),      # 只留关键区域
                      box=(760, 1230), center_y=968)

# 3) 数据卡 / 片尾卡
cards.make_data_card("work/cards/card_data.png",
                     [("2000MPa", "A柱关键区域"), ("9", "全车安全气囊")],
                     cfg["font_bold"], foot=["钢笼式车身"])
cards.make_end_card("work/cards/card_end.png", "品牌名", "收尾金句",
                    cfg["font_bold"], cfg["font_regular"], foot="#话题")
```

预处理出来的 PNG 直接当 `kind: "card"` 的分镜用。

## 输出规格

- 1080×1920 / 30fps / H.264 (crf 20) / AAC 192k 44.1kHz
- 响度 **-14 LUFS**，峰值 ≤ -1.5 dBTP（抖音、视频号都会做响度归一，提前对齐能避免二次压限）
- `+faststart`，三平台直接可传，无需转码

## 三条经验

1. **单段时长靠 `extra` 微调**，不要靠改语速。语速一改，全片节奏都变。
2. **花字只写结论，别重复口播**。口播说「车没保住，人保住了」，花字打「车没了 人没事」。
3. **先跑通一段**：第一次做先把 2~3 个分镜跑一遍，确认字体、字幕位置、音量对了，再铺全片。

## 常见调参

| 想要 | 改哪 |
|---|---|
| 全片更快 | `rate` +2%~+4% |
| 段间更紧 | `config.pad` 0.26 → 0.18 |
| 结尾多留一拍 | `config.tail` 0.85 → 1.2 |
| BGM 更小声 | `config.bgm_volume` 0.135 → 0.10 |
| 字幕换行难看 | 调该段 `cue_max` |
