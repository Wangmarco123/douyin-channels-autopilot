# 01 · 安装

## 1. 系统依赖

| 组件 | 用途 | 说明 |
|---|---|---|
| Python 3.10+ | 运行 | 建议 3.11/3.12 |
| FFmpeg + ffprobe | 剪辑 / 烧字幕 / 混音 | 必须带 **libass**（否则 `subtitles=` 滤镜不可用） |
| 中文字体 | 字幕与卡片 | Windows 自带微软雅黑即可；Linux 装 Noto Sans CJK |

验证 libass：

```bash
ffmpeg -hide_banner -filters | grep subtitles
```

有输出即为可用。

```bash
# Windows (winget)
winget install Gyan.FFmpeg
# macOS
brew install ffmpeg
# Ubuntu
sudo apt install ffmpeg fonts-noto-cjk
```

## 2. 安装本仓库

```bash
git clone https://github.com/Wangmarco123/douyin-channels-autopilot.git
cd douyin-channels-autopilot
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 3. 安装发布引擎（可选，只出片不需要）

发布依赖开源项目 [social-auto-upload](https://github.com/dreammis/social-auto-upload)（MIT）。
本仓库**不内置**它，请单独克隆：

```bash
git clone https://github.com/dreammis/social-auto-upload.git
cd social-auto-upload
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## 4. 配置

```bash
cp config.example.json config.json
```

改这几项：

```jsonc
{
  "ffmpeg":  "C:/ffmpeg/bin/ffmpeg.exe",   // 不在 PATH 就写绝对路径
  "ffprobe": "C:/ffmpeg/bin/ffprobe.exe",
  "font_bold":    "C:/Windows/Fonts/msyhbd.ttc",
  "font_regular": "C:/Windows/Fonts/msyh.ttc",

  "sau_dir":    "D:/tools/social-auto-upload",              // 发布才需要
  "sau_python": "D:/tools/social-auto-upload/.venv/Scripts/python.exe"
}
```

> `config.json` 已在 `.gitignore` 里，不会被提交。

## 5. 自检

```bash
python -m autopilot doctor
```

期望全部 `[OK]`。然后跑一遍最小示例：

```bash
python examples/run_example.py
```

看到 `out/demo.mp4`（约 15 秒竖版、有配音和字幕）就说明整条链是通的。
