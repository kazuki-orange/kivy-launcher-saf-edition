# -*- coding: utf-8 -*-
"""
SAF (Storage Access Framework) とキャッシュディレクトリ間の
ファイル転送を担うモジュール。

Classes:
    MimeResolver -- MIME タイプ推定ロジック
    SAFTransfer  -- SAF ↔ キャッシュ間のファイル転送
"""

import sys, os
import mimetypes

from kivy.utils import platform

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_paths import AppPaths

if platform == 'android':
    from jnius import autoclass
    DocumentFile     = autoclass('androidx.documentfile.provider.DocumentFile')
    Uri              = autoclass('android.net.Uri')
    Channels         = autoclass('java.nio.channels.Channels')
    FileInputStream  = autoclass('java.io.FileInputStream')
    FileOutputStream = autoclass('java.io.FileOutputStream')
    ByteBuffer       = autoclass('java.nio.ByteBuffer')


# ──────────────────────────────────────────────────────────────
# MimeResolver
# ──────────────────────────────────────────────────────────────

class MimeResolver:
    """
    ファイル名・バイト列から MIME タイプを多段階で推定するクラス。
    インスタンス化不要。すべて staticmethod で提供。

    Usage:
        mime = MimeResolver.guess("example.kv")
        mime = MimeResolver.guess("unknown_file", file_header=header_bytes)
    """

    _EXTRA_MIME: dict[str, str] = {
        '.kv':  'text/plain',
        '.ttc': 'font/ttc',
        '.ttf': 'font/ttf',
        '.otf': 'font/otf',
        '.py':  'text/x-python',
    }

    _MAGIC_SIGNATURES: dict[bytes, str] = {
        b'\x89PNG\r\n\x1a\n':    'image/png',
        b'\xff\xd8\xff':         'image/jpeg',
        b'GIF87a':               'image/gif',
        b'GIF89a':               'image/gif',
        b'%PDF':                 'application/pdf',
        b'PK\x03\x04':           'application/zip',
        b'\x1f\x8b':             'application/gzip',
        b'RIFF':                 'audio/wav',
        b'ID3':                  'audio/mpeg',
        b'\xff\xfb':             'audio/mpeg',
        b'OggS':                 'audio/ogg',
        b'fLaC':                 'audio/flac',
    }

    for _ext, _mime in _EXTRA_MIME.items():
        mimetypes.add_type(_mime, _ext)

    @staticmethod
    def guess(filename: str, file_header: bytes | None = None) -> str:
        """
        MIME タイプを多段階で推定する。

        優先順位:
          1. _EXTRA_MIME テーブル（拡張子完全一致）
          2. mimetypes 標準ライブラリ
          3. マジックバイト（file_header が渡された場合）
          4. フォールバック: 'application/octet-stream'

        Args:
            filename    : ファイル名（拡張子を含む）
            file_header : ファイル先頭バイト列（省略可）

        Returns:
            str: 推定された MIME タイプ
        """
        ext = os.path.splitext(filename)[1].lower()

        if ext in MimeResolver._EXTRA_MIME:
            return MimeResolver._EXTRA_MIME[ext]

        mime, _ = mimetypes.guess_type(filename)
        if mime:
            return mime

        if file_header:
            magic_mime = MimeResolver._from_magic(file_header)
            if magic_mime:
                return magic_mime

        return 'application/octet-stream'

    @staticmethod
    def _from_magic(header: bytes) -> str | None:
        """マジックバイトから MIME を推定する内部メソッド。"""
        for sig, mime in MimeResolver._MAGIC_SIGNATURES.items():
            if header.startswith(sig):
                return mime
        return None


# ──────────────────────────────────────────────────────────────
# SAFTransfer
# ──────────────────────────────────────────────────────────────

class SAFTransfer:
    """
    SAF ツリー URI ↔ ローカルキャッシュ間のファイル転送クラス。
    MimeResolver・AppPaths に依存する。
    インスタンス化不要。すべて staticmethod で提供。

    Usage:
        SAFTransfer.copy_to_cache()
        SAFTransfer.writeback_to_saf(filenames=["config.kv"])
        SAFTransfer.clear_cache()
    """

    @staticmethod
    def copy_to_cache(
        uri_str: str = 'auto',
        dest_dir: str = 'auto',
        subpath: str = 'auto',
        filenames: list[str] | str = 'auto',
        dirnames: list[str] | str = 'auto',
        log=print,
    ) -> None:
        """
        SAF ツリーのフォルダをローカルキャッシュへコピー。

        Args:
            uri_str   : SAF ツリー URI（'auto' で SharedPreferences から取得）
            dest_dir  : コピー先ローカルディレクトリ（'auto' で SharedPreferences から取得）
            subpath   : コピー元サブフォルダ（'/' 区切り相対パス、None でルート、'auto' で SharedPreferences から取得）
            filenames : コピー対象ファイル名リスト。'auto' の場合は全ファイル
            dirnames  : コピー対象フォルダ名リスト。'auto' の場合は全フォルダ
                        filenames・dirnames 両方 'auto' → 全再帰コピー
            log       : ログ関数
        """
        if platform != 'android':
            log("SAFTransfer.copy_to_cache: Android only")
            return

        uri_str  = AppPaths.selected_uri()     if uri_str  == 'auto' else uri_str
        dest_dir = AppPaths.temp_dir()         if dest_dir == 'auto' else dest_dir
        subpath  = AppPaths.selected_subpath() if subpath  == 'auto' else subpath

        from jnius import autoclass
        PythonActivity   = autoclass('org.kivy.android.PythonActivity')
        context          = PythonActivity.mActivity
        content_resolver = context.getContentResolver()

        root_uri = Uri.parse(uri_str)
        root_doc = DocumentFile.fromTreeUri(context, root_uri)
        if not root_doc or not root_doc.isDirectory():
            log(f"Invalid SAF URI: {uri_str}")
            return

        source_doc = SAFTransfer._resolve_subpath(root_doc, subpath, log)
        if source_doc is None:
            return

        def _copy_file(doc_file, local_dir):
            os.makedirs(local_dir, exist_ok=True)
            dest_path = os.path.join(local_dir, doc_file.getName())
            try:
                raw_stream  = content_resolver.openInputStream(doc_file.getUri())
                in_channel  = Channels.newChannel(raw_stream)
                fos         = FileOutputStream(dest_path)
                out_channel = fos.getChannel()
                buf = ByteBuffer.allocateDirect(1024 * 1024)
                while True:
                    buf.clear()
                    n = in_channel.read(buf)
                    if n == -1:
                        break
                    buf.flip()
                    out_channel.write(buf)
                out_channel.close()
                in_channel.close()
                fos.close()
                raw_stream.close()
            except Exception as e:
                log(f"Copy error [{doc_file.getName()}]: {e}")

        def _recursive_copy(doc_dir, local_dir):
            os.makedirs(local_dir, exist_ok=True)
            for f in doc_dir.listFiles():
                if f.isDirectory():
                    _recursive_copy(f, os.path.join(local_dir, f.getName()))
                else:
                    _copy_file(f, local_dir)

        if filenames == 'auto' and dirnames == 'auto':
            _recursive_copy(source_doc, dest_dir)
        else:
            file_set        = set(filenames) if filenames != 'auto' else None
            dir_set         = set(dirnames)  if dirnames  != 'auto' else None
            not_found_files = set(filenames) if file_set  is not None else set()
            not_found_dirs  = set(dirnames)  if dir_set   is not None else set()

            for f in source_doc.listFiles():
                name = f.getName()
                if f.isDirectory():
                    if dir_set is None or name in dir_set:
                        _recursive_copy(f, os.path.join(dest_dir, name))
                        not_found_dirs.discard(name)
                else:
                    if file_set is None or name in file_set:
                        _copy_file(f, dest_dir)
                        not_found_files.discard(name)

            for name in not_found_files:
                log(f"File not found in SAF: {name}")
            for name in not_found_dirs:
                log(f"Directory not found in SAF: {name}")

        log(f"SAF -> cache copy complete: {dest_dir} (from {subpath or 'root'})")

    @staticmethod
    def writeback_to_saf(
        src_dir: str = 'auto',
        uri_str: str = 'auto',
        subpath: str = 'auto',
        filenames: list[str] | str = 'auto',
        dirnames: list[str] | str = 'auto',
        log=print,
    ) -> None:
        """
        ローカルキャッシュを SAF ツリーへ書き戻す。

        Args:
            src_dir   : 書き戻し元ローカルディレクトリ（'auto' で SharedPreferences から取得）
            uri_str   : SAF ツリー URI（'auto' で SharedPreferences から取得）
            subpath   : 書き戻し先サブフォルダ（'/' 区切り相対パス、None でルート、'auto' で SharedPreferences から取得）
            filenames : 書き戻し対象ファイル名リスト。'auto' の場合は全ファイル
            dirnames  : 書き戻し対象フォルダ名リスト。'auto' の場合は全フォルダ
                        filenames・dirnames 両方 'auto' → 全再帰書き戻し
            log       : ログ関数
        """
        if platform != 'android':
            log("SAFTransfer.writeback_to_saf: Android only")
            return

        src_dir = AppPaths.temp_dir()          if src_dir == 'auto' else src_dir
        uri_str = AppPaths.selected_uri()      if uri_str == 'auto' else uri_str
        subpath = AppPaths.selected_subpath()  if subpath == 'auto' else subpath

        if not os.path.exists(src_dir):
            log(f"Source directory does not exist: {src_dir}")
            return

        from jnius import autoclass
        PythonActivity   = autoclass('org.kivy.android.PythonActivity')
        context          = PythonActivity.mActivity
        content_resolver = context.getContentResolver()

        root_doc = DocumentFile.fromTreeUri(context, Uri.parse(uri_str))
        if not root_doc:
            log(f"Invalid SAF URI: {uri_str}")
            return

        target_doc = SAFTransfer._ensure_subpath(root_doc, subpath, log)
        if target_doc is None:
            return

        def _writeback_file(local_path, doc_dir):
            name = os.path.basename(local_path)
            dest_file = doc_dir.findFile(name)
            if dest_file is not None:
                dest_file.delete()
            with open(local_path, 'rb') as f:
                header = f.read(16)
                data   = header + f.read()
            mime      = MimeResolver.guess(name, file_header=header)
            dest_file = doc_dir.createFile(mime, name)
            if dest_file is None:
                log(f"Cannot create SAF file: {name}")
                return
            try:
                out_stream = content_resolver.openOutputStream(dest_file.getUri())
                out_stream.write(data, 0, len(data))
                out_stream.flush()
                out_stream.close()
            except Exception as e:
                log(f"Writeback error [{name}]: {e}")

        def _recursive_writeback(local_dir, doc_dir):
            for name in os.listdir(local_dir):
                local_path = os.path.join(local_dir, name)
                if os.path.isdir(local_path):
                    sub_doc = doc_dir.findFile(name)
                    if sub_doc is None or not sub_doc.isDirectory():
                        sub_doc = doc_dir.createDirectory(name)
                    _recursive_writeback(local_path, sub_doc)
                else:
                    _writeback_file(local_path, doc_dir)

        if filenames == 'auto' and dirnames == 'auto':
            _recursive_writeback(src_dir, target_doc)
        else:
            file_set = set(filenames) if filenames != 'auto' else None
            dir_set  = set(dirnames)  if dirnames  != 'auto' else None

            for name in os.listdir(src_dir):
                local_path = os.path.join(src_dir, name)
                if os.path.isdir(local_path):
                    if dir_set is None or name in dir_set:
                        sub_doc = target_doc.findFile(name)
                        if sub_doc is None or not sub_doc.isDirectory():
                            sub_doc = target_doc.createDirectory(name)
                        _recursive_writeback(local_path, sub_doc)
                else:
                    if file_set is None or name in file_set:
                        _writeback_file(local_path, target_doc)

        log(f"Cache -> SAF writeback complete: {uri_str} / {subpath or ''}")

    @staticmethod
    def clear_cache(log=print) -> None:
        """
        キャッシュディレクトリ内のファイル・サブディレクトリをすべて削除する。
        ディレクトリ自体は保持する。

        Args:
            log: ログ関数（デフォルトは print）
        """
        import shutil
        temp_dir = AppPaths.temp_dir()
        if not os.path.exists(temp_dir):
            log(f"Cache already empty: {temp_dir}")
            return

        for name in os.listdir(temp_dir):
            path = os.path.join(temp_dir, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

        log(f"Cache cleared: {temp_dir}")

    # ── 内部ユーティリティ ────────────────────────────────────

    @staticmethod
    def _resolve_subpath(root_doc, subpath: str, log) -> 'DocumentFile | None':
        """subpath を辿って DocumentFile を返す。見つからなければ None。"""
        if not subpath:
            return root_doc
        current = root_doc
        for part in subpath.strip('/').split('/'):
            found = current.findFile(part)
            if found and found.isDirectory():
                current = found
            else:
                log(f"Subpath not found: {part}")
                return None
        return current

    @staticmethod
    def _ensure_subpath(root_doc, subpath: str, log) -> 'DocumentFile | None':
        """subpath を辿り、なければ作成して DocumentFile を返す。失敗時は None。"""
        if not subpath:
            return root_doc
        current = root_doc
        for part in subpath.strip('/').split('/'):
            found = current.findFile(part)
            if found and found.isDirectory():
                current = found
            else:
                current = current.createDirectory(part)
                if current is None:
                    log(f"Cannot create directory: {part}")
                    return None
        return current