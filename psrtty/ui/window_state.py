"""Logical-pixel window placement, bounded by the available monitor area."""
from PySide6.QtCore import QRect
from PySide6.QtGui import QGuiApplication

DEFAULT_SIZE = (1280, 800)


def fitted_rect(saved, areas, reset=False, margins=(0, 0, 0, 0)):
    primary = areas[0]
    valid = (isinstance(saved, dict) and all(type(saved.get(k)) is int for k in ('x','y','w','h'))
             and 0 < saved['w'] < 100000 and 0 < saved['h'] < 100000
             and abs(saved['x']) < 1000000 and abs(saved['y']) < 1000000)
    rect = QRect(saved['x'], saved['y'], saved['w'], saved['h']) if valid and not reset else None
    area = primary
    if rect:
        overlaps = [max(0, a.intersected(rect).width()) * max(0, a.intersected(rect).height()) for a in areas]
        if max(overlaps): area = areas[overlaps.index(max(overlaps))]
    left, top, right, bottom = margins
    usable = area.adjusted(left, top, -right, -bottom)
    width = min(rect.width() if rect else DEFAULT_SIZE[0], usable.width())
    height = min(rect.height() if rect else DEFAULT_SIZE[1], usable.height())
    result = QRect(0, 0, max(1,width), max(1,height))
    if rect and area.intersects(rect):
        result.moveTo(max(usable.left(), min(rect.x(), usable.right()-width+1)),
                      max(usable.top(), min(rect.y(), usable.bottom()-height+1)))
    else:
        result.moveCenter(usable.center())
    return result


def restore_window(window, saved, reset=False):
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen()
    screens = [primary] + [s for s in screens if s != primary]
    margins = window.windowHandle().frameMargins()
    rect = fitted_rect(saved, [s.availableGeometry() for s in screens], reset,
                       (margins.left(), margins.top(), margins.right(), margins.bottom()))
    window.setGeometry(rect)
    if not reset and isinstance(saved, dict) and saved.get('maximized') is True:
        window.showMaximized()
    window._refresh_macros()


def save_window(window):
    rect = window.normalGeometry() if window.isMaximized() or window.isMinimized() else window.geometry()
    return dict(x=rect.x(), y=rect.y(), w=rect.width(), h=rect.height(), maximized=window.isMaximized())
