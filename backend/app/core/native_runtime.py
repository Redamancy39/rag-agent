"""Load PyTorch before Paddle's native DLLs on Windows."""
import importlib
import importlib.util
import sys


def prepare_torch_runtime() -> bool:
    if sys.platform != 'win32' or importlib.util.find_spec('torch') is None:
        return False
    # Paddle and Torch ship overlapping native DLL names. Windows reuses loaded
    # DLLs by name; loading Paddle first can make Torch shm.dll fail with 127.
    importlib.import_module('torch')
    return True
