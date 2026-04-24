import Cocoa
import WebKit

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var pinned = true
    var isDragging = false
    var dragOrigin = NSPoint.zero
    var windowOrigin = NSPoint.zero
    var statusItem: NSStatusItem!
    var backendProcess: Process?
    var backendLaunchAttempted = false
    let backendPort = ProcessInfo.processInfo.environment["CLAUDE_WIDGET_PORT"] ?? "9113"

    func applicationDidFinishLaunching(_ notification: Notification) {
        let frame = NSRect(x: 0, y: 0, width: 320, height: 440)
        window = NSWindow(
            contentRect: frame,
            styleMask: [.borderless, .resizable],
            backing: .buffered,
            defer: false
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .stationary]
        window.isMovableByWindowBackground = true
        window.minSize = NSSize(width: 280, height: 320)

        window.contentView?.wantsLayer = true
        window.contentView?.layer?.cornerRadius = 14
        window.contentView?.layer?.masksToBounds = true

        let config = WKWebViewConfiguration()
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground")
        webView.configuration.userContentController.add(MessageHandler(delegate: self), name: "widget")

        window.contentView?.addSubview(webView)

        webView.loadHTMLString(usageHTML(port: backendPort), baseURL: URL(string: "http://localhost:\(backendPort)"))
        ensureBackendAndRefresh()

        // Position bottom-right
        if let screen = NSScreen.main {
            let x = screen.visibleFrame.origin.x + screen.visibleFrame.width - frame.width - 20
            let y = screen.visibleFrame.origin.y + 20
            window.setFrameOrigin(NSPoint(x: x, y: y))
        }

        window.makeKeyAndOrderFront(nil)
        setupStatusItem()
        NSApp.activate(ignoringOtherApps: true)
    }

    func ensureBackendAndRefresh() {
        if isBackendReady() {
            refreshWidget()
            return
        }

        startBundledBackendIfNeeded()

        let deadline = Date().addingTimeInterval(15)
        pollForBackend(until: deadline)
    }

    func refreshWidget() {
        webView.evaluateJavaScript("refresh()", completionHandler: nil)
        webView.evaluateJavaScript("checkVersion()", completionHandler: nil)
    }

    func pollForBackend(until deadline: Date) {
        guard Date() < deadline else {
            refreshWidget()
            return
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            guard let self else { return }
            if self.isBackendReady() {
                self.refreshWidget()
            } else {
                self.pollForBackend(until: deadline)
            }
        }
    }

    func isBackendReady() -> Bool {
        guard let url = URL(string: "http://127.0.0.1:\(backendPort)/api/status") else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = 1.5

        let semaphore = DispatchSemaphore(value: 0)
        var success = false
        let task = URLSession.shared.dataTask(with: request) { _, response, error in
            if let http = response as? HTTPURLResponse, http.statusCode == 200, error == nil {
                success = true
            }
            semaphore.signal()
        }
        task.resume()

        let result = semaphore.wait(timeout: .now() + 2)
        if result == .timedOut {
            task.cancel()
        }
        return success
    }

    func startBundledBackendIfNeeded() {
        guard !backendLaunchAttempted else { return }
        backendLaunchAttempted = true

        let fileManager = FileManager.default
        let scriptPath = Bundle.main.path(forResource: "claude-usage", ofType: "py")
            ?? Bundle.main.resourcePath.map { "\($0)/claude-usage.py" }

        guard let scriptPath, fileManager.fileExists(atPath: scriptPath) else { return }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [scriptPath]

        var env = ProcessInfo.processInfo.environment
        env["CLAUDE_WIDGET_PORT"] = backendPort
        process.environment = env

        let outputPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = outputPipe

        do {
            try process.run()
            backendProcess = process
        } catch {
            NSLog("ClaudeWidget failed to start backend: \(error.localizedDescription)")
        }
    }

    func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem.button {
            button.title = "⚡"
        }
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Show/Hide Usage", action: #selector(toggleWindow), keyEquivalent: "u"))
        menu.addItem(NSMenuItem(title: "Pin on Top", action: #selector(togglePin), keyEquivalent: "p"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit Claude Usage", action: #selector(quitApp), keyEquivalent: "q"))
        statusItem.menu = menu
    }

    @objc func toggleWindow() {
        if window.isVisible {
            window.orderOut(nil)
        } else {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    @objc func togglePin() {
        pinned = !pinned
        window.level = pinned ? .floating : .normal
        webView.evaluateJavaScript("updatePinState(\(pinned))", completionHandler: nil)
    }

    @objc func quitApp() { NSApp.terminate(nil) }

    func applicationWillTerminate(_ notification: Notification) {
        backendProcess?.terminate()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag || !window.isVisible {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
        return true
    }
}

class MessageHandler: NSObject, WKScriptMessageHandler {
    weak var delegate: AppDelegate?
    init(delegate: AppDelegate) { self.delegate = delegate }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let dict = message.body as? [String: Any], let action = dict["action"] as? String else { return }
        if action == "togglePin" { delegate?.togglePin() }
        else if action == "hideWidget" { delegate?.toggleWindow() }
        else if action == "openCoffee" {
            if let url = URL(string: "https://buymeacoffee.com/nathanbb") {
                NSWorkspace.shared.open(url)
            }
        }
        else if action == "share" {
            guard let webView = delegate?.webView else { return }
            let text = "Check out Claude Usage Widget \u{2014} monitor your Claude AI usage limits in a floating desktop widget!"
            let url = URL(string: "https://github.com/siperdudeuk/claude-usage-widget")!
            let picker = NSSharingServicePicker(items: [text, url])
            let anchor = NSRect(x: webView.bounds.midX - 1, y: webView.bounds.maxY - 40, width: 2, height: 2)
            picker.show(relativeTo: anchor, of: webView, preferredEdge: .minY)
        }
        else if action == "dragStart" {
            guard let window = delegate?.window else { return }
            delegate?.dragOrigin = NSEvent.mouseLocation
            delegate?.windowOrigin = window.frame.origin
            delegate?.isDragging = true
        } else if action == "dragMove" {
            guard let d = delegate, d.isDragging, let window = d.window else { return }
            let mouse = NSEvent.mouseLocation
            window.setFrameOrigin(NSPoint(x: d.windowOrigin.x + mouse.x - d.dragOrigin.x,
                                          y: d.windowOrigin.y + mouse.y - d.dragOrigin.y))
        } else if action == "dragEnd" { delegate?.isDragging = false }
    }
}

func usageHTML(port: String) -> String {
    return """
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      :root {
        --bg: rgba(13,17,23,0.92); --card: rgba(22,27,34,0.8); --border: rgba(48,54,61,0.5);
        --text: #e6edf3; --muted: #8b949e; --green: #3fb950;
        --yellow: #d29922; --red: #f85149; --blue: #58a6ff; --purple: #bc8cff;
      }
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
        background: var(--bg); color: var(--text);
        -webkit-user-select: none; user-select: none;
        border-radius: 14px; overflow: hidden;
      }
      .titlebar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 10px 14px 6px; cursor: grab;
      }
      .titlebar h1 { font-size: 13px; font-weight: 600; }
      .accent { color: var(--purple); }
      .controls { display: flex; gap: 6px; }
      .ctrl-btn {
        width: 24px; height: 24px; border-radius: 6px; border: none;
        background: var(--border); color: var(--muted); font-size: 12px;
        cursor: pointer; display: flex; align-items: center; justify-content: center;
      }
      .ctrl-btn:hover { background: rgba(88,166,255,0.2); color: var(--text); }
      .ctrl-btn.pinned { background: rgba(188,140,255,0.2); color: var(--purple); }
      .ctrl-btn.coffee { background: rgba(255,221,0,0.15); color: #ffdd00; font-size: 13px; }
      .ctrl-btn.coffee:hover { background: rgba(255,221,0,0.3); }
      .meta { font-size: 9px; color: var(--muted); padding: 0 14px 8px;
        border-bottom: 1px solid var(--border); }
      .content { padding: 10px 14px 14px; }
      .meter { margin-bottom: 10px; }
      .meter-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
      .meter-label { font-size: 11px; font-weight: 600; }
      .meter-value { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
      .meter-sub { font-size: 10px; color: var(--muted); }
      .bar-track { height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; margin-top: 4px; }
      .bar-fill { height: 100%; border-radius: 4px; transition: width 0.8s ease; }
      .bar-purple { background: linear-gradient(90deg, var(--purple), #d4a0ff); }
      .bar-blue { background: linear-gradient(90deg, var(--blue), #79c0ff); }
      .bar-green { background: var(--green); }
      .bar-yellow { background: var(--yellow); }
      .bar-red { background: var(--red); }
      .reset-time { font-size: 9px; color: var(--muted); margin-top: 2px; }
      .divider { border-top: 1px solid var(--border); margin: 8px 0; }
      .extra-row { display: flex; justify-content: space-between; font-size: 11px; padding: 3px 0; }
      .extra-label { color: var(--muted); }
      .error-box { background: rgba(248,81,73,0.1); border: 1px solid rgba(248,81,73,0.4);
        border-radius: 8px; padding: 10px; color: var(--red); font-size: 11px; }
      .setup-box { background: rgba(88,166,255,0.08); border: 1px solid rgba(88,166,255,0.3);
        border-radius: 8px; padding: 12px; font-size: 11px; }
      .setup-box h3 { font-size: 12px; font-weight: 600; margin-bottom: 8px; color: var(--blue); }
      .setup-step { display: flex; gap: 8px; padding: 4px 0; color: var(--muted); }
      .setup-step .num { color: var(--purple); font-weight: 700; min-width: 16px; }
      .setup-step.done { color: var(--green); }
      .setup-step.issue { color: var(--yellow); }
      .update-banner {
        background: linear-gradient(90deg, rgba(188,140,255,0.2), rgba(88,166,255,0.2));
        border: 1px solid rgba(188,140,255,0.5);
        border-radius: 8px; padding: 8px 10px; margin: 0 14px 10px;
        display: flex; align-items: center; justify-content: space-between;
        gap: 8px; font-size: 10px;
      }
      .update-banner .msg { color: var(--text); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .update-banner .msg b { color: var(--purple); }
      .update-btn {
        background: var(--purple); color: #1a1a2e; border: none;
        padding: 4px 10px; border-radius: 5px; font-size: 10px;
        font-weight: 700; cursor: pointer; white-space: nowrap;
      }
      .update-btn:hover { background: #d4a0ff; }
      .update-btn:disabled { opacity: 0.5; cursor: wait; }
      .coffee-banner {
        background: linear-gradient(90deg, rgba(255,221,0,0.08), rgba(255,180,0,0.08));
        border: 1px solid rgba(255,221,0,0.25);
        border-radius: 8px; padding: 8px 10px; margin: 0 14px 10px;
        display: flex; align-items: center; gap: 8px; font-size: 10px;
      }
      .coffee-banner .msg { color: var(--muted); flex: 1; }
      .coffee-banner .msg b { color: #ffdd00; }
      .coffee-link {
        background: rgba(255,221,0,0.2); color: #ffdd00; border: none;
        padding: 4px 10px; border-radius: 5px; font-size: 10px;
        font-weight: 700; cursor: pointer; white-space: nowrap;
      }
      .coffee-link:hover { background: rgba(255,221,0,0.35); }
      .coffee-dismiss {
        background: none; border: none; color: var(--muted); cursor: pointer;
        font-size: 14px; padding: 0 2px; line-height: 1;
      }
      .coffee-dismiss:hover { color: var(--text); }
      .share-toast {
        position: fixed; bottom: 12px; left: 50%; transform: translateX(-50%);
        background: var(--purple); color: #1a1a2e; padding: 6px 14px;
        border-radius: 6px; font-size: 10px; font-weight: 700;
        opacity: 0; transition: opacity 0.3s; pointer-events: none; z-index: 99;
      }
      .share-toast.show { opacity: 1; }
      .footer { padding: 6px 14px 10px; border-top: 1px solid var(--border);
        display: flex; justify-content: space-between; align-items: center;
        font-size: 9px; color: var(--muted); }
      .footer .users { display: flex; align-items: center; gap: 4px; }
      .footer .users .dot { width: 5px; height: 5px; border-radius: 50%;
        background: var(--green); display: inline-block; }
    </style>
    </head>
    <body>
    <div class="titlebar" id="titlebar">
      <h1>⚡ Claude <span class="accent">Usage</span></h1>
      <div class="controls">
        <button class="ctrl-btn" title="Share with friends" onclick="shareWidget()">📤</button>
        <button class="ctrl-btn coffee" title="Buy me a coffee" onclick="openCoffee()">☕</button>
        <button class="ctrl-btn pinned" id="pinBtn" title="Pin" onclick="togglePin()">📌</button>
        <button class="ctrl-btn" title="Hide" onclick="hideWidget()">✕</button>
      </div>
    </div>
    <div class="meta" id="meta">Loading...</div>
    <div id="updateBanner" style="display:none"></div>
    <div id="coffeeBanner" class="coffee-banner" style="display:none"></div>
    <div class="content" id="content">
      <div class="error-box">Connecting...</div>
    </div>
    <div class="footer" id="footer">
      <div class="users"><span class="dot"></span><span id="userCount">—</span></div>
      <span>github.com/siperdudeuk</span>
    </div>
    <div class="share-toast" id="shareToast">Link copied to clipboard!</div>

    <script>
    const API_PORT = '\(port)';
    const API_BASE = 'http://127.0.0.1:' + API_PORT;
    let isPinned = true;
    let APP_BOOTED_AT = Date.now();
    let STARTUP_GRACE_MS = 20000;
    let STARTUP_RETRY_MS = 1000;
    let STEADY_REFRESH_MS = 10000;
    let VERSION_REFRESH_MS = 300000;
    let USERCOUNT_REFRESH_MS = 600000;
    let startupState = { retryTimer: null, steadyInterval: null };
    function togglePin() { window.webkit.messageHandlers.widget.postMessage({action:"togglePin"}); }
    function hideWidget() { window.webkit.messageHandlers.widget.postMessage({action:"hideWidget"}); }
    function openCoffee() { window.webkit.messageHandlers.widget.postMessage({action:"openCoffee"}); }
    function shareWidget() { window.webkit.messageHandlers.widget.postMessage({action:"share"}); }
    function updatePinState(p) {
      isPinned = p;
      document.getElementById('pinBtn').className = p ? 'ctrl-btn pinned' : 'ctrl-btn';
    }

    const titlebar = document.getElementById('titlebar');
    let dragInterval = null;
    titlebar.addEventListener('mousedown', (e) => {
      if (e.target.closest('.ctrl-btn')) return;
      window.webkit.messageHandlers.widget.postMessage({action:"dragStart"});
      dragInterval = setInterval(() => {
        window.webkit.messageHandlers.widget.postMessage({action:"dragMove"});
      }, 16);
    });
    document.addEventListener('mouseup', () => {
      if (dragInterval) {
        clearInterval(dragInterval);
        dragInterval = null;
        window.webkit.messageHandlers.widget.postMessage({action:"dragEnd"});
      }
    });

    function barClass(pct) {
      if (pct >= 90) return 'bar-red';
      if (pct >= 70) return 'bar-yellow';
      return 'bar-purple';
    }

    function timeUntil(iso) {
      if (!iso) return '';
      const diff = new Date(iso) - new Date();
      if (diff <= 0) return 'resetting...';
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      if (h > 24) return Math.floor(h/24) + 'd ' + (h%24) + 'h';
      if (h > 0) return h + 'h ' + m + 'm';
      return m + 'm';
    }

    function renderMeter(label, pct, resetAt, barCls) {
      const cls = barCls || barClass(pct);
      const resetStr = resetAt ? 'Resets in ' + timeUntil(resetAt) : '';
      return '<div class="meter">' +
        '<div class="meter-header"><span class="meter-label">' + label + '</span>' +
        '<span class="meter-value">' + pct + '%</span></div>' +
        '<div class="bar-track"><div class="bar-fill ' + cls + '" style="width:' + pct + '%"></div></div>' +
        '<div class="reset-time">' + resetStr + '</div></div>';
    }

    function renderSetup(status, error) {
      const hasCrypto = status && status.has_cryptography;
      const hasCookies = status && status.has_chrome_cookies;
      const hasOrg = status && status.org_id;
      const method = status && status.method;

      let steps = '';

      if (!hasCrypto) {
        steps += '<div class="setup-step issue"><span class="num">1</span><span>Run: <b>pip3 install cryptography</b></span></div>';
      } else {
        steps += '<div class="setup-step done"><span class="num">✓</span><span>cryptography package installed</span></div>';
      }

      if (!hasCookies) {
        steps += '<div class="setup-step issue"><span class="num">2</span><span>Log into <b>claude.ai</b> in Chrome</span></div>';
      } else {
        steps += '<div class="setup-step done"><span class="num">✓</span><span>Chrome cookies found</span></div>';
      }

      if (!hasOrg) {
        steps += '<div class="setup-step issue"><span class="num">3</span><span>Waiting to detect your organisation...</span></div>';
      } else {
        steps += '<div class="setup-step done"><span class="num">✓</span><span>Organisation detected</span></div>';
      }

      if (method) {
        steps += '<div class="setup-step done"><span class="num">✓</span><span>Connected via ' + method + '</span></div>';
      }

      if (error && error !== 'Starting up...') {
        steps += '<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);color:var(--red);font-size:10px;">' + error + '</div>';
      }

      return '<div class="setup-box"><h3>Setup</h3>' + steps + '</div>';
    }

    function ensureSteadyRefresh() {
      if (!startupState.steadyInterval) {
        startupState.steadyInterval = setInterval(refresh, STEADY_REFRESH_MS);
      }
    }

    function clearStartupRetry() {
      if (startupState.retryTimer) {
        clearTimeout(startupState.retryTimer);
        startupState.retryTimer = null;
      }
    }

    function scheduleStartupRetry() {
      if (startupState.retryTimer) return;
      startupState.retryTimer = setTimeout(() => {
        startupState.retryTimer = null;
        refresh();
      }, STARTUP_RETRY_MS);
    }

    async function refresh() {
      try {
        const r = await fetch(API_BASE + '/api/usage');
        const d = await r.json();

        if (d.error) {
          // Fetch status to show setup guidance
          let status = null;
          try {
            const sr = await fetch(API_BASE + '/api/status');
            status = await sr.json();
          } catch(e2) {}
          document.getElementById('content').innerHTML = renderSetup(status, d.error);
          document.getElementById('meta').textContent = d.error === 'Starting up...' ? 'Starting...' : 'Setup needed';
          ensureSteadyRefresh();
          return;
        }

        clearStartupRetry();
        ensureSteadyRefresh();

        const ts = d.timestamp ? new Date(d.timestamp).toLocaleTimeString() : '—';
        document.getElementById('meta').textContent = 'Updated ' + ts + ' • Claude Max';

        let html = '';

        const LABELS = {
          five_hour: ['5-Hour Limit', null],
          seven_day: ['7-Day Limit', 'bar-blue'],
          seven_day_opus: ['Opus (7-Day)', 'bar-purple'],
          seven_day_sonnet: ['Sonnet (7-Day)', 'bar-green'],
          seven_day_oauth_apps: ['OAuth Apps (7-Day)', 'bar-blue'],
          seven_day_cowork: ['Claude Code (7-Day)', 'bar-purple'],
          seven_day_omelette: ['Claude Design (7-Day)', 'bar-blue'],
          iguana_necktie: ['Iguana (7-Day)', null],
          omelette_promotional: ['Design Promo (7-Day)', null],
        };
        const ORDER = ['five_hour','seven_day','seven_day_opus','seven_day_sonnet',
                       'seven_day_cowork','seven_day_omelette','seven_day_oauth_apps',
                       'iguana_necktie','omelette_promotional'];
        const seen = new Set();
        function prettify(k) {
          return k.replace(/_/g,' ').replace(/\\b\\w/g, c => c.toUpperCase());
        }
        for (const key of ORDER) {
          if (!(key in d)) continue;
          seen.add(key);
          const v = d[key];
          if (!v || typeof v !== 'object' || v.utilization == null) continue;
          const [label, cls] = LABELS[key] || [prettify(key), null];
          html += renderMeter(label, v.utilization, v.resets_at, cls);
        }
        for (const key of Object.keys(d)) {
          if (seen.has(key)) continue;
          const v = d[key];
          if (!v || typeof v !== 'object' || v.utilization == null) continue;
          const [label, cls] = LABELS[key] || [prettify(key), null];
          html += renderMeter(label, v.utilization, v.resets_at, cls);
        }

        if (d.extra_usage) {
          html += '<div class="divider"></div>';
          html += '<div class="extra-row"><span class="extra-label">Extra Credits</span><span>' +
            (d.extra_usage.is_enabled ? '✓ Enabled' : '✗ Disabled') + '</span></div>';
          if (d.extra_usage.monthly_limit != null) {
            html += '<div class="extra-row"><span class="extra-label">Monthly Limit</span><span>$' +
              (d.extra_usage.monthly_limit/100).toFixed(0) + '</span></div>';
          }
          if (d.extra_usage.used_credits != null) {
            html += '<div class="extra-row"><span class="extra-label">Used This Month</span><span>$' +
              (d.extra_usage.used_credits/100).toFixed(2) + '</span></div>';
          }
        }

        document.getElementById('content').innerHTML = html;
      } catch(e) {
        const stillBooting = (Date.now() - APP_BOOTED_AT) < STARTUP_GRACE_MS;
        document.getElementById('content').innerHTML =
          '<div class="setup-box"><h3>' + (stillBooting ? 'Starting backend...' : 'Backend unavailable') + '</h3>' +
          '<div class="setup-step"><span class="num">...</span><span>' +
            (stillBooting ? 'Retrying automatically' : 'The local usage service is not responding') +
          '</span></div>' +
          '<div style="margin-top:8px;font-size:10px;color:var(--muted);">' +
            (stillBooting ? 'This usually takes a few seconds on launch.' : 'If this persists, run <b>./start.sh</b>.') +
          '</div></div>';
        document.getElementById('meta').textContent = stillBooting ? 'Starting local service...' : 'Backend unavailable';
        scheduleStartupRetry();
      }
    }

    async function checkVersion() {
      try {
        const r = await fetch(API_BASE + '/api/version');
        const v = await r.json();
        const banner = document.getElementById('updateBanner');
        if (v.update_available) {
          const msg = v.latest_message || 'A new version is available';
          banner.className = 'update-banner';
          banner.style.display = 'flex';
          banner.innerHTML =
            '<span class="msg"><b>Update:</b> ' + msg + '</span>' +
            '<button class="update-btn" id="updateBtn" onclick="doUpdate()">Update</button>';
        } else {
          banner.style.display = 'none';
        }
      } catch(e) {}
    }

    async function doUpdate() {
      const btn = document.getElementById('updateBtn');
      if (btn) { btn.disabled = true; btn.textContent = 'Updating...'; }
      try {
        const r = await fetch(API_BASE + '/api/update', { method: 'POST' });
        const result = await r.json();
        if (result.success) {
          if (btn) btn.textContent = 'Done!';
          // The update script restarts the widget, so this window will close.
        } else {
          if (btn) { btn.disabled = false; btn.textContent = 'Retry'; }
          alert('Update failed: ' + (result.error || 'unknown error'));
        }
      } catch(e) {
        if (btn) { btn.disabled = false; btn.textContent = 'Retry'; }
      }
    }

    function checkCoffeePrompt() {
      const now = Date.now();
      const firstSeen = localStorage.getItem('cw_first_seen');
      if (!firstSeen) { localStorage.setItem('cw_first_seen', now.toString()); return; }
      if ((now - parseInt(firstSeen)) < 3 * 86400000) return;
      if (localStorage.getItem('cw_coffee_supported')) return;
      const dismissed = localStorage.getItem('cw_coffee_dismissed');
      if (dismissed && (now - parseInt(dismissed)) < 7 * 86400000) return;
      const banner = document.getElementById('coffeeBanner');
      banner.style.display = 'flex';
      banner.innerHTML =
        '<span class="msg">☕ <b>Enjoying the widget?</b> A coffee would be lovely!</span>' +
        '<button class="coffee-link" onclick="supportCoffee()">Support</button>' +
        '<button class="coffee-dismiss" onclick="dismissCoffee()">✕</button>';
    }
    function dismissCoffee() {
      localStorage.setItem('cw_coffee_dismissed', Date.now().toString());
      document.getElementById('coffeeBanner').style.display = 'none';
    }
    function supportCoffee() {
      localStorage.setItem('cw_coffee_supported', '1');
      document.getElementById('coffeeBanner').style.display = 'none';
      openCoffee();
    }

    const _CU = atob('aHR0cHM6Ly93d3cuc21hcnRwcm9wZXJ0eXNvZnR3YXJlLmNvbS9hcGkvd3QvY291bnQ=');
    async function fetchUserCount() {
      try {
        const r = await fetch(_CU);
        const d = await r.json();
        const n = d.active || d.total || 0;
        document.getElementById('userCount').textContent = n + ' active user' + (n !== 1 ? 's' : '');
      } catch(e) {}
    }

    refresh();
    checkVersion();
    setInterval(checkVersion, VERSION_REFRESH_MS);
    checkCoffeePrompt();
    fetchUserCount();
    setInterval(fetchUserCount, USERCOUNT_REFRESH_MS);
    </script>
    </body>
    </html>
    """
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
