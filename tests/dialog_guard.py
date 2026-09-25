"""Non-interactive test boundary. Unexpected dialogs fail instead of hanging.

A test expecting a dialog must patch that specific call and assert its contents.
Installed by UI fixtures only; application operation is unaffected.
"""
import sys
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox, QFileDialog


class DialogGuard:
    def __init__(self):
        self.events=[]
        self.patches=[]

    def _handler(self, name, result):
        def blocked(*args, **kwargs):
            title=kwargs.get('title', args[1] if len(args)>1 else '')
            message=kwargs.get('text', args[2] if len(args)>2 else '')
            event=f'{name}: {title} | {message}'
            self.events.append(event)
            print('UNEXPECTED TEST DIALOG: '+event, file=sys.stderr, flush=True)
            return result
        return blocked

    def start(self):
        for cls,name,result in [
            (QMessageBox,'warning',QMessageBox.Ok),
            (QMessageBox,'critical',QMessageBox.Ok),
            (QMessageBox,'information',QMessageBox.Ok),
            (QMessageBox,'question',QMessageBox.No),
            (QFileDialog,'getOpenFileName',('','')),
            (QFileDialog,'getOpenFileNames',([],'')),
            (QFileDialog,'getSaveFileName',('','')),
            (QFileDialog,'getExistingDirectory',''),
        ]:
            p=patch.object(cls,name,side_effect=self._handler(cls.__name__+'.'+name,result))
            p.start();self.patches.append(p)

    def stop(self):
        for p in reversed(self.patches):p.stop()
        self.patches.clear()
