#!/bin/bash
# Case materials helper: double-click for GUI, drop files for conversion.

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HELP_MD="$CONTENTS_DIR/Resources/使用说明.md"
README_MD="$CONTENTS_DIR/Resources/README.md"
OUTPUT_DIR="$HOME/Desktop/VisionOCR_Output"
ARCHIVE_DIR="$OUTPUT_DIR/archive"
LOG="/tmp/vision-ocr-app.log"
PY="/opt/homebrew/bin/python3"
GUI="$CONTENTS_DIR/Resources/vision-ocr-gui-native.py"
if [ ! -f "$GUI" ]; then
    GUI="$HOME/.local/bin/vision-ocr-gui-native.py"
fi
OCR_CLI="$HOME/.local/bin/vision-ocr-pdf"
AGENT_CLI="$HOME/.local/bin/visionocr-agent"
MINERU_CLI="$HOME/.local/bin/mineru-local"
LEGAL_OCR_CLI="$HOME/.local/bin/legal-ocr-convert"
DOCX_CLI="$HOME/.local/bin/md-to-docx"
TRANSCRIPT_CLI="$HOME/.local/bin/media-to-transcript"
MARKDOWN_CLI="$HOME/.local/bin/office-to-markdown"

print_usage() {
    if [ -f "$HELP_MD" ]; then
        cat "$HELP_MD"
        return
    fi
    printf '办案材料助手\n用法: %s "/path/to/file"\n输出: %s\n' "$0" "$OUTPUT_DIR"
}

print_notice() {
    printf '办案材料助手 AI调用须知:\n'
    printf '%s\n' "- 完整说明: $HELP_MD" "- 输出目录: $OUTPUT_DIR" "- 归档目录: $ARCHIVE_DIR"
}

print_engine_status() {
    printf '办案材料助手转换引擎状态\n'
    printf '========================\n'
    printf '本地 MinerU: %s\n' "$([ -x "$MINERU_CLI" ] && printf '可用' || printf '不可用')"
    printf 'Apple VisionOCR: %s\n' "$([ -f "$OCR_CLI" ] && printf '可用' || printf '不可用')"
    printf 'legal-ocr wrapper: %s\n' "$([ -x "$LEGAL_OCR_CLI" ] && printf '可用' || printf '不可用')"
    if [ -x "$LEGAL_OCR_CLI" ]; then
        printf '\nlegal-ocr 在线后端配置:\n'
        "$LEGAL_OCR_CLI" checktoken || true
    fi
}

notify() {
    /usr/bin/osascript - "$1" "$2" <<'APPLESCRIPT' >/dev/null 2>&1 || true
on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run
APPLESCRIPT
}

make_archive() {
    local src="$1"
    local stem="$2"
    local arc="$ARCHIVE_DIR/$(date +%Y%m%d_%H%M%S)_${stem}"
    if [ -e "$arc" ]; then
        arc="${arc}_$RANDOM"
    fi
    mkdir -p "$arc/input" "$arc/output"
    cp "$src" "$arc/input/"
    printf '%s' "$arc"
}

write_metadata() {
    "$PY" - "$1" "$2" "$3" "$4" "$5" <<'PY'
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

archive_dir, source, output, channel, success = sys.argv[1:]
data = {
    "source": source,
    "output": output,
    "channel": channel,
    "success": success == "true",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "hostname": platform.node(),
}
Path(archive_dir, "metadata.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
)
PY
}

case "${1:-}" in
    -h|--help|help)
        print_usage
        exit 0
        ;;
    --check-engines|--engines|engines)
        print_engine_status
        exit 0
        ;;
esac

case "${1:-}" in
    --wechat|--wechat-evidence)
        shift
        exec "$PY" "$GUI" --wechat "$@"
        ;;
esac

agent_mode=0
case "${1:-}" in
    --agent|--agent-fast)
        agent_mode=1
        export VISIONOCR_NO_OPEN=1
        shift
        ;;
esac

# OCR 引擎选择：
# --engine mineru|mineru-local|visionocr|legalocr|legalocr-paddle|legalocr-mineru
ocr_engine="mineru"
case "${1:-}" in
    --engine)
        shift
        ocr_engine="${1:-mineru}"
        shift
        ;;
esac

case "${1:-}" in
    -h|--help|help)
        print_usage
        exit 0
        ;;
    --check-engines|--engines|engines)
        print_engine_status
        exit 0
        ;;
esac

mkdir -p "$OUTPUT_DIR" "$ARCHIVE_DIR"
{
    printf '=== 办案材料助手启动 === %s\n' "$(date)"
    printf '输入数量: %s\n输出目录: %s\n' "$#" "$OUTPUT_DIR"
} > "$LOG"

print_notice

if [ "$#" -eq 0 ]; then
    if [ ! -f "$GUI" ]; then
        /usr/bin/osascript -e 'display alert "GUI脚本缺失" message "未找到本地办案材料助手界面脚本。"' >/dev/null 2>&1 || true
        exit 1
    fi
    exec "$PY" "$GUI"
fi

success_count=0
fail_count=0
handled_count=0

for file in "$@"; do
    if [ ! -f "$file" ]; then
        printf '跳过不存在的文件: %s\n' "$file" >> "$LOG"
        continue
    fi
    name="$(basename "$file")"
    stem="${name%.*}"
    ext="${name##*.}"
    ext="$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"
    output=""
    channel=""
    mineru_outdir=""
    handled_count=$((handled_count + 1))

    case "$ext" in
        pdf|png|jpg|jpeg|tif|tiff|bmp|gif|heic|webp)
            output="$OUTPUT_DIR/${stem}.md"
            if [ "$ocr_engine" = "legalocr" ] || [ "$ocr_engine" = "legalocr-auto" ]; then
                channel="legalocr-auto"
                command=( "$LEGAL_OCR_CLI" "$file" "--output" "$output" "--backend" "auto" )
            elif [ "$ocr_engine" = "legalocr-paddle" ] || [ "$ocr_engine" = "paddle" ]; then
                channel="legalocr-paddle"
                command=( "$LEGAL_OCR_CLI" "$file" "--output" "$output" "--backend" "paddle" "--paddle-model" "PaddleOCR-VL-1.5" )
            elif [ "$ocr_engine" = "legalocr-mineru" ]; then
                channel="legalocr-mineru"
                command=( "$LEGAL_OCR_CLI" "$file" "--output" "$output" "--backend" "mineru" )
            elif { [ "$ocr_engine" = "mineru" ] || [ "$ocr_engine" = "mineru-local" ]; } && [ -x "$MINERU_CLI" ]; then
                channel="mineru"
                mineru_outdir="$OUTPUT_DIR/_mineru_tmp_${stem}"
                command=( "$MINERU_CLI" -p "$file" -o "$mineru_outdir" )
            elif [ "$agent_mode" -eq 1 ] && [ -x "$AGENT_CLI" ]; then
                channel="ocr"
                command=( "$AGENT_CLI" "$file" "--output" "$output" )
            else
                channel="ocr"
                command=( "$PY" "$OCR_CLI" "$file" "--output" "$output" )
            fi
            ;;
        md|txt|markdown)
            output="$OUTPUT_DIR/${stem}.docx"
            channel="docx"
            command=( "$PY" "$DOCX_CLI" "$file" "--output" "$output" "--type" "general" )
            ;;
        mp3|wav|m4a|aac|flac|ogg|wma|mp4|m4v|mov|avi|mkv|webm|flv)
            output="$OUTPUT_DIR/${stem}_逐字稿.md"
            channel="transcript"
            command=( "$PY" "$TRANSCRIPT_CLI" "$file" "--output" "$output" )
            ;;
        pptx|ppt|xlsx|xls|xlsm|csv|tsv|ods|docx|doc|html|htm|epub|json|xml|zip)
            output="$OUTPUT_DIR/${stem}.md"
            channel="markitdown"
            command=( "$MARKDOWN_CLI" "$file" "--output" "$output" )
            ;;
        *)
            printf '不支持的文件类型: %s\n' "$file" >> "$LOG"
            handled_count=$((handled_count - 1))
            continue
            ;;
    esac

    archive="$(make_archive "$file" "$stem")"
    printf '%s: %s -> %s\n归档: %s\n' "$channel" "$file" "$output" "$archive" >> "$LOG"
    if [ "$agent_mode" -ne 1 ]; then
        notify "办案材料助手" "处理中：$name"
    fi
    if "${command[@]}" >> "$LOG" 2>&1; then
        # MinerU 输出到子目录 <outdir>/<stem>/auto/<stem>.md，需要提取
        if [ "$channel" = "mineru" ] && [ -d "$mineru_outdir" ]; then
            mineru_md=$(find "$mineru_outdir" -name "*.md" -type f | head -1)
            if [ -n "$mineru_md" ] && [ -f "$mineru_md" ]; then
                mv "$mineru_md" "$output"
                rm -rf "$mineru_outdir"
            else
                printf 'MinerU未生成md，降级到VisionOCR\n' >> "$LOG"
                channel="ocr"
                if [ "$agent_mode" -eq 1 ] && [ -x "$AGENT_CLI" ]; then
                    "$AGENT_CLI" "$file" "--output" "$output" >> "$LOG" 2>&1 || true
                else
                    "$PY" "$OCR_CLI" "$file" "--output" "$output" >> "$LOG" 2>&1 || true
                fi
                rm -rf "$mineru_outdir"
            fi
        fi
        if [ -f "$output" ]; then
            cp "$output" "$archive/output/"
            write_metadata "$archive" "$file" "$output" "$channel" "true"
            success_count=$((success_count + 1))
        else
            write_metadata "$archive" "$file" "$output" "$channel" "false"
            fail_count=$((fail_count + 1))
        fi
    else
        # 云端或本地 MinerU 失败时降级到本机 VisionOCR，保证尽量有可复核初稿。
        if [ "$channel" = "mineru" ] || [[ "$channel" == legalocr-* ]]; then
            printf '%s失败，降级到VisionOCR\n' "$channel" >> "$LOG"
            rm -rf "$mineru_outdir"
            channel="ocr"
            if [ "$agent_mode" -eq 1 ] && [ -x "$AGENT_CLI" ]; then
                command=( "$AGENT_CLI" "$file" "--output" "$output" )
            else
                command=( "$PY" "$OCR_CLI" "$file" "--output" "$output" )
            fi
            if "${command[@]}" >> "$LOG" 2>&1 && [ -f "$output" ]; then
                cp "$output" "$archive/output/"
                write_metadata "$archive" "$file" "$output" "$channel" "true"
                success_count=$((success_count + 1))
            else
                write_metadata "$archive" "$file" "$output" "$channel" "false"
                fail_count=$((fail_count + 1))
            fi
        else
            write_metadata "$archive" "$file" "$output" "$channel" "false"
            fail_count=$((fail_count + 1))
        fi
    fi
done

if [ "$handled_count" -eq 0 ]; then
    print_usage
    notify "办案材料助手" "没有可处理的文件"
    exit 1
fi

printf '完成: 成功=%s 失败=%s\n' "$success_count" "$fail_count" >> "$LOG"
if [ "$agent_mode" -ne 1 ]; then
    notify "办案材料助手" "转换完成：成功 $success_count，失败 $fail_count"
fi
if [ "${VISIONOCR_NO_OPEN:-0}" != "1" ]; then
    open "$OUTPUT_DIR"
fi
[ "$fail_count" -eq 0 ]
