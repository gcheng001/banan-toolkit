# 办案材料助手

完整说明：`使用说明.md`

入口：

```bash
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet "/path/to/file"
```

Agent 快速入口：

```bash
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --agent "/path/to/file"
visionocr-agent "/path/to/file" --output "/path/to/output.md"
visionocr-agent --engine legalocr-mineru "/path/to/file.pdf"
visionocr-agent --check-engines
```

PDF/图片引擎可选：

```bash
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --engine mineru "/path/to/file.pdf"
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --engine visionocr "/path/to/file.pdf"
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --engine legalocr "/path/to/file.pdf"
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --engine legalocr-paddle "/path/to/file.pdf"
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --engine legalocr-mineru "/path/to/file.pdf"
/Applications/办案工具集/办案材料助手.app/Contents/MacOS/droplet --check-engines
```

输出：`~/Desktop/VisionOCR_Output/`

归档：`~/Desktop/VisionOCR_Output/archive/`

支持 PDF/图片 OCR、Word/表格转 Markdown、Markdown 转 Word、音视频转逐字稿和微信录屏取证。界面中的“证据整理”会重新扫描当前输出文件夹，基于用户修改后的 Markdown/PDF/OCR 报告生成 `证据整理/案件材料汇总.md`、`案件时间线.md`、`materials_manifest.json` 和 `case_os_intake_package.json`。`legal-ocr` 选项会通过本机已安装 skill 调用 PaddleOCR/MinerU 在线后端或轻量接口，并执行保守法律后处理；处理结果需对照原件人工核实。
