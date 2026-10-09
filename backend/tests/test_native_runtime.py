from types import SimpleNamespace
import unittest
from unittest.mock import patch
from app.core.native_runtime import prepare_torch_runtime

class NativeRuntimeTests(unittest.TestCase):
    def test_windows_preloads_installed_torch(self):
        with patch('app.core.native_runtime.sys.platform','win32'), \
             patch('app.core.native_runtime.importlib.util.find_spec',return_value=SimpleNamespace()), \
             patch('app.core.native_runtime.importlib.import_module') as load:
            self.assertTrue(prepare_torch_runtime())
            load.assert_called_once_with('torch')

    def test_missing_torch_keeps_basic_mode_available(self):
        with patch('app.core.native_runtime.sys.platform','win32'), \
             patch('app.core.native_runtime.importlib.util.find_spec',return_value=None), \
             patch('app.core.native_runtime.importlib.import_module') as load:
            self.assertFalse(prepare_torch_runtime())
            load.assert_not_called()

    def test_non_windows_does_not_force_a_preload(self):
        with patch('app.core.native_runtime.sys.platform','linux'), \
             patch('app.core.native_runtime.importlib.import_module') as load:
            self.assertFalse(prepare_torch_runtime())
            load.assert_not_called()

    def test_ocr_preload_uses_the_same_guard_first(self):
        from app.rag.ocr.paddleocr_engine import _preload_paddle
        events=[]
        with patch('app.core.native_runtime.prepare_torch_runtime',side_effect=lambda:events.append('torch')), \
             patch('app.rag.ocr.paddleocr_engine.importlib.import_module',side_effect=lambda name:events.append(name)):
            _preload_paddle()
        self.assertEqual(events,['torch','paddle'])
