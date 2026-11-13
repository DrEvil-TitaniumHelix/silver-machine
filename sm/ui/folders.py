import json
from pathlib import Path
import subprocess
import sys
from threading import Lock

_picker = Lock()
UNAVAILABLE = 'The folder dialog could not open. Type the folder path instead.'


def browse():
    if not _picker.acquire(blocking=False):
        return dict(ok=False, message='A folder dialog is already open. Choose a folder or cancel it.'), 409
    try:
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


POWERSHELL = r'%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe'
CSHARP = """
using System; using System.Runtime.InteropServices;
public static class FolderPicker {
  [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialogRCW {}
  [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IFileDialog {
    [PreserveSig] uint Show(IntPtr parent);
    void SetFileTypes(uint n, IntPtr spec); void SetFileTypeIndex(uint i); void GetFileTypeIndex(out uint i);
    void Advise(IntPtr e, out uint c); void Unadvise(uint c); void SetOptions(uint o); void GetOptions(out uint o);
    void SetDefaultFolder(IntPtr i); void SetFolder(IntPtr i); void GetFolder(out IntPtr i); void GetCurrentSelection(out IntPtr i);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string n); void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string n);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string t); void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string t);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string t); void GetResult(out IShellItem i);
  }
  [ComImport, Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItem {
    void BindToHandler(IntPtr b, [MarshalAs(UnmanagedType.LPStruct)] Guid g, [MarshalAs(UnmanagedType.LPStruct)] Guid r, out IntPtr o);
    void GetParent(out IShellItem p); void GetDisplayName(uint s, [MarshalAs(UnmanagedType.LPWStr)] out string n);
  }
  [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
  public static string Pick(string title) {
    var d = (IFileDialog)new FileOpenDialogRCW();
    d.SetOptions(0x20 | 0x40 | 0x800 | 0x1000);   // PICKFOLDERS, FORCEFILESYSTEM, FILEMUSTEXIST, PATHMUSTEXIST
    d.SetTitle(title); d.SetOkButtonLabel("Use this folder");
    if (d.Show(GetForegroundWindow()) != 0) return "";
    IShellItem item; d.GetResult(out item); string path; item.GetDisplayName(0x80058000, out path); return path;
  }
}
"""
PICKER = ("Add-Type -TypeDefinition @'\n" + CSHARP + "\n'@; [Console]::Out.Write([FolderPicker]::Pick('Choose your game folder'))")


def main():
    if sys.platform == 'win32':
        import os
        exe = os.path.expandvars(POWERSHELL)
        try:
            run = subprocess.run([exe, '-NoProfile', '-NonInteractive', '-STA', '-Command', PICKER], capture_output=True,
                                 text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if run.returncode == 0:
                folder = run.stdout.strip()
                return dict(ok=True, folder=folder, cancelled=not bool(folder))
        except OSError:
            pass
    return tk_main()


def tk_main():
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.attributes('-alpha', 0)
        root.geometry('1x1+0+0')
        root.deiconify()
        root.lift()
        root.focus_force()
        root.update()
        folder = filedialog.askdirectory(parent=root, title='Choose your game folder', mustexist=True)
        return dict(ok=True, folder=folder or '', cancelled=not bool(folder))
    except Exception:
        return dict(ok=False, message=UNAVAILABLE)
    finally:
        if root is not None: root.destroy()


if __name__ == '__main__':
    print(json.dumps(main(), ensure_ascii=True))
