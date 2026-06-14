#!/opt/homebrew/bin/python3
"""Document-type processing helpers for the local Vision OCR tool."""

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum, auto


class DocumentType(Enum):
    """OCR material categories used by the GUI and CLI."""

    BOOK_DOCUMENT = auto()
    WECHAT_SCREENSHOT = auto()
    SMS_EMAIL = auto()
    CONTRACT_AGREEMENT = auto()
    DEBT_NOTE = auto()
    HANDWRITING = auto()
    TABLE_LIST = auto()
    BANK_RECEIPT = auto()
    INVOICE = auto()
    ID_CARD = auto()
    LEGAL_DOC = auto()
    EVIDENCE_GENERAL = auto()
    AUTO = auto()


@dataclass
class ProcessingConfig:
    dpi: int = 150
    keep_line_breaks: bool = False
    remove_headers: bool = True
    clean_garbage: bool = True
    merge_paragraphs: bool = True
    add_uncertainty_marker: bool = False


TYPE_CONFIGS = {
    DocumentType.BOOK_DOCUMENT: ProcessingConfig(),
    DocumentType.WECHAT_SCREENSHOT: ProcessingConfig(keep_line_breaks=True, remove_headers=False, clean_garbage=False, merge_paragraphs=False),
    DocumentType.SMS_EMAIL: ProcessingConfig(keep_line_breaks=True, remove_headers=False, clean_garbage=False, merge_paragraphs=False),
    DocumentType.CONTRACT_AGREEMENT: ProcessingConfig(dpi=200, keep_line_breaks=True, remove_headers=False, merge_paragraphs=False),
    DocumentType.DEBT_NOTE: ProcessingConfig(dpi=300, keep_line_breaks=True, remove_headers=False, clean_garbage=False, merge_paragraphs=False),
    DocumentType.HANDWRITING: ProcessingConfig(dpi=300, keep_line_breaks=True, remove_headers=False, clean_garbage=False, merge_paragraphs=False, add_uncertainty_marker=True),
    DocumentType.TABLE_LIST: ProcessingConfig(dpi=200, keep_line_breaks=True, remove_headers=False, merge_paragraphs=False),
    DocumentType.BANK_RECEIPT: ProcessingConfig(dpi=200, keep_line_breaks=True, remove_headers=False, merge_paragraphs=False),
    DocumentType.INVOICE: ProcessingConfig(dpi=200, keep_line_breaks=True, remove_headers=False, merge_paragraphs=False),
    DocumentType.ID_CARD: ProcessingConfig(dpi=200, keep_line_breaks=True, remove_headers=False, merge_paragraphs=False),
    DocumentType.LEGAL_DOC: ProcessingConfig(),
    DocumentType.EVIDENCE_GENERAL: ProcessingConfig(keep_line_breaks=True, remove_headers=False, clean_garbage=False, merge_paragraphs=False),
    DocumentType.AUTO: ProcessingConfig(),
}

TYPE_MAP_CLI = {
    "auto": DocumentType.AUTO,
    "book": DocumentType.BOOK_DOCUMENT,
    "wechat": DocumentType.WECHAT_SCREENSHOT,
    "sms": DocumentType.SMS_EMAIL,
    "contract": DocumentType.CONTRACT_AGREEMENT,
    "debt": DocumentType.DEBT_NOTE,
    "handwriting": DocumentType.HANDWRITING,
    "table": DocumentType.TABLE_LIST,
    "bank": DocumentType.BANK_RECEIPT,
    "invoice": DocumentType.INVOICE,
    "idcard": DocumentType.ID_CARD,
    "legal": DocumentType.LEGAL_DOC,
    "evidence": DocumentType.EVIDENCE_GENERAL,
}

TYPE_OPTIONS_GUI = [
    ("自动识别", DocumentType.AUTO),
    ("书籍/文书", DocumentType.BOOK_DOCUMENT),
    ("微信截图", DocumentType.WECHAT_SCREENSHOT),
    ("短信/邮件", DocumentType.SMS_EMAIL),
    ("合同/协议", DocumentType.CONTRACT_AGREEMENT),
    ("收条/借条", DocumentType.DEBT_NOTE),
    ("手写字迹", DocumentType.HANDWRITING),
    ("表格/清单", DocumentType.TABLE_LIST),
    ("银行回单", DocumentType.BANK_RECEIPT),
    ("发票/收据", DocumentType.INVOICE),
    ("身份证件", DocumentType.ID_CARD),
    ("司法文书", DocumentType.LEGAL_DOC),
    ("证据材料", DocumentType.EVIDENCE_GENERAL),
]

_FILENAME_KEYWORDS = {
    DocumentType.WECHAT_SCREENSHOT: ["微信", "聊天记录", "wechat", "wx_", "对话截图", "微信图片", "wx"],
    DocumentType.SMS_EMAIL: ["短信", "邮件", "sms", "email", "通信记录"],
    DocumentType.CONTRACT_AGREEMENT: ["合同", "协议", "契约", "补充协议", "买卖合同", "租赁合同", "借款合同", "服务合同", "劳动合同"],
    DocumentType.DEBT_NOTE: ["收条", "借条", "欠条", "借款条", "收据", "还款凭证", "欠款"],
    DocumentType.HANDWRITING: ["手写", "便条", "签名", "签收", "亲笔", "手书", "手签"],
    DocumentType.TABLE_LIST: ["清单", "表格", "明细", "汇总表", "统计表", "目录", "附表", "一览表"],
    DocumentType.BANK_RECEIPT: ["回单", "转账", "银行", "流水", "凭证", "网银", "支付凭证", "交易记录"],
    DocumentType.INVOICE: ["发票", "收据", "税票", "增值税", "专用发票", "普通发票"],
    DocumentType.ID_CARD: ["身份证", "营业执照", "户口本", "结婚证", "证件", "驾照", "驾驶证"],
    DocumentType.LEGAL_DOC: ["起诉状", "答辩状", "判决书", "裁定书", "调解书", "申请书", "上诉状", "申诉状", "执行书"],
    DocumentType.EVIDENCE_GENERAL: ["证据", "材料", "证明", "鉴定", "公证书", "取证"],
}

_SENTENCE_END = "。！？；.!?;"
_CONTINUE_PREFIX = "，。；：、)]}）》」』】,.;:"


def detect_type_by_filename(filename: str) -> DocumentType:
    name_lower = filename.lower()
    for doc_type, keywords in _FILENAME_KEYWORDS.items():
        if any(keyword.lower() in name_lower for keyword in keywords):
            return doc_type
    return DocumentType.AUTO


def get_config_for_type(doc_type: DocumentType) -> ProcessingConfig:
    return TYPE_CONFIGS.get(doc_type, TYPE_CONFIGS[DocumentType.BOOK_DOCUMENT])


def _is_cjk(char: str) -> bool:
    return bool(char) and "\u4e00" <= char <= "\u9fff"


def _clean_garbage(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _looks_like_doc_title(line: str) -> bool:
    return bool(re.match(r"^.{0,30}(起诉状|答辩状|裁定书|判决书|调解书|申请书|协议书|合同)$", line))


def _split_title_from_content(line: str) -> tuple[str, str]:
    return line, ""


def _looks_like_heading(line: str) -> bool:
    patterns = (
        r"^第[一二三四五六七八九十百零〇\d]+[章节条]",
        r"^[一二三四五六七八九十]+[、.]",
        r"^\d+[.、]\s*\S+",
        r"^[(（][一二三四五六七八九十\d]+[)）]",
    )
    return len(line) <= 50 and any(re.match(pattern, line) for pattern in patterns)


def _join(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if _is_cjk(left[-1]) or _is_cjk(right[0]) or right[0] in _CONTINUE_PREFIX:
        return left + right
    return left + " " + right


def _find_headers_footers(pages_lines: list[list[str]]) -> set[str]:
    if len(pages_lines) < 2:
        return set()
    candidates = []
    for lines in pages_lines:
        cleaned = [line.strip() for line in lines if line.strip()]
        candidates.extend(cleaned[:2])
        candidates.extend(cleaned[-2:])
    counts = Counter(candidates)
    threshold = max(2, (len(pages_lines) + 1) // 2)
    return {line for line, count in counts.items() if count >= threshold and len(line) <= 80}


def merge_paragraphs(lines, keep_line_breaks: bool = False) -> str:
    page_num_pattern = re.compile(r"^[-\u2014]\s*\d+\s*[-\u2014]$")
    cleaned = [_clean_garbage(line) for line in lines]
    cleaned = [line for line in cleaned if line and not page_num_pattern.match(line)]
    if not cleaned:
        return ""
    if keep_line_breaks:
        return "\n".join(cleaned)

    paragraphs = []
    buf = ""
    for index, line in enumerate(cleaned):
        nxt = cleaned[index + 1] if index + 1 < len(cleaned) else ""
        if _looks_like_doc_title(line):
            if buf:
                paragraphs.append(buf)
                buf = ""
            title, rest = _split_title_from_content(line)
            paragraphs.append(title)
            buf = rest
            continue
        if _looks_like_heading(line):
            if buf:
                paragraphs.append(buf)
                buf = ""
            paragraphs.append(line)
            continue
        buf = _join(buf, line)
        if line[-1] in _SENTENCE_END and (not nxt or nxt[0] not in _CONTINUE_PREFIX):
            paragraphs.append(buf)
            buf = ""
    if buf:
        paragraphs.append(buf)
    return "\n\n".join(paragraphs)


def merge_paragraphs_with_headers_removed(pages_lines: list) -> str:
    recurring = _find_headers_footers(pages_lines)
    pages = []
    for index, lines in enumerate(pages_lines, 1):
        text = merge_paragraphs([line for line in lines if line not in recurring])
        if text:
            pages.append(f"## 第{index}页\n\n{text}")
    return "\n\n".join(pages)


def merge_for_wechat(lines: list) -> str:
    time_pattern = re.compile(r"\d{1,2}:\d{2}|\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}")
    result = []
    for line in lines:
        line = line.strip()
        if line:
            result.append(f"\n**{line}**\n" if time_pattern.search(line) else line)
    return "\n".join(result)


def merge_for_sms_email(lines: list) -> str:
    result = []
    for line in lines:
        line = line.strip()
        if line:
            result.append(f"\n**{line}**\n" if re.search(r"(发件人|来自|发送方|收件人)[:：]", line) else line)
    return "\n".join(result)


def merge_for_contract(lines: list) -> str:
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^第[一二三四五六七八九十百零〇\d]+条", line):
            result.append(f"\n### {line}\n")
        elif re.search(r"(甲方|乙方|签字|盖章|签名|日期)[:：]", line):
            result.append(f"\n**{line}**\n")
        else:
            result.append(line)
    return "\n".join(result)


def merge_for_table(lines: list) -> str:
    return "\n".join(line.strip() for line in lines if line.strip())


def _normalise_ocr_item(item):
    if isinstance(item, str):
        return None
    if not isinstance(item, (list, tuple)) or len(item) < 3:
        return None
    text = str(item[0]).strip()
    if not text:
        return None
    try:
        confidence = float(item[1])
        x, y, w, h = [float(value) for value in item[2][:4]]
    except (TypeError, ValueError, IndexError):
        return None
    return {
        "text": text,
        "confidence": confidence,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "cx": x + w / 2,
        "cy": y + h / 2,
    }


def _group_ocr_rows(items: list) -> list:
    boxes = [_normalise_ocr_item(item) for item in items]
    boxes = [box for box in boxes if box]
    if not boxes:
        return []
    heights = sorted(box["h"] for box in boxes)
    median_height = heights[len(heights) // 2]
    tolerance = max(0.012, min(0.04, median_height * 0.75))
    rows = []
    for box in sorted(boxes, key=lambda b: (-b["cy"], b["x"])):
        matched = None
        for row in rows:
            if abs(row["cy"] - box["cy"]) <= tolerance:
                matched = row
                break
        if matched is None:
            rows.append({"cy": box["cy"], "items": [box]})
        else:
            matched["items"].append(box)
            matched["cy"] = sum(item["cy"] for item in matched["items"]) / len(matched["items"])
    for row in rows:
        row["items"].sort(key=lambda b: b["x"])
    rows.sort(key=lambda row: -row["cy"])
    return rows


def ocr_items_to_lines(items: list) -> list[str]:
    rows = _group_ocr_rows(items)
    if not rows:
        return [str(line).strip() for line in items if str(line).strip()]
    return [" ".join(item["text"] for item in row["items"]).strip() for row in rows]


def _escape_markdown_cell(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text.replace("\\", "\\\\").replace("|", "\\|")


def table_rows_to_markdown(rows: list[list[str]]) -> str:
    cleaned = []
    for row in rows:
        values = [_escape_markdown_cell(cell) for cell in row]
        if any(values):
            cleaned.append(values)
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    matrix = [row + [""] * (width - len(row)) for row in cleaned]
    header = matrix[0]
    if not any(header):
        header = [f"列{i}" for i in range(1, width + 1)]
    body = matrix[1:] or [[""] * width]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _cluster_columns(rows: list[dict]) -> list[float]:
    centers = []
    widths = []
    for row in rows:
        for item in row["items"]:
            centers.append(item["cx"])
            widths.append(item["w"])
    if not centers:
        return []
    widths.sort()
    median_width = widths[len(widths) // 2] if widths else 0.05
    tolerance = max(0.035, min(0.09, median_width * 0.65))
    clusters = []
    for center in sorted(centers):
        if not clusters or abs(clusters[-1][-1] - center) > tolerance:
            clusters.append([center])
        else:
            clusters[-1].append(center)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _rows_to_markdown_table(rows: list[dict]) -> str:
    columns = _cluster_columns(rows)
    if len(columns) < 2:
        return "\n".join(" ".join(item["text"] for item in row["items"]) for row in rows)
    table = []
    for row in rows:
        cells = [[] for _ in columns]
        for item in row["items"]:
            col_index = min(range(len(columns)), key=lambda i: abs(columns[i] - item["cx"]))
            cells[col_index].append(item["text"])
        table.append([" ".join(cell).strip() for cell in cells])
    return table_rows_to_markdown(table)


def ocr_items_to_layout_markdown(items: list, force_table: bool = False) -> str:
    rows = _group_ocr_rows(items)
    if not rows:
        return "\n".join(str(line).strip() for line in items if str(line).strip())

    def is_tableish(row):
        return len(row["items"]) >= 2

    blocks = []
    index = 0
    while index < len(rows):
        if is_tableish(rows[index]):
            end = index
            while end < len(rows) and is_tableish(rows[end]):
                end += 1
            if force_table or end - index >= 2:
                blocks.append(_rows_to_markdown_table(rows[index:end]))
                index = end
                continue

        text_lines = []
        while index < len(rows):
            if is_tableish(rows[index]):
                end = index
                while end < len(rows) and is_tableish(rows[end]):
                    end += 1
                if force_table or end - index >= 2:
                    break
            text_lines.append(" ".join(item["text"] for item in rows[index]["items"]).strip())
            index += 1
        if text_lines:
            blocks.append("\n".join(line for line in text_lines if line))
    return "\n\n".join(block for block in blocks if block.strip())


def ocr_pages_to_layout_markdown(
    pages_items: list[list],
    force_table: bool = False,
    page_numbers: list[int] | None = None,
) -> str:
    pages = []
    for index, items in enumerate(pages_items, 1):
        text = ocr_items_to_layout_markdown(items, force_table=force_table)
        if text:
            page_number = page_numbers[index - 1] if page_numbers and index - 1 < len(page_numbers) else index
            pages.append(f"## 第{page_number}页\n\n{text}")
    return "\n\n".join(pages)


def process_by_type(pages_lines: list, doc_type: DocumentType) -> str:
    config = get_config_for_type(doc_type)
    all_lines = [line for page_lines in pages_lines for line in page_lines]
    if doc_type == DocumentType.WECHAT_SCREENSHOT:
        return merge_for_wechat(all_lines)
    if doc_type == DocumentType.SMS_EMAIL:
        return merge_for_sms_email(all_lines)
    if doc_type == DocumentType.CONTRACT_AGREEMENT:
        return merge_for_contract(all_lines)
    if doc_type == DocumentType.TABLE_LIST:
        return merge_for_table(all_lines)
    if doc_type == DocumentType.HANDWRITING:
        pages = []
        for index, lines in enumerate(pages_lines, 1):
            text = "\n".join(line.strip() for line in lines if line.strip())
            if text:
                pages.append(f"## 第{index}页（手写材料 - 建议人工校验）\n\n{text}")
        result = "\n\n".join(pages)
        if config.add_uncertainty_marker:
            result += "\n\n备注：本材料为手写字迹，OCR识别可能存在误差，请与原文核对。"
        return result
    if doc_type == DocumentType.EVIDENCE_GENERAL:
        pages = []
        for index, lines in enumerate(pages_lines, 1):
            text = merge_paragraphs(lines, keep_line_breaks=config.keep_line_breaks)
            if text:
                pages.append(f"## 第{index}页\n\n{text}")
        return "\n\n".join(pages)
    if config.remove_headers and len(pages_lines) > 1:
        return merge_paragraphs_with_headers_removed(pages_lines)
    return merge_paragraphs(all_lines, keep_line_breaks=config.keep_line_breaks)
