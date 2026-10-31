from pathlib import Path
from urllib.parse import urlparse, urljoin, unquote, parse_qs
from html import escape
import re
import time
import tempfile
import shutil
import sys, random, math
import requests
from bs4 import BeautifulSoup
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPointF, QRect, QEasingCurve, QPropertyAnimation, Property, QSettings, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QRadialGradient, QFont, QPixmap, QIcon, QLinearGradient, QGradient, QFontMetricsF, QPainterPath, QDesktopServices
from PySide6.QtWidgets import QStyle, QStyleOptionButton
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox, QTextEdit, QFrame,
    QAbstractButton, QCheckBox, QDialog, QDialogButtonBox,
    QScrollArea, QGridLayout, QSpinBox, QSizePolicy, QGraphicsDropShadowEffect)

BASE_URL = 'https://pawchive.pw'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36'
PAGE_SIZE = 50
PROFILE_URL_RE = re.compile(
    r'https://pawchive\.pw/(?:fanbox|patreon|subscribestar|discord|boosty)/user/[^/?#]+/?'
)
INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def absolute_post_url(href):
    """Normalize a post link found in a card to an absolute Pawchive URL."""
    href = (href or '').strip()
    if not href:
        return ''
    parsed = urlparse(urljoin(f'{BASE_URL}/', href))
    if parsed.hostname != 'pawchive.pw' or parsed.scheme not in {'http', 'https'}:
        return ''
    return parsed._replace(scheme='https').geturl()


def safe_path_component(value, fallback='post', limit=180):
    """Make a title or attachment name safe as a single Windows path component."""
    value = str(value or '').replace('\\', '/').rsplit('/', 1)[-1]
    value = INVALID_FILENAME_RE.sub('_', value).strip(' .')
    if not value:
        value = fallback
    stem = value.split('.', 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        value = f'_{value}'
    if len(value) > limit:
        suffix = Path(value).suffix
        value = value[:max(1, limit - len(suffix))].rstrip(' .') + suffix
    return value or fallback


def unique_path(directory, name):
    """Return a non-existing path by adding a numeric suffix before its extension."""
    directory=Path(directory)
    candidate=directory/name
    if not candidate.exists():
        return candidate
    base=Path(name)
    number=2
    while True:
        candidate=directory/f'{base.stem} ({number}){base.suffix}'
        if not candidate.exists():
            return candidate
        number+=1


def valid_download(path, extension, content_type=''):
    """Reject successful HTTP challenge pages and obvious file/signature mismatches."""
    ctype=(content_type or '').lower()
    if 'text/html' in ctype or 'application/json' in ctype:
        return False
    try:
        with open(path,'rb') as f: head=f.read(32)
        if not head: return False
        if head.lstrip().lower().startswith((b'<!doctype html',b'<html',b'<?xml')): return False
    except OSError: return False
    ext=extension.lower()
    checks={
        '.jpg':lambda b:b.startswith(b'\xff\xd8\xff'), '.jpeg':lambda b:b.startswith(b'\xff\xd8\xff'),
        '.png':lambda b:b.startswith(b'\x89PNG\r\n\x1a\n'), '.gif':lambda b:b.startswith((b'GIF87a',b'GIF89a')),
        '.webp':lambda b:b.startswith(b'RIFF') and b[8:12]==b'WEBP', '.zip':lambda b:b.startswith((b'PK\x03\x04',b'PK\x05\x06',b'PK\x07\x08')),
        '.7z':lambda b:b.startswith(b'7z\xbc\xaf\x27\x1c'), '.rar':lambda b:b.startswith((b'Rar!\x1a\x07\x00',b'Rar!\x1a\x07\x01\x00')),
        '.pdf':lambda b:b.startswith(b'%PDF-'), '.psd':lambda b:b.startswith(b'8BPS'),
        '.mp4':lambda b:len(b)>=8 and b[4:8]==b'ftyp', '.m4v':lambda b:len(b)>=8 and b[4:8]==b'ftyp',
        '.mov':lambda b:len(b)>=8 and b[4:8]==b'ftyp', '.webm':lambda b:b.startswith(b'\x1aE\xdf\xa3'),
        '.mkv':lambda b:b.startswith(b'\x1aE\xdf\xa3')
    }
    checker=checks.get(ext)
    return checker(head) if checker else True
TEXT = {
 '简体中文': {'title':'Pawchive 图片下载器','browse':'浏览…','start':'开始下载','ready':'准备就绪','working':'正在获取帖子附件…','done':'下载完成','open_folder':'打开文件夹','empty':'没有找到原图附件。','choose':'选择文件夹','error':'出错了'},
 'English': {'title':'Pawchive Image Downloader','browse':'Browse…','start':'Download images','ready':'Ready','working':'Finding post attachments…','done':'Download complete','open_folder':'Open folder','empty':'No original attachment links were found.','choose':'Choose a folder','error':'Something went wrong'},
 '日本語': {'title':'Pawchive 画像ダウンローダー','browse':'参照…','start':'ダウンロード','ready':'準備完了','working':'添付画像を確認中…','done':'ダウンロード完了','open_folder':'フォルダーを開く','empty':'元画像のリンクが見つかりません。','choose':'フォルダーを選択','error':'エラー'},
 '繁體中文': {'title':'Pawchive 圖片下載器','browse':'瀏覽…','start':'開始下載','ready':'準備就緒','working':'正在取得貼文附件…','done':'下載完成','open_folder':'開啟資料夾','empty':'找不到原圖附件。','choose':'選擇資料夾','error':'發生錯誤'}
}
AUX_TEXT = {
 '简体中文': {'profile_hint':'请输入画师主页链接。','profile_valid':'✓ 画师主页链接有效','folder_needed':'✓ 链接有效；请先选择图片保存文件夹','profile_invalid':'链接格式无效：请输入 pawchive.pw 下的完整画师主页链接。','note_titles':'默认：每个图集分别保存到以标题命名的文件夹中。','note_flat':'已关闭分文件夹；可选择按发布日期排序并为图片编号。','scan_status':'正在扫描画师主页标题…','scan_failed':'扫描失败','empty_scan':'没有扫描到完整图集标题。','close_wait':'正在停止并清理未完成的图集…','cache_cleared':'临时缓存已清理；下载文件未受影响。','cache_failed':'缓存清理失败：{}','log_copied':'日志已复制到剪贴板。','copy_tooltip':'复制日志','cache_tooltip':'清理临时缓存','choose_title':'选择要下载的图集','choose_summary':'扫描到 {count} 个图集。点击封面卡片选择。','select_all':'全选','select_none':'全不选','cover_missing':'封面暂不可用','no_direct':'无直链文件','back_top':'回到顶部','ok':'确定','cancel':'取消','scan_window':'正在寻找图集','scan_searching':'正在沿着画师主页寻找图集…','scan_paused':'扫描已暂停','scan_finishing':'正在完成当前图集…','scan_count':'已扫描 {pages} 页 · 找到 {posts} 个图集','unknown':'未知','cancelled':'用户已停止下载','bad_content':'响应内容与文件类型不匹配（Content-Type: {content_type}）','download_failed':'下载失败（已重试4次）：{title} / {filename} — {error}','album_failed':'下载中止：图集“{title}”的文件连续失败，已停止以避免留下不完整图集。','download_fail_prefix':'下载失败','no_selected':'没有找到所选图集。','pause':'暂停','resume':'继续','finish':'结束扫描','file_progress':'正在下载{count}：{name} · {current:.1f}/{total:.1f} MB','unknown_progress':'正在下载{count}：{name} · 已接收 {current:.1f} MB'},
 '繁體中文': {'profile_hint':'請輸入畫師首頁連結。','profile_valid':'✓ 畫師首頁連結有效','folder_needed':'✓ 連結有效；請先選擇圖片儲存資料夾','profile_invalid':'連結格式無效：請輸入 pawchive.pw 下的完整畫師首頁連結。','note_titles':'預設：每篇圖集分別存入以標題命名的資料夾。','note_flat':'已關閉分資料夾；可選擇按發布日期排序並為圖片編號。','scan_status':'正在掃描畫師首頁標題…','scan_failed':'掃描失敗','empty_scan':'沒有掃描到完整圖集標題。','close_wait':'正在停止並清理未完成的圖集…','cache_cleared':'暫存快取已清理；下載檔案未受影響。','cache_failed':'快取清理失敗：{}','log_copied':'日誌已複製到剪貼簿。','copy_tooltip':'複製日誌','cache_tooltip':'清理暫存快取','choose_title':'選擇要下載的圖集','choose_summary':'掃描到 {count} 個圖集。點擊封面卡片選擇。','select_all':'全選','select_none':'全不選','cover_missing':'封面暫不可用','no_direct':'無直連檔案','back_top':'回到頂端','ok':'確定','cancel':'取消','scan_window':'正在尋找圖集','scan_searching':'正在沿著畫師首頁尋找圖集…','scan_paused':'掃描已暫停','scan_finishing':'正在完成目前圖集…','scan_count':'已掃描 {pages} 頁 · 找到 {posts} 個圖集','unknown':'未知','cancelled':'使用者已停止下載','bad_content':'回應內容與檔案類型不符（Content-Type: {content_type}）','download_failed':'下載失敗（已重試4次）：{title} / {filename} — {error}','album_failed':'下載中止：圖集「{title}」的檔案連續失敗，已停止以避免留下不完整圖集。','download_fail_prefix':'下載失敗','no_selected':'找不到所選圖集。','pause':'暫停','resume':'繼續','finish':'結束掃描','file_progress':'正在下載{count}：{name} · {current:.1f}/{total:.1f} MB','unknown_progress':'正在下載{count}：{name} · 已接收 {current:.1f} MB'},
 'English': {'profile_hint':'Enter a creator profile URL.','profile_valid':'✓ Creator profile URL is valid','folder_needed':'✓ URL is valid; choose a save folder','profile_invalid':'Invalid URL. Enter a complete creator profile link from pawchive.pw.','note_titles':'Default: save each post in a folder named after its title.','note_flat':'Post folders are off; you can number files by publication date.','scan_status':'Scanning creator posts…','scan_failed':'Scan failed','empty_scan':'No complete posts were found.','close_wait':'Stopping and cleaning up the unfinished post…','cache_cleared':'Temporary cache cleared; downloaded files were not changed.','cache_failed':'Could not clear cache: {}','log_copied':'Log copied to the clipboard.','copy_tooltip':'Copy log','cache_tooltip':'Clear temporary cache','choose_title':'Choose posts to download','choose_summary':'Found {count} posts. Click cover cards to select.','select_all':'Select all','select_none':'Select none','cover_missing':'Cover unavailable','no_direct':'No direct-link files','back_top':'Back to top','ok':'OK','cancel':'Cancel','scan_window':'Finding posts','scan_searching':'Searching creator posts…','scan_paused':'Scan paused','scan_finishing':'Finishing the current post…','scan_count':'Scanned {pages} pages · found {posts} posts','unknown':'unknown','cancelled':'Download stopped by the user','bad_content':'The response does not match the file type (Content-Type: {content_type})','download_failed':'Download failed after 4 attempts: {title} / {filename} — {error}','album_failed':'Stopped because a file in post “{title}” failed repeatedly. The incomplete post was removed.','download_fail_prefix':'Download failed','no_selected':'The selected posts could not be found.','pause':'Pause','resume':'Resume','finish':'Finish scan','file_progress':'Downloading{count}: {name} · {current:.1f}/{total:.1f} MB','unknown_progress':'Downloading{count}: {name} · {current:.1f} MB received'},
 '日本語': {'profile_hint':'クリエイターページのURLを入力してください。','profile_valid':'✓ クリエイターページURLは有効です','folder_needed':'✓ URLは有効です。保存先を選択してください','profile_invalid':'URLが無効です。pawchive.pw の完全なクリエイターページURLを入力してください。','note_titles':'既定：投稿ごとにタイトル名のフォルダーへ保存します。','note_flat':'投稿別フォルダーは無効です。公開日順に番号を付けられます。','scan_status':'クリエイターの投稿をスキャン中…','scan_failed':'スキャンに失敗しました','empty_scan':'完全な投稿が見つかりませんでした。','close_wait':'停止して未完了の投稿を削除しています…','cache_cleared':'一時キャッシュを削除しました。ダウンロード済みファイルは変更されていません。','cache_failed':'キャッシュを削除できませんでした：{}','log_copied':'ログをクリップボードにコピーしました。','copy_tooltip':'ログをコピー','cache_tooltip':'一時キャッシュを削除','choose_title':'ダウンロードする投稿を選択','choose_summary':'{count} 件の投稿が見つかりました。カバーをクリックして選択します。','select_all':'すべて選択','select_none':'選択解除','cover_missing':'カバーを表示できません','no_direct':'直接リンクのファイルなし','back_top':'先頭へ戻る','ok':'決定','cancel':'キャンセル','scan_window':'投稿を検索中','scan_searching':'クリエイターの投稿を検索中…','scan_paused':'スキャンを一時停止しました','scan_finishing':'現在の投稿を完了しています…','scan_count':'{pages} ページを確認 · {posts} 件の投稿','unknown':'不明','cancelled':'ユーザーがダウンロードを停止しました','bad_content':'応答内容がファイル形式と一致しません（Content-Type: {content_type}）','download_failed':'4回再試行しましたが失敗しました：{title} / {filename} — {error}','album_failed':'投稿「{title}」のファイルが連続して失敗したため中止しました。未完了の投稿を削除しました。','download_fail_prefix':'ダウンロード失敗','no_selected':'選択した投稿が見つかりません。','pause':'一時停止','resume':'再開','finish':'スキャン終了','file_progress':'ダウンロード中{count}：{name} · {current:.1f}/{total:.1f} MB','unknown_progress':'ダウンロード中{count}：{name} · {current:.1f} MB 受信済み'}
}

class Worker(QThread):
    progress = Signal(str, int, int)
    finished_ok = Signal(int)
    failed = Signal(str)
    def __init__(self, folder, profile, order, by_title, selected_post_urls=None, rename_order=False, start_number=1, lang='简体中文'):
        super().__init__()
        self.folder = Path(folder)
        self.profile = profile.rstrip('/')
        self.order = order
        self.by_title = by_title
        self.selected_post_urls = set(selected_post_urls or [])
        self.rename_order = rename_order
        self.start_number = start_number
        self.text = AUX_TEXT[lang]
        self.current_album = None
        self.created_album = False
    def wait_interruptibly(self,seconds):
        deadline=time.monotonic()+seconds
        while not self.isInterruptionRequested():
            remaining=deadline-time.monotonic()
            if remaining<=0: return
            time.sleep(min(.1,remaining))
        raise RuntimeError(self.text['cancelled'])
    def run(self):
        current_temp=None
        session=None
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            s=session=requests.Session(); s.headers['User-Agent']=USER_AGENT
            posts=[]; offset=0; visited=set()
            while True:
                if self.isInterruptionRequested(): raise RuntimeError(self.text['cancelled'])
                page=f'{self.profile}?o={offset}' if offset else self.profile
                r=s.get(page,timeout=30); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
                cards=soup.select('article.post-card')
                if not cards: break
                page_post_count=len(posts)
                for card in cards:
                    a=card.select_one('a[href*="/post/"]'); post_time=card.select_one('time.timestamp[datetime]')
                    if not a or not post_time: continue
                    post_url=absolute_post_url(a.get('href'))
                    if not post_url: continue
                    if post_url in visited: continue
                    visited.add(post_url); posts.append((post_time.get('datetime',''),post_url,card.select_one('.post-card__header').get_text(' ',strip=True) if card.select_one('.post-card__header') else 'post'))
                if len(cards)<PAGE_SIZE or len(posts)==page_post_count: break
                offset+=PAGE_SIZE
            if not posts: raise RuntimeError('EMPTY')
            if self.selected_post_urls: posts=[p for p in posts if p[1] in self.selected_post_urls]
            if not posts: raise RuntimeError('NO_SELECTED_POSTS')
            posts.sort(key=lambda x:x[0],reverse=self.order=='newest')
            saved=0; total=len(posts); downloaded=[]; owners={}; duplicate_names=set()
            for post_index,(dt,post_url,title) in enumerate(posts,1):
                if self.isInterruptionRequested(): raise RuntimeError(self.text['cancelled'])
                r=s.get(post_url,timeout=30); r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
                title_el=soup.select_one('h1.post__title span')
                if title_el: title=title_el.get_text(' ',strip=True)
                safe=safe_path_component(title, limit=100)
                dest=self.folder/safe if self.by_title else self.folder
                self.created_album=self.by_title and not dest.exists(); self.current_album=dest if self.by_title else None
                dest.mkdir(parents=True,exist_ok=True)
                links=[]; link_urls=set()
                for a in soup.select('.post__files a.fileThumb[href], a.post__attachment-link[href]'):
                    u=a.get('href','').strip()
                    direct='post__attachment-link' in (a.get('class') or [])
                    if u.startswith(('https://file.pawchive.pw/','https://n2.pawchive.pw/')) and u not in link_urls:
                        name=a.get('download','').strip()
                        if not name:
                            name=(parse_qs(urlparse(u).query).get('f') or [''])[0]
                        if not name:
                            name=re.sub(r'^Download\s+','',a.get_text(' ',strip=True),flags=re.I)
                        link_urls.add(u); links.append((u,name,direct))
                for j,(url,name,direct) in enumerate(links,1):
                    name=safe_path_component(unquote(name or Path(urlparse(url).path).name), fallback=f'image_{j}.bin')
                    target=dest/name
                    if not self.by_title and name in duplicate_names:
                        target=unique_path(dest,safe_path_component(f'({safe}) - {name}',fallback=name,limit=240))
                    elif target.exists():
                        previous_album=owners.get(name)
                        if direct and not self.by_title and previous_album is not None and previous_album!=post_url:
                            duplicate_names.add(name)
                            for record_index,(saved_date,previous_path,album_url,album_title,original_name) in enumerate(downloaded):
                                if original_name!=name: continue
                                prefixed=safe_path_component(f'({album_title}) - {previous_path.name}',fallback=previous_path.name,limit=240)
                                renamed_path=unique_path(dest,prefixed)
                                previous_path.rename(renamed_path)
                                owners.pop(previous_path.name,None); owners[renamed_path.name]=album_url
                                downloaded[record_index]=(saved_date,renamed_path,album_url,album_title,original_name)
                            target=unique_path(dest,safe_path_component(f'({safe}) - {name}',fallback=name,limit=240))
                        elif direct and not self.by_title and previous_album is None:
                            target=unique_path(dest,safe_path_component(f'({safe}) - {name}',fallback=name,limit=240))
                        else:
                            target=unique_path(dest,name)
                    temp=target.with_name(target.name+'.part'); current_temp=temp
                    ext=Path(urlparse(url).path).suffix.lower()
                    # Large/non-image direct attachments are more likely to be rate limited.
                    # Keep them serial and add a modest randomized cooldown between attempts.
                    direct_file=ext in {'.zip','.rar','.7z','.tar','.gz','.psd','.clip','.mp4','.mov','.webm','.mkv','.pdf'}
                    if direct_file and saved:
                        self.wait_interruptibly(random.uniform(1.8,3.8))
                    last_error=None; content_type=''
                    for attempt in range(1,5):
                        try:
                            if direct_file and attempt>1: self.wait_interruptibly(min(18,3*(2**(attempt-2))+random.uniform(.5,2.5)))
                            headers={'Referer':post_url,'Accept':'*/*'}
                            with s.get(url,stream=True,timeout=(20,45),headers=headers) as image:
                                image.raise_for_status()
                                content_type=image.headers.get('content-type','')
                                size=int(image.headers.get('content-length') or 0); received=0
                                self.progress.emit(f'({post_index}/{total}) {safe} / {target.name}',0,size)
                                last_progress=0.0
                                with temp.open('wb') as f:
                                    for chunk in image.iter_content(131072):
                                        if self.isInterruptionRequested(): raise RuntimeError(self.text['cancelled'])
                                        if chunk:
                                            f.write(chunk); received+=len(chunk)
                                            now=time.monotonic()
                                            if now-last_progress>=.08:
                                                self.progress.emit(f'({post_index}/{total}) {safe} / {target.name}',received,size)
                                                last_progress=now
                                self.progress.emit(f'({post_index}/{total}) {safe} / {target.name}',received,size)
                            if not valid_download(temp,Path(target.name).suffix,content_type):
                                raise ValueError(self.text['bad_content'].format(content_type=content_type or self.text['unknown']))
                            temp.replace(target); last_error=None; break
                        except (requests.RequestException, OSError, ValueError) as exc:
                            last_error=exc
                            try: temp.unlink(missing_ok=True)
                            except OSError: pass
                            if attempt<4: self.wait_interruptibly(1.5*attempt)
                    if last_error is not None:
                        self.progress.emit(self.text['download_failed'].format(title=safe,filename=target.name,error=last_error),len(visited),total)
                        raise RuntimeError(self.text['album_failed'].format(title=safe))
                    saved+=1; downloaded.append((dt,target,post_url,safe,name)); owners[target.name]=post_url; current_temp=None; self.progress.emit(f'✓  ({post_index}/{total}) {safe} / {target.name}',1,1)
                self.current_album=None; self.created_album=False
            if self.rename_order:
                for index,(_,path,_,_,_) in enumerate(sorted(downloaded,key=lambda item:item[0]),self.start_number):
                    extension=''.join(path.suffixes)
                    renamed=path.with_name(f'{index}{extension}')
                    bump=1
                    while renamed.exists() and renamed!=path:
                        renamed=path.with_name(f'{index}_{bump}{extension}'); bump+=1
                    if renamed!=path: path.rename(renamed)
            self.finished_ok.emit(saved)
        except Exception as e:
            if current_temp:
                try: current_temp.unlink(missing_ok=True)
                except OSError: pass
            if self.current_album and self.created_album:
                shutil.rmtree(self.current_album,ignore_errors=True)
            self.failed.emit(str(e))
        finally:
            if session is not None:
                session.close()

class Particle:
    def __init__(self,x,y,click=False):
        a=random.random()*math.tau; speed=random.uniform(1.1,3.5) if click else random.uniform(.3,1.4)
        self.x=x; self.y=y; self.vx=math.cos(a)*speed; self.vy=math.sin(a)*speed; self.life=random.randint(18,34); self.max=self.life; self.size=random.uniform(2,5) if click else random.uniform(1.5,3.5); self.click=click; self.hue=random.choice([24,32,48,350]) if click else random.choice([184,195,210,270])
    def move(self): self.x+=self.vx; self.y+=self.vy; self.vy+=.025; self.life-=1

class GlowButton(QPushButton):
    def __init__(self,*a):
        super().__init__(*a); self.hover=0.; self.hover_animation=QPropertyAnimation(self,b'hoverLevel',self); self.hover_animation.setDuration(240); self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic); self.setMouseTracking(True)
    def getHover(self): return self.hover
    def setHover(self,value): self.hover=float(value); self.update()
    hoverLevel=Property(float,getHover,setHover)
    def animate_hover(self,target):
        self.hover_animation.stop(); self.hover_animation.setStartValue(self.hover); self.hover_animation.setEndValue(target); self.hover_animation.start()
    def enterEvent(self,e): self.animate_hover(1.0); super().enterEvent(e)
    def leaveEvent(self,e): self.animate_hover(0.0); super().leaveEvent(e)
    def paintEvent(self,e):
        super().paintEvent(e)
        if self.hover<=0:return
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha=int(45+210*self.hover); width=1.8+2.6*self.hover
        glow=QColor(255,72,82,alpha) if not self.isEnabled() else QColor(73,214,255,alpha)
        p.setPen(QPen(glow,width)); p.setBrush(Qt.BrushStyle.NoBrush)
        rect=self.rect().adjusted(3,3,-3,-3); p.drawRoundedRect(rect,13,13)
        p.setPen(QPen(QColor(121,232,255,int(alpha*.35)),1.0)); p.drawRoundedRect(rect.adjusted(2,2,-2,-2),11,11); p.end()

class ParticleOverlay(QWidget):
    """Transparent, mouse-through layer kept above all UI controls."""
    def __init__(self, parent):
        super().__init__(parent)
        self.host=parent; self.sparks=[]; self.rings=[]; self._last_tick=time.monotonic()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.sync()
        self.raise_()
    def sync(self):
        self.setGeometry(self.host.rect())
    @property
    def has_effects(self):
        return bool(self.sparks or self.rings)
    def launch_firework(self,point):
        palette=('#ff5b72','#ffb347','#ffe45c','#5bdb91','#45c8e8','#7187ff','#cc72ee')
        x,y=point.x(),point.y()
        for i in range(26):
            angle=math.tau*i/26+random.uniform(-.09,.09); speed=random.uniform(48,108)
            self.sparks.append({'x':x,'y':y,'px':x,'py':y,'vx':math.cos(angle)*speed,'vy':math.sin(angle)*speed,'age':0.0,'life':random.uniform(.68,.92),'color':QColor(random.choice(palette))})
        if len(self.sparks)>104: self.sparks=self.sparks[-104:]
        self.rings.append({'x':x,'y':y,'age':0.0,'life':.4,'color':QColor('#fff0a8')})
        if len(self.rings)>12: self.rings=self.rings[-12:]
        self._last_tick=time.monotonic(); self.sync(); self.raise_(); self.update()
        if not self.host.fx.isActive(): self.host.fx.start(16)
    def advance(self):
        now=time.monotonic(); dt=max(.001,min(.05,now-self._last_tick)); self._last_tick=now
        for spark in self.sparks:
            spark['px']=spark['x']; spark['py']=spark['y']
            spark['x']+=spark['vx']*dt; spark['y']+=spark['vy']*dt
            spark['vy']+=125*dt; spark['vx']*=max(0.0,1-0.38*dt); spark['age']+=dt
        self.sparks=[spark for spark in self.sparks if spark['age']<spark['life']]
        for ring in self.rings: ring['age']+=dt
        self.rings=[ring for ring in self.rings if ring['age']<ring['life']]
    def paintEvent(self,e):
        p=QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            for dot in self.host.particles:
                alpha=max(0,int(220*dot.life/dot.max)); c=QColor.fromHsv(dot.hue,220 if dot.click else 150,255,alpha)
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(c); p.drawEllipse(QPointF(dot.x,dot.y),dot.size,dot.size)
            for ring in self.rings:
                progress=min(1.0,ring['age']/ring['life']); fade=1-progress*progress*(3-2*progress)
                color=QColor(ring['color']); color.setAlphaF(.72*fade)
                p.setPen(QPen(color,max(.2,1.8*fade))); p.setBrush(Qt.BrushStyle.NoBrush)
                radius=4+27*progress; p.drawEllipse(QPointF(ring['x'],ring['y']),radius,radius)
            for spark in self.sparks:
                progress=min(1.0,spark['age']/spark['life']); fade=1-progress*progress*(3-2*progress)
                color=QColor(spark['color']); glow=QColor(color); glow.setAlphaF(.2*fade)
                p.setPen(QPen(glow,max(.3,3.4*fade))); p.drawLine(QPointF(spark['px'],spark['py']),QPointF(spark['x'],spark['y']))
                color.setAlphaF(.95*fade); p.setPen(QPen(color,max(.2,1.25*fade))); p.drawLine(QPointF(spark['px'],spark['py']),QPointF(spark['x'],spark['y']))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(color); p.drawEllipse(QPointF(spark['x'],spark['y']),1.9*fade,1.9*fade)
        finally:
            p.end()

class ThemeSwitch(QAbstractButton):
    def __init__(self, callback):
        # Keep the original visible switch dimensions; expanded hit area is handled by App.eventFilter.
        super().__init__(); self.setFixedSize(76,36); self.setCursor(Qt.CursorShape.PointingHandCursor); self.dark=True; self.offset=4.0; self.callback=callback
        self.animation=QPropertyAnimation(self,b'offsetProp',self); self.animation.setDuration(420); self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic); self.pressed.connect(self.toggle)
    def getOffset(self): return self.offset
    def setOffset(self,v): self.offset=float(v); self.update()
    offsetProp=Property(float,getOffset,setOffset)
    def toggle(self):
        self.dark=not self.dark; self.callback(self.dark); self.animation.stop(); self.animation.setStartValue(self.offset); self.animation.setEndValue(4.0 if self.dark else 44.0); self.animation.start()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#18315c' if self.dark else '#f2c94c')); p.drawRoundedRect(self.rect(),18,18)
        x=self.offset; p.setBrush(QColor('#263f70' if self.dark else '#ffdc70')); p.drawEllipse(int(x),4,28,28)
        p.setPen(QColor('#e8f1ff' if self.dark else '#fff7d1')); p.setFont(QFont('Segoe UI Symbol',18))
        p.drawText(int(x),4,28,28,Qt.AlignmentFlag.AlignCenter,'☾' if self.dark else '☀')
        p.end()

class GlowCheckBox(QCheckBox):
    def __init__(self,*args):
        super().__init__(*args); self.setAttribute(Qt.WidgetAttribute.WA_Hover,True); self._glow=0.0
        self.glow_anim=QPropertyAnimation(self,b'glowLevel',self); self.glow_anim.setDuration(420); self.glow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._ripple=0.0; self.ripple_anim=QPropertyAnimation(self,b'rippleLevel',self); self.ripple_anim.setDuration(620); self.ripple_anim.setStartValue(0.0); self.ripple_anim.setEndValue(1.0); self.ripple_anim.setEasingCurve(QEasingCurve.Type.OutCubic); self.ripple_anim.finished.connect(self.finish_ripple); self.stateChanged.connect(self.checked_ripple)
    def getGlow(self): return self._glow
    def setGlow(self,value): self._glow=float(value); self.update()
    glowLevel=Property(float,getGlow,setGlow)
    def getRipple(self): return self._ripple
    def setRipple(self,value): self._ripple=float(value); self.update()
    rippleLevel=Property(float,getRipple,setRipple)
    def checked_ripple(self,state):
        if state:
            self.ripple_anim.stop(); self._ripple=0.0; self.ripple_anim.start()
    def finish_ripple(self):
        self._ripple=0.0
        self.update()
    def enterEvent(self,event):
        self.glow_anim.stop(); self.glow_anim.setStartValue(self._glow); self.glow_anim.setEndValue(1.0); self.glow_anim.start(); super().enterEvent(event)
    def leaveEvent(self,event):
        self.glow_anim.stop(); self.glow_anim.setStartValue(self._glow); self.glow_anim.setEndValue(0.0); self.glow_anim.start(); super().leaveEvent(event)
    def paintEvent(self,event):
        super().paintEvent(event)
        opt=QStyleOptionButton(); opt.initFrom(self); indicator=self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator,opt,self)
        center=indicator.center()
        if self._glow>0:
            painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            try:
                radius=max(indicator.width(),indicator.height())*.95
                grad=QRadialGradient(QPointF(center),radius); grad.setColorAt(0,QColor(75,210,245,int(62*self._glow))); grad.setColorAt(.55,QColor(75,210,245,int(25*self._glow))); grad.setColorAt(1,QColor(75,210,245,0))
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
                painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(grad); painter.drawEllipse(QPointF(center),radius,radius)
            finally:
                painter.end()
        if self._ripple>0:
            painter=QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            try:
                max_radius=max(indicator.width(),indicator.height())*1.45; ripple_radius=max_radius*self._ripple
                fade=(1-self._ripple)**2*(1+2*self._ripple); alpha=int(135*fade)
                edge=QRadialGradient(QPointF(center),max(1,ripple_radius))
                edge.setColorAt(0,QColor(255,255,255,0)); edge.setColorAt(.65,QColor(120,230,255,int(alpha*.08))); edge.setColorAt(.84,QColor(145,238,255,alpha)); edge.setColorAt(1,QColor(100,210,245,0))
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
                painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(edge); painter.drawEllipse(QPointF(center),ripple_radius,ripple_radius)
            finally:
                painter.end()

class SoftComboBox(QComboBox):
    def __init__(self,*args):
        super().__init__(*args); self.popup_animation=None
    def showPopup(self):
        if self.view().window().isVisible(): return
        super().showPopup(); popup=self.view().window()
        if popup and popup.isVisible():
            final=popup.geometry(); start=QRect(final.x(),final.y()-12,final.width(),final.height()); popup.setGeometry(start)
            self.popup_animation=QPropertyAnimation(popup,b'geometry',self); self.popup_animation.setDuration(260); self.popup_animation.setStartValue(start); self.popup_animation.setEndValue(final); self.popup_animation.setEasingCurve(QEasingCurve.Type.OutCubic); self.popup_animation.start()

class RainbowProgress(QWidget):
    def __init__(self): super().__init__(); self.value=0; self.indeterminate=False; self.phase=0; self.setFixedHeight(24)
    def setValue(self,v): self.value=max(0,min(100,v)); self.indeterminate=False; self.update()
    def setIndeterminate(self): self.indeterminate=True; self.phase=(self.phase+17)%100; self.update()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); r=self.rect().adjusted(1,5,-1,-5)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#202735')); p.drawRoundedRect(r,7,7)
        if self.indeterminate:
            colors=getattr(self,'colors',[QColor('#ff5c74'),QColor('#ffb547'),QColor('#ffe45c'),QColor('#58d68d'),QColor('#45c8e8'),QColor('#6686ff'),QColor('#bd70ef')])
            span=max(36,r.width()*.22); travel=max(1,r.width()-span-8); start=r.left()+4+travel*self.phase/100
            grad=QLinearGradient(start,0,start+span,0)
            for i,c in enumerate(colors): grad.setColorAt(i/(len(colors)-1),c)
            p.setBrush(grad); p.drawRoundedRect(start,r.top()+2,span,r.height()-4,6,6)
        elif self.value:
            span=(r.width()-8)*self.value/100; colors=getattr(self,'colors',[QColor('#ff5c74'),QColor('#ffb547'),QColor('#ffe45c'),QColor('#58d68d'),QColor('#45c8e8'),QColor('#6686ff'),QColor('#bd70ef')])
            grad=QLinearGradient(r.left()+4,0,r.left()+4+max(1,span),0)
            for i,c in enumerate(colors): grad.setColorAt(i/(len(colors)-1),c)
            p.setBrush(grad); p.drawRoundedRect(r.left()+4,r.top()+2,max(0,span),r.height()-4,6,6)
            # A spaced helical ribbon motif, with the number of loops growing with progress.
            p.setPen(QPen(QColor(255,255,255,105),1.1)); loops=max(1,int(self.value/18))
            for i in range(loops):
                x=r.left()+10+i*max(12,(span-12)/max(1,loops))
                if x<r.left()+span: p.drawArc(int(x-4),r.top()+3,8,r.height()-6,0,2880)
        p.end()


class RainbowCredit(QLabel):
    """Animated creator credit with a capped hover flow and click fireworks."""
    fireworkRequested=Signal(QPointF)
    def __init__(self, text):
        super().__init__(text)
        self.phase=0.0; self.flow_speed=1.5; self.hovered=False
        self.bounce_index=None; self.bounce_started=0.0
        self._last_tick=time.monotonic()
        self.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet('background:transparent;font-size:13px;')
        self.setMouseTracking(True)
        self.animation_timer=QTimer(self); self.animation_timer.setInterval(24); self.animation_timer.timeout.connect(self.advance_animation); self.animation_timer.start()

    def enterEvent(self,event):
        super().enterEvent(event)

    def leaveEvent(self,event):
        self.hovered=False
        super().leaveEvent(event)

    def mouseMoveEvent(self,event):
        self.hovered=self.character_at(event.position().x(),event.position().y()) is not None
        super().mouseMoveEvent(event)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            point=event.position()
            index=self.character_at(point.x(),point.y())
            if index is not None:
                self.hovered=True
                self.bounce_index=index; self.bounce_started=time.monotonic()
                self.launch_firework(point)
        super().mousePressEvent(event)

    def text_geometry(self):
        text_rect=self.contentsRect().adjusted(0,0,-2,0)
        metrics=QFontMetricsF(self.font()); text=self.text(); width=metrics.horizontalAdvance(text)
        if self.alignment() & Qt.AlignmentFlag.AlignRight:
            x=text_rect.right()-width
        elif self.alignment() & Qt.AlignmentFlag.AlignHCenter:
            x=text_rect.left()+(text_rect.width()-width)/2
        else:
            x=text_rect.left()
        baseline=text_rect.top()+(text_rect.height()-metrics.height())/2+metrics.ascent()
        return text_rect,metrics,x,baseline

    def character_at(self,mouse_x,mouse_y=None):
        _,metrics,x,baseline=self.text_geometry(); text=self.text(); candidates=[]
        if mouse_y is not None and not baseline-metrics.ascent()-3<=mouse_y<=baseline+metrics.descent()+3: return None
        for index,char in enumerate(text):
            if char.isspace(): continue
            left=x+metrics.horizontalAdvance(text[:index]); right=x+metrics.horizontalAdvance(text[:index+1])
            candidates.append((max(left-mouse_x,0,mouse_x-right),index,left,right))
        if not candidates: return None
        distance,index,left,right=min(candidates,key=lambda item:item[0])
        return index if left-3<=mouse_x<=right+3 else None

    def launch_firework(self,point):
        host_point=self.mapTo(self.window(),point.toPoint())
        self.fireworkRequested.emit(QPointF(host_point))

    def advance_animation(self):
        now=time.monotonic(); dt=max(.001,min(.06,now-self._last_tick)); self._last_tick=now
        target_speed=4.6 if self.hovered else 1.5
        blend=min(1.0,dt/.32); self.flow_speed+=(target_speed-self.flow_speed)*blend
        self.phase=(self.phase+self.flow_speed*dt*50)%100
        if self.bounce_index is not None and now-self.bounce_started>.68: self.bounce_index=None
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            text_rect,metrics,x,baseline=self.text_geometry(); font=self.font(); text=self.text()
            gradient=QLinearGradient(text_rect.left()-self.phase,0,text_rect.left()+100-self.phase,0)
            gradient.setSpread(QGradient.Spread.RepeatSpread)
            for position,color in ((0,'#ff5470'),(.17,'#ffad45'),(.34,'#ffe45a'),(.51,'#55d990'),(.68,'#42c7e8'),(.85,'#6a82ff'),(1,'#ff5470')):
                gradient.setColorAt(position,QColor(color))
            path=QPainterPath()
            if self.bounce_index is None:
                path.addText(x,baseline,font,text)
            else:
                bounce_progress=min(1.0,max(0.0,(time.monotonic()-self.bounce_started)/.68))
                offset=-13*math.exp(-4.2*bounce_progress)*math.sin(math.tau*1.55*bounce_progress)
                for index,char in enumerate(text):
                    char_x=x+metrics.horizontalAdvance(text[:index])
                    path.addText(char_x,baseline+offset if index==self.bounce_index else baseline,font,char)
            painter.fillPath(path,QBrush(gradient))
        finally:
            painter.end()

class ScanAnimation(QDialog):
    """A small animated orbit shown while profile pages and covers are scanned."""
    def __init__(self,parent):
        super().__init__(parent); self.setFixedSize(390,250); self.setModal(False); self._allow_close=False
        self.phase=0; self.pages=0; self.posts=0; self.paused=False; self.finish_requested=False; self.lang='简体中文'; self.scanner=None
        layout=QVBoxLayout(self); layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.art=QLabel(); self.art.setFixedSize(220,120); self.art.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.art,0,Qt.AlignmentFlag.AlignCenter)
        self.message=QLabel(); self.message.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(self.message)
        self.counter=QLabel(); self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter); self.counter.setStyleSheet('color:#91a7be'); layout.addWidget(self.counter)
        actions=QHBoxLayout(); self.pause_button=QPushButton(); self.resume_button=QPushButton(); self.finish_button=QPushButton(); actions.addWidget(self.pause_button); actions.addWidget(self.resume_button); actions.addWidget(self.finish_button); layout.addLayout(actions)
        self.pause_button.clicked.connect(self.pause_scan); self.resume_button.clicked.connect(self.resume_scan); self.finish_button.clicked.connect(self.finish_scan); self.resume_button.setEnabled(False)
        self.timer=QTimer(self); self.timer.timeout.connect(self.animate); self.timer.start(35); self.animate()
    def pause_scan(self):
        self.paused=True
        if self.scanner: self.scanner.paused=True
        self.pause_button.setEnabled(False); self.resume_button.setEnabled(True); self.message.setText(AUX_TEXT[self.lang]['scan_paused'])
    def resume_scan(self):
        self.paused=False
        if self.scanner: self.scanner.paused=False
        self.pause_button.setEnabled(True); self.resume_button.setEnabled(False); self.message.setText(AUX_TEXT[self.lang]['scan_searching'])
    def finish_scan(self):
        self.finish_requested=True; self.paused=False
        if self.scanner: self.scanner.finish_requested=True; self.scanner.paused=False
        self.pause_button.setEnabled(False); self.resume_button.setEnabled(False); self.finish_button.setEnabled(False)
        self.message.setText(AUX_TEXT[self.lang]['scan_finishing'])
    def set_language(self,lang):
        self.lang=lang; t=AUX_TEXT[lang]
        self.setWindowTitle(t['scan_window']); self.pause_button.setText(t['pause']); self.resume_button.setText(t['resume']); self.finish_button.setText(t['finish'])
        message=t['scan_finishing'] if self.finish_requested else t['scan_paused'] if self.paused else t['scan_searching']
        self.message.setText(message); self.update_counts(self.pages,self.posts)
    def update_counts(self,pages,posts):
        self.pages=pages; self.posts=posts; self.counter.setText(AUX_TEXT[self.lang]['scan_count'].format(pages=pages,posts=posts))
    def animate(self):
        self.phase=(self.phase+5)%360; pix=QPixmap(220,120); pix.fill(Qt.GlobalColor.transparent); painter=QPainter(pix); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(95,135,175,90),2)); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawEllipse(54,9,112,102)
        palette=['#ff647c','#ffae52','#f3db59','#53d695','#43c8df','#668bff','#bf70eb']
        for i,color in enumerate(palette):
            angle=math.radians(self.phase+i*360/len(palette)); x=110+53*math.cos(angle); y=60+47*math.sin(angle); radius=5 if i%2 else 7
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(color)); painter.drawEllipse(QPointF(x,y),radius,radius)
        painter.setPen(QColor('#eaf3ff')); painter.setFont(QFont('Segoe UI Symbol',23)); painter.drawText(80,44,60,42,Qt.AlignmentFlag.AlignCenter,'✦'); painter.end(); self.art.setPixmap(pix)
    def closeEvent(self,event):
        if self.scanner and self.scanner.isRunning() and not self._allow_close:
            self.finish_scan()
            self.hide()
            event.ignore()
            return
        self.timer.stop()
        super().closeEvent(event)
    def hideEvent(self,event):
        self.timer.stop()
        super().hideEvent(event)

class ProfileScanWorker(QThread):
    counts=Signal(int,int); result=Signal(object); failed=Signal(str)
    def __init__(self,profile,cache_dir):
        super().__init__(); self.profile=profile.rstrip('/'); self.cache_dir=Path(cache_dir); self.paused=False; self.finish_requested=False
    def run(self):
        session=requests.Session()
        session.headers['User-Agent']=USER_AGENT
        try:
            titles=[]; offset=0; seen=set()
            while True:
                while self.paused and not self.finish_requested and not self.isInterruptionRequested(): time.sleep(.08)
                if self.finish_requested or self.isInterruptionRequested(): break
                url=f'{self.profile}?o={offset}' if offset else self.profile
                response=session.get(url,timeout=20); response.raise_for_status(); soup=BeautifulSoup(response.text,'html.parser'); cards=soup.select('article.post-card')
                if self.isInterruptionRequested(): break
                if not cards: break
                page_post_count=len(titles)
                self.counts.emit(offset//PAGE_SIZE+1,len(titles))
                for card in cards:
                    while self.paused and not self.finish_requested and not self.isInterruptionRequested(): time.sleep(.08)
                    if self.finish_requested or self.isInterruptionRequested(): break
                    link=card.select_one('a[href*="/post/"]'); title=card.select_one('.post-card__header'); img=card.select_one('img.post-card__image')
                    if not link or not title: continue
                    post_url=absolute_post_url(link.get('href'))
                    if not post_url: continue
                    if post_url in seen: continue
                    image_path=None
                    if img:
                        src=img.get('data-src') or img.get('src')
                        if src:
                            try:
                                ir=session.get(src,timeout=8); ir.raise_for_status(); suffix=Path(unquote(urlparse(src).path)).suffix.lower(); suffix=suffix if re.fullmatch(r'\.[a-z0-9]{1,8}',suffix) else '.img'; image_path=self.cache_dir/f'{len(titles):06}{suffix}'; image_path.write_bytes(ir.content)
                            except requests.RequestException: pass
                    if self.isInterruptionRequested(): break
                    formats=[]
                    try:
                        detail=session.get(post_url,timeout=12); detail.raise_for_status(); ds=BeautifulSoup(detail.text,'html.parser')
                        for attachment in ds.select('a.post__attachment-link[href]'):
                            ext=Path(urlparse(attachment['href']).path).suffix.lower()
                            if ext and ext not in formats: formats.append(ext)
                    except requests.RequestException: pass
                    if self.isInterruptionRequested(): break
                    seen.add(post_url); titles.append({'title':title.get_text(' ',strip=True),'url':post_url,'image':str(image_path) if image_path else None,'formats':formats}); self.counts.emit(offset//PAGE_SIZE+1,len(titles))
                    if self.finish_requested: break
                if self.finish_requested or len(cards)<PAGE_SIZE or len(titles)==page_post_count: break
                offset+=PAGE_SIZE
            self.result.emit(titles)
        except Exception as exc: self.failed.emit(str(exc))
        finally:
            session.close()

class App(QWidget):
    def __init__(self):
        super().__init__(); self.setObjectName('appRoot'); self.lang='简体中文'; self.particles=[]; self.setMouseTracking(True); self.setMinimumSize(900,820); self.resize(1180,941); self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        icon_path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'1.ico'; self.setWindowIcon(QIcon(str(icon_path))) if icon_path.exists() else None; self.cache_dir=Path(tempfile.mkdtemp(prefix='pawchive_cache_')); self.busy=False; self._close_when_worker_stops=False; self.settings=QSettings('PawchiveTools','PawchiveDownloader')
        root=QVBoxLayout(self); root.setContentsMargins(56,30,56,30); root.setSpacing(18)
        top=QHBoxLayout(); self.heading=QLabel(); self.heading.setStyleSheet('font-size:23px;font-weight:700'); top.addWidget(self.heading,1); self.theme=ThemeSwitch(self.apply_theme); top.addWidget(self.theme); self.clear_cache=QPushButton('🧹'); self.clear_cache.setToolTip('清理临时缓存'); self.clear_cache.setFixedSize(42,42); self.clear_cache.setCursor(Qt.CursorShape.PointingHandCursor); self.clear_cache.setStyleSheet('QPushButton{background:transparent;border:1px solid #60758e;border-radius:21px;font-size:20px} QPushButton:hover{background:#263c53;border-color:#74d7eb} QPushButton:disabled{color:#68717d;border-color:#414b58}'); self.clear_cache.clicked.connect(self.clear_cache_files); top.addWidget(self.clear_cache); self.language=SoftComboBox(); self.language.addItems(TEXT); self.language.currentTextChanged.connect(self.set_lang); top.addWidget(self.language); root.addLayout(top)
        self.main_card=QFrame(); self.main_card.setObjectName('mainCard'); self.main_card.setMaximumWidth(950)
        self.card_shadow=QGraphicsDropShadowEffect(self.main_card); self.card_shadow.setBlurRadius(28); self.card_shadow.setOffset(0,7); self.main_card.setGraphicsEffect(self.card_shadow)
        box=QVBoxLayout(self.main_card); box.setContentsMargins(30,24,30,26); box.setSpacing(16)
        self.card_accent=QFrame(); self.card_accent.setObjectName('cardAccent'); self.card_accent.setFixedHeight(3); box.addWidget(self.card_accent)
        self.profile_label=QLabel('请输入完整的 pawchive.pw 画师主页链接'); self.profile_label.setObjectName('sectionLabel'); self.profile_label.setWordWrap(True); box.addWidget(self.profile_label); self.profile=QLineEdit(); self.profile.setMinimumHeight(66); self.profile.setStyleSheet('QLineEdit{background:rgba(25,31,43,150);border:1px solid #65748a;border-radius:12px;padding:14px 18px} QLineEdit:focus{border:2px solid #58c8e8}'); box.addWidget(self.profile); self.profile_hint=QLabel('请输入画师主页链接。'); self.profile_hint.setObjectName('muted'); box.addWidget(self.profile_hint); self.profile.textChanged.connect(self.validate_profile)
        self.options_panel=QFrame(); self.options_panel.setObjectName('optionsPanel'); self.options_panel.setAutoFillBackground(False); options=QHBoxLayout(self.options_panel); options.setContentsMargins(12,8,12,8); options.setSpacing(16); self.order_label=QLabel('日期顺序'); self.order_label.setObjectName('optionLabel'); self.order_label.setStyleSheet('background:transparent;border:0'); options.addWidget(self.order_label); self.order_combo=SoftComboBox(); self.order_combo.addItems(['从新到旧','从旧到新']); options.addWidget(self.order_combo); self.title_check=GlowCheckBox('按图集标题分别存入文件夹'); self.title_check.setChecked(True); self.title_check.setStyleSheet('background:transparent;border:0'); options.addWidget(self.title_check); self.select_posts_check=GlowCheckBox('先扫描标题并选择下载图集'); self.select_posts_check.setChecked(True); self.select_posts_check.setStyleSheet('background:transparent;border:0'); options.addWidget(self.select_posts_check); options.addStretch(1); box.addWidget(self.options_panel)
        self.rename_container=QWidget(); self.rename_row=QHBoxLayout(self.rename_container); self.rename_row.setContentsMargins(0,0,0,0); self.rename_check=GlowCheckBox('下载后按日期顺序编号重命名'); self.rename_check.setChecked(True); self.rename_row.addWidget(self.rename_check); self.start_number_label=QLabel(); self.rename_row.addWidget(self.start_number_label); self.start_number=QSpinBox(); self.start_number.setRange(0,999999999); self.start_number.setValue(1); self.rename_row.addWidget(self.start_number); self.rename_row.addStretch(1); box.addWidget(self.rename_container); self.rename_container.setVisible(False)
        self.title_check.toggled.connect(lambda checked:self.rename_container.setVisible(not checked))
        self.title_check.toggled.connect(self.update_note)
        folder_row=QHBoxLayout(); self.folder_label=QLabel('选择图片保存文件夹'); self.folder_label.setObjectName('sectionLabel'); self.folder_label.setWordWrap(True); folder_row.addWidget(self.folder_label,1); self.default_path_check=GlowCheckBox('保存为默认路径'); self.default_path_check.setChecked(False); folder_row.addWidget(self.default_path_check); self.default_path_check.toggled.connect(self.save_default_path_setting); self.browse=GlowButton(); self.browse.clicked.connect(self.pick); folder_row.addWidget(self.browse); box.addLayout(folder_row); self.path=QLineEdit(); self.path.setMinimumHeight(58); self.path.setReadOnly(True); self.path.setStyleSheet('QLineEdit{background:rgba(25,31,43,110);border:1px solid #65748a;border-radius:12px;padding:14px 18px}'); self.path.setText(self.settings.value('default_save_path','',type=str));
        box.addWidget(self.path); self.start=GlowButton(); self.start.setCursor(Qt.CursorShape.PointingHandCursor); self.start.setMinimumHeight(62); self.start.setStyleSheet('QPushButton{background:#2b9dbd;border:0;border-radius:14px;font-weight:700;color:#08151b} QPushButton:hover{background:#52c3df} QPushButton:disabled{background:#344451;color:#8999a5}'); self.start.clicked.connect(self.download); self.start.setEnabled(False); box.addWidget(self.start); root.addWidget(self.main_card,0,Qt.AlignmentFlag.AlignHCenter)
        self.note=QLabel('默认：每个图集分别保存到以标题命名的文件夹中。'); self.note.setObjectName('muted'); self.note.setMaximumWidth(950); self.note.setAlignment(Qt.AlignmentFlag.AlignLeft); root.addWidget(self.note,0,Qt.AlignmentFlag.AlignHCenter)
        self.completed_path=None; self.status_container=QWidget(); self.status_container.setMaximumWidth(950); status_row=QHBoxLayout(self.status_container); status_row.setContentsMargins(0,0,0,0); status_row.setSpacing(10); self.status=QLabel(); self.status.setObjectName('muted'); self.status.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter); self.status.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred); status_row.addWidget(self.status,1); self.open_folder_button=QPushButton(); self.open_folder_button.setCursor(Qt.CursorShape.PointingHandCursor); self.open_folder_button.setFixedHeight(36); self.open_folder_button.setVisible(False); self.open_folder_button.clicked.connect(self.open_download_folder); status_row.addWidget(self.open_folder_button,0,Qt.AlignmentFlag.AlignRight); root.addWidget(self.status_container,0,Qt.AlignmentFlag.AlignHCenter); self.progress=RainbowProgress(); self.progress.setMinimumWidth(700); self.progress.setMaximumWidth(950); self.progress.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed); root.addWidget(self.progress,0,Qt.AlignmentFlag.AlignHCenter)
        log_row=QHBoxLayout(); log_row.setAlignment(Qt.AlignmentFlag.AlignHCenter); self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(75); self.log.setMaximumHeight(125); self.log.setMaximumWidth(950); self.log.setStyleSheet('QTextEdit{background:transparent;border:1px solid transparent;border-radius:12px;padding:13px} QScrollBar:vertical{background:#171f2d;width:14px;margin:8px 3px;border-radius:7px} QScrollBar::handle:vertical{background:#52647d;min-height:42px;border-radius:7px;border:2px solid #171f2d} QScrollBar::handle:vertical:hover{background:#65c9e4} QScrollBar::handle:vertical:pressed{background:#9be8f5} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent}'); self.log.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred); log_row.addWidget(self.log,1); self.copy_log=QPushButton('⧉'); self.copy_log.setToolTip('复制日志'); self.copy_log.setFixedSize(46,46); self.copy_log.setCursor(Qt.CursorShape.PointingHandCursor); self.copy_log.setStyleSheet('QPushButton{background:#263a54;color:#eaf8ff;border:1px solid #5e7896;border-radius:21px;font-size:20px} QPushButton:hover{background:#347f9a;border-color:#8de7f5} QPushButton:pressed{background:#1b596e}'); self.copy_log.clicked.connect(self.copy_log_text); log_row.addWidget(self.copy_log); root.addLayout(log_row,1); self.credit=RainbowCredit('千泽音奈  ·  QQ：3412892533'); root.addWidget(self.credit); self.set_lang(self.lang)
        self.apply_theme(True)
        self.fx=QTimer(self); self.fx.timeout.connect(self.tick)
        self.overlay=ParticleOverlay(self); self.overlay.show(); self.overlay.raise_(); self.credit.fireworkRequested.connect(self.overlay.launch_firework)
        self._last_particle=QPointF(-1000,-1000)
        QApplication.instance().installEventFilter(self)
    def set_lang(self,l):
        self.lang=l; t=TEXT[l]; self.setWindowTitle(t['title']); self.heading.setText(t['title']); self.browse.setText(t['browse']); self.start.setText(t['start'])
        self.open_folder_button.setText(t['open_folder'])
        en=l=='English'; ja=l=='日本語'
        self.profile_label.setText('请输入完整的 pawchive.pw 画师主页链接' if l=='简体中文' else '請輸入完整的 pawchive.pw 畫師首頁連結' if l=='繁體中文' else 'Enter the full Pawchive creator profile URL' if en else 'PawchiveのクリエイターページURLを入力')
        self.folder_label.setText('选择图片保存文件夹' if l=='简体中文' else '選擇圖片儲存資料夾' if l=='繁體中文' else 'Image save folder' if en else '画像の保存先フォルダー')
        self.default_path_check.setText('保存为默认路径' if l=='简体中文' else '設為預設路徑' if l=='繁體中文' else 'Save as default folder' if en else '既定の保存先にする')
        self.order_label.setText('日期顺序' if l=='简体中文' else '日期順序' if l=='繁體中文' else 'Date order' if en else '日付順')
        self.order_combo.setItemText(0,'从新到旧' if l=='简体中文' else '從新到舊' if l=='繁體中文' else 'Newest first' if en else '新しい順')
        self.order_combo.setItemText(1,'从旧到新' if l=='简体中文' else '從舊到新' if l=='繁體中文' else 'Oldest first' if en else '古い順')
        self.title_check.setText('按图集标题分别存入文件夹' if l=='简体中文' else '按圖集標題分別存入資料夾' if l=='繁體中文' else 'Save each post in a title folder' if en else '投稿ごとにタイトル別フォルダーへ保存')
        self.select_posts_check.setText('先扫描标题并选择下载图集' if l=='简体中文' else '先掃描標題並選擇下載圖集' if l=='繁體中文' else 'Scan titles and choose posts first' if en else 'タイトルをスキャンして投稿を選択')
        self.rename_check.setText('下载后按日期顺序编号重命名' if l=='简体中文' else '下載後按日期順序編號重新命名' if l=='繁體中文' else 'Rename files in date order' if en else '日付順に番号を付けて名前を変更')
        self.start_number_label.setText('起始编号' if l=='简体中文' else '起始編號' if l=='繁體中文' else 'Start number' if en else '開始番号')
        self.note.setText(AUX_TEXT[l]['note_titles' if self.title_check.isChecked() else 'note_flat'])
        self.clear_cache.setToolTip(AUX_TEXT[l]['cache_tooltip']); self.copy_log.setToolTip(AUX_TEXT[l]['copy_tooltip'])
        if not self.busy: self.status.setText(t['ready']); self.completed_path=None; self.open_folder_button.hide()
        self.validate_profile()
        if hasattr(self,'splash') and self.splash.isVisible(): self.splash.set_language(l)
    def update_note(self,checked=None):
        self.note.setText(AUX_TEXT[self.lang]['note_titles' if self.title_check.isChecked() else 'note_flat'])
    def set_busy_state(self,busy):
        self.busy=busy
        if busy: self.completed_path=None; self.open_folder_button.hide()
        controls=(self.profile,self.order_combo,self.title_check,self.select_posts_check,self.rename_check,self.start_number,self.default_path_check,self.browse)
        for widget in controls: widget.setEnabled(not busy)
        self.clear_cache.setEnabled(not busy)
        self.validate_profile()
    def validate_profile(self,text=None):
        value=(text if text is not None else self.profile.text()).strip()
        valid=bool(PROFILE_URL_RE.fullmatch(value))
        has_folder=bool(self.path.text().strip())
        self.start.setEnabled(valid and has_folder and not self.busy)
        t=AUX_TEXT[self.lang]
        if valid:
            self.profile_hint.setText(t['profile_valid'] if has_folder else t['folder_needed']); self.profile_hint.setStyleSheet('color:#55cb91' if has_folder else 'color:#ffbd58')
        elif value:
            self.profile_hint.setText(t['profile_invalid']); self.profile_hint.setStyleSheet('color:#ff7b83')
        else:
            self.profile_hint.setText(t['profile_hint']); self.profile_hint.setStyleSheet('color:#aab8ca')
    def apply_theme(self,dark):
        if dark:
            bg='#10141d'; fg='#e9f1fb'; field='#191f2b'; muted='#aab8ca'; track='#202735'; colors=['#ff5c74','#ffb547','#ffe45c','#58d68d','#45c8e8','#6686ff','#bd70ef']
        else:
            bg='#fffaf0'; fg='#29364a'; field='#ffffff'; muted='#68758a'; track='#e7ebf1'; colors=['#e84a5f','#ed8c26','#d6b51e','#269b62','#1689a8','#4d65cf','#9250bc']
        self.setStyleSheet(f'QWidget{{background:transparent;color:{fg};font-family:Georgia,Palatino Linotype,Microsoft YaHei;font-size:15px}} QWidget#appRoot{{background:{bg}}} QDialog{{background:{bg};color:{fg}}} QLineEdit,QTextEdit{{background:transparent;border:1px solid transparent;border-radius:12px;padding:13px;color:{fg}}} QCheckBox{{background:transparent;spacing:12px;color:{fg}}} QCheckBox:hover{{color:#8feaff}} QCheckBox::indicator{{width:22px;height:22px;border:2px solid #8292a8;border-radius:5px;background:{field}}} QCheckBox::indicator:hover{{border:2px solid #58d8f5;background:rgba(88,200,232,55)}} QCheckBox::indicator:checked{{background:#58c8e8;border:2px solid #58c8e8}} QComboBox{{background:{field};border:1px solid #8795a8;border-radius:10px;padding:9px 30px 9px 12px;color:{fg};min-width:150px;min-height:24px}} QComboBox QAbstractItemView{{background:{field};color:{fg};border:1px solid #8795a8;selection-background-color:#58c8e8;selection-color:#10202a;outline:0}} QComboBox::drop-down{{background:transparent;border:0;width:28px}} QComboBox::down-arrow{{image:none;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid {muted};margin-right:10px}} QLabel#muted{{background:transparent;color:{muted}}} QLabel#sectionLabel{{background:transparent;font-size:16px;font-weight:600;color:{fg}}} QLabel#optionLabel{{background:transparent;font-size:14px;font-weight:600;color:{muted}}}')
        surface='rgba(255,255,255,6)' if dark else 'rgba(255,255,255,220)'
        surface_border='rgba(140,170,210,42)' if dark else '#e1e7ef'
        self.main_card.setStyleSheet(f'QFrame#mainCard{{background:{surface};border:1px solid {surface_border};border-radius:20px}} QFrame#optionsPanel{{background:transparent;border:0;border-radius:0}} QFrame#optionsPanel QLabel,QFrame#optionsPanel QCheckBox{{background:transparent;border:0}} QFrame#cardAccent{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #43cbe8,stop:0.52 #718cff,stop:1 #b576ea);border:0;border-radius:1px}}')
        self.card_shadow.setColor(QColor(0,0,0,76) if dark else QColor(49,75,112,32))
        input_bg='rgba(25,31,43,155)' if dark else '#ffffff'
        input_border='#65748a' if dark else '#c8d2df'
        self.profile.setStyleSheet(f'QLineEdit{{background:{input_bg};border:1px solid {input_border};border-radius:12px;padding:14px 18px;color:{fg}}} QLineEdit:focus{{border:2px solid #58c8e8}}')
        path_bg='rgba(25,31,43,110)' if dark else 'rgba(255,255,255,190)'
        self.path.setStyleSheet(f'QLineEdit{{background:{path_bg};border:1px solid {input_border};border-radius:12px;padding:14px 18px;color:{fg}}}')
        log_bg='rgba(255,255,255,5)' if dark else 'rgba(255,255,255,190)'
        log_border='#2c3748' if dark else '#e1e7ef'
        scroll_track='#171f2d' if dark else '#edf1f6'
        scroll_handle='#52647d' if dark else '#b3bfce'
        scroll_hover='#65c9e4' if dark else '#7d98b8'
        self.log.setStyleSheet(f'QTextEdit{{background:{log_bg};border:1px solid {log_border};border-radius:14px;padding:13px;color:{fg}}} QScrollBar:vertical{{background:{scroll_track};width:14px;margin:8px 3px;border-radius:7px}} QScrollBar::handle:vertical{{background:{scroll_handle};min-height:42px;border-radius:7px;border:2px solid {scroll_track}}} QScrollBar::handle:vertical:hover{{background:{scroll_hover}}} QScrollBar::handle:vertical:pressed{{background:#9be8f5}} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0}} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:transparent}}')
        copy_bg='#263a54' if dark else '#e8eef6'
        copy_fg='#eaf8ff' if dark else '#35475f'
        copy_border='#5e7896' if dark else '#c5d0df'
        self.copy_log.setStyleSheet(f'QPushButton{{background:{copy_bg};color:{copy_fg};border:1px solid {copy_border};border-radius:21px;font-size:20px}} QPushButton:hover{{background:#347f9a;color:#eaf8ff;border-color:#8de7f5}} QPushButton:pressed{{background:#1b596e;color:#eaf8ff}}')
        folder_bg='#203b4b' if dark else '#e7f3f8'
        folder_fg='#a7e9f5' if dark else '#28647a'
        folder_border='#3b7389' if dark else '#b7d8e3'
        self.open_folder_button.setStyleSheet(f'QPushButton{{background:{folder_bg};color:{folder_fg};border:1px solid {folder_border};border-radius:12px;padding:5px 13px;font-weight:600}} QPushButton:hover{{background:#347f9a;color:#ffffff;border-color:#8de7f5}} QPushButton:pressed{{background:#1b596e;color:#ffffff}}')
        self.progress.colors=[QColor(c) for c in colors]; self.progress.track=QColor(track); self.progress.update()
        if hasattr(self,'overlay'): self.overlay.update()
    def pick(self):
        d=QFileDialog.getExistingDirectory(self,TEXT[self.lang]['choose'],self.path.text() or str(Path.home()))
        if d:
            if not self.path.text() or Path(d)!=Path(self.path.text()): self.completed_path=None; self.open_folder_button.hide()
            self.path.setText(d)
            if self.default_path_check.isChecked(): self.settings.setValue('default_save_path',d)
            self.validate_profile()
    def save_default_path_setting(self,checked):
        if checked and self.path.text(): self.settings.setValue('default_save_path',self.path.text())
        elif not checked: self.settings.remove('default_save_path')
    def copy_log_text(self):
        QApplication.clipboard().setText(self.log.toPlainText())
        self.completed_path=None; self.open_folder_button.hide()
        self.status.setText(AUX_TEXT[self.lang]['log_copied'])
    def clear_cache_files(self):
        if self.busy: return
        try:
            for item in self.cache_dir.iterdir():
                shutil.rmtree(item) if item.is_dir() else item.unlink(missing_ok=True)
            self.completed_path=None; self.open_folder_button.hide()
            self.status.setText(AUX_TEXT[self.lang]['cache_cleared'])
        except OSError as exc: self.log.append(AUX_TEXT[self.lang]['cache_failed'].format(exc))
    def open_download_folder(self):
        folder=Path(self.completed_path) if self.completed_path else None
        if folder and folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            self.completed_path=None; self.open_folder_button.hide()
    def choose_titles(self,titles):
        colors=['#ff5b6e','#ff9f43','#f2d34f','#3dcc83','#32c9d8','#568bff','#bd69ed']; text=AUX_TEXT[self.lang]
        dialog=QDialog(self); dialog.setWindowTitle(text['choose_title']); dialog.resize(980,760)
        layout=QVBoxLayout(dialog); label=QLabel(text['choose_summary'].format(count=len(titles))); layout.addWidget(label)
        tools=QHBoxLayout(); all_btn=QPushButton(text['select_all']); none_btn=QPushButton(text['select_none']); tools.addWidget(all_btn); tools.addWidget(none_btn); tools.addStretch(1); layout.addLayout(tools)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet('QScrollArea{border:0;background:transparent} QScrollBar:vertical{background:#171f2d;width:14px;margin:8px 3px 8px 3px;border-radius:7px} QScrollBar::handle:vertical{background:#52647d;min-height:42px;border-radius:7px;border:2px solid #171f2d} QScrollBar::handle:vertical:hover{background:#65c9e4} QScrollBar::handle:vertical:pressed{background:#9be8f5} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;background:transparent} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent}'); body=QWidget(); grid=QGridLayout(body); grid.setSpacing(14); selected=set(range(len(titles))); checks=[]
        for i,entry in enumerate(titles):
            card=QFrame(); card.setCursor(Qt.CursorShape.PointingHandCursor); card.setObjectName('coverCard'); card.setStyleSheet('QFrame#coverCard{background:transparent;border:3px solid transparent;border-radius:12px}'); v=QVBoxLayout(card); v.setContentsMargins(6,6,6,6)
            cover=QLabel(); cover.setFixedSize(190,145); cover.setAlignment(Qt.AlignmentFlag.AlignCenter); cover.setStyleSheet('border:0;background:transparent'); cover.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            if entry['image']:
                pix=QPixmap(entry['image'])
                if not pix.isNull(): cover.setPixmap(pix.scaled(190,145,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            if not cover.pixmap(): cover.setText(text['cover_missing'])
            check=GlowCheckBox(); check.setChecked(True); check.setStyleSheet('QCheckBox{background:rgba(15,20,30,90);border-radius:10px;padding:2px} QCheckBox::indicator{width:23px;height:23px;border:2px solid white;border-radius:6px;background:rgba(20,25,35,100)} QCheckBox::indicator:checked{background:#58c8e8;border-color:white}'); checks.append(check)
            type_label=QLabel(); type_label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); type_label.setStyleSheet('background:rgba(10,12,18,175);border-radius:5px;padding:2px 5px;font-weight:700'); type_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            formats=entry.get('formats',[])
            if formats:
                chips=' '.join(f'<span style="color:{colors[k%len(colors)]};">{escape(ext.upper())}</span>' for k,ext in enumerate(formats))
                type_label.setText(chips)
            else: type_label.setText(f'<span style="color:#b4becb">{text["no_direct"]}</span>')
            overlay=QGridLayout(); overlay.setContentsMargins(0,0,0,0); overlay.addWidget(cover,0,0,2,2); overlay.addWidget(check,0,0,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop); overlay.addWidget(type_label,1,1,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignBottom); v.addLayout(overlay)
            name=QLabel(entry['title']); name.setTextFormat(Qt.TextFormat.PlainText); name.setWordWrap(True); name.setMaximumWidth(190); name.setStyleSheet('border:0;background:transparent'); name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
            v.addWidget(name); grid.addWidget(card,i//4,i%4)
            initial=random.choice(colors); card.setStyleSheet(f'QFrame#coverCard{{background:rgba(255,255,255,8);border:3px solid {initial};border-radius:12px}}')
            check.stateChanged.connect(lambda state,idx=i,widget=card: self._set_card_selection(idx,state,selected,widget,colors))
            def toggle(event, idx=i, widget=card):
                checks[idx].setChecked(not checks[idx].isChecked())
            card.mousePressEvent=toggle
        all_btn.clicked.connect(lambda: [check.setChecked(True) for check in checks])
        none_btn.clicked.connect(lambda: [check.setChecked(False) for check in checks])
        scroll.setWidget(body); layout.addWidget(scroll,1)
        top_button=QPushButton('↑'); top_button.setToolTip(text['back_top']); top_button.setFixedSize(42,42); top_button.setCursor(Qt.CursorShape.PointingHandCursor); top_button.setStyleSheet('QPushButton{background:#263a54;color:#eaf8ff;border:1px solid #5e7896;border-radius:21px;font-size:22px;font-weight:700} QPushButton:hover{background:#347f9a;border-color:#8de7f5} QPushButton:pressed{background:#1b596e}'); top_button.clicked.connect(lambda:scroll.verticalScrollBar().setValue(0)); layout.addWidget(top_button,0,Qt.AlignmentFlag.AlignRight)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); buttons.button(QDialogButtonBox.StandardButton.Ok).setText(text['ok']); buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(text['cancel']); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted: return None
        return {titles[i]['url'] for i in selected}
    @staticmethod
    def _set_card_selection(index,state,selected,widget,colors):
        if state:
            selected.add(index); color=random.choice(colors); widget.setStyleSheet(f'QFrame#coverCard{{background:rgba(255,255,255,8);border:3px solid {color};border-radius:12px}}')
        else:
            selected.discard(index); widget.setStyleSheet('QFrame#coverCard{background:transparent;border:3px solid transparent;border-radius:12px}')
    def download(self):
        if self.busy: return
        if not self.path.text(): self.pick()
        if not self.path.text():return
        profile=self.profile.text().strip()
        if not PROFILE_URL_RE.fullmatch(profile):
            self.status.setText(AUX_TEXT[self.lang]['profile_invalid']); return
        selected=None
        if self.select_posts_check.isChecked():
            self.set_busy_state(True); self.status.setText(AUX_TEXT[self.lang]['scan_status'])
            self.splash=ScanAnimation(self); self.splash.set_language(self.lang); self.splash.show()
            self.scanner=ProfileScanWorker(profile,self.cache_dir); self.splash.scanner=self.scanner
            self.scanner.counts.connect(self.splash.update_counts); self.scanner.result.connect(self.scan_finished); self.scanner.failed.connect(self.scan_failed); self.scanner.start(); return
        self.launch_worker(profile,selected)
    def scan_finished(self,titles):
        if hasattr(self,'scanner') and self.scanner.isRunning(): self.scanner.wait()
        self.splash._allow_close=True
        self.splash.close()
        if self._close_when_worker_stops:
            self.busy=False
            QTimer.singleShot(0,self.close)
            return
        if not titles:
            self.scan_failed(AUX_TEXT[self.lang]['empty_scan']); return
        selected=self.choose_titles(titles)
        if self._close_when_worker_stops:
            self.busy=False
            QTimer.singleShot(0,self.close)
            return
        if selected is None or not selected:
            self.set_busy_state(False); self.status.setText(TEXT[self.lang]['ready']); return
        self.launch_worker(self.profile.text().strip(),selected)
    def scan_failed(self,message):
        if hasattr(self,'scanner') and self.scanner.isRunning(): self.scanner.wait()
        if hasattr(self,'splash'): self.splash._allow_close=True; self.splash.close()
        self.set_busy_state(False); self.status.setText(AUX_TEXT[self.lang]['scan_failed']); self.log.append(str(message))
        if self._close_when_worker_stops: QTimer.singleShot(0,self.close)
    def launch_worker(self,profile,selected):
        self.set_busy_state(True); self.progress.setValue(0); self.log.clear(); self.status.setText(TEXT[self.lang]['working']); order='newest' if self.order_combo.currentIndex()==0 else 'oldest'; self.worker=Worker(self.path.text(),profile,order,self.title_check.isChecked(),selected,not self.title_check.isChecked() and self.rename_check.isChecked(),self.start_number.value(),self.lang); self.worker.progress.connect(self.update_progress); self.worker.finished_ok.connect(self.done); self.worker.failed.connect(self.error); self.worker.start()
    def update_progress(self,name,i,total):
        failure_prefixes=tuple(text['download_fail_prefix'] for text in AUX_TEXT.values())
        if name.startswith('✓'):
            self.progress.setValue(100); self.log.append(name); return
        if name.startswith(failure_prefixes):
            self.log.append(name); return
        if total:
            self.progress.setValue(int(i*100/total))
        else:
            self.progress.setIndeterminate()
        match=re.search(r'\((\d+/\d+)\)',name); count=f' {match.group(0)}' if match else ''
        message='file_progress' if total else 'unknown_progress'
        self.status.setText(AUX_TEXT[self.lang][message].format(count=count,name=name,current=i/1024/1024,total=total/1024/1024))
    def done(self,n):
        if hasattr(self,'worker') and self.worker.isRunning(): self.worker.wait()
        self.set_busy_state(False); self.status.setText(f"{TEXT[self.lang]['done']} · {n}"); folder=Path(self.path.text()) if self.path.text().strip() else None; self.completed_path=str(folder) if n>0 and folder and folder.is_dir() else None; self.open_folder_button.setVisible(bool(self.completed_path))
        if self._close_when_worker_stops: QTimer.singleShot(0,self.close)
    def error(self,e):
        if hasattr(self,'worker') and self.worker.isRunning(): self.worker.wait()
        self.set_busy_state(False); self.completed_path=None; self.open_folder_button.hide(); self.status.setText(TEXT[self.lang]['error']); self.log.append(TEXT[self.lang]['empty'] if e=='EMPTY' else AUX_TEXT[self.lang]['no_selected'] if e=='NO_SELECTED_POSTS' else e)
        if self._close_when_worker_stops: QTimer.singleShot(0,self.close)
    def closeEvent(self,event):
        if self.busy:
            event.ignore(); self._close_when_worker_stops=True; self.status.setText(AUX_TEXT[self.lang]['close_wait'])
            if hasattr(self,'worker') and self.worker.isRunning(): self.worker.requestInterruption()
            if hasattr(self,'scanner') and self.scanner.isRunning():
                self.scanner.requestInterruption()
                if hasattr(self,'splash'): self.splash._allow_close=True; self.splash.hide()
            return
        QApplication.instance().removeEventFilter(self)
        self.credit.animation_timer.stop(); self.fx.stop()
        shutil.rmtree(self.cache_dir,ignore_errors=True); super().closeEvent(event)
    def eventFilter(self,obj,event):
        if event.type()==event.Type.MouseMove:
            gp=event.globalPosition().toPoint(); local=self.mapFromGlobal(gp)
            dx=local.x()-self._last_particle.x(); dy=local.y()-self._last_particle.y()
            if self.rect().contains(local) and random.random()<.24 and abs(dx)+abs(dy)>8 and len(self.particles)<100:
                self.particles.append(Particle(local.x(),local.y())); self._last_particle=QPointF(local)
                if not self.fx.isActive(): self.fx.start(16)
        elif event.type()==event.Type.MouseButtonPress:
            gp=event.globalPosition().toPoint(); local=self.mapFromGlobal(gp)
            theme_origin=self.theme.mapToGlobal(self.theme.rect().topLeft())
            theme_rect=QRect(theme_origin,self.theme.size())
            if theme_rect.adjusted(-2,-4,2,4).contains(gp) and not theme_rect.contains(gp):
                self.theme.click()
                return True
            credit_local=self.credit.mapFromGlobal(gp)
            credit_character_hit=self.credit.character_at(credit_local.x(),credit_local.y()) is not None
            if self.rect().contains(local) and not credit_character_hit:
                for _ in range(min(9, max(0, 100-len(self.particles)))): self.particles.append(Particle(local.x(),local.y(),True))
                if self.particles and not self.fx.isActive(): self.fx.start(16)
        return super().eventFilter(obj,event)
    def tick(self):
        for p in self.particles:p.move()
        self.particles=[p for p in self.particles if p.life>0]
        self.overlay.advance()
        if self.particles or self.overlay.has_effects:
            self.overlay.sync(); self.overlay.raise_(); self.overlay.update()
        else:
            self.fx.stop()
    def resizeEvent(self,e):
        super().resizeEvent(e)
        if hasattr(self,'overlay'): self.overlay.sync(); self.overlay.raise_()
    def showEvent(self,e):
        super().showEvent(e)
        if hasattr(self,'overlay'): self.overlay.sync(); self.overlay.raise_()

if __name__=='__main__':
    if '--self-test-output' in sys.argv:
        import argparse
        from smoke_test import run
        parser=argparse.ArgumentParser(description='Offline startup check; never downloads files.')
        parser.add_argument('--self-test-output',type=Path,required=True)
        args=parser.parse_args()
        sys.exit(run(App,args.self_test_output))
    app=QApplication(sys.argv); w=App(); w.show(); w.raise_(); w.activateWindow(); sys.exit(app.exec())








