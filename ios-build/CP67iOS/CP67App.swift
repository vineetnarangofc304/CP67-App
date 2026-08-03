import SwiftUI

@main
struct CP67App: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .ignoresSafeArea(.all)
                .statusBar(hidden: false)
        }
    }
}
