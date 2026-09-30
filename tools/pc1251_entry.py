"""PyInstaller 用エントリポイント

`pc1251emu.app` をパッケージとして読み込み、CLI/アプリを起動する。
"""

from pc1251emu.app import cli

if __name__ == "__main__":
    cli()
