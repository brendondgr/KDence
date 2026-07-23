// KWin script injected by KWinFocusSource (placeholders %SERVICE%/%PATH%/%IFACE% are
// substituted in Python before loading). It reports the focused window's identity to
// a private, local DBus service.
//
// Why callDBus and nothing else: KWin's script engine is sandboxed. print()/console.log
// are swallowed unless the kwin_scripting logging category is enabled (it is off by
// default), and there is no setTimeout/timer. callDBus is the one reliable egress, and
// it is fire-and-forget. No logic lives here -- it forwards the raw resourceClass and
// caption; identity and privacy policy are decided in Python.
function tkReport(tag, w) {
  var cls = w ? String(w.resourceClass) : "";
  var cap = w ? String(w.caption) : "";
  callDBus("%SERVICE%", "%PATH%", "%IFACE%", "Report", tag, cls, cap);
}

// The window whose captionChanged we are currently subscribed to, plus our handler, so we
// can disconnect cleanly on the next activation (no leaked connections, no stale window).
var tkBound = null;
var tkHandler = null;

// Subscribe to the focused window's captionChanged so a document / tab / track switch
// *within* one focused window is reported too -- not only window activation. Rebound on
// every activation. Without this, staying in one window while changing its content is
// invisible (the caption-stream bug the detail feature depends on fixing).
function tkBindCaption(w) {
  if (tkBound && tkHandler) {
    try {
      tkBound.captionChanged.disconnect(tkHandler);
    } catch (e) {
      // The previous window may already be gone; ignore.
    }
  }
  tkBound = w;
  tkHandler = null;
  if (w) {
    tkHandler = function () {
      tkReport("caption", tkBound);
    };
    try {
      w.captionChanged.connect(tkHandler);
    } catch (e) {
      // Some surfaces (the desktop, certain overrides) expose no captionChanged; that is
      // fine -- we still get their identity on activation.
    }
  }
}

// Report the window focused at load time, then every subsequent activation. In
// Plasma 6 the signal is workspace.windowActivated (renamed from Plasma 5's
// clientActivated); it fires with a null window when focus goes to the desktop.
tkReport("initial", workspace.activeWindow);
tkBindCaption(workspace.activeWindow);
workspace.windowActivated.connect(function (w) {
  tkReport("activated", w);
  tkBindCaption(w);
});
