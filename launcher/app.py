# -*- coding: utf-8 -*-

import os
from datetime import datetime
from kivy.lang import Builder
from kivy.app import App
from kivy.utils import platform
from kivy.properties import ListProperty, BooleanProperty, StringProperty
from glob import glob
from os.path import dirname, join, exists

# Android特有のクラスインポート
if platform == 'android':
    from jnius import autoclass, cast
    from android.activity import bind as activity_bind
    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    Intent = autoclass("android.content.Intent")
    Uri = autoclass("android.net.Uri")
    DocumentFile = autoclass("androidx.documentfile.provider.DocumentFile")
    String = autoclass("java.lang.String")
    Context = autoclass("android.content.Context")


class Launcher(App):
    paths = ListProperty()
    logs = ListProperty()
    display_logs = BooleanProperty(False)
    selected_dir_uri = StringProperty('')

    def log(self, log_msg):
        print(log_msg)
        self.logs.append(f"{datetime.now().strftime('%X.%f')}: {log_msg}")

    def build(self):
        self.log('Launcher build start!')

        if platform == 'android':
            activity_bind(on_activity_result=self._on_activity_result)
            # 1. 保存されたURIを読み込む（self.selected_dir_uri に値が入る）
            self.load_saved_uri()
            
            # 2. SAFのURIがない場合のみ、デフォルトパスを設定する
            if not self.selected_dir_uri:
                Environment = autoclass('android.os.Environment')
                sdcard_path = Environment.getExternalStorageDirectory().getAbsolutePath()
                self.paths = [sdcard_path + "/kivy"]
            else:
                # ログ表示用にパス名を整形
                display_name = self.selected_dir_uri.split('%3A')[-1]
                self.paths = [f"SAF: {display_name}"]
        else:
            self.paths = [os.path.expanduser("~/kivy")]

        self.root = Builder.load_file("launcher/app.kv")
        self.refresh_entries()
        return self.root

    # --- Android用 永続化ロジック ---
    def get_shared_prefs(self):
        activity = PythonActivity.mActivity
        return activity.getSharedPreferences("LauncherPrefs", Context.MODE_PRIVATE)

    def load_saved_uri(self):
        if platform == 'android':
            prefs = self.get_shared_prefs()
            saved_uri = prefs.getString("selected_uri", "")
            if saved_uri:
                self.selected_dir_uri = saved_uri
                self.paths = [f"SAF: {saved_uri.split('%3A')[-1]}"]
                self.log(f"Restored saved URI: {saved_uri}")

    def save_uri(self, uri_str, subpath=''):
        if platform == 'android':
            prefs = self.get_shared_prefs()
            editor = prefs.edit()
            editor.putString("selected_uri", uri_str)
            editor.putString("selected_subpath", subpath)
            editor.apply()
            self.log(f"URI saved. subpath: '{subpath}'")

    # --- SAF ディレクトリ選択 ---
    def open_directory_picker(self):
        if platform == 'android':
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            flags = (Intent.FLAG_GRANT_READ_URI_PERMISSION |
                     Intent.FLAG_GRANT_WRITE_URI_PERMISSION |
                     Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            intent.addFlags(flags)
            PythonActivity.mActivity.startActivityForResult(intent, 1001)
        else:
            self.log("SAF is only available on Android")

    def _on_activity_result(self, request_code, result_code, data):
        if request_code == 1001 and result_code == -1:  # RESULT_OK
            uri = data.getData()

            content_resolver = PythonActivity.mActivity.getContentResolver()
            take_flags = (Intent.FLAG_GRANT_READ_URI_PERMISSION |
                          Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            content_resolver.takePersistableUriPermission(uri, take_flags)

            self.selected_dir_uri = uri.toString()
            self.paths = [f"Selected: {uri.getPath().split(':')[-1]}"]

            self.save_uri(self.selected_dir_uri)
            self.log(f"Access granted to: {self.selected_dir_uri}")
            self.refresh_entries()

    def refresh_entries(self):
        data = []
        self.log('Starting refresh...')

        entries = []
        if platform == 'android' and self.selected_dir_uri:
            self.log(f"Scanning selected SAF folder...")
            entries = list(self.find_entries_saf(self.selected_dir_uri))

        if not entries:
            self.log(f"Scanning default paths: {self.paths}")
            entries = list(self.find_entries(paths=self.paths))

        if not entries:
            self.log("No apps found in the selected directory.")

        for entry in entries:
            data.append({
                "data_title": entry.get("title", "- no title -"),
                "data_path": entry.get("path"),
                "data_logo": entry.get("logo", "data/logo/kivy-icon-64.png"),
                "data_orientation": entry.get("orientation", ""),
                "data_author": entry.get("author", ""),
                "data_entry": entry
            })
        self.root.ids.rv.data = data

    def read_entry_local(self, filename):
        data = {}
        try:
            with open(filename, "r") as fd:
                for line in fd:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        data[k] = v.strip()
        except Exception:
            return None
        
        app_path = dirname(filename)
        data["entrypoint"] = join(app_path, "main.py")
        data["path"] = app_path
        
        # ヒント通り: android.txtのlogo設定か、なければicon.pngを探す
        icon_file = data.get("logo", "icon.png")
        icon_path = join(app_path, icon_file)
        if exists(icon_path):
            data["logo"] = icon_path
        else:
            data["logo"] = "data/logo/kivy-icon-64.png" # デフォルト
            
        return data

    # --- 従来のスキャンロジック ---
    def find_entries(self, path=None, paths=None):
        if paths is not None:
            for path in paths:
                self.log(f"Scanning directory: {path}")
                for entry in self.find_entries(path=path):
                    yield entry
        elif path is not None:
            if not exists(path):
                self.log(f"Path does not exist: {path}")
                return
            for filename in glob("{}/*/android.txt".format(path)):
                entry = self.read_entry_local(filename)
                if entry:
                    self.log(f"Found app: {entry.get('title')} in {os.path.dirname(filename)}")
                    yield entry

    # --- SAFスキャンロジック ---
    def find_entries_saf(self, uri_str):
        try:
            context = PythonActivity.mActivity
            root_uri = Uri.parse(uri_str)
            root_doc = DocumentFile.fromTreeUri(context, root_uri)
            if not root_doc or not root_doc.isDirectory():
                self.log("Invalid SAF directory")
                return

            self.log(f"Scanning SAF URI: {uri_str}")

            for app_dir in root_doc.listFiles():
                if app_dir.isDirectory():
                    conf_file = app_dir.findFile("android.txt")
                    if conf_file:
                        entry = self.read_entry_saf(app_dir, conf_file)
                        if entry:
                            self.log(f"Found SAF app: {entry.get('title')} (Folder: {app_dir.getName()})")
                            yield entry
        except Exception as e:
            self.log(f"SAF Scan Error: {e}")

    def read_entry_saf(self, app_dir, conf_file):
        data = {}
        try:
            context = PythonActivity.mActivity
            content_resolver = context.getContentResolver()
            
            # android.txt の読み込み
            stream = content_resolver.openInputStream(conf_file.getUri())
            Scanner = autoclass('java.util.Scanner')
            scanner = Scanner(stream).useDelimiter("\\A")
            content = scanner.next() if scanner.hasNext() else ""
            stream.close()

            for line in content.splitlines():
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    data[k] = v.strip()
            
            data["path"] = app_dir.getUri().toString()
            data["entrypoint"] = "main.py"
            
            # --- アイコンのキャッシュ処理 ---
            # android.txtにlogo指定があればそれ、なければ icon.png
            target_icon_name = data.get("logo", "icon.png")
            icon_doc = app_dir.findFile(target_icon_name)
            
            if icon_doc:
                # アイコンを一時的に保存するパスを作成（アプリ毎にユニークな名前）
                cache_dir = context.getCacheDir().getAbsolutePath()
                icon_cache_dir = os.path.join(cache_dir, "icons")
                if not os.path.exists(icon_cache_dir):
                    os.makedirs(icon_cache_dir)
                
                # ファイル名が重複しないようアプリのフォルダ名を接頭辞にする
                local_icon_path = os.path.join(icon_cache_dir, f"{app_dir.getName()}_{target_icon_name}")
                
                # アイコンファイルをコピー
                is_stream = content_resolver.openInputStream(icon_doc.getUri())
                j_stream = cast('java.io.InputStream', is_stream)
                
                # 8KBくらいのバッファで十分
                buf = bytearray(8192)
                with open(local_icon_path, "wb") as out_file:
                    while True:
                        size = j_stream.read(buf)
                        if size <= 0:
                            break
                        out_file.write(buf[:size])
                is_stream.close()
                
                data["logo"] = local_icon_path
            else:
                data["logo"] = "data/logo/kivy-icon-64.png" # デフォルト
                
            return data
        except Exception as e:
            self.log(f"Error reading SAF entry: {e}")
            return None

    def start_activity(self, entry):
        if platform == "android":
            self.start_android_activity(entry)
        else:
            self.start_desktop_activity(entry)

    def start_desktop_activity(self, entry):
        import sys
        from subprocess import Popen
        entrypoint = entry["entrypoint"]
        env = os.environ.copy()
        env["KIVYLAUNCHER_ENTRYPOINT"] = entrypoint
        main_py = os.path.realpath(os.path.join(
            os.path.dirname(__file__), "..", "main.py"))
        cmd = Popen([sys.executable, main_py], env=env)

    def start_android_activity(self, entry):
        if entry["path"].startswith("content://"):
            self.launch_saf_app(entry)
        else:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            Intent = autoclass("android.content.Intent")
            String = autoclass("java.lang.String")

            intent = Intent(activity.getApplicationContext(), PythonActivity)
            intent.putExtra("entrypoint", String(entry.get("entrypoint")))
            intent.putExtra("orientation", String(entry.get("orientation")))
            activity.startActivity(intent)
            autoclass("java.lang.System").exit(0)

    def launch_saf_app(self, entry):
        self.log('Copying SAF files to cache...')
        import shutil
        activity = PythonActivity.mActivity
        context = activity.getApplicationContext()
        content_resolver = context.getContentResolver()

        # アプリフォルダ名をsubpathとして保存
        app_uri_str = entry["path"]
        app_doc = DocumentFile.fromTreeUri(context, Uri.parse(app_uri_str))
        app_folder_name = app_doc.getName() if app_doc else ''
        self.save_uri(self.selected_dir_uri, subpath=app_folder_name)
        self.log(f"Saved subpath: '{app_folder_name}'")

        # キャッシュディレクトリの準備
        temp_dir = os.path.join(context.getCacheDir().getAbsolutePath(), "temp_app")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)

        def recursive_copy(document_file, target_path):
            if not os.path.exists(target_path):
                os.makedirs(target_path)

            Channels = autoclass('java.nio.channels.Channels')
            FileOutputStream = autoclass('java.io.FileOutputStream')

            for f in document_file.listFiles():
                dest = os.path.join(target_path, f.getName())
                if f.isDirectory():
                    recursive_copy(f, dest)
                else:
                    try:
                        in_stream = content_resolver.openInputStream(f.getUri())
                        in_channel = Channels.newChannel(in_stream)

                        fos = FileOutputStream(dest)
                        out_channel = fos.getChannel()

                        position = 0
                        chunk = 1024 * 1024
                        while True:
                            transferred = out_channel.transferFrom(in_channel, position, chunk)
                            if transferred <= 0:
                                break
                            position += transferred

                        out_channel.close()
                        fos.close()
                        in_stream.close()
                    except Exception as e:
                        self.log(f"Copy error: {f.getName()} -> {e}")

        try:
            root_doc = DocumentFile.fromTreeUri(context, Uri.parse(entry["path"]))
            recursive_copy(root_doc, temp_dir)

            Intent = autoclass("android.content.Intent")
            String = autoclass("java.lang.String")
            intent = Intent(context, PythonActivity)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK)

            intent.putExtra("android_argument", String(temp_dir))
            intent.putExtra("entrypoint", String("main.py"))
            intent.putExtra("orientation", String(entry.get("orientation", "")))

            activity.startActivity(intent)
            autoclass("java.lang.System").exit(0)
        except Exception as e:
            self.log(f"Launch Error: {e}")