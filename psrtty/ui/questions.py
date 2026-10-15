"""Explicitly localized confirmation buttons, independent of OS language."""
from PySide6.QtWidgets import QMessageBox
from ..i18n import tr

def ask_question(parent,title,text,yes_key='qt.10',no_key='qt.12'):
    box=QMessageBox(parent)
    box.setWindowTitle(title);box.setIcon(QMessageBox.Question);box.setText(text)
    # A native Windows dialog may use the OS UI language rather than the app's.
    box.setOption(QMessageBox.Option.DontUseNativeDialog,True)
    box.setStandardButtons(QMessageBox.Yes|QMessageBox.No)
    box.button(QMessageBox.Yes).setText(tr(yes_key))
    box.button(QMessageBox.No).setText(tr(no_key))
    box.setDefaultButton(QMessageBox.No);box.setEscapeButton(QMessageBox.No)
    return box.exec()
