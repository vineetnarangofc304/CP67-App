# CP67 Mall — ProGuard rules for the native WebView shell.
#
# NOTE: minifyEnabled is currently OFF (see build.gradle), but these rules exist
# so that anyone re-enabling it later doesn't reintroduce the v1.7 camera crash
# where R8 stripped/obfuscated the anonymous WebChromeClient callbacks.

# Keep our activity
-keep public class com.homelandadvantage.cp67.WebViewActivity { *; }

# Keep all WebView-related classes + generic ValueCallback signature
-keep class android.webkit.** { *; }
-keep class androidx.webkit.** { *; }
-dontwarn android.webkit.**

# Keep FileProvider (used for camera photo Uris)
-keep class androidx.core.content.FileProvider { *; }

# Keep anonymous inner classes overriding WebChromeClient / WebViewClient
-keepclassmembers class * extends android.webkit.WebChromeClient {
    public *;
}
-keepclassmembers class * extends android.webkit.WebViewClient {
    public *;
}

# Preserve annotations used by JS interfaces / androidx
-keepattributes *Annotation*, Signature, Exceptions, InnerClasses

# Prevent stripping of ValueCallback<Uri[]> generic
-keep class android.webkit.ValueCallback { *; }
