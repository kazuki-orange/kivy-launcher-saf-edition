# -*- coding: utf-8 -*-
"""
画面遷移・アプリ終了を一元管理するモジュール。

Classes:
    ScreenTransition -- 画面遷移・アプリ起動・停止
"""

import sys, os

from kivy.utils import platform
from kivy.app import App

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_paths import AppPaths
from saf_cache import SAFTransfer


class ScreenTransition:
    """
    画面遷移・アプリ終了を一元管理するユーティリティクラス。
    インスタンス化不要。すべて staticmethod で提供。

    Usage:
        ScreenTransition.to_launcher()
        ScreenTransition.to_app("my_app")
    """

    # ── 公開メソッド ──────────────────────────────────────────

    @staticmethod
    def to_launcher() -> None:
        """
        ランチャー画面へ戻る。
        - Android : ランチャー Activity を再起動しプロセスを終了
        - その他   : Kivy アプリを安全に停止
        """
        if platform == 'android':
            ScreenTransition._android_restart()
        else:
            ScreenTransition._stop_app()

    @staticmethod
    def to_app(app_name: str) -> None:
        """
        ランチャー内の別アプリへ遷移する。
        """
        if platform != 'android':
            print(f"ScreenTransition.to_app: Android only (app_name={app_name})")
            return

        SAFTransfer.clear_cache()
        
        # 1. SAF → キャッシュへコピー（app_name をサブフォルダとして指定）
        # ここで AppPaths.temp_dir() (.../temp_app) の中にファイルが展開される
        SAFTransfer.copy_to_cache(subpath=app_name)

        # キャッシュディレクトリ自体のパス
        cache_dir = AppPaths.temp_dir()
        # 実行ファイル名 (root/main.py の期待値に合わせて相対パスまたはファイル名)
        entry_file = "main.py" 

        entrypoint_full = os.path.join(cache_dir, entry_file)
        if not os.path.exists(entrypoint_full):
            print(f"ScreenTransition.to_app: entrypoint が見つかりません: {entrypoint_full}")
            return

        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity       = PythonActivity.mActivity
            Intent         = autoclass("android.content.Intent")
            String         = autoclass("java.lang.String") # Stringをインポート

            pm = activity.getPackageManager()
            # 常に自分自身のメインActivityを取得
            restart_intent = pm.getLaunchIntentForPackage(activity.getPackageName())

            if restart_intent is None:
                print("ScreenTransition.to_app: Launch Intent が取得できません")
                ScreenTransition._stop_app()
                return

            # フラグの設定 (ランチャーの launch_saf_app と合わせる)
            restart_intent.addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK
            )

            # ── 重要: root/main.py の dispatch() が期待するキーをセット ──
            # 1. キャッシュディレクトリのパス (android_argument)
            restart_intent.putExtra("android_argument", String(cache_dir))
            # 2. エントリポイントのファイル名 (entrypoint)
            restart_intent.putExtra("entrypoint", String(entry_file))
            # 3. 必要に応じて向きも指定（デフォルト空文字）
            restart_intent.putExtra("orientation", String(""))

            # 念のため古い引数を削除
            restart_intent.removeExtra("android_main_py") 

            activity.startActivity(restart_intent)
            activity.finish()
            autoclass("java.lang.System").exit(0)

        except Exception as e:
            print(f"ScreenTransition.to_app: 遷移失敗: {e}")
            ScreenTransition._stop_app()

    # ── 内部メソッド ─────────────────────────────────────────

    @staticmethod
    def _android_restart() -> None:
        """Android でランチャーを再起動する内部処理。"""
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity       = PythonActivity.mActivity
            Intent         = autoclass("android.content.Intent")

            intent = activity.getIntent()
            if intent:
                intent.removeExtra("android_argument")
                intent.removeExtra("entrypoint")

            pm             = activity.getPackageManager()
            restart_intent = pm.getLaunchIntentForPackage(activity.getPackageName())

            if restart_intent:
                restart_intent.addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK
                )
                activity.startActivity(restart_intent)
                activity.finish()
                autoclass("java.lang.System").exit(0)
            else:
                ScreenTransition._stop_app()

        except Exception as e:
            print(f"ScreenTransition: Android restart failed: {e}")
            ScreenTransition._stop_app()

    @staticmethod
    def _stop_app() -> None:
        """実行中の Kivy アプリを安全に停止する内部処理。"""
        app = App.get_running_app()
        if app:
            app.stop()
        else:
            import sys
            sys.exit(0)