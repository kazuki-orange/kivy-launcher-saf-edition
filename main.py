# -*- coding: utf-8 -*-

def run_entrypoint(entrypoint, app_dir=None):
    import runpy
    import sys
    import os
    import traceback

    # 1. 現在のディレクトリを覚えておく
    original_cwd = os.getcwd()

    # モジュールキャッシュのクリーンアップ用に初期スナップショットを取得
    initial_modules = dict(sys.modules)

    if app_dir:
        os.chdir(app_dir)
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)

    try:
        runpy.run_path(entrypoint, run_name="__main__")
    except Exception:
        traceback.print_exc()
    finally:
        # 2. 【重要】子アプリがどう終わっても、必ず元の場所に戻る
        os.chdir(original_cwd)
        if app_dir and app_dir in sys.path:
            sys.path.remove(app_dir)

        # アプリ実行中にロードされたモジュールを削除し、キャッシュの干渉を防ぐ
        for mod_name in list(sys.modules.keys()):
            if mod_name not in initial_modules:
                del sys.modules[mod_name]

def run_launcher():
    from launcher.app import Launcher
    Launcher().run()

def dispatch():
    import os

    # desktop launch
    entrypoint = os.environ.get("KIVYLAUNCHER_ENTRYPOINT")
    if entrypoint is not None:
        return run_entrypoint(entrypoint)

    # try android
    try:
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = activity.getIntent()
        
        # 新版の仕組み: android_argument (キャッシュディレクトリ) を取得
        arg_dir = intent.getStringExtra("android_argument")
        entrypoint = intent.getStringExtra("entrypoint")
        orientation = intent.getStringExtra("orientation")
        
        if orientation == "portrait":
            activity.setRequestedOrientation(0x1) # 縦
        elif orientation == "landscape":
            activity.setRequestedOrientation(0x0) # 横
        elif orientation == "reverse_portrait":
            activity.setRequestedOrientation(0x9) # 逆縦
        elif orientation == "reverse_landscape":
            activity.setRequestedOrientation(0x8) # 逆横

        if arg_dir and entrypoint:
            # キャッシュされたフォルダ内のmain.pyを実行
            target_main = os.path.join(arg_dir, entrypoint)
            return run_entrypoint(target_main, app_dir=arg_dir)
        
        elif entrypoint is not None:
            # 従来通りの直接パス実行
            return run_entrypoint(entrypoint)

    except Exception:
        import traceback
        traceback.print_exc()

    run_launcher()

if __name__ == "__main__":
    dispatch()
