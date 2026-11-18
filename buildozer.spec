[app]
title = OsuKeys
package.name = osukeys
package.domain = org.osukeys
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0
requirements = python3==3.10.16,kivy==2.3.0,pyjnius,android
orientation = landscape
fullscreen = 1

# INTERNET dibutuhkan untuk kirim paket UDP
# (mode USB tethering / WiFi)
android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
