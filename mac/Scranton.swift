// Scranton as a Mac app: its own window and Dock icon around the local page (http://localhost:8300).
// Built on Lu's Mac by `./scranton.sh install-app` (swiftc from the Xcode Command Line Tools).
// The server itself is kept running by `./scranton.sh install-service`; if it isn't up, the app
// starts it with `./scranton.sh start` and waits.

import Cocoa
import WebKit

let scrantonDir: String = {
    // Set at build time in Info.plist (ScrantonDir); falls back to ~/Scranton.
    if let d = Bundle.main.object(forInfoDictionaryKey: "ScrantonDir") as? String, !d.isEmpty { return d }
    return NSHomeDirectory() + "/Scranton"
}()
let port: Int = (Bundle.main.object(forInfoDictionaryKey: "ScrantonPort") as? Int) ?? 8300
let home = URL(string: "http://localhost:\(port)/")!

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var status: NSTextField!
    var startedServer = false
    var tries = 0

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenu()

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()          // keeps localStorage (drafts, read state) between launches
        config.mediaTypesRequiringUserActionForPlayback = []   // the "needs you" sound may play without a click first
        config.userContentController.add(self, name: "scranton")
        // The page tells the app how many things need Lu: shown on the Dock icon.
        let js = """
        (function(){
          function send(){ try{ var b=document.getElementById('sc-inbox-badge');
            var n=(b && !b.classList.contains('hidden')) ? b.textContent : '';
            window.webkit.messageHandlers.scranton.postMessage({badge:n}); }catch(e){} }
          document.addEventListener('DOMContentLoaded', function(){
            var b=document.getElementById('sc-inbox-badge');
            if(b){ new MutationObserver(send).observe(b,{childList:true,characterData:true,subtree:true,attributes:true}); }
            send(); });
        })();
        """
        config.userContentController.addUserScript(WKUserScript(source: js, injectionTime: .atDocumentEnd, forMainFrameOnly: true))

        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = false
        web.setValue(false, forKey: "drawsBackground")   // no white flash in dark mode

        status = NSTextField(labelWithString: "Starting Scranton…")
        status.font = .systemFont(ofSize: 14)
        status.textColor = .secondaryLabelColor
        status.alignment = .center
        status.maximumNumberOfLines = 0
        status.isSelectable = true
        status.translatesAutoresizingMaskIntoConstraints = false

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                          backing: .buffered, defer: false)
        window.title = "Scranton"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.minSize = NSSize(width: 720, height: 520)
        window.contentView = web
        web.addSubview(status)
        NSLayoutConstraint.activate([
            status.centerXAnchor.constraint(equalTo: web.centerXAnchor),
            status.centerYAnchor.constraint(equalTo: web.centerYAnchor),
        ])
        window.center()
        _ = window.setFrameAutosaveName("ScrantonMain")
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        connect()
    }

    // Keep running when the window is closed (like Slack); clicking the Dock icon brings it back.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { window.makeKeyAndOrderFront(nil) }
        return true
    }

    // MARK: server

    func serverUp(_ done: @escaping (Bool) -> Void) {
        var req = URLRequest(url: home)
        req.timeoutInterval = 2
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            let ok = (resp as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { done(ok) }
        }.resume()
    }

    func connect() {
        serverUp { ok in
            if ok {
                self.status.isHidden = true
                self.web.load(URLRequest(url: home))
                return
            }
            if !self.startedServer {
                self.startedServer = true
                self.status.stringValue = "Starting Scranton…"
                self.startServer()
            }
            self.tries += 1
            if self.tries > 90 {
                self.status.stringValue = "Scranton didn't start.\nOpen Terminal and run: cd \(scrantonDir) && ./scranton.sh start\nDetails: data/logs/server.log"
                return
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.connect() }
        }
    }

    func startServer() {
        // A login shell, so PATH has Homebrew (tmux, claude, codex…) like in Terminal.
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-lc", "cd \"\(scrantonDir)\" && ./scranton.sh start >> data/logs/app-launch.log 2>&1"]
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        try? p.run()
    }

    // MARK: page

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { retryLater() }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { retryLater() }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { webView.reload() }

    func retryLater() {
        status.isHidden = false
        status.stringValue = "Can't reach Scranton. Trying again…"
        tries = 0
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.connect() }
    }

    // Links to anything other than Scranton itself (GitHub, previews…) open in the browser.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, let host = url.host,
           !(host == "localhost" || host == "127.0.0.1"), url.scheme == "http" || url.scheme == "https" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        if let url = action.request.url, url.scheme == "mailto" {
            NSWorkspace.shared.open(url); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }

    // target=_blank / window.open
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if url.host == "localhost" || url.host == "127.0.0.1" { webView.load(URLRequest(url: url)) }
            else { NSWorkspace.shared.open(url) }
        }
        return nil
    }

    // <input type="file"> (the + button)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.canChooseFiles = true
        panel.beginSheetModal(for: window) { r in completionHandler(r == .OK ? panel.urls : nil) }
    }

    // confirm() (e.g. "Delete this message?") and alert()
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { r in completionHandler(r == .alertFirstButtonReturn) }
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }
    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert()
        a.messageText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 280, height: 24))
        field.stringValue = defaultText ?? ""
        a.accessoryView = field
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { r in completionHandler(r == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any] else { return }
        if let badge = body["badge"] as? String {
            NSApp.dockTile.badgeLabel = (badge.isEmpty || badge == "0") ? nil : badge
        }
    }

    // MARK: menu (without an Edit menu, ⌘C / ⌘V / ⌘A don't work in a WKWebView)

    @objc func reloadPage(_ s: Any?) { web.reload() }
    @objc func openInBrowser(_ s: Any?) { NSWorkspace.shared.open(web.url ?? home) }
    @objc func zoomIn(_ s: Any?) { web.pageZoom = min(web.pageZoom + 0.1, 2.0) }
    @objc func zoomOut(_ s: Any?) { web.pageZoom = max(web.pageZoom - 0.1, 0.6) }
    @objc func zoomReset(_ s: Any?) { web.pageZoom = 1.0 }

    func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem(); main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About Scranton", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide Scranton", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let others = appMenu.addItem(withTitle: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        others.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit Scranton", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu

        let editItem = NSMenuItem(); main.addItem(editItem)
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit

        let viewItem = NSMenuItem(); main.addItem(viewItem)
        let view = NSMenu(title: "View")
        view.addItem(withTitle: "Reload", action: #selector(reloadPage(_:)), keyEquivalent: "r")
        view.addItem(withTitle: "Open in Browser", action: #selector(openInBrowser(_:)), keyEquivalent: "")
        view.addItem(.separator())
        view.addItem(withTitle: "Zoom In", action: #selector(zoomIn(_:)), keyEquivalent: "+")
        view.addItem(withTitle: "Zoom Out", action: #selector(zoomOut(_:)), keyEquivalent: "-")
        view.addItem(withTitle: "Actual Size", action: #selector(zoomReset(_:)), keyEquivalent: "0")
        view.addItem(.separator())
        let fs = view.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        fs.keyEquivalentModifierMask = [.command, .control]
        viewItem.submenu = view

        let winItem = NSMenuItem(); main.addItem(winItem)
        let win = NSMenu(title: "Window")
        win.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        win.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winItem.submenu = win
        NSApp.windowsMenu = win

        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
_ = app.setActivationPolicy(.regular)
app.run()
