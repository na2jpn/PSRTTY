from PySide6.QtWidgets import QGroupBox, QLabel


class HintGroupBox(QGroupBox):
    """A second caption on the right edge, without occupying content height."""
    def __init__(self, title, hint, parent=None):
        super().__init__(title, parent)
        self.hint = QLabel(hint, self)
        self.hint.setStyleSheet('background: #fffaf2; color: #a35108; padding: 0 4px;')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.hint.adjustSize()
        available = max(0, self.width()-self.fontMetrics().horizontalAdvance(self.title())-40)
        self.hint.setVisible(available >= self.hint.sizeHint().width())
        self.hint.move(self.width()-self.hint.width()-12, 0)


class HeaderControlGroupBox(QGroupBox):
    """Keep an interactive control on the top border, outside the content layout."""
    def __init__(self, title, control, parent=None):
        super().__init__(title, parent)
        self.header_control = control
        control.setParent(self)
        control.setStyleSheet('background: #fffdf9; padding: 0 4px;')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.header_control.adjustSize()
        self.header_control.move(max(0, self.width()-self.header_control.width()-12), 0)
        self.header_control.raise_()

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setWidth(max(size.width(), self.fontMetrics().horizontalAdvance(self.title())
                          + self.header_control.sizeHint().width()+40))
        return size


class FooterHintGroupBox(QGroupBox):
    """Place a caption across the bottom border with room for its full height."""
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.footer = QLabel(self)
        self.footer.setStyleSheet('background: #fffaf2; color: #a35108; padding: 0 4px;')

    def set_footer(self, text):
        self.footer.setText(text)
        self._place_footer()
        self.update()

    def _place_footer(self):
        self.footer.adjustSize()
        self.footer.move(max(0, self.width()-self.footer.width()-12), self.height()-self.footer.height())
        self.footer.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_footer()

    def paintEvent(self, event):
        from PySide6.QtWidgets import QStyleOptionGroupBox, QStylePainter, QStyle
        option = QStyleOptionGroupBox()
        self.initStyleOption(option)
        option.rect.adjust(0, 0, 0, -self.footer.height()//2)
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_GroupBox, option)
