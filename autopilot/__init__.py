# -*- coding: utf-8 -*-
"""抖音 / 微信视频号 竖版短视频自动化：成片装配 + 发布封装。

模块：
  config   配置加载与环境自检
  cards    PIL 卡片/封面（截图悬浮卡、数据卡、片尾卡、3:4 封面）
  engine   成片装配（分段配音 -> 时间轴对齐 -> KenBurns/模糊填充 -> ASS 双层字幕 -> BGM+响度归一）
  publish  发布（包装 social-auto-upload：抖音 / 视频号）
"""

__version__ = "1.0.0"
