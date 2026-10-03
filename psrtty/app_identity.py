"""Configure Windows taskbar identity before creating QApplication."""
import sys
import ctypes
from PySide6.QtGui import QIcon
from .paths import resource_path

APP_ID = 'PSHamware.PSRTTY.Desktop'


def configure_app_identity():
    if sys.platform != 'win32': return
    try:
        function = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = ctypes.c_long
        return function(APP_ID) >= 0
    except (AttributeError, OSError):
        return False


def application_icon():
    icon = QIcon(str(resource_path('assets/psrtty.ico')))
    if icon.isNull(): icon = QIcon(str(resource_path('assets/psrtty.png')))
    return icon
