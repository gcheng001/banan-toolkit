# 办案材料助手

面向本机办案材料处理的 macOS 工具集，当前主入口是 `办案材料助手.app`。

## 功能

- 材料转 Markdown：PDF、图片、Office 文档转可检索 Markdown。
- 转 Word：Markdown 转 Word，并支持页面、字体、字号、首行缩进和行距设置。
- 录屏取证：微信/聊天录屏导出为可复核截图 PDF，支持原始截图缓存和多次重新导出。

## 下载使用

普通用户建议下载 GitHub Releases 里的 macOS zip，解压后打开 `办案材料助手.app`。

第一次打开时，如果 macOS 提示来自未知开发者，可以在「系统设置 -> 隐私与安全性」里允许打开。

## 运行环境

当前版本是本机工具包，不是完全自带运行时的商业安装包。目标机器需要具备：

- macOS 11 或更高版本。
- Homebrew Python：`/opt/homebrew/bin/python3`。
- PyObjC：用于原生 macOS 界面。
- ffmpeg：用于录屏取证抽帧。
- 可选 OCR/转换工具：`vision-ocr-pdf`、`mineru-local`、`legal-ocr-convert`、`md-to-docx`、`office-to-markdown`、`media-to-transcript`。

可以在 App 内或命令行检查引擎状态：

```bash
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --check-engines
```

## 录屏取证重导出逻辑

第一次点击「导出取证材料」会建立原始截图缓存，默认每 0.5 秒一张。

后续调整保留间隔后点击「重新导出（复用截图）」会直接从缓存重拼 PDF，不重新读取视频抽帧。只有选择更密的原始缓存，例如 0.25 秒/张，才需要重新抽一次视频。

## 注意

本工具输出结果用于办案材料整理和复核辅助，不替代人工核对。OCR、视频抽帧、去重和云端整理结果都需要对照原件复查。
