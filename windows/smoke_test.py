"""Offline startup check shared by source runs and the frozen release."""
import json
from pathlib import Path
import tempfile

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QSettings, QTimer, qVersion
from PySide6.QtWidgets import QApplication
import requests


def run(window_class, output):
    app = QApplication([])
    report = {'ok': False, 'pyside': pyside_version, 'qt': qVersion()}
    failures = []
    original_request = requests.sessions.Session.request

    def reject_network(*args, **kwargs):
        raise RuntimeError('The offline startup check must not access the network.')

    requests.sessions.Session.request = reject_network
    with tempfile.TemporaryDirectory(prefix='pawchive_startup_check_') as directory:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, directory)
        window = window_class()
        cache = window.cache_dir

        def check():
            try:
                if window.windowIcon().isNull():
                    raise RuntimeError('The bundled application icon is missing.')
                if window.start.isEnabled():
                    raise RuntimeError('Download must be disabled without a profile and folder.')
                window.profile.setText('https://pawchive.pw/fanbox/user/offline-check')
                if window.start.isEnabled():
                    raise RuntimeError('Download must be disabled without a folder.')
                window.path.setText(directory)
                window.validate_profile()
                if not window.start.isEnabled():
                    raise RuntimeError('Download validation did not accept the test inputs.')
                window.profile.clear()
                window.language.setCurrentIndex(2)
                window.language.setCurrentIndex(0)
                window.progress.setValue(45)
                window.grab()  # Exercise painting of controls, gradients and the icon.
                window.theme.click()
                app.processEvents()
                window.grab()
                window.theme.click()
                app.processEvents()
                window.grab()
                report.update(ok=True, checks=[
                    'QtCore/QtGui/QtWidgets import', 'native GUI startup',
                    'bundled icon', 'input validation', 'language switching',
                    'theme switching', 'rainbow progress painting'])
            except Exception as error:
                failures.append(str(error))
            finally:
                window.close()
                app.quit()

        window.show()
        QTimer.singleShot(350, check)
        app.exec()
        report['cache_removed'] = not cache.exists()
        report['ok'] = report['ok'] and report['cache_removed'] and not failures
        if failures:
            report['errors'] = failures
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    requests.sessions.Session.request = original_request
    return 0 if report['ok'] else 1
