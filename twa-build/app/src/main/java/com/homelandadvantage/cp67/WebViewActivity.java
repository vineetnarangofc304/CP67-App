/*
 * WebViewActivity — native Android WebView shell for CP67 Mall.
 *
 * Replaces the Chrome Custom Tabs TWA experience with a true in-app WebView so:
 *   - Chrome no longer opens in the background (feels like a real native app)
 *   - Camera works reliably (we grant WebView.PermissionRequest natively)
 *   - Gallery picker works via onShowFileChooser
 *
 * The Bubblewrap-generated LauncherActivity/DelegationService remain in the APK
 * so Digital Asset Links / notification delegation continue to work if
 * a browser deep-links back into the app; but the default launcher intent
 * routes here first.
 */
package com.homelandadvantage.cp67;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ProgressBar;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import java.io.File;

public class WebViewActivity extends Activity {

    private static final String TAG = "CP67WebView";
    private static final String START_URL = "https://cp67bot.fundlexperiences.com/app/welcome";
    private static final int REQ_CAMERA_PERM = 1001;
    private static final int REQ_FILE_CHOOSER = 1002;

    private WebView webView;
    private ValueCallback<Uri[]> fileUploadCallback;
    private PermissionRequest pendingPermissionRequest;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Immersive-lite: keep status bar but color it
        getWindow().setStatusBarColor(Color.parseColor("#2C1810"));
        getWindow().setNavigationBarColor(Color.parseColor("#2C1810"));
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_USER_PORTRAIT);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#FDF6EE"));

        webView = new WebView(this);
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT);
        webView.setLayoutParams(params);
        root.addView(webView);

        setContentView(root);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(false);   // allow autoplay for camera preview
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setUserAgentString(s.getUserAgentString() + " CP67Mall/1.4");

        // Enable service workers + web push
        try {
            android.webkit.CookieManager.getInstance().setAcceptCookie(true);
            android.webkit.CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);
        } catch (Exception e) {
            Log.w(TAG, "Cookie config failed", e);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                String host = url.getHost();
                // Keep same-origin navigation inside WebView; external links → system browser
                if (host != null && host.endsWith("fundlexperiences.com")) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, url));
                } catch (ActivityNotFoundException ignored) {}
                return true;
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> {
                    // We only care about VIDEO_CAPTURE (camera). Grant it if we
                    // already have the Android camera permission; otherwise ask
                    // the OS and retry.
                    String[] resources = request.getResources();
                    boolean wantsCamera = false;
                    for (String r : resources) {
                        if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(r)) wantsCamera = true;
                    }
                    if (!wantsCamera) {
                        request.deny();
                        return;
                    }

                    if (ContextCompat.checkSelfPermission(WebViewActivity.this,
                            Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                        request.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                    } else {
                        pendingPermissionRequest = request;
                        ActivityCompat.requestPermissions(WebViewActivity.this,
                                new String[]{Manifest.permission.CAMERA}, REQ_CAMERA_PERM);
                    }
                });
            }

            @Override
            public boolean onShowFileChooser(WebView webView,
                                             ValueCallback<Uri[]> filePathCallback,
                                             FileChooserParams fileChooserParams) {
                if (fileUploadCallback != null) {
                    fileUploadCallback.onReceiveValue(null);
                }
                fileUploadCallback = filePathCallback;
                try {
                    Intent intent = fileChooserParams.createIntent();
                    // Ensure gallery + camera capture both accessible
                    intent.setType("image/*");
                    startActivityForResult(intent, REQ_FILE_CHOOSER);
                    return true;
                } catch (ActivityNotFoundException e) {
                    fileUploadCallback = null;
                    return false;
                }
            }
        });

        webView.loadUrl(START_URL);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                            @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_CAMERA_PERM && pendingPermissionRequest != null) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                pendingPermissionRequest.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
            } else {
                pendingPermissionRequest.deny();
            }
            pendingPermissionRequest = null;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_FILE_CHOOSER) {
            if (fileUploadCallback == null) return;
            Uri[] results = null;
            if (resultCode == Activity.RESULT_OK && data != null) {
                if (data.getDataString() != null) {
                    results = new Uri[]{Uri.parse(data.getDataString())};
                } else if (data.getClipData() != null) {
                    int n = data.getClipData().getItemCount();
                    results = new Uri[n];
                    for (int i = 0; i < n; i++) {
                        results[i] = data.getClipData().getItemAt(i).getUri();
                    }
                }
            }
            fileUploadCallback.onReceiveValue(results);
            fileUploadCallback = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
