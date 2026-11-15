import os,subprocess
import math,sys
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLayout, QMenu, QMessageBox, QPushButton, QWidget,QMainWindow,QApplication
from PyQt6.QtGui import QPainter, QPen, QColor, QImage, QPixmap,QGuiApplication,QColor
from PyQt6.QtCore import Qt, QPointF, QSize, QRectF,QPoint
import ctypes, sys
def set_click_through(widget, enable: bool):
    if sys.platform != 'win32':
        return
    hwnd = int(widget.winId())
    user32 = ctypes.windll.user32
    GWL_EXSTYLE      = -20
    WS_EX_LAYERED    = 0x00080000
    WS_EX_TRANSPARENT= 0x00000020
    SWP_NOMOVE       = 0x0002
    SWP_NOSIZE       = 0x0001
    SWP_NOZORDER     = 0x0004
    SWP_FRAMECHANGED = 0x0020
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

    if enable:
        new_style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT
    else:
        new_style = style & ~WS_EX_TRANSPARENT

    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
    user32.SetWindowPos(
        hwnd, 0, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
    )
def uiaccess(win):
    s_path=sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
    uiaccesstools_path=os.path.join(os.path.dirname(s_path),"uiaccesstools.exe")
    command=[uiaccesstools_path,sys.executable] if getattr(sys, 'frozen', False) else [uiaccesstools_path,sys.executable,sys.argv[0]]
    if os.path.isfile(uiaccesstools_path):
        try:
            result = subprocess.run(command,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            QMessageBox.critical(win,"错误",f"启动uiaccesstools.exe失败：{e}")
        else:
            if result.returncode == 0:
                sys.exit()
    else:
        QMessageBox.critical(win,"错误","找不到uiaccesstools.exe")


class Canvas(QWidget):
    SPEED_FULL_THIN = 80.0
    WIDTH_MAX = 2.3
    WIDTH_MIN = 0.85
    WIDTH_EMA = 0.85
    SUBDIV = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setMouseTracking(True)

        # 状态
        self._mode = 'p'
        self._pen_color = QColor(255, 0, 0)
        self._pen_size = 4
        self._eraser_size = 24
        self._background: QPixmap | None = None
        self._hover_pos: QPointF | None = None

        self.base_image: QImage | None = None
        self.image: QImage | None = None

        # 历史
        self.strokes: list[dict] = []
        self.redo_stack: list[dict] = []
        self.current: dict | None = None
        self.width_factor = 1.0

        # ---- 增量渲染状态 ----
        self._stroke_painter: QPainter | None = None   # 一笔期间持续打开
        self._stroke_color: QColor | None = None
        self._next_segment = 1                          # 下一个待绘制的贝塞尔段索引

        self._ensure_image()

    # ---------------- 对外接口 ----------------
    def clear(self):
        self._end_stroke_painter()
        self.strokes.clear()
        self.redo_stack.clear()
        self.current = None
        self.width_factor = 1.0
        self._hover_pos = None
        self._refresh()

    def drawMode(self, mode: str):
        if mode not in ('p', 'e'):
            return
        self._mode = mode
        if mode == 'p':
            self._hover_pos = None
        self.update()

    def setColor(self, color: QColor):
        self._pen_color = QColor(color)

    def setPSize(self, size: int):
        self._pen_size = max(1, int(size))

    def setESize(self, size: int):
        self._eraser_size = max(1, int(size))
        if self._mode == 'e':
            self.update()

    def cancel(self):
        if self.strokes:
            self.redo_stack.append(self.strokes.pop())
            self._refresh()

    def rework(self):
        if self.redo_stack:
            self.strokes.append(self.redo_stack.pop())
            self._refresh()

    # ---------------- 内部工具 ----------------
    def _refresh(self):
        self._end_stroke_painter()
        self._render_base()
        self._render_current()
        self.update()

    def _end_stroke_painter(self):
        if self._stroke_painter is not None:
            self._stroke_painter.end()
            self._stroke_painter = None

    def _dpr(self) -> float:
        d = self.devicePixelRatioF()
        return d if d > 0 else 1.0

    def _ensure_image(self):
        dpr = self._dpr()
        w = max(1, int(round(self.width() * dpr)))
        h = max(1, int(round(self.height() * dpr)))
        if self.base_image is not None and self.base_image.size() == QSize(w, h):
            return
        self._end_stroke_painter()
        self.base_image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        self.base_image.fill(Qt.GlobalColor.transparent)
        self._render_strokes(self.base_image, self.strokes)
        if self.current is not None and len(self.current['points']) >= 2:
            self._end_stroke_painter()
            self.strokes.append(self.current)
            self.current = None
        self._render_current()
        if self.current is not None:
            self._next_segment = max(1, len(self.current['points']) - 1)

    def resizeEvent(self, e):
        self._ensure_image()
        super().resizeEvent(e)

    # ---------------- 键盘 ----------------
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_P:
            self.drawMode('p')
        elif k == Qt.Key.Key_E:
            self.drawMode('e')
        elif k == Qt.Key.Key_Z:
            self.cancel()
        elif k == Qt.Key.Key_Y:
            self.rework()
        elif k == Qt.Key.Key_C:
            self.clear()
        else:
            super().keyPressEvent(e)

    # ---------------- 鼠标 ----------------
    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        pos = e.position()
        self._hover_pos = pos

        if self._mode == 'p':
            self.width_factor = 1.0
            widths, color = [float(self._pen_size)], QColor(self._pen_color)
        else:
            widths, color = [float(self._eraser_size)], None

        self.current = {
            'mode': self._mode, 'points': [pos],
            'widths': widths, 'color': color,
        }
        self._begin_stroke()          # 只做一次 base 复制
        self.update()

    def mouseMoveEvent(self, e):
        self._hover_pos = e.position()
        if self.current is None:
            if self._mode == 'e':
                self.update()
            return

        pos = e.position()
        if self.current['mode'] == 'p':
            last = self.current['points'][-1]
            d = math.hypot(pos.x() - last.x(), pos.y() - last.y())
            t = min(d / self.SPEED_FULL_THIN, 1.0)
            target = self.WIDTH_MAX - (self.WIDTH_MAX - self.WIDTH_MIN) * t
            self.width_factor = (self.width_factor * self.WIDTH_EMA
                                 + target * (1.0 - self.WIDTH_EMA))
            w = self._pen_size * self.width_factor
        else:
            w = float(self._eraser_size)

        self.current['points'].append(pos)
        self.current['widths'].append(w)
        self._extend_stroke()         # 只画新段
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.current is None:
            return

        pts = self.current['points']
        widths = self.current['widths']
        n = len(pts)

        p = self._stroke_painter
        if p is None:
            p = self._stroke_painter_create()

        # 收尾：原版最后一次 out.append(pts[-1]) 产生的“尾巴”
        if n == 1:
            pass
        elif n == 2:
            self._draw_line(p, pts[0], widths[0], pts[1], widths[1])
        else:
            start = (pts[-2] + pts[-1]) / 2.0
            ws = (widths[-2] + widths[-1]) / 2.0
            self._draw_line(p, start, ws, pts[-1], widths[-1])

        self._end_stroke_painter()
        self.strokes.append(self.current)
        self.current = None
        self.redo_stack.clear()
        self.base_image = self.image.copy()
        self.update()

    def leaveEvent(self, e):
        self._hover_pos = None
        self.update()
        super().leaveEvent(e)

    # ---------------- 增量渲染 ----------------
    def _begin_stroke(self):
        # 一笔只复制一次 base —— 这是核心优化之一
        self.image = self.base_image.copy()
        self._next_segment = 1

        pts = self.current['points']
        widths = self.current['widths']
        p = self._stroke_painter_create()
        r = max(0.5, widths[0]) / 2.0
        p.drawEllipse(pts[0], r, r)   # 起点小圆点

    def _stroke_painter_create(self) -> QPainter:
        p = QPainter(self.image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self._dpr(), self._dpr())
        if self.current['mode'] == 'e':
            p.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear)
            self._stroke_color = QColor(0, 0, 0)
        else:
            p.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)
            self._stroke_color = self.current['color']
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._stroke_color)
        self._stroke_painter = p
        return p

    def _extend_stroke(self):
        """只绘制目前可确定的、尚未绘制的贝塞尔段。"""
        pts = self.current['points']
        widths = self.current['widths']
        n = len(pts)
        if n < 2:
            return
        p = self._stroke_painter or self._stroke_painter_create()

        # 段 k (k>=1) 需要 pts[k+1] 存在；现有 n 个点时能画到段 n-2
        while self._next_segment <= n - 2:
            k = self._next_segment
            if k == 1:
                start, ws = pts[0], widths[0]
            else:
                start = (pts[k - 1] + pts[k]) / 2.0
                ws = (widths[k - 1] + widths[k]) / 2.0
            ctrl, wc = pts[k], widths[k]
            end = (pts[k] + pts[k + 1]) / 2.0
            we = (widths[k] + widths[k + 1]) / 2.0
            self._draw_quad(p, start, ws, ctrl, wc, end, we)
            self._next_segment += 1

    def _draw_quad(self, p, start, ws, ctrl, wc, end, we):
        N = self.SUBDIV
        p.setBrush(Qt.BrushStyle.NoBrush)
        prev_pt, prev_w = start, ws
        for i in range(1, N + 1):
            t = i / N
            mt = 1.0 - t
            cur_pt = mt * mt * start + 2.0 * mt * t * ctrl + t * t * end
            cur_w = mt * mt * ws + 2.0 * mt * t * wc + t * t * we
            p.setPen(QPen(
                self._stroke_color, max(0.5, (prev_w + cur_w) / 2.0),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ))
            p.drawLine(prev_pt, cur_pt)
            prev_pt, prev_w = cur_pt, cur_w

    def _draw_line(self, p, p0, w0, p1, w1):
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(
            self._stroke_color, max(0.5, (w0 + w1) / 2.0),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        p.drawLine(p0, p1)

    # ---------------- 全量重渲（撤销/重做/resize 时用） ----------------
    def _render_strokes(self, image: QImage, strokes):
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self._dpr(), self._dpr())
        for s in strokes:
            self._draw_stroke(p, s['points'], s['widths'], s['mode'], s['color'])
        p.end()

    def _render_base(self):
        if self.base_image is None:
            return
        self.base_image.fill(Qt.GlobalColor.transparent)
        self._render_strokes(self.base_image, self.strokes)

    def _render_current(self):
        if self.base_image is None:
            return
        self.image = self.base_image.copy()
        if self.current is not None:
            self._render_strokes(self.image, [self.current])

    def _sample_stroke(self, pts, widths):
        if len(pts) == 1:
            return [(pts[0], widths[0])]
        out = [(pts[0], widths[0])]
        prev, w_prev = pts[0], widths[0]
        N = self.SUBDIV
        for i in range(1, len(pts) - 1):
            ctrl, w_ctrl = pts[i], widths[i]
            end = (pts[i] + pts[i + 1]) / 2.0
            w_end = (widths[i] + widths[i + 1]) / 2.0
            for k in range(1, N + 1):
                t = k / N
                mt = 1.0 - t
                out.append((
                    mt * mt * prev + 2.0 * mt * t * ctrl + t * t * end,
                    mt * mt * w_prev + 2.0 * mt * t * w_ctrl + t * t * w_end,
                ))
            prev, w_prev = end, w_end
        out.append((pts[-1], widths[-1]))
        return out
    def hide_hover(self):
        #清掉橡皮擦光标
        if self._hover_pos is not None:
            self._hover_pos = None
            self.update()
    def _draw_stroke(self, painter: QPainter, points, widths, mode, color):
        if mode == 'e':
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear)
            color = QColor(0, 0, 0)
        else:
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver)

        if len(points) == 1:
            r = max(0.5, widths[0]) / 2.0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(points[0], r, r)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            samples = self._sample_stroke(points, widths)
            for (p0, w0), (p1, w1) in zip(samples, samples[1:]):
                painter.setPen(QPen(
                    color, max(0.5, (w0 + w1) / 2.0),
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                ))
                painter.drawLine(p0, p1)

        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver)

    # ---------------- paintEvent ----------------
    def paintEvent(self, e):
        self._ensure_image()
        p = QPainter(self)
        target = QRectF(0, 0, self.width(), self.height())

        if self._background is not None and not self._background.isNull():
            p.drawPixmap(target, self._background, QRectF(self._background.rect()))

        if self.image is not None:
            p.drawImage(target, self.image)

        if self._mode == 'e' and self._hover_pos is not None:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = self._eraser_size / 2.0
            center = self._hover_pos
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 220), 2.0))
            p.drawEllipse(center, r, r)
            p.setPen(QPen(QColor(0, 0, 0, 180), 1.0))
            p.drawEllipse(center, r - 1.0, r - 1.0)

class childWin(QWidget):
    def __init__(self,parent):
        super().__init__(parent)
        self.notAcceptFocus=False

        self.setWindowTitle(" ")
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowCloseButtonHint)
        self.mainLayout=QHBoxLayout(self)

        self.cao_zuo_Btn=QPushButton("操")
        self.pen_mode_Btn=QPushButton("笔")
        self.ca_chu_Btn=QPushButton("擦")
        self.che_xiao_Btn=QPushButton("撤")
        self.chong_zuo_Btn=QPushButton("重")
        self.qing_kong_Btn=QPushButton("清")
        self.she_zhi_Btn=QPushButton("设")

        self.cao_zuo_Btn.setToolTip("操作：正常操作计算机")
        self.pen_mode_Btn.setToolTip("笔：在屏幕上图画，快捷键p")
        self.ca_chu_Btn.setToolTip("擦除之前图画的痕迹，快捷键e")
        self.che_xiao_Btn.setToolTip("撤销上一笔，快捷键z")
        self.chong_zuo_Btn.setToolTip("恢复上一次撤销，快捷键y")
        self.qing_kong_Btn.setToolTip("清空画布，快捷键c")
        self.she_zhi_Btn.setToolTip("更多的选项，也可以在画布上右键打开同样菜单。")

        self.mainLayout.addWidget(self.cao_zuo_Btn)
        self.mainLayout.addWidget(self.pen_mode_Btn)
        self.mainLayout.addWidget(self.ca_chu_Btn)
        self.mainLayout.addWidget(self.che_xiao_Btn)
        self.mainLayout.addWidget(self.chong_zuo_Btn)
        self.mainLayout.addWidget(self.qing_kong_Btn)
        self.mainLayout.addWidget(self.she_zhi_Btn)
        

        si=40
        self.cao_zuo_Btn.setFixedSize(si,si)
        self.pen_mode_Btn.setFixedSize(si,si)
        self.ca_chu_Btn.setFixedSize(si,si)
        self.che_xiao_Btn.setFixedSize(si,si)
        self.chong_zuo_Btn.setFixedSize(si,si)
        self.qing_kong_Btn.setFixedSize(si,si)
        self.she_zhi_Btn.setFixedSize(si,si)
        

        self.che_xiao_Btn.clicked.connect(self.parent().canvas.cancel)
        self.chong_zuo_Btn.clicked.connect(self.parent().canvas.rework)
        self.pen_mode_Btn.clicked.connect(lambda:[self.parent().ifshow(),self.parent().canvas.drawMode("p")])
        self.ca_chu_Btn.clicked.connect(lambda:[self.parent().ifshow(),self.parent().canvas.drawMode("e")])
        self.cao_zuo_Btn.clicked.connect(self.parent().hideWin)
        self.qing_kong_Btn.clicked.connect(self.parent().canvas.clear)
        self.she_zhi_Btn.clicked.connect(self.showSettings)
        
    def showEvent(self, a0):
        screen = QApplication.primaryScreen().size()
        self.move(screen.width()-self.width()-20,screen.height()-self.height()-50)
        self.layout().setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        return super().showEvent(a0)
    def showSettings(self,pos=None,isc=False):
        menu = QMenu(self)
        
        color_menu=menu.addMenu("颜色")

        red=color_menu.addAction("红色")
        blue=color_menu.addAction("蓝色")
        green=color_menu.addAction("绿色")
        orange=color_menu.addAction("橙色")
        yellow=color_menu.addAction("黄色")
        pink=color_menu.addAction("粉色")
        black=color_menu.addAction("黑色")
        white=color_menu.addAction("白色")
        purple=color_menu.addAction("紫色")

        red.triggered.connect(lambda:self.parent().canvas.setColor(Qt.GlobalColor.red))
        blue.triggered.connect(lambda:self.parent().canvas.setColor(Qt.GlobalColor.blue))
        green.triggered.connect(lambda: self.parent().canvas.setColor(Qt.GlobalColor.green))

        orange.triggered.connect(lambda: self.parent().canvas.setColor(QColor("#FF7F27")))
        yellow.triggered.connect(lambda: self.parent().canvas.setColor(Qt.GlobalColor.yellow))
        pink.triggered.connect(lambda: self.parent().canvas.setColor(QColor("#FFAEC9")))
        black.triggered.connect(lambda: self.parent().canvas.setColor(Qt.GlobalColor.black))
        white.triggered.connect(lambda: self.parent().canvas.setColor(Qt.GlobalColor.white))
        purple.triggered.connect(lambda: self.parent().canvas.setColor(QColor("#A349A4")))

        size_menu=menu.addMenu("粗细...")
        s9=size_menu.addAction("9")
        s8=size_menu.addAction("8")
        s7=size_menu.addAction("7")
        s6=size_menu.addAction("6")
        s5=size_menu.addAction("5")
        s4=size_menu.addAction("4")
        s3=size_menu.addAction("3")
        s2=size_menu.addAction("2")
        s1=size_menu.addAction("1")

        s9.triggered.connect(lambda: self.parent().canvas.setPSize(9))
        s8.triggered.connect(lambda: self.parent().canvas.setPSize(8))
        s7.triggered.connect(lambda: self.parent().canvas.setPSize(7))
        s6.triggered.connect(lambda: self.parent().canvas.setPSize(6))
        s5.triggered.connect(lambda: self.parent().canvas.setPSize(5))
        s4.triggered.connect(lambda: self.parent().canvas.setPSize(4))
        s3.triggered.connect(lambda: self.parent().canvas.setPSize(3))
        s2.triggered.connect(lambda: self.parent().canvas.setPSize(2))
        s1.triggered.connect(lambda: self.parent().canvas.setPSize(1))

        menu.addSeparator()

        uia=menu.addAction("以uiaccess重新启动")
        uia.triggered.connect(lambda:uiaccess(self))

        if not isc:
            menu.exec(self.mapToGlobal(QPoint(0,0)))
        else:
            menu.exec(pos)


        
    def closeEvent(self, a0):
        self.parent().close()
        sys.exit()
        return super().closeEvent(a0)
    def information(self,info):
        if info=="p":
            pass
        elif info=="e":
            pass

class mainWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScreenPenPlus - HCT")
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
        self.canvas=Canvas(self)
        self.setCentralWidget(self.canvas)
        self.canvas.setESize(40)
    def showEvent(self, e):
        super().showEvent(e)
        set_click_through(self, True)

        screen_size=QApplication.primaryScreen().size()
        self.move(0,0)
        self.resize(screen_size.width(),screen_size.height())
    
class GetMouseInput(QWidget):
    def __init__(self,parent):
        super().__init__(parent)
        self.isfullscreen=True
        #继承父窗口
        self.canvas = self.parent().canvas

        self.setWindowTitle("SPP-GMI")
        self.setMouseTracking(True)
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.WindowCloseButtonHint|Qt.WindowType.FramelessWindowHint)
        self.setWindowOpacity(0.01)
    def hideWin(self):
        self.isfullscreen=False
        self.canvas.hide_hover()
        self.unlock()
    def ifshow(self):
        if self.isfullscreen:
            pass
        else:
            self.isfullscreen=True
            self.lock()
    def lock(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,False)
        set_click_through(self, False)
        #恢复
        screen_size=QApplication.primaryScreen().size()
        self.move(0,0)
        self.parent().move(0,0)
        self.resize(screen_size.width(),screen_size.height())
        self.parent().resize(screen_size.width(),screen_size.height())
    def unlock(self):
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        set_click_through(self, True)
        #减少屏幕底部1像素，防止任务栏失踪
        screen_size=QApplication.primaryScreen().size()
        self.move(0,0)
        self.parent().move(0,0)
        self.resize(screen_size.width(),screen_size.height()-1)
        self.parent().resize(screen_size.width(),screen_size.height()-1)
    def mousePressEvent(self, a0):
        if a0.button() == Qt.MouseButton.LeftButton:
            return self.canvas.mousePressEvent(a0)
        else:
            t.showSettings(a0.pos(),isc=True)
    def mouseMoveEvent(self, a0):
        return self.canvas.mouseMoveEvent(a0)
    def mouseReleaseEvent(self, a0):
        if a0.button() == Qt.MouseButton.LeftButton:
            return self.canvas.mouseReleaseEvent(a0)
    def keyPressEvent(self, a0):
        return self.canvas.keyPressEvent(a0)
    def showEvent(self, a0):
        screen_size=QApplication.primaryScreen().size()
        self.move(0,0)
        self.resize(screen_size.width(),screen_size.height())
        return super().showEvent(a0)
        
        
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = mainWin()
    w.show()

    l=GetMouseInput(w)
    l.show()

    t=childWin(l)
    t.show()

    sys.exit(app.exec())
