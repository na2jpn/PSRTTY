"""Independent tool lifetimes and native ownership for Windows stacking."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from tests import test_ui_v02 as fixture
from psrtty.ui.direct_tx import DirectTxWindow
from psrtty.ui.shortcut_guide import ShortcutGuide
from psrtty.ui.cross_scope import CrossScopeWindow
from psrtty.ui.control_window import ControlWindow
from psrtty.ui.sub_decode import SubDecodeWindow
from psrtty.ui.window_state import save_window
from psrtty.live_tx import LiveText
from psrtty.i18n import configure

class UI109Fix1Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    pump=fixture.UITests.pump

    def open_tools(self):
        w=self.window
        w.direct_window=DirectTxWindow(w)
        w.shortcut_window=ShortcutGuide(w)
        w.scope_window=CrossScopeWindow(w.audio,w)
        w.control_window=ControlWindow(w)
        w.sub_window=SubDecodeWindow(w)
        tools=[w.direct_window,w.shortcut_window,w.scope_window,w.control_window,w.sub_window]
        for tool in tools:tool.show()
        self.pump(.02)
        return tools

    def test_native_owner_absent_on_all_five_windows(self):
        for tool in self.open_tools():
            with self.subTest(window=type(tool).__name__):
                self.assertIsNone(tool.parentWidget())
                self.assertTrue(tool.isWindow())
                self.assertEqual(tool.windowModality(),Qt.NonModal)
                self.assertFalse(tool.windowFlags() & Qt.WindowStaysOnTopHint)
                self.assertIsNone(tool.windowHandle().transientParent())
                self.assertEqual(tool.windowIcon().cacheKey(),self.window.windowIcon().cacheKey())
                self.assertIn('#fffaf3',tool.styleSheet())

    def test_main_focus_retains_visible_tools_and_background_work(self):
        w=self.window;tools=self.open_tools();d=w.direct_window
        session=LiveText('CQ',0,True);d.session=session;w.active_tx_id=72
        try:
            with patch.object(w,'_stop_tx') as stop,patch.object(w.sub_window.worker,'stop') as sub_stop:
                w.show();w.raise_();w.activateWindow();self.pump(.03)
                self.assertTrue(all(t.isVisible() for t in tools))
                self.assertIs(d.session,session);self.assertEqual(w.active_tx_id,72)
                self.assertTrue(w.scope_window.timer.isActive());self.assertTrue(w.scope_window.fade_timer.isActive())
                self.assertTrue(w.sub_window.timer.isActive());self.assertIs(w.audio.sub_worker,w.sub_window.worker)
                stop.assert_not_called();sub_stop.assert_not_called()
        finally:w.active_tx_id=None;d.finished()

    def test_cross_scope_position_saved_without_widget_parent(self):
        w=self.window;w.scope_window=CrossScopeWindow(w.audio,w);s=w.scope_window
        s.show();self.pump(.02);s.setGeometry(30,40,330,365)
        expected=save_window(s);s.close()
        self.assertEqual(w.store.data['ui']['scope_window'],expected)
        self.assertFalse(w.audio.scope_enabled);self.assertFalse(s.timer.isActive())

    def test_main_shutdown_closes_all_independent_tools(self):
        tools=self.open_tools();self.window.close();self.pump(.15)
        self.assertTrue(all(not t.isVisible() for t in tools))
        self.assertIsNone(self.window.audio.sub_worker)
        self.assertFalse(self.window.scope_window.timer.isActive())
        self.assertFalse(self.window.direct_window.timer.isActive())

    def test_direct_recall_and_keys_after_detaching_native_owner(self):
        w=self.window;w._open_direct();d=w.direct_window;d.close();w._open_direct()
        self.assertIs(w.direct_window,d);self.assertTrue(d.isVisible())
        with patch('psrtty.ui.main_window.QApplication.activeWindow',return_value=w),patch.object(d,'focus_input') as focus,patch.object(d,'toggle') as toggle:
            w._direct_key(11);focus.assert_called_once();toggle.assert_not_called()
        with patch('psrtty.ui.main_window.QApplication.activeWindow',return_value=d),patch.object(d,'toggle') as toggle:
            w._direct_key(11);toggle.assert_called_once()
        w._toggle_direct();self.assertFalse(d.isVisible())

    def test_english_titles_survive_independent_window_style(self):
        configure('en')
        try:
            tools=self.open_tools()
            self.assertEqual(tools[0].windowTitle(),'Direct TX')
            self.assertEqual(tools[1].windowTitle(),'Keyboard shortcut guide')
            self.assertNotIn('サブデコ',tools[4].windowTitle())
        finally:configure('ja')
