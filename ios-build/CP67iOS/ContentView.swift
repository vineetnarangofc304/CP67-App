import SwiftUI
import WebKit

/// Root screen — hosts the WKWebView that loads the Homeland Advantage PWA.
struct ContentView: View {
    @State private var isLoading = true

    // ⚠ Point this at the PRODUCTION URL for App Store submission.
    // For internal TestFlight builds you can point at preview.
    private let appURL = URL(string: "https://mall-rewards-1.emergent.host/app/welcome")!

    var body: some View {
        ZStack {
            Color(red: 0.98, green: 0.97, blue: 0.96)   // #FAF8F5 luxury cream splash background
                .ignoresSafeArea()

            WebViewContainer(url: appURL, isLoading: $isLoading)
                .ignoresSafeArea()

            if isLoading {
                SplashView()
            }
        }
    }
}

/// Full-bleed splash while the PWA boots (< 800 ms typically).
struct SplashView: View {
    var body: some View {
        VStack(spacing: 18) {
            // Point 57: real Homeland Advantage logo instead of the "HA" tile.
            Image("AppLogo")
                .resizable()
                .scaledToFit()
                .frame(width: 240)
            ProgressView()
                .progressViewStyle(CircularProgressViewStyle(tint: Color(red: 0.72, green: 0.53, blue: 0.04)))
                .padding(.top, 12)
        }
    }
}
