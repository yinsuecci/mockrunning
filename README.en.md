# Route Studio

[简体中文](README.md) · **English**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](#quickstart)
[![iOS and Android](https://img.shields.io/badge/Test%20devices-iOS%20%7C%20Android-2E7D64)](#devices)
[![GitHub stars](https://img.shields.io/github/stars/yinsuecci/mockrunning?style=flat&logo=github)](https://github.com/yinsuecci/mockrunning/stargazers)
[![Download source ZIP](https://img.shields.io/badge/Download-Source%20ZIP-2563EB)](https://github.com/yinsuecci/mockrunning/archive/refs/heads/main.zip)

📣 **Share**
[![Share on X](https://img.shields.io/badge/X-Share-black?logo=x&logoColor=white)](https://x.com/intent/post?url=https%3A%2F%2Fgithub.com%2Fyinsuecci%2Fmockrunning)
[![Share on Telegram](https://img.shields.io/badge/Telegram-Share-26A5E4?logo=telegram&logoColor=white)](https://t.me/share/url?url=https%3A%2F%2Fgithub.com%2Fyinsuecci%2Fmockrunning)

## 🧭 Purpose

Route Studio is a local GPX route editor and location playback tool. Draw, import, or export a route in your browser, then replay simulated locations on an authorized iPhone or Android test device. The web service listens only on loopback; wireless mode connects the computer to the phone without exposing the web controls on your network.

## 📚 Contents

- [Download](#download)
- [Quickstart](#quickstart)
- [Connect a device](#devices)
- [Edit and replay routes](#playback)
- [Limitations and troubleshooting](#limitations)
- [Command line](#cli)

<a name="download"></a>

## 📦 Download

[Download source ZIP](https://github.com/yinsuecci/mockrunning/archive/refs/heads/main.zip) · [View GitHub Releases](https://github.com/yinsuecci/mockrunning/releases)

The ZIP contains source code, not an installer. To get the source with Git:

```bash
git clone https://github.com/yinsuecci/mockrunning.git
cd mockrunning
```

<a name="quickstart"></a>

## 🚀 Quickstart

With Python 3.11 or newer, run from the source directory:

```bash
python -m pip install -e .
ios-location-map
```

1. Open [127.0.0.1:8765](http://127.0.0.1:8765).
2. In the device playback tab (「手机回放」), connect an authorized [test device](#devices) and import [the sample route](routes/sample.gpx).
3. Start playback (「开始移动」). When finished, stop and clear the simulation (「停止并清除模拟」) to request normal location reporting.

<a name="devices"></a>

## 🔌 Connect a Device

- **iPhone:** Trust the computer and enable Developer Mode. Windows requires Apple Mobile Device Support; Linux requires `usbmuxd` and `libimobiledevice`. For a wireless connection using an external tunnel, enter the RSD address and port reported by that trusted tunnel, not the phone's ordinary Wi-Fi IP. Keep the tunnel running. Older iOS versions have limited hardware test coverage.
- **Android:** Enable location and USB debugging, authorize the computer, and make Android SDK Platform-Tools' `adb` available on `PATH` or via `ADB_PATH`. The ROM must support ADB test location providers. For wireless debugging, pair using the pairing address and code, then connect using the separate debugging address.

<a name="playback"></a>

## 🗺️ Edit and Replay Routes

- Draw waypoints in the route editor (「布设路线」), import a GPX, or export the route. Waypoints are joined in order; there is no automatic road routing.
- Load the edited route into device playback, then adjust speed, update interval, or looping. Pause to change parameters. Clearing the loaded route is separate from clearing the browser's editor draft.
- **Simulated steps** are a web-only estimate based on cadence and active playback time. The default is 160 steps/min; zero stops accumulation. Pausing does not add steps. No phone or third-party app receives these counts.

<a name="limitations"></a>

## ⚠️ Limitations and Troubleshooting

- Android test locations retain the system mock flag. A successful send does not mean another app used the position. If a ROM blocks test-provider permissions, ADB discovery alone is not enough.
- The iOS DVT adapter sends latitude and longitude, not horizontal accuracy or motion sensor data. Neither physical-device adapter writes system step counts or raw GNSS measurements.
- The map and place search require internet access. Routes can still be edited by coordinates if the map is unavailable. If a device disconnects during playback, reconnect before retrying cleanup.

<a name="cli"></a>

## ⌨️ Command Line

```bash
ios-location list --platform android
ios-location validate routes/sample.gpx
ios-location play routes/sample.gpx --platform android --speed-kmh 5
ios-location clear --platform android --udid DEVICE_SERIAL
```

Use one controller per device. See the [Chinese guide](README.md#命令行) for more CLI examples and [Android emulator commands](README.md#android-模拟器测试).
