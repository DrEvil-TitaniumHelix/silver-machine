"""Click-only native folder picker, isolated from the HTTP server's threads."""
import json
from pathlib import Path
import subprocess
import sys
from threading import Lock

_picker = Lock()
UNAVAILABLE = 'Native folder browsing is unavailable. Install Python with Tk support, or type the folder path.'


def browse():
    if not _picker.acquire(blocking=False):
        return dict(ok=False, message='A folder dialog is already open. Choose a folder or cancel it.'), 409
    try:
        # Tk owns its process/main thread, so Tcl cleanup cannot race HTTP workers.
        result = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve())],
                                capture_output=True, text=True, encoding='utf-8',
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode: return dict(ok=False, message=UNAVAILABLE), 503
        value = json.loads(result.stdout)
        return value, 200 if value.get('ok') else 503
    except (OSError, ValueError):
        return dict(ok=False, message=UNAVAILABLE), 503
    finally:
        _picker.release()


def main():
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        # An invisible owner can take focus before Windows enters its native
        # modal loop; a withdrawn owner alone can leave the browser foreground.
        root.attributes('-alpha', 0)
        root.geometry('1x1+0+0')
        root.deiconify()
        root.lift()
        root.focus_force()
        root.update()
        folder = filedialog.askdirectory(parent=root, title='Choose your game folder', mustexist=True)
        return dict(ok=True, folder=folder or '', cancelled=not bool(folder))
    except (ImportError, RuntimeError, OSError) as error:
        return dict(ok=False, message=UNAVAILABLE)
    except Exception:
        # Includes TclError on machines without a graphical desktop.
        return dict(ok=False, message=UNAVAILABLE)
    finally:
        if root is not None: root.destroy()


if __name__ == '__main__':
    print(json.dumps(main(), ensure_ascii=True))
