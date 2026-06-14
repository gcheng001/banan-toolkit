#!/opt/homebrew/bin/python3
"""VisionOCR native GUI (files/images to Markdown and Markdown to Word)."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import objc
from Cocoa import (
    NSAlert,
    NSApplication,
    NSAppearance,
    NSBezierPath,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRange,
    NSMakeRect,
    NSMakeSize,
    NSOpenPanel,
    NSPopUpButton,
    NSScrollView,
    NSTextField,
    NSTextView,
    NSViewHeightSizable,
    NSViewMaxXMargin,
    NSViewMaxYMargin,
    NSViewMinXMargin,
    NSViewMinYMargin,
    NSViewWidthSizable,
    NSView,
    NSWindow,
    NSObject,
)
from objc import IBAction
from Foundation import NSURL
from PyObjCTools import AppHelper


def _keychain_get_wechat() -> str:
    proc = subprocess.run(["security", "find-generic-password", "-a", WECHAT_KEYCHAIN_SERVICE, "-s", WECHAT_KEYCHAIN_SERVICE, "-w"], text=True, capture_output=True)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()

def _keychain_set_wechat(value: str) -> None:
    subprocess.run(["security", "delete-generic-password", "-a", WECHAT_KEYCHAIN_SERVICE, "-s", WECHAT_KEYCHAIN_SERVICE], text=True, capture_output=True)
    proc = subprocess.run(["security", "add-generic-password", "-U", "-a", WECHAT_KEYCHAIN_SERVICE, "-s", WECHAT_KEYCHAIN_SERVICE, "-w", value], text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "写入 Keychain 失败")

def _osascript_prompt(message: str, default: str = "", hidden: bool = False) -> str | None:
    escaped_message = message.replace('"', '\\"')
    escaped_default = default.replace('"', '\\"')
    script = [f'display dialog "{escaped_message}" default answer "{escaped_default}" buttons {{"取消", "确定"}} default button "确定"']
    if hidden:
        script[0] += " with hidden answer"
    script.extend(["set textReturned to text returned of result", "return textReturned"])
    proc = subprocess.run(["osascript", "-e", script[0], "-e", script[1], "-e", script[2]], text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vision_ocr_utils import DocumentType, TYPE_OPTIONS_GUI

_NSFilenamesPboardType = "NSFilenamesPboardType"
_NSPasteboardTypeFileURL = "public.file-url"
_NSURLPboardType = "NSURLPboardType"

CLI = shutil.which("vision-ocr-pdf") or str(Path(__file__).resolve().parent / "vision-ocr-pdf")
DOCX_CLI = shutil.which("md-to-docx") or str(Path(__file__).resolve().parent / "md-to-docx")
TRANSCRIPT_CLI = shutil.which("media-to-transcript") or str(Path(__file__).resolve().parent / "media-to-transcript")
MARKDOWN_CLI = shutil.which("office-to-markdown") or str(Path.home() / ".local/bin/office-to-markdown")
MINERU_CLI = shutil.which("mineru-local") or str(Path.home() / ".local/bin/mineru-local")
LEGAL_OCR_CLI = shutil.which("legal-ocr-convert") or str(Path.home() / ".local/bin/legal-ocr-convert")
WECHAT_PROJECT_ROOT = Path("/Users/Apple/Codex/wechat-evidence")
WECHAT_CLI = Path(__file__).resolve().parent / "wechat_evidence.py"
if not WECHAT_CLI.exists():
    WECHAT_CLI = WECHAT_PROJECT_ROOT / "wechat_evidence.py"
WECHAT_OUTPUT_DIR = Path.home() / "Desktop" / "录屏取证输出"
WECHAT_KEYCHAIN_SERVICE = "wechat-evidence-cloud"
WECHAT_DEFAULT_CLOUD_BASE_URL = "https://api.deepseek.com"
WECHAT_DEFAULT_CLOUD_MODEL = "deepseek-chat"


AUDIO_EXTS = {"mp3", "wav", "m4a", "aac", "flac", "ogg", "wma"}
VIDEO_EXTS = {"mp4", "m4v", "mov", "avi", "mkv", "webm", "flv"}
IMAGE_EXTS = {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "gif", "heic", "webp"}
OCR_EXTS = {"pdf"} | IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS
DOCX_EXTS = {"md", "txt", "markdown"}
MARKDOWN_EXTS = {"docx", "doc", "xlsx", "xls", "xlsm", "csv", "tsv", "ods", "pptx", "ppt", "html", "htm", "epub", "json", "xml", "zip"}
TO_MARKDOWN_EXTS = OCR_EXTS | MARKDOWN_EXTS


def _c(r, g, b, a=1.0):
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, a)


C_WHITE = _c(1.0, 1.0, 1.0)
C_APP_BG = _c(0.965, 0.968, 0.972)
C_HEADER_BG = _c(0.985, 0.985, 0.985)
C_PANEL_BG = _c(0.982, 0.982, 0.982)
C_TEXT = _c(0.10, 0.10, 0.11)
C_TEXT_STRONG = _c(0.03, 0.03, 0.035)
C_DIM = _c(0.46, 0.47, 0.50)
C_MUTED = _c(0.62, 0.63, 0.66)
C_BORDER = _c(0.87, 0.87, 0.88)
C_BORDER_SOFT = _c(0.92, 0.92, 0.93)
C_BLUE_BG = C_APP_BG
C_BLUE_ACCENT = _c(0.12, 0.16, 0.22)
C_BLUE_ACCENT_LIGHT = _c(0.95, 0.97, 1.0)
C_GREEN_BG = C_APP_BG
C_GREEN_ACCENT = _c(0.14, 0.26, 0.20)
C_GREEN_ACCENT_LIGHT = _c(0.94, 0.97, 0.95)
C_ORANGE_BG = C_APP_BG
C_ORANGE_ACCENT = _c(0.66, 0.33, 0.06)
C_ORANGE_ACCENT_LIGHT = _c(1.0, 0.95, 0.78)
C_PILL_BLUE = _c(0.93, 0.96, 1.0)
C_PILL_YELLOW = _c(1.0, 0.94, 0.74)


def _font(size, weight=0.0):
    return NSFont.systemFontOfSize_weight_(size, weight)


def _label(text, x, y, w, h, size=13, weight=0.0, color=None, align=0):
    field = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    field.setStringValue_(text)
    field.setFont_(_font(size, weight))
    field.setTextColor_(color or C_TEXT)
    field.setBezeled_(False)
    field.setDrawsBackground_(False)
    field.setEditable_(False)
    field.setSelectable_(False)
    field.setAlignment_(align)
    return field


def _input_field(x, y, w, h, placeholder=""):
    field = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    field.setFont_(_font(13))
    field.setPlaceholderString_(placeholder)
    return field


def _btn(title, x, y, w, h, target, action):
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    btn.setTitle_(title)
    btn.setBezelStyle_(1)
    btn.setFont_(_font(13, 0.25))
    btn.setTarget_(target)
    btn.setAction_(action)
    return btn


def _nav_btn(title, x, y, w, h, target, action):
    btn = _btn(title, x, y, w, h, target, action)
    btn.setFont_(_font(14, 0.45))
    return btn


def _checkbox(title, x, y, w, h, checked=True):
    btn = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    btn.setButtonType_(3)
    btn.setTitle_(title)
    btn.setFont_(_font(12))
    btn.setState_(1 if checked else 0)
    return btn


def _set_view_style(view, bg, border, radius=10.0):
    view.setWantsLayer_(True)
    layer = view.layer()
    layer.setCornerRadius_(radius)
    layer.setBackgroundColor_(bg.CGColor())
    layer.setBorderWidth_(1.0)
    layer.setBorderColor_(border.CGColor())


def _fill_view(view, bg):
    view.setWantsLayer_(True)
    view.layer().setBackgroundColor_(bg.CGColor())


def _resize(view, mask):
    view.setAutoresizingMask_(mask)
    return view


def _register_file_drag(view):
    view.registerForDraggedTypes_([_NSFilenamesPboardType, _NSPasteboardTypeFileURL, _NSURLPboardType])
    return view


def _pin_panel_controls_to_top(panel, bottom_views=()):
    bottom_ids = {id(view) for view in bottom_views}
    for view in panel.subviews():
        if id(view) not in bottom_ids:
            _resize(view, PIN_TOP)


def _center_in_parent(view, pin_top=True):
    mask = NSViewMinXMargin | NSViewMaxXMargin
    if pin_top:
        mask |= PIN_TOP
    _resize(view, mask)
    return view


PIN_TOP = NSViewMinYMargin
PIN_BOTTOM = NSViewMaxYMargin
PIN_RIGHT = NSViewMinXMargin
FILL_WIDTH = NSViewWidthSizable
FILL_HEIGHT = NSViewHeightSizable


class ProgressBar(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(ProgressBar, self).initWithFrame_(frame)
        if self is None:
            return None
        self.value = 0.0
        self.accent = C_BLUE_ACCENT
        return self

    def setValue_(self, value):
        self.value = max(0.0, min(1.0, float(value)))
        self.setNeedsDisplay_(True)

    def setAccent_(self, color):
        self.accent = color
        self.setNeedsDisplay_(True)

    def drawRect_(self, _rect):
        b = self.bounds()
        C_BORDER_SOFT.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 4, 4).fill()
        if self.value > 0:
            fill = NSMakeRect(b.origin.x, b.origin.y, b.size.width * self.value, b.size.height)
            self.accent.set()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(fill, 4, 4).fill()


class DropZone(NSView):
    def initWithFrame_controller_(self, frame, ctrl):
        self = objc.super(DropZone, self).initWithFrame_(frame)
        if self is None:
            return None
        self.ctrl = ctrl
        _register_file_drag(self)
        return self

    def drawRect_(self, _rect):
        b = self.bounds()
        accent = self.ctrl.current_accent
        C_PANEL_BG.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 10, 10).fill()
        accent.set()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 10, 10)
        path.setLineDash_count_phase_([5.0, 5.0], 2, 0.0)
        path.stroke()

    def draggingEntered_(self, _sender):
        return 1

    def performDragOperation_(self, sender):
        pb = sender.draggingPasteboard()
        paths = pb.propertyListForType_(_NSFilenamesPboardType) or []
        if not paths:
            urls = pb.readObjectsForClasses_options_([NSURL], None) or []
            paths = [url.path() for url in urls if url and url.isFileURL()]
        allowed = VIDEO_EXTS if self.ctrl.mode == "wechat" else (TO_MARKDOWN_EXTS if self.ctrl.mode == "ocr" else DOCX_EXTS)
        added = 0
        for p in paths:
            p = str(p)
            if os.path.isdir(p):
                for name in os.listdir(p):
                    fp = os.path.join(p, name)
                    if os.path.isfile(fp):
                        ext = Path(fp).suffix.lower().lstrip(".")
                        if ext in allowed:
                            added += self.ctrl._add_file(fp)
            elif os.path.isfile(p):
                ext = Path(p).suffix.lower().lstrip(".")
                if ext in allowed:
                    added += self.ctrl._add_file(p)
        self.ctrl._refresh_files()
        self.ctrl.status_label.setStringValue_(f"已添加 {added} 个文件" if added else "没有可用文件")
        return True


class Controller(NSObject):
    def init(self):
        self = objc.super(Controller, self).init()
        if self is None:
            return None
        self.app = NSApplication.sharedApplication()
        self.mode = "ocr"
        self.files = []
        self.links = []
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.jobs = 2
        self.selected_type = DocumentType.AUTO
        self.selected_docx_type = "general"
        self.selected_whisper_model = "base"
        self.selected_ocr_engine = "mineru"
        self.wechat_mode = "quick"
        self.selected_wechat_stride = "auto"
        self.wechat_output_dir = WECHAT_OUTPUT_DIR
        self.wechat_cloud_base_url = WECHAT_DEFAULT_CLOUD_BASE_URL
        self.wechat_cloud_model = WECHAT_DEFAULT_CLOUD_MODEL
        self.current_accent = C_TEXT_STRONG
        self.current_soft_accent = C_PANEL_BG
        self.output_dir = Path.home() / "Desktop" / "VisionOCR_Output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._active_panel = None
        self._start_time = None
        self._timer_stop = False
        self._build_ui()
        self._apply_theme()
        return self

    @objc.python_method
    def _build_ui(self):
        width = 1280
        height = 800
        topbar_h = 74
        bottom_h = 58
        header_h = 58
        margin = 20

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(80, 60, width, height), 15, 2, False
        )
        win.setTitle_("VisionOCR 办案助手")
        win.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameAqua"))
        win.setMinSize_(NSMakeSize(1080, 800))
        self.window = win
        root = win.contentView()

        self.sidebar = NSView.alloc().initWithFrame_(NSMakeRect(0, height - topbar_h, width, topbar_h))
        _resize(self.sidebar, FILL_WIDTH | PIN_TOP)
        root.addSubview_(self.sidebar)
        _set_view_style(self.sidebar, C_HEADER_BG, C_BORDER_SOFT, 0)

        self.brand_icon = _label("V", 46, 25, 24, 24, size=19, weight=0.75, color=C_TEXT_STRONG)
        self.brand_title = _label("办案材料助手", 82, 27, 140, 22, size=15, weight=0.55, color=C_TEXT_STRONG)
        self.sidebar.addSubview_(self.brand_icon)
        self.sidebar.addSubview_(self.brand_title)

        self.nav_ocr = _nav_btn("▣ 材料转 MD", 250, 20, 118, 34, self, "switchToOCR:")
        self.nav_docx = _nav_btn("▤ 转 Word", 390, 20, 108, 34, self, "switchToDOCX:")
        self.nav_wechat = _nav_btn("◉ 录屏取证", 520, 20, 116, 34, self, "switchToWeChat:")
        self.sidebar.addSubview_(self.nav_ocr)
        self.sidebar.addSubview_(self.nav_docx)
        self.sidebar.addSubview_(self.nav_wechat)

        self.nav_ocr_bar = NSView.alloc().initWithFrame_(NSMakeRect(260, 0, 98, 3))
        self.nav_docx_bar = NSView.alloc().initWithFrame_(NSMakeRect(404, 0, 78, 3))
        self.nav_wechat_bar = NSView.alloc().initWithFrame_(NSMakeRect(534, 0, 84, 3))
        for bar in (self.nav_ocr_bar, self.nav_docx_bar, self.nav_wechat_bar):
            _fill_view(bar, C_TEXT_STRONG)
            self.sidebar.addSubview_(bar)

        self.btn_history = _btn("◷ 历史记录", width - 238, 22, 104, 30, self, "openHistory:")
        self.btn_feedback = _btn("○ 反馈", width - 122, 22, 76, 30, self, "noop:")
        _resize(self.btn_history, PIN_RIGHT)
        _resize(self.btn_feedback, PIN_RIGHT)
        self.sidebar.addSubview_(self.btn_history)
        self.sidebar.addSubview_(self.btn_feedback)

        main_h = height - topbar_h
        self.main = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, main_h))
        _resize(self.main, FILL_WIDTH | FILL_HEIGHT)
        root.addSubview_(self.main)
        _fill_view(self.main, C_APP_BG)

        self.page_title = _label("材料转 MD", 48, main_h - 40, 160, 24, size=15, weight=0.65, color=C_TEXT_STRONG)
        self.page_subtitle = _label("将案卷 PDF、图片、Office 文档转为可检索 Markdown", 184, main_h - 40, 520, 24, size=13, color=C_DIM)
        _resize(self.page_title, PIN_TOP)
        _resize(self.page_subtitle, PIN_TOP | FILL_WIDTH)
        self.main.addSubview_(self.page_title)
        self.main.addSubview_(self.page_subtitle)

        self.bottom = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, bottom_h))
        _resize(self.bottom, FILL_WIDTH | PIN_BOTTOM)
        self.main.addSubview_(self.bottom)
        _set_view_style(self.bottom, C_WHITE, C_BORDER, 0)
        self.status_label = _label("已就绪", 48, 22, 260, 20, size=13, color=C_DIM)
        self.bottom.addSubview_(self.status_label)
        self.progress_bar = ProgressBar.alloc().initWithFrame_(NSMakeRect(430, 25, 260, 7))
        self.bottom.addSubview_(self.progress_bar)
        self.pct_label = _label("0%", 700, 18, 44, 20, size=13, weight=0.45)
        self.timer_label = _label("00:00", 758, 18, 72, 20, size=13, color=C_DIM)
        _resize(self.pct_label, PIN_RIGHT)
        _resize(self.timer_label, PIN_RIGHT)
        self.bottom.addSubview_(self.pct_label)
        self.bottom.addSubview_(self.timer_label)
        self.btn_clear = _btn("清空", 846, 13, 78, 30, self, "clearList:")
        self.btn_pause = _btn("暂停", 932, 13, 78, 30, self, "pauseProcessing:")
        self.btn_stop = _btn("停止", 1018, 13, 78, 30, self, "stopProcessing:")
        self.btn_start = _btn("开始转换", 1108, 13, 116, 30, self, "startProcessing:")
        for btn in (self.btn_clear, self.btn_pause, self.btn_stop, self.btn_start):
            _resize(btn, PIN_RIGHT)
        self.btn_pause.setEnabled_(False)
        self.btn_stop.setEnabled_(False)
        self.bottom.addSubview_(self.btn_clear)
        self.bottom.addSubview_(self.btn_pause)
        self.bottom.addSubview_(self.btn_stop)
        self.bottom.addSubview_(self.btn_start)

        body_h = main_h - header_h - bottom_h
        self.ocr_page = NSView.alloc().initWithFrame_(NSMakeRect(0, bottom_h, width, body_h))
        self.docx_page = NSView.alloc().initWithFrame_(NSMakeRect(0, bottom_h, width, body_h))
        _resize(self.ocr_page, FILL_WIDTH | FILL_HEIGHT)
        _resize(self.docx_page, FILL_WIDTH | FILL_HEIGHT)
        self.main.addSubview_(self.ocr_page)
        self.main.addSubview_(self.docx_page)

        self._build_ocr_page(body_h)
        self._build_docx_page(body_h)
        self.wechat_page = NSView.alloc().initWithFrame_(NSMakeRect(0, bottom_h, width, body_h))
        _resize(self.wechat_page, FILL_WIDTH | FILL_HEIGHT)
        self.main.addSubview_(self.wechat_page)
        self._build_wechat_page(body_h)
        self.wechat_page.setHidden_(True)
        self.docx_page.setHidden_(True)

        win.makeKeyAndOrderFront_(None)

    @objc.python_method
    def _build_ocr_page(self, body_h):
        _fill_view(self.ocr_page, C_APP_BG)
        left = NSView.alloc().initWithFrame_(NSMakeRect(20, 20, 320, body_h - 40))
        _resize(left, FILL_HEIGHT | NSViewMaxXMargin)
        _set_view_style(left, C_WHITE, C_BORDER, 12)
        self.ocr_page.addSubview_(left)

        left.addSubview_(_label("转换设置", 18, left.bounds().size.height - 38, 200, 24, size=15, weight=0.65, color=C_TEXT_STRONG))
        left.addSubview_(_label("文件类型", 18, left.bounds().size.height - 70, 120, 18, size=12, color=C_DIM))
        self.type_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 98, 284, 28), False)
        for lbl, _ in TYPE_OPTIONS_GUI:
            self.type_popup.addItemWithTitle_(lbl)
        self.type_popup.setTarget_(self)
        self.type_popup.setAction_("typeChanged:")
        left.addSubview_(self.type_popup)

        left.addSubview_(_label("并发数", 18, left.bounds().size.height - 132, 120, 18, size=12, color=C_DIM))
        self.jobs_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 160, 284, 28), False)
        for opt in ["1", "2", "3", "4"]:
            self.jobs_popup.addItemWithTitle_(opt)
        self.jobs_popup.selectItemAtIndex_(1)
        self.jobs_popup.setTarget_(self)
        self.jobs_popup.setAction_("jobsChanged:")
        left.addSubview_(self.jobs_popup)

        left.addSubview_(_label("OCR / Whisper 模型", 18, left.bounds().size.height - 194, 160, 18, size=12, color=C_DIM))
        self.whisper_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 222, 284, 28), False)
        for opt in ["base（快）", "small", "medium", "large（准）"]:
            self.whisper_popup.addItemWithTitle_(opt)
        self.whisper_popup.setTarget_(self)
        self.whisper_popup.setAction_("whisperChanged:")
        left.addSubview_(self.whisper_popup)

        left.addSubview_(_label("识别引擎", 18, left.bounds().size.height - 256, 160, 18, size=12, color=C_DIM))
        self.ocr_engine_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 284, 284, 28), False)
        for opt in ["本地 MinerU（默认）", "Apple VisionOCR", "legal-ocr 自动", "legal-ocr MinerU", "PaddleOCR-VL（需配置）"]:
            self.ocr_engine_popup.addItemWithTitle_(opt)
        self.ocr_engine_popup.setTarget_(self)
        self.ocr_engine_popup.setAction_("ocrEngineChanged:")
        left.addSubview_(self.ocr_engine_popup)

        left.addSubview_(_label("输出目录", 18, left.bounds().size.height - 326, 100, 18, size=12, color=C_DIM))
        self.out_path_ocr = _input_field(18, left.bounds().size.height - 354, 252, 28)
        self.out_path_ocr.setStringValue_(str(self.output_dir).replace(str(Path.home()), "~"))
        left.addSubview_(self.out_path_ocr)
        self.btn_out_ocr = _btn("📁", 274, left.bounds().size.height - 354, 28, 28, self, "pickOutputDir:")
        left.addSubview_(self.btn_out_ocr)

        self.btn_start_left_ocr = _btn("▶  转为 Markdown", 18, 14, 284, 34, self, "startProcessing:")
        _resize(self.btn_start_left_ocr, PIN_BOTTOM)
        left.addSubview_(self.btn_start_left_ocr)
        _pin_panel_controls_to_top(left, (self.btn_start_left_ocr,))

        right = NSView.alloc().initWithFrame_(NSMakeRect(356, 20, self.ocr_page.bounds().size.width - 376, body_h - 40))
        _resize(right, FILL_WIDTH | FILL_HEIGHT)
        self.ocr_page.addSubview_(right)

        self.drop_zone = DropZone.alloc().initWithFrame_controller_(NSMakeRect(0, right.bounds().size.height - 210, right.bounds().size.width, 210), self)
        _resize(self.drop_zone, FILL_WIDTH | PIN_TOP)
        right.addSubview_(self.drop_zone)
        dz_title = _label("拖入文件或点击选择", right.bounds().size.width / 2 - 110, 116, 220, 28, size=16, weight=0.65, color=C_TEXT_STRONG, align=2)
        dz_subtitle = _label("支持 PDF / 图片 / Word / Excel / 音视频", right.bounds().size.width / 2 - 150, 88, 300, 22, size=13, color=C_DIM, align=2)
        self.drop_zone.addSubview_(_register_file_drag(_center_in_parent(dz_title)))
        self.drop_zone.addSubview_(_register_file_drag(_center_in_parent(dz_subtitle)))
        self.btn_pick = _btn("选择文件", right.bounds().size.width / 2 - 44, 56, 88, 32, self, "selectFiles:")
        self.drop_zone.addSubview_(_register_file_drag(_center_in_parent(self.btn_pick)))

        link_label = _label("或直接粘贴链接（支持主流平台）", 0, right.bounds().size.height - 248, 260, 20, size=12, color=C_DIM)
        _resize(link_label, PIN_TOP)
        right.addSubview_(link_label)
        self.link_field = _input_field(0, right.bounds().size.height - 282, right.bounds().size.width - 92, 30, "https://youtube.com/...  或  https://...")
        self.btn_add_link = _btn("添加", right.bounds().size.width - 84, right.bounds().size.height - 282, 84, 30, self, "addLink:")
        _resize(self.link_field, FILL_WIDTH | PIN_TOP)
        _resize(self.btn_add_link, PIN_RIGHT | PIN_TOP)
        right.addSubview_(self.link_field)
        right.addSubview_(self.btn_add_link)

        watermark_label = _label("去水印（可选，转换完成后可执行）", 0, right.bounds().size.height - 332, 260, 20, size=13, color=C_DIM)
        _resize(watermark_label, PIN_TOP)
        right.addSubview_(watermark_label)
        self.watermark_field = _input_field(
            0,
            right.bounds().size.height - 366,
            right.bounds().size.width - 124,
            30,
            "留空为不处理；示例：高城13303201410164518",
        )
        right.addSubview_(self.watermark_field)
        self.btn_remove_watermark = _btn("一键去水印", right.bounds().size.width - 116, right.bounds().size.height - 366, 116, 30, self, "removeWatermark:")
        _resize(self.watermark_field, FILL_WIDTH | PIN_TOP)
        _resize(self.btn_remove_watermark, PIN_RIGHT | PIN_TOP)
        right.addSubview_(self.btn_remove_watermark)

        queue_label = _label("任务队列", 0, right.bounds().size.height - 414, 120, 22, size=16, weight=0.65, color=C_TEXT_STRONG)
        _resize(queue_label, PIN_TOP)
        right.addSubview_(queue_label)
        table_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, right.bounds().size.width, right.bounds().size.height - 446))
        _resize(table_scroll, FILL_WIDTH | FILL_HEIGHT)
        table_scroll.setHasVerticalScroller_(True)
        self.task_text = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, right.bounds().size.width, right.bounds().size.height - 446))
        _resize(self.task_text, FILL_WIDTH | FILL_HEIGHT)
        self.task_text.setEditable_(False)
        self.task_text.setFont_(_font(12))
        table_scroll.setDocumentView_(self.task_text)
        _set_view_style(table_scroll, C_WHITE, C_BORDER, 10)
        right.addSubview_(table_scroll)

    @objc.python_method
    def _build_docx_page(self, body_h):
        _fill_view(self.docx_page, C_APP_BG)
        left = NSView.alloc().initWithFrame_(NSMakeRect(20, 20, 320, body_h - 40))
        _resize(left, FILL_HEIGHT | NSViewMaxXMargin)
        _set_view_style(left, C_WHITE, C_BORDER, 12)
        self.docx_page.addSubview_(left)

        left.addSubview_(_label("输入方式", 18, left.bounds().size.height - 36, 120, 22, size=15, weight=0.65, color=C_TEXT_STRONG))
        self.input_mode = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 66, 284, 28), False)
        self.input_mode.addItemWithTitle_("文件导入")
        self.input_mode.addItemWithTitle_("文本粘贴")
        self.input_mode.selectItemAtIndex_(0)
        left.addSubview_(self.input_mode)

        self.docx_drop = DropZone.alloc().initWithFrame_controller_(NSMakeRect(18, left.bounds().size.height - 188, 284, 104), self)
        left.addSubview_(self.docx_drop)
        self.docx_drop.addSubview_(_register_file_drag(_label("拖入 Markdown 文件", 57, 58, 170, 24, size=14, weight=0.55, align=2)))
        self.docx_drop.addSubview_(_register_file_drag(_label("支持 .md / .txt", 42, 38, 200, 20, size=12, color=C_DIM, align=2)))
        self.btn_pick_docx = _btn("选择文件", 96, 10, 96, 26, self, "selectFiles:")
        self.docx_drop.addSubview_(_register_file_drag(self.btn_pick_docx))

        left.addSubview_(_label("输出设置", 18, left.bounds().size.height - 216, 120, 22, size=15, weight=0.65, color=C_TEXT_STRONG))
        left.addSubview_(_label("输出目录", 18, left.bounds().size.height - 242, 120, 18, size=12, color=C_DIM))
        self.out_path_docx = _input_field(18, left.bounds().size.height - 270, 252, 28)
        self.out_path_docx.setStringValue_(str(self.output_dir).replace(str(Path.home()), "~"))
        left.addSubview_(self.out_path_docx)
        self.btn_out_docx = _btn("📁", 274, left.bounds().size.height - 270, 28, 28, self, "pickOutputDir:")
        left.addSubview_(self.btn_out_docx)

        left.addSubview_(_label("页面设置", 18, left.bounds().size.height - 300, 120, 18, size=12, color=C_DIM))
        self.page_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 328, 136, 28), False)
        self.page_popup.addItemWithTitle_("A4（标准）")
        self.page_popup.addItemWithTitle_("A3")
        self.page_popup.addItemWithTitle_("Letter")
        left.addSubview_(self.page_popup)
        self.margin_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(166, left.bounds().size.height - 328, 136, 28), False)
        self.margin_popup.addItemWithTitle_("标准（2.54cm）")
        self.margin_popup.addItemWithTitle_("窄")
        self.margin_popup.addItemWithTitle_("宽")
        left.addSubview_(self.margin_popup)

        left.addSubview_(_label("段落", 18, left.bounds().size.height - 360, 120, 18, size=12, color=C_DIM))
        self.first_indent_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 388, 136, 28), False)
        for opt in ["首行 2 字符", "无缩进", "首行 4 字符"]:
            self.first_indent_popup.addItemWithTitle_(opt)
        left.addSubview_(self.first_indent_popup)
        self.line_spacing_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(166, left.bounds().size.height - 388, 136, 28), False)
        for opt in ["1.5 倍行距", "1.0 倍行距", "1.15 倍行距", "2.0 倍行距"]:
            self.line_spacing_popup.addItemWithTitle_(opt)
        left.addSubview_(self.line_spacing_popup)

        left.addSubview_(_label("字体", 18, left.bounds().size.height - 420, 120, 18, size=12, color=C_DIM))
        self.font_preset_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 448, 284, 28), False)
        for opt in ["法律文书默认", "法院常用", "通用宋体", "屏幕友好"]:
            self.font_preset_popup.addItemWithTitle_(opt)
        left.addSubview_(self.font_preset_popup)

        left.addSubview_(_label("标题字体 / 正文字体", 18, left.bounds().size.height - 480, 160, 18, size=12, color=C_DIM))
        self.title_font_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 508, 136, 28), False)
        for opt in ["黑体", "宋体", "仿宋", "微软雅黑"]:
            self.title_font_popup.addItemWithTitle_(opt)
        left.addSubview_(self.title_font_popup)
        self.body_font_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(166, left.bounds().size.height - 508, 136, 28), False)
        for opt in ["仿宋", "宋体", "微软雅黑", "苹方"]:
            self.body_font_popup.addItemWithTitle_(opt)
        left.addSubview_(self.body_font_popup)

        left.addSubview_(_label("标题字号 / 正文字号", 18, left.bounds().size.height - 536, 160, 18, size=12, color=C_DIM))
        self.title_size_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 564, 136, 28), False)
        for opt in ["15 pt", "16 pt", "18 pt", "22 pt"]:
            self.title_size_popup.addItemWithTitle_(opt)
        left.addSubview_(self.title_size_popup)
        self.body_size_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(166, left.bounds().size.height - 564, 136, 28), False)
        for opt in ["12 pt", "10.5 pt", "14 pt", "16 pt"]:
            self.body_size_popup.addItemWithTitle_(opt)
        left.addSubview_(self.body_size_popup)

        self.btn_start_left_docx = _btn("⇄  开始转换", 18, 14, 284, 34, self, "startProcessing:")
        _resize(self.btn_start_left_docx, PIN_BOTTOM)
        left.addSubview_(self.btn_start_left_docx)
        self.btn_start_left_docx.setHidden_(True)
        _pin_panel_controls_to_top(left, (self.btn_start_left_docx,))

        right = NSView.alloc().initWithFrame_(NSMakeRect(356, 20, self.docx_page.bounds().size.width - 376, body_h - 40))
        _resize(right, FILL_WIDTH | FILL_HEIGHT)
        self.docx_page.addSubview_(right)

        md_title = _label("Markdown 预览与编辑（可选）", 0, right.bounds().size.height - 32, 240, 22, size=16, weight=0.65, color=C_TEXT_STRONG)
        _resize(md_title, PIN_TOP)
        right.addSubview_(md_title)
        md_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, right.bounds().size.height - 242, right.bounds().size.width, 198))
        _resize(md_scroll, FILL_WIDTH | PIN_TOP)
        md_scroll.setHasVerticalScroller_(True)
        self.md_editor = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, right.bounds().size.width, 198))
        _resize(self.md_editor, FILL_WIDTH | FILL_HEIGHT)
        self.md_editor.setEditable_(True)
        self.md_editor.setFont_(_font(15))
        md_scroll.setDocumentView_(self.md_editor)
        _set_view_style(md_scroll, C_WHITE, C_BORDER, 10)
        right.addSubview_(md_scroll)

        preview_title = _label("Word 预览（实时预览转换效果）", 0, right.bounds().size.height - 284, 260, 22, size=16, weight=0.65, color=C_TEXT_STRONG)
        _resize(preview_title, PIN_TOP)
        right.addSubview_(preview_title)
        preview_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, right.bounds().size.width, right.bounds().size.height - 318))
        _resize(preview_scroll, FILL_WIDTH | FILL_HEIGHT)
        preview_scroll.setHasVerticalScroller_(True)
        self.word_preview = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, right.bounds().size.width, right.bounds().size.height - 318))
        _resize(self.word_preview, FILL_WIDTH | FILL_HEIGHT)
        self.word_preview.setEditable_(False)
        self.word_preview.setFont_(_font(16))
        self.word_preview.setString_("办案报告：\n\n（此处显示转换后的 Word 版式预览摘要）")
        preview_scroll.setDocumentView_(self.word_preview)
        _set_view_style(preview_scroll, C_WHITE, C_BORDER, 10)
        right.addSubview_(preview_scroll)

    @objc.python_method
    def _apply_theme(self):
        if self.mode == "ocr":
            accent = C_TEXT_STRONG
            soft = C_PANEL_BG
            title = "材料转 MD"
            subtitle = "将案卷 PDF、图片、Office 文档转为可检索 Markdown"
            start_title = "开始转换"
        elif self.mode == "docx":
            accent = C_TEXT_STRONG
            soft = C_PANEL_BG
            title = "转 Word"
            subtitle = "将 Markdown 文本生成 Word 文书，保留右侧纸张预览"
            start_title = "生成 Word"
        elif self.mode == "wechat":
            accent = C_TEXT_STRONG
            soft = C_PANEL_BG
            title = "录屏取证"
            subtitle = "将聊天录屏导出为可复核截图 PDF 和文字索引"
            start_title = "导出取证材料"
        else:
            accent = C_TEXT_STRONG
            soft = C_PANEL_BG
            title = "Word/表格 → Markdown"
            subtitle = "将 Word 文档和 Excel/CSV 表格转换为 Markdown 格式"
            start_title = "转为 Markdown"
        self.current_accent = accent
        self.current_soft_accent = soft
        self.window.setBackgroundColor_(C_APP_BG)
        _set_view_style(self.sidebar, C_HEADER_BG, C_BORDER_SOFT, 0)
        self.page_title.setStringValue_(title)
        self.page_title.setTextColor_(C_TEXT_STRONG)
        self.page_subtitle.setStringValue_(subtitle)
        self.progress_bar.setAccent_(accent)
        self.pct_label.setTextColor_(C_TEXT_STRONG)
        self.btn_start.setTitle_(start_title)
        self.btn_start_left_ocr.setTitle_("▶  转为 Markdown")
        self.btn_start_left_docx.setTitle_("⇄  开始转换")

        _set_view_style(self.nav_ocr, C_WHITE if self.mode == "ocr" else C_HEADER_BG, C_BORDER if self.mode == "ocr" else C_HEADER_BG, 8)
        _set_view_style(self.nav_docx, C_WHITE if self.mode == "docx" else C_HEADER_BG, C_BORDER if self.mode == "docx" else C_HEADER_BG, 8)
        _set_view_style(self.nav_wechat, C_WHITE if self.mode == "wechat" else C_HEADER_BG, C_BORDER if self.mode == "wechat" else C_HEADER_BG, 8)
        self.nav_ocr.setContentTintColor_(C_TEXT_STRONG if self.mode == "ocr" else C_DIM)
        self.nav_docx.setContentTintColor_(C_TEXT_STRONG if self.mode == "docx" else C_DIM)
        self.nav_wechat.setContentTintColor_(C_TEXT_STRONG if self.mode == "wechat" else C_DIM)
        self.nav_ocr_bar.setHidden_(self.mode != "ocr")
        self.nav_docx_bar.setHidden_(self.mode != "docx")
        self.nav_wechat_bar.setHidden_(self.mode != "wechat")
        self.drop_zone.setNeedsDisplay_(True)
        self.docx_drop.setNeedsDisplay_(True)
        if hasattr(self, "wechat_drop"):
            self.wechat_drop.setNeedsDisplay_(True)
        if hasattr(self, "wechat_page"):
            self.wechat_page.setHidden_(self.mode != "wechat")

    @objc.python_method
    def _add_file(self, path):
        ext = Path(path).suffix.lower().lstrip(".")
        if ext not in self._allowed_exts():
            return 0
        if path not in [item["path"] for item in self.files]:
            self.files.append({"path": path})
            return 1
        return 0

    @objc.python_method
    def _refresh_files(self):
        if not self.files:
            self.task_text.setString_("文件名\t状态\t进度\t耗时\n（暂无任务）")
            return
        rows = ["文件名\t状态\t进度\t耗时"]
        for item in self.files[:200]:
            name = Path(item["path"]).name
            rows.append(f"{name}\t排队中\t0%\t--:--")
        self.task_text.setString_("\n".join(rows))
        if self.mode == "docx":
            first = Path(self.files[0]["path"])
            try:
                txt = first.read_text(encoding="utf-8", errors="ignore")
                self.md_editor.setString_(txt[:10000])
            except Exception:
                pass

    @objc.python_method
    def _alert(self, title, message):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.runModal()

    @IBAction
    def switchToOCR_(self, _sender):
        self.mode = "ocr"
        self.files = []
        self.ocr_page.setHidden_(False)
        self.docx_page.setHidden_(True)
        self._apply_theme()
        self._refresh_files()

    @IBAction
    def switchToDOCX_(self, _sender):
        self.mode = "docx"
        self.files = []
        self.ocr_page.setHidden_(True)
        self.docx_page.setHidden_(False)
        self._apply_theme()
        self._refresh_files()

    @IBAction
    def switchToWeChat_(self, _sender):
        self.mode = "wechat"
        self.files = []
        self.ocr_page.setHidden_(True)
        self.docx_page.setHidden_(True)
        self.wechat_page.setHidden_(False)
        self._apply_theme()
        self._refresh_files()

    @IBAction
    def noop_(self, _sender):
        return

    @IBAction
    def typeChanged_(self, sender):
        self.selected_type = TYPE_OPTIONS_GUI[sender.indexOfSelectedItem()][1]

    @IBAction
    def jobsChanged_(self, sender):
        self.jobs = int(sender.titleOfSelectedItem())

    @IBAction
    def whisperChanged_(self, sender):
        model_map = {"base（快）": "base", "small": "small", "medium": "medium", "large（准）": "large"}
        self.selected_whisper_model = model_map.get(sender.titleOfSelectedItem(), "base")

    @IBAction
    def ocrEngineChanged_(self, sender):
        engine_map = {
            "本地 MinerU（默认）": "mineru",
            "Apple VisionOCR": "visionocr",
            "legal-ocr 自动": "legalocr-auto",
            "legal-ocr MinerU": "legalocr-mineru",
            "PaddleOCR-VL（需配置）": "legalocr-paddle",
        }
        self.selected_ocr_engine = engine_map.get(sender.titleOfSelectedItem(), "mineru")

    @objc.python_method
    def _allowed_exts(self):
        if self.mode == "wechat":
            return VIDEO_EXTS
        if self.mode == "docx":
            return DOCX_EXTS
        return TO_MARKDOWN_EXTS

    @IBAction
    def addLink_(self, _sender):
        url = self.link_field.stringValue().strip()
        if url and url not in self.links:
            self.links.append(url)
            self.link_field.setStringValue_("")

    @IBAction
    def pickOutputDir_(self, _sender):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        self._active_panel = panel
        self.status_label.setStringValue_("等待选择输出目录...")

        def done(result):
            try:
                if result == 1 and panel.URLs():
                    path = Path(panel.URLs()[0].path())
                    path.mkdir(parents=True, exist_ok=True)
                    self.output_dir = path
                    shown = str(path).replace(str(Path.home()), "~")
                    self.out_path_ocr.setStringValue_(shown)
                    self.out_path_docx.setStringValue_(shown)
                    if hasattr(self, "out_path_wechat"):
                        self.out_path_wechat.setStringValue_(shown)
                    self.status_label.setStringValue_("输出目录已更新")
                else:
                    self.status_label.setStringValue_("已取消选择")
            finally:
                self._active_panel = None

        panel.beginSheetModalForWindow_completionHandler_(self.window, done)

    @IBAction
    def selectFiles_(self, _sender):
        panel = NSOpenPanel.openPanel()
        panel.setAllowsMultipleSelection_(True)
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        self._active_panel = panel
        self.status_label.setStringValue_("等待选择文件...")

        def done(result):
            try:
                if result == 1:
                    added = 0
                    for url in panel.URLs():
                        added += self._add_file(url.path())
                    self._refresh_files()
                    self.status_label.setStringValue_(f"已添加 {added} 个文件" if added else "没有可用文件")
                else:
                    self.status_label.setStringValue_("已取消选择")
            finally:
                self._active_panel = None

        panel.beginSheetModalForWindow_completionHandler_(self.window, done)

    @IBAction
    def pauseProcessing_(self, _sender):
        self.is_paused = not self.is_paused
        self.btn_pause.setTitle_("继续" if self.is_paused else "暂停")

    @IBAction
    def stopProcessing_(self, _sender):
        self.should_stop = True
        self.status_label.setStringValue_("已请求停止（当前文件后）")


    @IBAction
    def removeWatermark_(self, _sender):
        """一键去水印：对输出目录中的 PDF/MD 文件去除指定水印文字。"""
        watermark_text = self.watermark_field.stringValue().strip()
        if not watermark_text:
            self._alert("提示", "请输入水印文字，例如：高城13303201410164518")
            return

        # 收集输出目录中的文件
        pdf_files = list(self.output_dir.glob("*.pdf"))
        md_files = list(self.output_dir.glob("*.md"))
        target_files = pdf_files + md_files

        if not target_files:
            self._alert("提示", f"输出目录中没有找到 PDF 或 Markdown 文件：\n{self.output_dir}")
            return

        removed_count = 0
        for fpath in target_files:
            try:
                if fpath.suffix.lower() == ".pdf":
                    if self._remove_pdf_watermark(fpath, watermark_text):
                        removed_count += 1
                elif fpath.suffix.lower() in (".md", ".markdown", ".txt"):
                    if self._remove_md_watermark(fpath, watermark_text):
                        removed_count += 1
            except Exception as e:
                print(f"处理 {fpath.name} 失败: {e}")

        if removed_count > 0:
            self._alert("完成", f"已处理 {removed_count} 个文件的水印。")
        else:
            self._alert("完成", f"未在文件中找到水印文字：{watermark_text}")

    @objc.python_method
    def _remove_pdf_watermark(self, pdf_path, watermark_text):
        """使用 PyMuPDF 去除 PDF 中的水印文字。"""
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        modified = False

        for page_num in range(len(doc)):
            page = doc[page_num]
            # 获取页面上的所有文本块
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block["type"] == 0:  # 文本块
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if watermark_text in span["text"]:
                                # 获取文本区域的边界框
                                rect = fitz.Rect(span["bbox"])
                                # 用白色矩形覆盖水印区域
                                annot = page.add_redact_annot(rect)
                                modified = True

            # 应用所有 redaction
            if modified:
                page.apply_redactions()

        if modified:
            # 保存到原文件
            backup = pdf_path.with_suffix(".pdf.bak")
            if not backup.exists():
                pdf_path.rename(backup)
                doc.save(str(pdf_path))
                doc.close()
                return True

        doc.close()
        return False

    @objc.python_method
    def _remove_md_watermark(self, md_path, watermark_text):
        """去除 Markdown/文本文件中的水印文字。"""
        content = md_path.read_text(encoding="utf-8")
        if watermark_text not in content:
            return False

        # 删除水印文字（可能单独一行或嵌入文本中）
        # 先尝试删除整行
        lines = content.splitlines()
        new_lines = [line for line in lines if watermark_text not in line]

        # 如果删除整行后行数没变，说明水印是嵌入在某行中
        if len(new_lines) == len(lines):
            new_content = content.replace(watermark_text, "")
        else:
            new_content = "\n".join(new_lines)

        # 备份原文件
        backup = md_path.with_suffix(md_path.suffix + ".bak")
        if not backup.exists():
            md_path.rename(backup)
            md_path.write_text(new_content, encoding="utf-8")
            return True

        return False

    @IBAction
    def clearList_(self, _sender):
        self.files = []
        self.links = []
        self.link_field.setStringValue_("")
        self.md_editor.setString_("")
        self._refresh_files()
        self.progress_bar.setValue_(0.0)
        self.pct_label.setStringValue_("0%")
        self.timer_label.setStringValue_("00:00")
        self.status_label.setStringValue_("已清空")

    @IBAction
    def startProcessing_(self, _sender):
        if self.is_running:
            return
        if self.mode == "wechat":
            if not self.files:
                self._alert("请先选择视频", "拖入或选择一个微信录屏视频后再开始导出。")
                return
            self._run_wechat()
            return
        if self.mode == "ocr":
            if not self.files:
                self._alert("无输入", "请先拖入或选择 PDF/音频/视频文件。")
                return
            self._run_ocr()
            return
        if self.files:
            self._run_docx_files()
            return
        text = self.md_editor.string().strip()
        if not text:
            self._alert("无输入", "请先拖入 Markdown 文件，或直接在编辑区粘贴 Markdown 文本。")
            return
        self._run_docx_text(text)

    @objc.python_method
    def _set_running_ui(self, running):
        self.btn_start.setEnabled_(not running)
        self.btn_start_left_ocr.setEnabled_(not running)
        self.btn_start_left_docx.setEnabled_(not running)
        if hasattr(self, "btn_start_left_wechat"):
            self.btn_start_left_wechat.setEnabled_(not running)
        self.btn_pause.setEnabled_(running)
        self.btn_stop.setEnabled_(running)
        if not running:
            self.btn_pause.setTitle_("暂停")

    @objc.python_method
    def _timer_loop(self):
        paused_time = 0.0
        pause_start = None
        while not self._timer_stop and self.is_running:
            if self.is_paused and pause_start is None:
                pause_start = time.time()
            if not self.is_paused and pause_start is not None:
                paused_time += time.time() - pause_start
                pause_start = None
            if self._start_time:
                elapsed = int(time.time() - self._start_time - paused_time)
                m, s = divmod(max(elapsed, 0), 60)
                self.timer_label.setStringValue_(f"{m:02d}:{s:02d}")
            time.sleep(0.3)

    @objc.python_method
    def _run_ocr(self):
        shown = self.out_path_ocr.stringValue().strip() if hasattr(self, "out_path_ocr") else ""
        if shown:
            self.output_dir = Path(shown.replace("~", str(Path.home()), 1)).expanduser()
            self.output_dir.mkdir(parents=True, exist_ok=True)
        self.is_running = True
        self.is_paused = False
        self.should_stop = False
        self._timer_stop = False
        self._start_time = time.time()
        self.progress_bar.setValue_(0.0)
        self.pct_label.setStringValue_("0%")
        self.status_label.setStringValue_("转 Markdown 中...")
        self._set_running_ui(True)
        threading.Thread(target=self._timer_loop, daemon=True).start()
        threading.Thread(target=self._ocr_thread, daemon=True).start()

    @objc.python_method
    def _ocr_command_for_file(self, path, out):
        ext = path.suffix.lower().lstrip(".")
        if ext in AUDIO_EXTS or ext in VIDEO_EXTS:
            return [TRANSCRIPT_CLI, str(path), "--output", str(out)], "transcript", None
        if ext in {"pdf"} | IMAGE_EXTS:
            engine = self.selected_ocr_engine
            if engine == "mineru" and os.path.exists(MINERU_CLI):
                tmp_dir = self.output_dir / f"_mineru_tmp_{path.stem}_{int(time.time())}"
                return [MINERU_CLI, "-p", str(path), "-o", str(tmp_dir)], "mineru", tmp_dir
            if engine == "legalocr-auto" and os.path.exists(LEGAL_OCR_CLI):
                return [LEGAL_OCR_CLI, str(path), "--output", str(out), "--backend", "auto"], "legalocr-auto", None
            if engine == "legalocr-mineru" and os.path.exists(LEGAL_OCR_CLI):
                return [LEGAL_OCR_CLI, str(path), "--output", str(out), "--backend", "mineru"], "legalocr-mineru", None
            if engine == "legalocr-paddle" and os.path.exists(LEGAL_OCR_CLI):
                return [LEGAL_OCR_CLI, str(path), "--output", str(out), "--backend", "paddle", "--paddle-model", "PaddleOCR-VL-1.5"], "legalocr-paddle", None
            return [CLI, str(path), "--output", str(out)], "visionocr", None
        return [MARKDOWN_CLI, str(path), "-o", str(out)], "markitdown", None

    @objc.python_method
    def _finish_mineru_output(self, tmp_dir, out):
        if not tmp_dir or not Path(tmp_dir).exists():
            return False
        try:
            md_files = sorted(Path(tmp_dir).rglob("*.md"))
            if md_files:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(md_files[0]), str(out))
                return True
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return False

    @objc.python_method
    def _ocr_thread(self):
        total = len(self.files)
        for idx, item in enumerate(self.files):
            if self.should_stop:
                break
            while self.is_paused and not self.should_stop:
                time.sleep(0.2)
            path = Path(item["path"])
            ext = path.suffix.lower().lstrip(".")
            if ext in AUDIO_EXTS or ext in VIDEO_EXTS:
                out = self.output_dir / f"{path.stem}_逐字稿.md"
            elif ext in {"pdf"} | IMAGE_EXTS:
                out = self.output_dir / f"{path.stem}.md"
            else:
                out = self.output_dir / f"{path.stem}.md"
            cmd, channel, tmp_dir = self._ocr_command_for_file(path, out)
            self.status_label.setStringValue_(f"处理中：{path.name}（{channel}）")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            base = idx / total
            while proc.poll() is None:
                if self.should_stop:
                    proc.terminate()
                    break
                while self.is_paused and not self.should_stop:
                    time.sleep(0.2)
                bump = min(base + (0.88 / total), (idx + 0.88) / total)
                self.progress_bar.setValue_(bump)
                self.pct_label.setStringValue_(f"{int(bump * 100)}%")
                time.sleep(0.25)
            if channel == "mineru":
                if not self._finish_mineru_output(tmp_dir, out):
                    self.status_label.setStringValue_(f"MinerU未生成结果，降级 VisionOCR：{path.name}")
                    subprocess.run([CLI, str(path), "--output", str(out)], text=True, capture_output=True)
            elif proc.returncode not in (0, None) and channel.startswith("legalocr"):
                self.status_label.setStringValue_(f"{channel}失败，降级 VisionOCR：{path.name}")
                subprocess.run([CLI, str(path), "--output", str(out)], text=True, capture_output=True)
            done = (idx + 1) / total
            self.progress_bar.setValue_(done)
            self.pct_label.setStringValue_(f"{int(done * 100)}%")
        self._finish_run()

    @objc.python_method
    def _run_docx_files(self):
        shown = self.out_path_docx.stringValue().strip() if hasattr(self, "out_path_docx") else ""
        if shown:
            self.output_dir = Path(shown.replace("~", str(Path.home()), 1)).expanduser()
            self.output_dir.mkdir(parents=True, exist_ok=True)
        self.is_running = True
        self.is_paused = False
        self.should_stop = False
        self._timer_stop = False
        self._start_time = time.time()
        self.progress_bar.setValue_(0.0)
        self.pct_label.setStringValue_("0%")
        self.status_label.setStringValue_("Markdown 转 Word 中...")
        self._set_running_ui(True)
        threading.Thread(target=self._timer_loop, daemon=True).start()
        threading.Thread(target=self._docx_files_thread, daemon=True).start()

    @objc.python_method
    def _docx_value_number(self, popup, default):
        if not popup:
            return default
        text = popup.titleOfSelectedItem() or ""
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        return float(m.group(1)) if m else default

    @objc.python_method
    def _docx_indent_pt(self):
        text = self.first_indent_popup.titleOfSelectedItem() if hasattr(self, "first_indent_popup") else ""
        if "无" in text:
            return 0
        if "4" in text:
            return 48
        return 24

    @objc.python_method
    def _docx_margin_values(self):
        text = self.margin_popup.titleOfSelectedItem() if hasattr(self, "margin_popup") else ""
        if "窄" in text:
            return 1.8, 1.8
        if "宽" in text:
            return 3.5, 3.5
        return 3.18, 3.18

    @objc.python_method
    def _docx_page_values(self):
        text = self.page_popup.titleOfSelectedItem() if hasattr(self, "page_popup") else ""
        if "A3" in text:
            return 29.7, 42.0
        if "Letter" in text:
            return 21.59, 27.94
        return 21.0, 29.7

    @objc.python_method
    def _docx_font_pair(self):
        preset = self.font_preset_popup.titleOfSelectedItem() if hasattr(self, "font_preset_popup") else ""
        title_font = self.title_font_popup.titleOfSelectedItem() if hasattr(self, "title_font_popup") else "黑体"
        body_font = self.body_font_popup.titleOfSelectedItem() if hasattr(self, "body_font_popup") else "仿宋"
        if "法院" in preset:
            return "黑体", "仿宋"
        if "宋体" in preset:
            return "黑体", "宋体"
        if "屏幕" in preset:
            return "微软雅黑", "微软雅黑"
        return title_font, body_font

    @objc.python_method
    def _docx_config_path(self):
        page_w, page_h = self._docx_page_values()
        margin_l, margin_r = self._docx_margin_values()
        title_font, body_font = self._docx_font_pair()
        title_size = self._docx_value_number(self.title_size_popup, 15)
        body_size = self._docx_value_number(self.body_size_popup, 12)
        line_spacing = self._docx_value_number(self.line_spacing_popup, 1.5)
        indent = self._docx_indent_pt()
        content = f"""name: "GUI自定义法律文书格式"
description: "由办案材料助手界面生成"
page:
  width: {page_w}
  height: {page_h}
  margin_top: 2.54
  margin_bottom: 2.54
  margin_left: {margin_l}
  margin_right: {margin_r}
fonts:
  default:
    name: "{body_font}"
    name_alt: "{body_font}"
    ascii: "Times New Roman"
    size: {body_size}
    color: "#000000"
titles:
  level1:
    font: "{title_font}"
    font_alt: "Times New Roman"
    size: {title_size}
    bold: true
    align: "center"
    space_before: 6
    space_after: 6
    indent: 0
  level2:
    font: "{title_font}"
    font_alt: "Times New Roman"
    size: {body_size}
    bold: true
    align: "justify"
    indent: {indent}
  level3:
    font: "{title_font}"
    font_alt: "Times New Roman"
    size: {body_size}
    bold: true
    align: "justify"
    indent: {indent}
  level4:
    font: "{title_font}"
    font_alt: "Times New Roman"
    size: {body_size}
    bold: true
    align: "justify"
    indent: {indent}
paragraph:
  line_spacing: {line_spacing}
  first_line_indent: {indent}
  align: "justify"
page_number:
  enabled: true
  format: "1/x"
  font: "Times New Roman"
  size: 10.5
  position: "center"
quotes:
  convert_to_chinese: true
table:
  border_enabled: true
  border_color: "#000000"
  border_width: 4
  line_spacing: 1.2
image:
  display_ratio: 1.0
  max_width_cm: 14.64
  target_dpi: 260
horizontal_rule:
  character: "─"
  repeat_count: 55
  font: "Times New Roman"
  size: 12
  color: "#808080"
  alignment: "center"
"""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", encoding="utf-8", delete=False)
        try:
            tmp.write(content)
            return tmp.name
        finally:
            tmp.close()

    @objc.python_method
    def _docx_files_thread(self):
        total = len(self.files)
        config_path = self._docx_config_path()
        for idx, item in enumerate(self.files):
            if self.should_stop:
                break
            while self.is_paused and not self.should_stop:
                time.sleep(0.2)
            src = Path(item["path"])
            out = self.output_dir / f"{src.stem}.docx"
            self.status_label.setStringValue_(f"处理中：{src.name}")
            subprocess.run([DOCX_CLI, str(src), "--type", self.selected_docx_type, "--config", config_path, "--output", str(out)], check=False)
            done = (idx + 1) / total
            self.progress_bar.setValue_(done)
            self.pct_label.setStringValue_(f"{int(done * 100)}%")
        self._finish_run()

    @objc.python_method
    def _run_docx_text(self, text):
        shown = self.out_path_docx.stringValue().strip() if hasattr(self, "out_path_docx") else ""
        if shown:
            self.output_dir = Path(shown.replace("~", str(Path.home()), 1)).expanduser()
            self.output_dir.mkdir(parents=True, exist_ok=True)
        self.is_running = True
        self.is_paused = False
        self.should_stop = False
        self._timer_stop = False
        self._start_time = time.time()
        self.progress_bar.setValue_(0.0)
        self.pct_label.setStringValue_("0%")
        self.status_label.setStringValue_("粘贴文本转 Word 中...")
        self._set_running_ui(True)
        threading.Thread(target=self._timer_loop, daemon=True).start()
        threading.Thread(target=self._docx_text_thread, args=(text,), daemon=True).start()

    @objc.python_method
    def _docx_text_thread(self, text):
        tmp_path = None
        config_path = self._docx_config_path()
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as tmp:
                tmp.write(text)
                tmp_path = tmp.name
            name = f"粘贴_{time.strftime('%Y%m%d_%H%M%S')}.docx"
            out = self.output_dir / name
            self.progress_bar.setValue_(0.3)
            self.pct_label.setStringValue_("30%")
            subprocess.run([DOCX_CLI, tmp_path, "--type", self.selected_docx_type, "--config", config_path, "--output", str(out)], check=False)
            self.progress_bar.setValue_(1.0)
            self.pct_label.setStringValue_("100%")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        self._finish_run()


    @objc.python_method
    def _build_wechat_page(self, body_h):
        _fill_view(self.wechat_page, C_APP_BG)
        left = NSView.alloc().initWithFrame_(NSMakeRect(20, 20, 320, body_h - 40))
        _resize(left, FILL_HEIGHT | NSViewMaxXMargin)
        _set_view_style(left, C_WHITE, C_BORDER, 12)
        self.wechat_page.addSubview_(left)

        left.addSubview_(_label("取证设置", 18, left.bounds().size.height - 36, 120, 22, size=15, weight=0.65, color=C_TEXT_STRONG))
        left.addSubview_(_label("处理模式", 18, left.bounds().size.height - 72, 120, 18, size=12, color=C_DIM))
        self.wechat_mode_control = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 104, 284, 28), False)
        self.wechat_mode_control.addItemWithTitle_("快速初稿")
        self.wechat_mode_control.addItemWithTitle_("OCR增强")
        self.wechat_mode_control.selectItemAtIndex_(0)
        self.wechat_mode_control.setTarget_(self)
        self.wechat_mode_control.setAction_("wechatModeChanged:")
        left.addSubview_(self.wechat_mode_control)

        left.addSubview_(_label("抽帧策略", 18, left.bounds().size.height - 146, 120, 18, size=12, color=C_DIM))
        self.wechat_capture_level = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 178, 284, 28), False)
        for opt in ["更少页", "平衡", "少漏内容"]:
            self.wechat_capture_level.addItemWithTitle_(opt)
        self.wechat_capture_level.selectItemAtIndex_(2)
        left.addSubview_(self.wechat_capture_level)

        left.addSubview_(_label("选帧方式", 18, left.bounds().size.height - 220, 120, 18, size=12, color=C_DIM))
        self.wechat_stride_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 252, 284, 28), False)
        for opt in ["自动判断滚动速度", "每 8 张留 1 张", "每 10 张留 1 张", "每 15 张留 1 张", "每 20 张留 1 张", "智能去重（旧逻辑）"]:
            self.wechat_stride_popup.addItemWithTitle_(opt)
        self.wechat_stride_popup.setTarget_(self)
        self.wechat_stride_popup.setAction_("wechatStrideChanged:")
        left.addSubview_(self.wechat_stride_popup)

        left.addSubview_(_label("输出质量", 18, left.bounds().size.height - 294, 120, 18, size=12, color=C_DIM))
        self.wechat_quality = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(18, left.bounds().size.height - 326, 284, 28), False)
        for opt in ["清晰", "平衡", "体积"]:
            self.wechat_quality.addItemWithTitle_(opt)
        self.wechat_quality.selectItemAtIndex_(0)
        left.addSubview_(self.wechat_quality)

        left.addSubview_(_label("选项", 18, left.bounds().size.height - 368, 120, 18, size=12, color=C_DIM))
        self.wechat_keep_raw = _checkbox("保留原始帧", 18, left.bounds().size.height - 396, 130, 22, True)
        self.wechat_context_overlap = _checkbox("相邻页少量重复", 160, left.bounds().size.height - 396, 142, 22, True)
        self.wechat_local_ocr = _checkbox("本地OCR优先", 18, left.bounds().size.height - 426, 130, 22, True)
        self.wechat_candidate_ocr = _checkbox("候选页OCR", 160, left.bounds().size.height - 426, 130, 22, False)
        self.wechat_cloud_ocr = _checkbox("手动云端整理", 18, left.bounds().size.height - 458, 140, 22, False)
        left.addSubview_(self.wechat_keep_raw)
        left.addSubview_(self.wechat_context_overlap)
        left.addSubview_(self.wechat_local_ocr)
        left.addSubview_(self.wechat_candidate_ocr)
        left.addSubview_(self.wechat_cloud_ocr)
        left.addSubview_(_btn("云端设置", 176, left.bounds().size.height - 458, 126, 26, self, "configureWeChatCloud:"))

        left.addSubview_(_label("输出目录", 18, left.bounds().size.height - 498, 100, 18, size=12, color=C_DIM))
        self.out_path_wechat = _input_field(18, left.bounds().size.height - 526, 252, 28)
        self.out_path_wechat.setStringValue_(str(self.wechat_output_dir).replace(str(Path.home()), "~"))
        left.addSubview_(self.out_path_wechat)
        self.btn_out_wechat = _btn("📁", 274, left.bounds().size.height - 526, 28, 28, self, "pickOutputDir:")
        left.addSubview_(self.btn_out_wechat)

        self.btn_start_left_wechat = _btn("导出取证材料", 18, 14, 284, 34, self, "startProcessing:")
        _resize(self.btn_start_left_wechat, PIN_BOTTOM)
        left.addSubview_(self.btn_start_left_wechat)
        _set_view_style(self.btn_start_left_wechat, C_PANEL_BG, C_BORDER, 8)
        self.btn_start_left_wechat.setContentTintColor_(C_TEXT_STRONG)
        _pin_panel_controls_to_top(left, (self.btn_start_left_wechat,))

        right = NSView.alloc().initWithFrame_(NSMakeRect(356, 20, self.wechat_page.bounds().size.width - 376, body_h - 40))
        _resize(right, FILL_WIDTH | FILL_HEIGHT)
        self.wechat_page.addSubview_(right)

        self.wechat_drop = DropZone.alloc().initWithFrame_controller_(NSMakeRect(0, right.bounds().size.height - 230, right.bounds().size.width, 230), self)
        _resize(self.wechat_drop, FILL_WIDTH | PIN_TOP)
        right.addSubview_(self.wechat_drop)
        wechat_title = _label("拖入聊天录屏", right.bounds().size.width / 2 - 100, 132, 200, 30, size=17, weight=0.75, color=C_TEXT_STRONG, align=2)
        wechat_subtitle = _label("MP4 / MOV / M4V，可批量处理", right.bounds().size.width / 2 - 150, 102, 300, 22, size=13, color=C_DIM, align=2)
        self.wechat_drop.addSubview_(_register_file_drag(_center_in_parent(wechat_title)))
        self.wechat_drop.addSubview_(_register_file_drag(_center_in_parent(wechat_subtitle)))
        self.btn_pick_wechat = _btn("选择录屏", right.bounds().size.width / 2 - 48, 72, 96, 32, self, "selectFiles:")
        self.wechat_drop.addSubview_(_register_file_drag(_center_in_parent(self.btn_pick_wechat)))
        _set_view_style(self.btn_pick_wechat, C_WHITE, C_BORDER, 8)
        self.btn_pick_wechat.setContentTintColor_(C_TEXT_STRONG)

        self.wechat_hint = _label("快速初稿本地处理；OCR增强默认仅在本机生成文字索引，只有勾选云端整理才发送文字摘要。", 0, right.bounds().size.height - 292, right.bounds().size.width, 22, size=12, color=C_DIM)
        _resize(self.wechat_hint, FILL_WIDTH | PIN_TOP)
        right.addSubview_(self.wechat_hint)

        self.wechat_task_text = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, right.bounds().size.width, right.bounds().size.height - 320))
        self.wechat_task_text.setEditable_(False)
        self.wechat_task_text.setFont_(_font(12))
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, right.bounds().size.width, right.bounds().size.height - 320))
        _resize(scroll, FILL_WIDTH | FILL_HEIGHT)
        scroll.setDocumentView_(self.wechat_task_text)
        scroll.setHasVerticalScroller_(True)
        _set_view_style(scroll, C_WHITE, C_BORDER, 10)
        right.addSubview_(scroll)

    @IBAction
    def wechatModeChanged_(self, sender):
        idx = sender.indexOfSelectedItem() if sender.respondsToSelector_("indexOfSelectedItem") else sender.selectedSegment()
        self.wechat_mode = "ocr" if idx == 1 else "quick"

    @IBAction
    def wechatStrideChanged_(self, sender):
        stride_map = {
            "自动判断滚动速度": "auto",
            "每 8 张留 1 张": "8",
            "每 10 张留 1 张": "10",
            "每 15 张留 1 张": "15",
            "每 20 张留 1 张": "20",
            "智能去重（旧逻辑）": "legacy",
        }
        self.selected_wechat_stride = stride_map.get(sender.titleOfSelectedItem(), "auto")

    @objc.python_method
    def _control_index(self, control):
        if control.respondsToSelector_("indexOfSelectedItem"):
            return int(control.indexOfSelectedItem())
        return int(control.selectedSegment())

    @objc.python_method
    def _wechat_profile_args(self):
        capture_level = self._control_index(self.wechat_capture_level)
        selected_quality = self._control_index(self.wechat_quality)

        image_ext = "png"
        max_width = None
        pdf_quality = "90"
        if selected_quality == 1:
            max_width = "1080"
            pdf_quality = "86"
        elif selected_quality == 2:
            image_ext = "jpg"
            max_width = "1080"
            pdf_quality = "78"

        if capture_level == 2:
            burst_fps = "12"
            dedupe_distance = "4"
            dedupe_window = "6"
            pixel_delta = "0.015"
            interval = "1.5"
            label = "少漏内容"
            stable_motion_distance = "14"
        elif capture_level == 1:
            burst_fps = "10"
            dedupe_distance = "5"
            dedupe_window = "8"
            pixel_delta = "0.02"
            interval = "2"
            label = "平衡"
            stable_motion_distance = "18"
        else:
            burst_fps = "8"
            dedupe_distance = "8"
            dedupe_window = "12"
            pixel_delta = "0.05"
            interval = "3"
            label = "更少页"
            stable_motion_distance = "20"

        if capture_level == 2:
            min_visual_delta = "0.4" if bool(self.wechat_context_overlap.state()) else "0.8"
        elif capture_level == 1:
            min_visual_delta = "0.6" if bool(self.wechat_context_overlap.state()) else "1.0"
        else:
            min_visual_delta = "0.9" if bool(self.wechat_context_overlap.state()) else "1.4"
        args = [
            "--image-ext", image_ext,
            "--filter", "auto",
            "--burst-fps", burst_fps,
            "--dedupe-distance", dedupe_distance,
            "--dedupe-window", dedupe_window,
            "--min-visual-delta", min_visual_delta,
            "--pixel-delta", pixel_delta,
            "--stable-motion-distance", stable_motion_distance,
            "--interval", interval,
            "--pdf-jpeg-quality", pdf_quality,
        ]
        if self.selected_wechat_stride != "legacy":
            args += ["--stride-frames", self.selected_wechat_stride]
            label += " / 自动步长" if self.selected_wechat_stride == "auto" else f" / 每{self.selected_wechat_stride}帧"
        if max_width:
            args += ["--max-width", max_width]
        if not bool(self.wechat_keep_raw.state()):
            args.append("--no-keep-raw")
        return args, label

    @objc.python_method
    def _run_wechat(self):
        if not WECHAT_CLI.exists():
            self._alert("微信取证工具缺失", f"未找到：{WECHAT_CLI}")
            return
        self.wechat_output_dir = Path(self.out_path_wechat.stringValue().strip().replace("~", str(Path.home()), 1)).expanduser() if self.out_path_wechat.stringValue().strip() else WECHAT_OUTPUT_DIR
        self.wechat_output_dir.mkdir(parents=True, exist_ok=True)
        self.is_running = True
        self.is_paused = False
        self.should_stop = False
        self._timer_stop = False
        self._start_time = time.time()
        self.progress_bar.setValue_(0.0)
        self.pct_label.setStringValue_("0%")
        self.status_label.setStringValue_("微信录屏导出中...")
        self._set_running_ui(True)
        threading.Thread(target=self._timer_loop, daemon=True).start()
        threading.Thread(target=self._wechat_thread, daemon=True).start()

    @objc.python_method
    def _wechat_thread(self):
        profile_args, profile_label = self._wechat_profile_args()
        total = len(self.files)
        rows = ["文件名\t状态\t输出"]
        failures = []
        generated_dirs = []
        notes = []
        ok_count = 0

        for idx, item in enumerate(self.files, start=1):
            if self.should_stop:
                break
            while self.is_paused and not self.should_stop:
                time.sleep(0.2)
            path = Path(item["path"])
            self.status_label.setStringValue_(f"正在导出：{path.name}（{profile_label}）")
            cmd = [
                sys.executable, str(WECHAT_CLI), "interval-pdf", str(path),
                "--out-base", str(self.wechat_output_dir), *profile_args,
            ]
            proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            while proc.poll() is None:
                if self.should_stop:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        proc.kill()
                    break
                time.sleep(0.3)
            stdout_text = proc.stdout.read() if proc.stdout else ""
            export_dir = None
            pdfs = []
            for line in stdout_text.splitlines():
                line = line.strip()
                if line.endswith(".pdf") and Path(line).exists():
                    pdfs.append(Path(line))
                elif line.startswith("/") and Path(line).is_dir():
                    export_dir = Path(line)
            if proc.returncode == 0 and export_dir and pdfs:
                validate = subprocess.run([sys.executable, str(WECHAT_CLI), "validate-export", str(export_dir)], text=True, capture_output=True, timeout=30)
                if validate.returncode == 0:
                    ok_count += 1
                    generated_dirs.append(export_dir)
                    rows.append(f"{path.name}\t完成\t{pdfs[0]}")
                else:
                    msg = validate.stderr.strip() or validate.stdout.strip() or "导出校验失败"
                    failures.append(f"{path.name}: {msg}")
                    rows.append(f"{path.name}\t失败\t{msg}")
            else:
                msg = proc.stderr.read().strip() if proc.stderr else "导出失败"
                failures.append(f"{path.name}: {msg[:80]}")
                rows.append(f"{path.name}\t失败\t{msg[:80]}")
            self.wechat_task_text.setString_("\n".join(rows))
            done = idx / total
            self.progress_bar.setValue_(done * 0.82)
            self.pct_label.setStringValue_(f"{int(done * 82)}%")

        if self.wechat_mode == "ocr" and generated_dirs and bool(self.wechat_local_ocr.state()):
            self.status_label.setStringValue_("正在生成本地 OCR 文字索引...")
            notes.extend(self._run_wechat_local_ocr(generated_dirs))
            self.progress_bar.setValue_(0.92)
            self.pct_label.setStringValue_("92%")

        if failures:
            self.status_label.setStringValue_(f"完成 {ok_count}/{total}，有失败项")
            self._alert("部分视频导出失败", "\n".join(failures[:3]))
        elif notes:
            self.status_label.setStringValue_(f"导出完成：{ok_count} 个视频；{notes[0]}")
            self._alert("导出完成", "\n".join(notes[:4]))
        else:
            self.status_label.setStringValue_(f"导出完成：{ok_count} 个视频")
        self._finish_run()

    @objc.python_method
    def _run_wechat_local_ocr(self, export_dirs):
        notes = []
        scope = "selected" if bool(self.wechat_candidate_ocr.state()) else "raw"
        for export_dir in export_dirs:
            cmd = [sys.executable, str(WECHAT_CLI), "ocr-index", str(export_dir), "--scope", scope, "--jobs", "2"]
            proc = subprocess.run(cmd, text=True, capture_output=True)
            if proc.returncode != 0:
                notes.append(f"{export_dir.name} 本地OCR失败")
        if not notes:
            notes.append("本地OCR索引已生成")
        return notes

    @objc.python_method
    def _confirm_wechat_cloud(self) -> bool:
        alert = NSAlert.alloc().init()
        alert.setMessageText_("确认云端整理")
        alert.setInformativeText_("只会发送 OCR 文字、时间戳、截图编号和 SHA256，不会发送录屏文件或截图图像。")
        alert.addButtonWithTitle_("继续")
        alert.addButtonWithTitle_("取消")
        return alert.runModal() == 1000

    @IBAction
    def configureWeChatCloud_(self, _sender):
        base_url = _osascript_prompt("请输入云端 base URL", self.wechat_cloud_base_url)
        if base_url is None:
            return
        model = _osascript_prompt("请输入云端 model", self.wechat_cloud_model)
        if model is None:
            return
        key_default = "********" if _keychain_get_wechat() else ""
        api_key = _osascript_prompt("请输入 API Key（留空保留现有）", key_default, hidden=True)
        if api_key is None:
            return
        self.wechat_cloud_base_url = base_url.strip() or WECHAT_DEFAULT_CLOUD_BASE_URL
        self.wechat_cloud_model = model.strip() or WECHAT_DEFAULT_CLOUD_MODEL
        if api_key.strip() and api_key.strip() != "********":
            try:
                _keychain_set_wechat(api_key.strip())
            except RuntimeError as exc:
                self._alert("云端设置失败", str(exc))
                return
        self._alert("云端设置已保存", f"base URL: {self.wechat_cloud_base_url}\nmodel: {self.wechat_cloud_model}")

    @objc.python_method
    def _finish_run(self):
        self._timer_stop = True
        self.is_running = False
        self._set_running_ui(False)
        if self.should_stop:
            self.status_label.setStringValue_("已停止")
        else:
            self.status_label.setStringValue_("处理完成")
            self.progress_bar.setValue_(1.0)
            self.pct_label.setStringValue_("100%")
            self._update_docx_preview()
            if self.mode == "wechat":
                subprocess.run(["open", str(self.wechat_output_dir)], check=False)
            else:
                subprocess.run(["open", str(self.output_dir)], check=False)

    @objc.python_method
    def _update_docx_preview(self):
        text = self.md_editor.string().strip()
        if not text:
            return
        lines = [line for line in text.splitlines() if line.strip()][:14]
        preview = ["办案报告（预览）", ""]
        for line in lines:
            if line.startswith("#"):
                preview.append(line.lstrip("# ").strip())
            else:
                preview.append(line)
        self.word_preview.setString_("\n".join(preview))
        self.word_preview.scrollRangeToVisible_(NSMakeRange(0, 0))

    def run(self):
        self.app.setActivationPolicy_(0)
        self.app.activateIgnoringOtherApps_(True)
        AppHelper.runEventLoop(installInterrupt=True)


if __name__ == "__main__":
    ctrl = Controller.alloc().init()
    ctrl.run()
