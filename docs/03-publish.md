# 03 · 发布（抖音 / 微信视频号）

发布层只是把 [social-auto-upload](https://github.com/dreammis/social-auto-upload) 的 CLI 包了一层，
外加**平台硬约束的前置校验**——省掉「跑完 2 分钟浏览器、最后一步被拒」的时间。

## 先登录（每个账号只需一次）

```bash
python -m autopilot login douyin  --account main
python -m autopilot login channels --account main
```

会弹出 **带界面的** 浏览器（登录必须 `--headed`，否则看不到二维码）。
用手机扫码，成功后 cookie 存在 `social-auto-upload/cookies/`。

确认登录态是否还有效：

```bash
python -m autopilot check douyin  --account main     # 输出 valid / invalid
python -m autopilot check channels --account main
```

## 抖音

```bash
python -m autopilot publish douyin \
  --file      out/作品A.mp4 \
  --title     "开头一句话，决定前3秒留不留人" \
  --desc      "补充事实与结论，完整信息放这里，不要塞进标题。" \
  --tags      "话题一,话题二,话题三" \
  --thumbnail out/封面A.jpg
```

| 参数 | 说明 |
|---|---|
| `--title` | **≤30 字**，上游是 `title[:30]`，超长会被**静默截断**，所以本地先拦 |
| `--desc` | 写进正文描述，会被拼在标题下方 |
| `--tags` | 逗号分隔，**不写 `#`**，工具自己加 |
| `--thumbnail` | 3:4 竖版封面 1080×1440 |
| `--schedule` | `"YYYY-MM-DD HH:MM"`，定时发布（抖音支持） |

定时后想改成立即发？**不用重传**，见 [04-gotchas](04-gotchas.md) 第 2 条。

## 微信视频号

```bash
python -m autopilot publish channels \
  --file        out/作品A.mp4 \
  --title       "视频号这里的 title 是描述正文，可以写长一点，讲清楚发生了什么。" \
  --desc        "追加一段结尾或补充说明。" \
  --short-title "车没了但人没事" \
  --tags        "话题一,话题二,话题三" \
  --thumbnail   out/封面A.jpg
```

| 参数 | 说明 |
|---|---|
| `--title` | 描述正文，可以长 |
| `--desc` | 追加一段描述 |
| `--short-title` | **7~15 字**，视频号的「短标题」入口，这个位置流量更好 |
| `--thumbnail` | 3:4 竖版封面 |
| `--schedule` | ❌ **不要用**，会给本工具直接报错拦截（原因见 04-gotchas 第 1 条） |

## 封面

两个平台都用 **3:4（1080×1440）**：

```bash
python -m autopilot cover examples/cover.example.json
```

封面设计三原则：

1. **一张图看懂发生了什么**（事故车、对比图、极限场景）
2. **大字只有一句结论**，不超过 10 字
3. **副标放数字/限定语**（时间、里程、官方口径），别放大段文字

## 发布后自检

```bash
# 抖音发布结果在创作者中心「内容管理 → 作品」，注意看是「已发布」还是「定时:」
# 视频号在「内容管理 → 视频」，首页视频总数 +1 即为成功
```

工具退出码非 0 时不要盲目重试——**可能已经提交成功**（平台回执慢）。
先去后台确认，再决定是否重发。

## 只发不校验（看命令长什么样）

```bash
python -m autopilot publish douyin --file out/a.mp4 --title "测试" --dry-run
```

会打印真正要执行的命令而不执行，方便排查参数问题。
