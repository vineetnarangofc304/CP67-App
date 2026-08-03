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
            ZStack {
                RoundedRectangle(cornerRadius: 20)
                    .fill(LinearGradient(
                        colors: [Color(red: 0.72, green: 0.53, blue: 0.04),
                                 Color(red: 0.85, green: 0.65, blue: 0.13)],
                        startPoint: .topLeading, endPoint: .bottomTrailing
                    ))
                    .frame(width: 84, height: 84)
                Text("HA")
                    .font(.system(size: 34, weight: .heavy, design: .rounded))
                    .foregroundColor(.white)
            }
            Text("Homeland Advantage")
                .font(.system(size: 20, weight: .semibold, design: .serif))
                .foregroundColor(Color(red: 0.12, green: 0.11, blue: 0.09))
            ProgressView()
                .progressViewStyle(CircularProgressViewStyle(tint: Color(red: 0.72, green: 0.53, blue: 0.04)))
                .padding(.top, 12)
        }
    }
}
