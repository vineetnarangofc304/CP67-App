import SwiftUI
import WebKit
import AVFoundation
import PhotosUI

/// SwiftUI wrapper around WKWebView with:
///   • Camera bridge (matches your Android `AndroidBridge` — window.iOSBridge.openCamera())
///   • Photo picker bridge
///   • Universal Links support
///   • APNs device token relay
///   • Safe fallback: standard <input type="file" capture="environment"> still works.
struct WebViewContainer: UIViewRepresentable {
    let url: URL
    @Binding var isLoading: Bool

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let userContent = WKUserContentController()

        // ---- JS bridge: matches Android's window.AndroidBridge.openCamera() pattern ----
        userContent.add(context.coordinator, name: "iOSBridge")

        // Inject a JS shim so BillUpload.jsx can detect the bridge exactly like Android:
        //   window.iOSBridge.openCamera()  →  triggers native camera
        //   window.__cp67OnCameraResult(dataUrl)  →  called by native when photo taken
        let bridgeShim = """
        window.__cp67Native = true;
        window.iOSBridge = {
            openCamera: function() {
                window.webkit.messageHandlers.iOSBridge.postMessage({action: 'openCamera'});
            },
            openGallery: function() {
                window.webkit.messageHandlers.iOSBridge.postMessage({action: 'openGallery'});
            }
        };
        """
        userContent.addUserScript(WKUserScript(source: bridgeShim,
                                                injectionTime: .atDocumentStart,
                                                forMainFrameOnly: false))

        let config = WKWebViewConfiguration()
        config.userContentController = userContent
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        config.preferences.javaScriptCanOpenWindowsAutomatically = true
        // Enable service workers / offline shell (PWA)
        if #available(iOS 14.0, *) {
            config.limitsNavigationsToAppBoundDomains = false
        }

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.customUserAgent = (webView.value(forKey: "userAgent") as? String ?? "") + " CP67iOSApp/1.0"

        context.coordinator.webView = webView
        webView.load(URLRequest(url: url))

        // APNs token → forward to JS once available
        NotificationCenter.default.addObserver(forName: .apnsTokenReceived, object: nil, queue: .main) { note in
            if let token = note.object as? String {
                let js = "window.__cp67APNsToken = '\(token)'; window.dispatchEvent(new CustomEvent('apnsTokenReady', {detail: '\(token)'}));"
                webView.evaluateJavaScript(js, completionHandler: nil)
            }
        }

        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler,
                        UIImagePickerControllerDelegate, UINavigationControllerDelegate,
                        PHPickerViewControllerDelegate {
        var parent: WebViewContainer
        weak var webView: WKWebView?
        private var pendingChooser: ((URL?) -> Void)?

        init(_ parent: WebViewContainer) { self.parent = parent }

        // MARK: Navigation

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                self.parent.isLoading = false
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            self.parent.isLoading = false
        }

        // External links open in Safari (App Store guideline 4.2)
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if let url = navigationAction.request.url,
               let host = url.host,
               !host.contains("mall-rewards-1.emergent.host"),
               !host.contains("emergent.host"),
               !host.contains("emergentagent.com") {
                if UIApplication.shared.canOpenURL(url) {
                    UIApplication.shared.open(url)
                    decisionHandler(.cancel)
                    return
                }
            }
            decisionHandler(.allow)
        }

        // MARK: JS Bridge

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "iOSBridge",
                  let dict = message.body as? [String: Any],
                  let action = dict["action"] as? String else { return }

            switch action {
            case "openCamera":
                DispatchQueue.main.async { self.launchCamera() }
            case "openGallery":
                DispatchQueue.main.async { self.launchGallery() }
            default:
                break
            }
        }

        // MARK: Camera

        private func launchCamera() {
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async {
                    guard granted else {
                        self.sendCameraError("permission_denied")
                        return
                    }
                    guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
                        self.sendCameraError("camera_unavailable")
                        return
                    }
                    let picker = UIImagePickerController()
                    picker.sourceType = .camera
                    picker.cameraCaptureMode = .photo
                    picker.allowsEditing = false
                    picker.delegate = self
                    self.topViewController()?.present(picker, animated: true)
                }
            }
        }

        private func launchGallery() {
            if #available(iOS 14.0, *) {
                var config = PHPickerConfiguration()
                config.selectionLimit = 1
                config.filter = .images
                let picker = PHPickerViewController(configuration: config)
                picker.delegate = self
                topViewController()?.present(picker, animated: true)
            } else {
                let picker = UIImagePickerController()
                picker.sourceType = .photoLibrary
                picker.allowsEditing = false
                picker.delegate = self
                topViewController()?.present(picker, animated: true)
            }
        }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            picker.dismiss(animated: true)
            guard let image = info[.originalImage] as? UIImage else {
                sendCameraError("no_image"); return
            }
            deliverImage(image)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            picker.dismiss(animated: true)
            sendCameraError("cancelled")
        }

        @available(iOS 14.0, *)
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            picker.dismiss(animated: true)
            guard let first = results.first else { sendCameraError("cancelled"); return }
            first.itemProvider.loadObject(ofClass: UIImage.self) { obj, _ in
                DispatchQueue.main.async {
                    if let img = obj as? UIImage {
                        self.deliverImage(img)
                    } else {
                        self.sendCameraError("no_image")
                    }
                }
            }
        }

        // Downscale before base64 encoding so we stay well under Mongo doc limits
        private func deliverImage(_ image: UIImage) {
            let maxDim: CGFloat = 1600
            let scaled = image.downscaled(maxDim: maxDim)
            guard let jpeg = scaled.jpegData(compressionQuality: 0.82) else {
                sendCameraError("encode_failed"); return
            }
            let dataUrl = "data:image/jpeg;base64," + jpeg.base64EncodedString()
            let escaped = dataUrl.replacingOccurrences(of: "\\", with: "\\\\")
                                 .replacingOccurrences(of: "'", with: "\\'")
            let js = "if (window.__cp67OnCameraResult) { window.__cp67OnCameraResult('\(escaped)'); }"
            webView?.evaluateJavaScript(js, completionHandler: nil)
        }

        private func sendCameraError(_ code: String) {
            let js = "if (window.__cp67OnCameraError) { window.__cp67OnCameraError('\(code)'); }"
            webView?.evaluateJavaScript(js, completionHandler: nil)
        }

        private func topViewController() -> UIViewController? {
            guard let root = UIApplication.shared.connectedScenes
                .compactMap({ ($0 as? UIWindowScene)?.keyWindow })
                .first?.rootViewController else { return nil }
            var top = root
            while let presented = top.presentedViewController { top = presented }
            return top
        }
    }
}

extension UIImage {
    func downscaled(maxDim: CGFloat) -> UIImage {
        let w = size.width, h = size.height
        let longest = max(w, h)
        guard longest > maxDim else { return self }
        let scale = maxDim / longest
        let newSize = CGSize(width: floor(w * scale), height: floor(h * scale))
        let renderer = UIGraphicsImageRenderer(size: newSize)
        return renderer.image { _ in draw(in: CGRect(origin: .zero, size: newSize)) }
    }
}
