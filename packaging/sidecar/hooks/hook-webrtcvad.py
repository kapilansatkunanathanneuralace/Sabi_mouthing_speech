"""Avoid contrib hook metadata lookup for webrtcvad-wheels."""

from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = collect_dynamic_libs("webrtcvad")
datas = []
hiddenimports = []
