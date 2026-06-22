# Kivy Launcher SAF Edition

A modern, unofficial update to the original Kivy Launcher, specifically redesigned for newer Android versions (Android 10+).

## Why Kivy Launcher SAF Edition?

The original Kivy Launcher struggled with modern Android's **Scoped Storage** and **Storage Access Framework (SAF)** requirements. On newer Android devices, apps can no longer freely access `/sdcard/kivy`.

**Kivy Launcher SAF Edition** solves this by:
1.  **Using SAF:** Letting you pick any folder using the native Android directory picker.
2.  **Copy-to-Cache Execution:** Automatically copying your Kivy app to a private internal cache directory before execution. This ensures that standard Python features like `import`, `open()`, and `os.chdir()` work perfectly, even when the source files are in restricted storage areas.

## Key Features

-   **Full SAF Support:** Access projects from internal storage, SD cards, or even cloud providers that support the Android Document Provider API.
-   **Modern Android Compatibility:** Works seamlessly on Android 11, 12, 13, and 14.
-   **Persistent Permissions:** Remembers your selected project folder across restarts.
-   **Dynamic Orientation:** Supports `portrait`, `landscape`, `reverse_portrait`, and `reverse_landscape` settings via `android.txt`.
-   **Clean Environment:** Automatically resets the working directory and system path between app launches to prevent cross-contamination.

## How to Use

### 1. Prepare your Kivy Projects
Organize your projects in a single root folder (e.g., a folder named `my_kivy_apps`). Each app should be in its own subfolder:

```text
my_kivy_apps/
├── Project1/
│   ├── main.py
│   ├── android.txt
│   └── icon.png (optional)
└── Project2/
    ├── main.py
    └── android.txt
```

### 2. Create `android.txt`
In each project folder, create a file named `android.txt` to define the app's metadata:

```ini
title=My Cool App
author=Your Name
orientation=portrait
logo=icon.png (optional)
```

### 3. Launch with Kivy Launcher SAF Edition
1.  Open **Kivy Launcher SAF Edition** on your Android device.
2.  Tap **"Select Folder"**.
3.  Use the system picker to navigate to and select your `my_kivy_apps` folder.
4.  Your apps will appear in the list. Tap one to launch!

## Technical Implementation Notes

### The Copy-to-Cache Loop
Because Python's standard library cannot interact directly with `content://` URIs provided by SAF, Kivy Launcher SAF Edition performs a "Recursive Copy" from the SAF URI to the app's internal `cache` directory (`/data/user/0/.../cache/temp_app`). 
-   The app is then executed from this local filesystem path.
-   This allows for 100% compatibility with existing Kivy apps without code changes.

### Entrypoint Execution
The launcher uses `runpy.run_path()` to execute `main.py`. It carefully manages `os.chdir()` and `sys.path` to ensure the sub-app feels like it's running as a standalone application.

## Development & Building

If you want to build this launcher yourself, use [Buildozer](https://github.com/kivy/buildozer).

```bash
buildozer android debug deploy run
```

### Key Requirements
The project relies on:
-   `pyjnius` for deep Android API integration.
-   Native `androidx.documentfile` for SAF operations.

---
*Note: This is an unofficial community project and is not affiliated with the official Kivy organization.*
