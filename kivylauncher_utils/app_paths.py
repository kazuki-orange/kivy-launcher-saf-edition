# -*- coding: utf-8 -*-
"""
アプリが使用するパス・URI を提供するモジュール。

Classes:
    AppPaths -- パス・URI 取得
"""

import os

from kivy.utils import platform


class AppPaths:
    """
    アプリが使用するパス・URI を取得するクラス。
    SharedPreferences およびシステム API へのアクセスを集約する。
    インスタンス化不要。すべて staticmethod で提供。

    Usage:
        temp_dir = AppPaths.temp_dir()
        uri      = AppPaths.selected_uri()
        subpath  = AppPaths.selected_subpath()
    """

    _PREFS_NAME = "LauncherPrefs"

    @staticmethod
    def temp_dir() -> str:
        """
        キャッシュディレクトリの絶対パスを返す。

        Returns:
            str: Android では getCacheDir()/temp_app、
                 デスクトップでは ~/.kivylauncher/temp_app
        """
        if platform == 'android':
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity.getApplicationContext()
            return os.path.join(context.getCacheDir().getAbsolutePath(), "temp_app")
        return os.path.join(os.path.expanduser("~"), ".kivylauncher", "temp_app")

    @staticmethod
    def selected_uri() -> str:
        """
        SharedPreferences に保存された SAF URI を返す。

        Returns:
            str: SAF ツリー URI 文字列。未設定の場合は空文字。
        """
        if platform != 'android':
            return ''
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Context  = autoclass('android.content.Context')
        activity = PythonActivity.mActivity
        prefs = activity.getSharedPreferences(
            AppPaths._PREFS_NAME, Context.MODE_PRIVATE
        )
        return prefs.getString("selected_uri", "")

    @staticmethod
    def selected_subpath() -> str:
        """
        SharedPreferences に保存された subpath を返す。

        Returns:
            str: subpath 文字列。未設定の場合は空文字。
        """
        if platform != 'android':
            return ''
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Context  = autoclass('android.content.Context')
        activity = PythonActivity.mActivity
        prefs = activity.getSharedPreferences(
            AppPaths._PREFS_NAME, Context.MODE_PRIVATE
        )
        return prefs.getString("selected_subpath", "")