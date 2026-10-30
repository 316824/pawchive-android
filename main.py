"""Mobile Pawchive downloader entry point (PySide6 / Android)."""
from __future__ import annotations

import html
import os
import random
import re
import shutil
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

from PySide6.QtCore import Qt, QDir, QFile, QFileInfo, QStandardPaths, QThread, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget,
)

BASE_URL = "https://pawchive.pw"
USER_AGENT = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/128 Mobile Safari/537.36"
PAGE_SIZE = 50
PROFILE_RE = re.compile(r"https://pawchive\.pw/(?:fanbox|patreon|subscribestar|discord|boosty)/user/[^/?#]+/?$")
INVALID_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
PALETTE = ["#ff647c", "#ffad45", "#f0d84c", "#48c988", "#38bfd3", "#638bff", "#ba70ea"]


def safe_name(value: str, fallback: str = "post") -> str:
    value = INVALID_NAME.sub("_", str(value or "")).strip(" .") or fallback
    return value[:120]


def absolute_post_url(href: str) -> str:
    url = urljoin(BASE_URL + "/", (href or "").strip())
    parsed = urlparse(url)
    if parsed.hostname != "pawchive.pw" or parsed.path.find("/post/") < 0:
        return ""
    return parsed._replace(scheme="https").geturl()


class PawchiveParser(HTMLParser):
    """Small stdlib parser for Pawchive cards and attachment links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards = []
        self.attachments = []
        self.card = None
        self.card_depth = 0
        self.header_depth = 0
        self.h1_depth = 0
        self.title_span_depth = 0
        self.title_span_seen = False
        self.title_text = []
        self.header_text = []
        self.in_attachment = 0
        self.attachment_text = []
        self.attachment = None
        self.in_files = 0

    @staticmethod
    def _classes(attrs):
        return set(dict(attrs).get("class", "").split())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "article" and "post-card" in classes:
            self.card = {"url": "", "date": "", "title": "", "image": None, "formats": []}
            self.card_depth = 1
            self.header_depth = 0
            self.header_text = []
        elif self.card is not None:
            if tag == "article": self.card_depth += 1
            if tag == "a" and "/post/" in attrs.get("href", "") and not self.card["url"]:
                self.card["url"] = absolute_post_url(attrs.get("href", ""))
            if tag == "time" and "timestamp" in classes:
                self.card["date"] = attrs.get("datetime", "")
            if tag == "img" and "post-card__image" in classes:
                self.card["image"] = attrs.get("data-src") or attrs.get("src")
            if "post-card__header" in classes:
                self.header_depth = 1
            elif self.header_depth and tag not in ("br",):
                self.header_depth += 1
        if tag == "h1" and "post__title" in classes:
            self.h1_depth = 1
            self.title_span_depth = 0
            self.title_span_seen = False
            self.title_text = []
        elif self.h1_depth:
            if tag == "h1": self.h1_depth += 1
            if tag == "span" and not self.title_span_seen:
                self.title_span_seen = True
                self.title_span_depth = 1
            elif self.title_span_depth:
                self.title_span_depth += 1
        if tag == "div" and "post__files" in classes:
            self.in_files += 1
        if tag == "a":
            direct = "post__attachment-link" in classes
            thumb = "fileThumb" in classes and self.in_files > 0
            url = attrs.get("href", "")
            if (direct or thumb) and url.startswith(("https://file.pawchive.pw/", "https://n2.pawchive.pw/")):
                self.attachment = {"url": url, "name": attrs.get("download", ""), "direct": direct}
                self.attachment_text = []
                self.in_attachment = 1
            elif self.in_attachment:
                self.in_attachment += 1

    def handle_endtag(self, tag):
        if self.card is not None:
            if self.header_depth:
                self.header_depth -= 1
                if self.header_depth == 0:
                    self.card["title"] = "".join(self.header_text).strip()
            if tag == "article":
                self.card_depth -= 1
                if self.card_depth <= 0:
                    if self.card.get("url") and self.card.get("date"):
                        self.cards.append(self.card)
                    self.card = None
        if self.in_attachment:
            self.in_attachment -= 1
            if tag == "a" and self.in_attachment == 0:
                if self.attachment:
                    if not self.attachment["name"]:
                        self.attachment["name"] = "".join(self.attachment_text).strip()
                    self.attachments.append(self.attachment)
                self.attachment = None
        if tag == "div" and self.in_files:
            self.in_files -= 1
        if self.h1_depth:
            if self.title_span_depth:
                self.title_span_depth -= 1
            if tag == "h1":
                self.h1_depth -= 1

    def handle_data(self, data):
        if self.card is not None and self.header_depth:
            self.header_text.append(data)
        if self.h1_depth and self.title_span_seen and self.title_span_depth:
            self.title_text.append(data)
        if self.in_attachment:
            self.attachment_text.append(data)


def fetch_bytes(url: str, referer: str = "", timeout: int = 30):
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if referer: headers["Referer"] = referer
    request = Request(url, headers=headers)
    return urlopen(request, timeout=timeout)


def fetch_page(url: str, referer: str = "") -> str:
    with fetch_bytes(url, referer, 30) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")


def iter_profile(profile: str, cancel_check=lambda: False, progress=None, stop_after_page=None):
    offset = 0
    seen = set()
    result = []
    while True:
        if cancel_check(): raise RuntimeError("已停止")
        page_url = f"{profile}?o={offset}" if offset else profile
        parser = PawchiveParser(); parser.feed(fetch_page(page_url))
        cards = parser.cards
        if not cards: break
        before = len(result)
        for card in cards:
            if card["url"] not in seen:
                seen.add(card["url"]); result.append(card)
        if progress: progress(offset // PAGE_SIZE + 1, len(result))
        if stop_after_page and stop_after_page(): break
        if len(cards) < PAGE_SIZE or len(result) == before: break
        offset += PAGE_SIZE
    return result


class ScanWorker(QThread):
    progress = Signal(int, int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, profile: str, cache_dir: Path):
        super().__init__(); self.profile = profile.rstrip("/"); self.cache_dir = cache_dir
        self.paused = False; self.finish_requested = False

    def run(self):
        try:
            posts = iter_profile(self.profile, self.isInterruptionRequested,
                                 lambda pages, count: self.progress.emit(pages, count),
                                 lambda: self.finish_requested)
            complete = []
            for idx, post in enumerate(posts):
                while self.paused and not self.finish_requested and not self.isInterruptionRequested():
                    time.sleep(.08)
                if self.isInterruptionRequested(): raise RuntimeError("扫描已停止")
                if self.finish_requested: break
                try:
                    detail = PawchiveParser(); detail.feed(fetch_page(post["url"]))
                    title = "".join(detail.title_text).strip() or post["title"] or "post"
                    formats = []
                    for item in detail.attachments:
                        ext = Path(urlparse(item["url"]).path).suffix.lower()
                        if ext and ext not in formats: formats.append(ext)
                    post["title"] = title; post["formats"] = formats
                except Exception:
                    post["formats"] = []
                if post.get("image"):
                    try:
                        with fetch_bytes(post["image"], post["url"], 12) as response:
                            suffix = Path(urlparse(post["image"]).path).suffix or ".img"
                            image_path = self.cache_dir / f"cover_{idx:05}{suffix}"
                            image_path.write_bytes(response.read())
                            post["local_image"] = str(image_path)
                    except Exception: post["local_image"] = None
                complete.append(post)
                self.progress.emit(0, len(complete))
            self.done.emit(complete)
        except Exception as exc:
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    progress = Signal(str, int, int)
    log = Signal(str)
    done = Signal(int)
    failed = Signal(str)

    def __init__(self, staging: Path, profile: str, order: str, by_title: bool,
                 selected_urls=None, rename_order=False, start_number=1):
        super().__init__(); self.staging = staging; self.profile = profile.rstrip("/")
        self.order = order; self.by_title = by_title; self.selected_urls = set(selected_urls or [])
        self.rename_order = rename_order; self.start_number = start_number; self.current_album = None

    def run(self):
        current_temp = None
        try:
            self.staging.mkdir(parents=True, exist_ok=True)
            posts = iter_profile(self.profile, self.isInterruptionRequested)
            if self.selected_urls: posts = [p for p in posts if p["url"] in self.selected_urls]
            posts.sort(key=lambda p: p["date"], reverse=self.order == "newest")
            if not posts: raise RuntimeError("没有找到可下载的图集")
            saved = 0; records = []; duplicate_names = set(); owners = {}
            total = len(posts)
            for post_index, post in enumerate(posts, 1):
                if self.isInterruptionRequested(): raise RuntimeError("用户已停止下载")
                parser = PawchiveParser(); parser.feed(fetch_page(post["url"]))
                title = "".join(parser.title_text).strip() or post["title"] or "post"
                title_safe = safe_name(title)
                dest = self.staging / title_safe if self.by_title else self.staging
                dest.mkdir(parents=True, exist_ok=True)
                self.current_album = dest if self.by_title else None
                if not parser.attachments:
                    self.log.emit(f"没有找到附件：{title}"); continue
                for index, item in enumerate(parser.attachments, 1):
                    if self.isInterruptionRequested(): raise RuntimeError("用户已停止下载")
                    name = item["name"].strip()
                    if name.lower().startswith("download "): name = name[9:].strip()
                    if not name:
                        name = (parse_qs(urlparse(item["url"]).query).get("f") or [""])[0]
                    if not name: name = Path(urlparse(item["url"]).path).name or f"image_{index}.bin"
                    name = safe_name(unquote(name), f"image_{index}.bin")
                    target = dest / name
                    if not self.by_title and name in duplicate_names:
                        target = dest / self._unique(f"({title_safe}) - {name}", dest)
                    elif target.exists():
                        prior = owners.get(name)
                        if not self.by_title and prior and prior != post["url"]:
                            duplicate_names.add(name)
                            for old in records:
                                if old["name"] == name and old["path"].exists():
                                    old_target = dest / self._unique(f"({old['title']}) - {old['path'].name}", dest)
                                    old["path"].rename(old_target); owners.pop(name, None)
                                    owners[old_target.name] = old["url"]
                            target = dest / self._unique(f"({title_safe}) - {name}", dest)
                        else: target = dest / self._unique(name, dest)
                    part = target.with_name(target.name + ".part"); current_temp = part
                    last_error = None
                    for attempt in range(1, 5):
                        try:
                            if attempt > 1: time.sleep(min(12, 2 ** attempt + random.random()))
                            received = 0
                            with fetch_bytes(item["url"], post["url"], 45) as response, part.open("wb") as out:
                                total_bytes = int(response.headers.get("Content-Length", 0) or 0)
                                content_type = response.headers.get("Content-Type", "").lower()
                                self.progress.emit(f"({post_index}/{total}) {title_safe} / {target.name}", 0, total_bytes)
                                while True:
                                    if self.isInterruptionRequested(): raise RuntimeError("用户已停止下载")
                                    chunk = response.read(128 * 1024)
                                    if not chunk: break
                                    if received == 0 and ("text/html" in content_type or chunk.lstrip().lower().startswith(b"<!doctype html")):
                                        raise RuntimeError("网站返回了网页而不是文件")
                                    out.write(chunk); received += len(chunk)
                                    self.progress.emit(f"({post_index}/{total}) {title_safe} / {target.name}", received, total_bytes)
                            part.replace(target); last_error = None; break
                        except Exception as exc:
                            last_error = exc
                            try: part.unlink(missing_ok=True)
                            except OSError: pass
                            if isinstance(exc, RuntimeError) and self.isInterruptionRequested(): raise
                    if last_error:
                        self.log.emit(f"下载失败：{title_safe} / {name} — {last_error}")
                        if self.by_title:
                            shutil.rmtree(dest, ignore_errors=True)
                            raise RuntimeError(f"图集“{title}”下载不完整，已删除该图集并停止。")
                        raise RuntimeError(f"文件下载连续失败，已停止：{name}")
                    current_temp = None; saved += 1; owners[target.name] = post["url"]
                    records.append({"date": post["date"], "path": target, "url": post["url"], "title": title_safe, "name": name})
                    self.log.emit(f"✓ {title_safe} / {target.name}")
            if self.rename_order and not self.by_title:
                records.sort(key=lambda item: item["date"])
                for number, record in enumerate(records, self.start_number):
                    path = record["path"]
                    numbered = path.with_name(f"{number}{path.suffix}")
                    if numbered.exists(): numbered = path.with_name(f"{number}_{path.name}")
                    path.rename(numbered)
            self.done.emit(saved)
        except Exception as exc:
            if current_temp:
                try: current_temp.unlink(missing_ok=True)
                except OSError: pass
            self.failed.emit(str(exc))

    @staticmethod
    def _unique(name: str, directory: Path) -> str:
        path = Path(name)
        candidate = path.name; number = 2
        while (directory / candidate).exists():
            candidate = f"{path.stem} ({number}){path.suffix}"; number += 1
        return candidate


class ExportWorker(QThread):
    progress = Signal(int, int)
    done = Signal()
    failed = Signal(str)

    def __init__(self, source: Path, destination: QUrl):
        super().__init__(); self.source = source; self.destination = destination

    def run(self):
        try:
            root = self.destination.toLocalFile() if self.destination.isLocalFile() else self.destination.toString(QUrl.ComponentFormattingOption.FullyEncoded)
            files = [p for p in self.source.rglob("*") if p.is_file() and not p.name.endswith(".part")]
            for index, src in enumerate(files, 1):
                relative = src.relative_to(self.source).as_posix()
                target_dir = str(QDir(root).filePath(str(Path(relative).parent))) if "/" in relative else root
                if "/" in relative and not QDir().mkpath(target_dir):
                    raise RuntimeError(f"无法创建目录：{relative}")
                filename = Path(relative).name
                target = str(QDir(target_dir).filePath(filename))
                stem, suffix = Path(filename).stem, Path(filename).suffix
                number = 2
                while QFileInfo(target).exists():
                    target = str(QDir(target_dir).filePath(f"{stem} ({number}){suffix}")); number += 1
                if not QFile.copy(str(src), target):
                    raise RuntimeError(f"无法保存文件：{relative}")
                self.progress.emit(index, len(files))
            self.done.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class PostSelectionDialog(QDialog):
    def __init__(self, posts, parent=None):
        super().__init__(parent); self.setWindowTitle("选择要下载的图集")
        self.resize(540, 700); self.setMinimumSize(320, 420); self.posts = posts; self.checks = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"扫描到 {len(posts)} 个图集；默认全部选中。"))
        buttons = QHBoxLayout(); all_button = QPushButton("全选"); none_button = QPushButton("全不选")
        buttons.addWidget(all_button); buttons.addWidget(none_button); buttons.addStretch(1); layout.addLayout(buttons)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); body = QWidget(); rows = QVBoxLayout(body)
        for post in posts:
            row = QFrame(); row.setObjectName("postRow"); line = QHBoxLayout(row)
            check = QCheckBox(); check.setChecked(True); self.checks.append(check); line.addWidget(check)
            cover = QLabel(); cover.setFixedSize(76, 76); cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cover_path = post.get("local_image")
            if cover_path and Path(cover_path).exists():
                pix = QPixmap(cover_path)
                if not pix.isNull(): cover.setPixmap(pix.scaled(76, 76, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else: cover.setText("封面暂不可用")
            line.addWidget(cover)
            texts = QVBoxLayout(); title = QLabel(post.get("title") or "post"); title.setWordWrap(True); title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            texts.addWidget(title)
            formats = post.get("formats") or []
            tag = QLabel("可下载：" + ("  ".join(formats) if formats else "图片附件")); tag.setStyleSheet(f"color:{random.choice(PALETTE)};font-weight:600")
            texts.addWidget(tag); line.addLayout(texts, 1); rows.addWidget(row)
        rows.addStretch(1); scroll.setWidget(body); layout.addWidget(scroll, 1)
        all_button.clicked.connect(lambda: [item.setChecked(True) for item in self.checks])
        none_button.clicked.connect(lambda: [item.setChecked(False) for item in self.checks])
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept); box.rejected.connect(self.reject); layout.addWidget(box)

    def selected_urls(self):
        return {post["url"] for post, check in zip(self.posts, self.checks) if check.isChecked()}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Pawchive 下载器"); self.resize(430, 850)
        self.setMinimumSize(320, 520); self.destination = QUrl(); self.worker = None; self.scanner = None; self.exporter = None
        self.cache_root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation) or tempfile.gettempdir())
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.setStyleSheet("""
            QWidget { background:#101722; color:#edf4ff; font-size:15px; }
            QLineEdit,QComboBox,QSpinBox,QPlainTextEdit { background:#182334; border:1px solid #40536d; border-radius:12px; padding:10px; }
            QPushButton { background:#253953; border:1px solid #597493; border-radius:12px; padding:11px; min-height:24px; }
            QPushButton:pressed { background:#2f7894; }
            QPushButton:disabled { color:#8190a2; background:#1a2532; }
            QCheckBox { spacing:10px; padding:5px; }
            QCheckBox::indicator { width:22px; height:22px; border:2px solid #8295ad; border-radius:6px; background:#182334; }
            QCheckBox::indicator:checked { background:#51bfd9; border-color:#51bfd9; }
            QProgressBar { border:1px solid #40536d; border-radius:8px; text-align:center; min-height:18px; background:#182334; }
            QProgressBar::chunk { border-radius:7px; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff647c,stop:.25 #ffad45,stop:.5 #48c988,stop:.75 #38bfd3,stop:1 #ba70ea); }
            QFrame#postRow { background:#172231; border:1px solid #31435a; border-radius:12px; }
        """)
        central = QWidget(); self.setCentralWidget(central); root = QVBoxLayout(central); root.setContentsMargins(18, 18, 18, 18); root.setSpacing(12)
        heading = QLabel("Pawchive 图片下载器"); heading.setStyleSheet("font-size:22px;font-weight:700;color:#a9e7f4"); root.addWidget(heading)
        form = QFormLayout(); form.setSpacing(10)
        self.profile = QLineEdit(); self.profile.setPlaceholderText("https://pawchive.pw/fanbox/user/…"); self.profile.setMinimumHeight(48)
        form.addRow("画师主页", self.profile)
        folder_row = QHBoxLayout(); self.folder_label = QLabel("尚未选择保存位置"); self.folder_label.setWordWrap(True); self.folder_label.setMinimumHeight(40)
        self.browse = QPushButton("选择保存位置"); self.browse.clicked.connect(self.choose_folder); folder_row.addWidget(self.folder_label, 1); folder_row.addWidget(self.browse); form.addRow("保存到", folder_row)
        root.addLayout(form)
        self.order = QComboBox(); self.order.addItems(["从新到旧", "从旧到新"])
        self.by_title = QCheckBox("按图集标题分别存入文件夹"); self.by_title.setChecked(True)
        self.scan_first = QCheckBox("扫描封面和标题后选择图集"); self.scan_first.setChecked(True)
        self.rename = QCheckBox("平铺保存时按日期编号"); self.rename.setChecked(True); self.rename.setVisible(False)
        self.start_number = QSpinBox(); self.start_number.setRange(0, 999999999); self.start_number.setValue(1); self.start_number.setVisible(False)
        self.by_title.toggled.connect(lambda checked: (self.rename.setVisible(not checked), self.start_number.setVisible(not checked)))
        options = QFrame(); options_layout = QVBoxLayout(options); options_layout.setContentsMargins(0, 0, 0, 0)
        order_row = QHBoxLayout(); order_row.addWidget(QLabel("日期顺序")); order_row.addWidget(self.order, 1); options_layout.addLayout(order_row)
        options_layout.addWidget(self.by_title); options_layout.addWidget(self.scan_first); options_layout.addWidget(self.rename)
        number_row = QHBoxLayout(); number_row.addWidget(QLabel("起始编号")); number_row.addWidget(self.start_number); number_row.addStretch(1); options_layout.addLayout(number_row)
        root.addWidget(options)
        self.start = QPushButton("开始下载"); self.start.setStyleSheet("QPushButton{background:#34a8c2;color:#07161b;font-weight:700;border:0;font-size:17px;min-height:34px}"); self.start.clicked.connect(self.begin); root.addWidget(self.start)
        self.status = QLabel("准备就绪"); self.status.setWordWrap(True); root.addWidget(self.status)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0); root.addWidget(self.progress)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setPlaceholderText("下载日志"); root.addWidget(self.log, 1)
        controls = QHBoxLayout(); self.pause = QPushButton("暂停扫描"); self.resume = QPushButton("继续扫描"); self.finish_scan = QPushButton("结束扫描")
        for button in (self.pause, self.resume, self.finish_scan): controls.addWidget(button)
        root.addLayout(controls); self.pause.setEnabled(False); self.resume.setEnabled(False); self.finish_scan.setEnabled(False)
        self.pause.clicked.connect(self.pause_scanning); self.resume.clicked.connect(self.resume_scanning); self.finish_scan.clicked.connect(self.finish_scanning)

    def choose_folder(self):
        start = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        url = QFileDialog.getExistingDirectoryUrl(self, "选择图片保存文件夹", QUrl.fromLocalFile(start))
        if not url.isEmpty():
            self.destination = url
            label = url.fileName() or url.toString()
            self.folder_label.setText(label)

    def begin(self):
        profile = self.profile.text().strip().rstrip("/")
        if not PROFILE_RE.fullmatch(profile):
            QMessageBox.warning(self, "链接无效", "请输入 Pawchive 上完整的画师主页链接。")
            return
        if self.destination.isEmpty():
            QMessageBox.information(self, "选择保存位置", "请先选择图片保存文件夹。")
            return
        self.profile.setEnabled(False); self.browse.setEnabled(False); self.start.setEnabled(False); self.log.clear()
        if self.scan_first.isChecked():
            self.status.setText("正在扫描画师主页和封面…"); self.pause.setEnabled(True); self.finish_scan.setEnabled(True)
            self.scan_cache = Path(tempfile.mkdtemp(prefix="pawchive_scan_", dir=str(self.cache_root)))
            self.scanner = ScanWorker(profile, self.scan_cache); self.scanner.progress.connect(self.scan_progress)
            self.scanner.done.connect(self.scan_done); self.scanner.failed.connect(self.scan_failed); self.scanner.start()
        else:
            self.launch_download(profile, None)

    def scan_progress(self, pages, count):
        if pages: self.status.setText(f"扫描中：{pages} 页 · {count} 个图集")
        else: self.status.setText(f"正在读取图集详情… 已完成 {count} 个")

    def scan_done(self, posts):
        self.pause.setEnabled(False); self.resume.setEnabled(False); self.finish_scan.setEnabled(False)
        if not posts: self.scan_failed("没有扫描到完整图集。"); return
        dialog = PostSelectionDialog(posts, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.set_idle(); return
        selected = dialog.selected_urls()
        if not selected:
            self.scan_failed("没有选择要下载的图集。"); return
        self.launch_download(self.profile.text().strip().rstrip("/"), selected)

    def scan_failed(self, message):
        self.log.appendPlainText(str(message)); self.status.setText("扫描失败或已停止")
        self.set_idle()

    def pause_scanning(self):
        if self.scanner and self.scanner.isRunning():
            self.scanner.paused = True; self.pause.setEnabled(False); self.resume.setEnabled(True); self.status.setText("扫描已暂停")

    def resume_scanning(self):
        if self.scanner and self.scanner.isRunning():
            self.scanner.paused = False; self.pause.setEnabled(True); self.resume.setEnabled(False); self.status.setText("继续扫描中…")

    def finish_scanning(self):
        if self.scanner and self.scanner.isRunning():
            self.scanner.finish_requested = True; self.scanner.paused = False; self.finish_scan.setEnabled(False); self.status.setText("正在完成当前图集…")

    def launch_download(self, profile, selected):
        self.pause.setEnabled(False); self.resume.setEnabled(False); self.finish_scan.setEnabled(False)
        self.status.setText("正在下载附件…"); self.progress.setValue(0)
        self.stage = Path(tempfile.mkdtemp(prefix="pawchive_download_", dir=str(self.cache_root)))
        self.worker = DownloadWorker(self.stage, profile, "newest" if self.order.currentIndex() == 0 else "oldest",
                                     self.by_title.isChecked(), selected,
                                     self.rename.isChecked(), self.start_number.value())
        self.worker.progress.connect(self.download_progress); self.worker.log.connect(self.log.appendPlainText)
        self.worker.done.connect(self.download_done); self.worker.failed.connect(self.download_failed); self.worker.start()

    def download_progress(self, name, received, total):
        if total: self.progress.setValue(min(100, int(received * 100 / total)))
        self.status.setText(f"正在下载 {name} · {received / 1048576:.1f} / {total / 1048576:.1f} MB" if total else f"正在下载 {name} · {received / 1048576:.1f} MB")

    def download_done(self, count):
        self.progress.setValue(100); self.status.setText(f"下载完成 · {count} 个文件，正在保存到手机所选文件夹…")
        self.exporter = ExportWorker(self.stage, self.destination); self.exporter.progress.connect(self.export_progress)
        self.exporter.done.connect(self.export_done); self.exporter.failed.connect(self.export_failed); self.exporter.start()

    def export_progress(self, index, total):
        self.status.setText(f"正在保存到手机：{index}/{total}")

    def export_done(self):
        shutil.rmtree(self.stage, ignore_errors=True)
        if hasattr(self, "scan_cache"): shutil.rmtree(self.scan_cache, ignore_errors=True)
        self.status.setText("下载完成，文件已保存到所选文件夹。")
        self.log.appendPlainText("保存完成。可在手机文件管理器中打开所选文件夹。")
        self.set_idle()

    def export_failed(self, message):
        self.status.setText("保存失败；已下载内容仍保留在应用临时区。")
        self.log.appendPlainText(str(message)); self.set_idle()

    def download_failed(self, message):
        self.log.appendPlainText(str(message)); self.status.setText("下载未完成")
        shutil.rmtree(self.stage, ignore_errors=True)
        if hasattr(self, "scan_cache"): shutil.rmtree(self.scan_cache, ignore_errors=True)
        self.set_idle()

    def set_idle(self):
        self.profile.setEnabled(True); self.browse.setEnabled(True); self.start.setEnabled(True)
        self.pause.setEnabled(False); self.resume.setEnabled(False); self.finish_scan.setEnabled(False)

    def closeEvent(self, event):
        for thread in (self.scanner, self.worker, self.exporter):
            if thread and thread.isRunning():
                thread.requestInterruption(); thread.wait(1500)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("PawchiveDownloader")
    window = MainWindow(); window.show()
    app.exec()
