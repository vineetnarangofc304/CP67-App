# CP67 Mall — Android TWA Build

This folder contains the Trusted Web Activity (TWA) wrapper for the CP67 Mall PWA.

## Artifacts

| File                          | Purpose                                      |
| ----------------------------- | -------------------------------------------- |
| `app-release-signed.apk`      | Signed APK (sideload / direct distribution)  |
| `app-release-bundle.aab`      | Android App Bundle (upload to Play Console)  |
| `android.keystore`            | **PROD signing key — back up immediately**   |
| `assetlinks.json`             | Digital Asset Links file                     |
| `twa-manifest.json`           | Bubblewrap project config                    |

## Configuration

| Field          | Value                                                          |
| -------------- | -------------------------------------------------------------- |
| Package ID     | `com.homelandadvantage.cp67`                                   |
| App Name       | `CP67 Mall`                                                    |
| Launcher       | `CP67 Mall`                                                    |
| Version        | `1` (`appVersionCode=1`, `appVersionName=1`)                   |
| Host           | `mall-engage-preview.preview.emergentagent.com`                |
| Start URL      | `/app/welcome`                                                 |
| Theme color    | `#2C1810`                                                      |
| Background     | `#FDF6EE`                                                      |

## Signing key (KEEP SAFE)

| Field              | Value                |
| ------------------ | -------------------- |
| Keystore path      | `./android.keystore` |
| Alias              | `android`            |
| Keystore password  | `CP67Mall@2025`      |
| Key password       | `CP67Mall@2025`      |
| SHA-256 fingerprint| `32:BF:48:D0:63:E1:4C:64:26:7B:59:1B:45:50:97:AE:46:F1:8F:E9:EE:35:4C:B6:BE:BB:03:23:5C:31:40:5E` |

> ⚠ Lose this keystore and you lose the ability to publish updates to the same Play listing. Back it up to a secure vault BEFORE Play Store submission.

## Digital Asset Links

`assetlinks.json` is auto-deployed at:
`https://mall-engage-preview.preview.emergentagent.com/.well-known/assetlinks.json`

It is required so the TWA opens without the Chrome address bar.

## Rebuild after changes

```bash
cd /app/twa-build
node bootstrap.js               # only if twa-manifest.json must be regenerated
BUBBLEWRAP_KEYSTORE_PASSWORD='CP67Mall@2025' \
BUBBLEWRAP_KEY_PASSWORD='CP67Mall@2025' \
bubblewrap build --skipPwaValidation
```

## Bumping the version (for Play Store updates)

Edit `twa-manifest.json` and increment `appVersionCode` & `appVersionName`, then rerun the build command above.

## Notes for the build host

The container is `aarch64`, but Android build tools ship as `x86_64` ELF
binaries. The build-tools `aapt`, `aapt2`, `aidl`, `zipalign`, `dexdump`,
`split-select`, `bcc_compat`, `llvm-rs-cc` are wrapped with shell scripts that
delegate to `qemu-x86_64-static`. The same is done for the gradle-cached
`aapt2-*-linux/aapt2`. If you wipe `~/.gradle/caches` you must rewrap the new
`aapt2` after the next build.
