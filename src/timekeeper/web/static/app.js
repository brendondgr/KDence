/* TimeKeeper live view.
 *
 * Polls the Phase 5 read-back API every 2s (data changes ~every collector interval, so
 * polling beats streaming -- build-plan Step 6.1) and renders the dashboard. Between polls
 * the two live counters tick locally each second, FROZEN while idle so "Active today" stops
 * when you walk away (the 6.1 pass condition). A failed fetch flips to an "offline" badge
 * and keeps retrying, recovering when the API/collector returns (Step 6.2). All aggregation
 * is client-side over /api/timeline spans -- the API stays untouched from Phase 5.
 */
(function () {
  "use strict";

  var POLL_MS = 2000;
  var PALETTE = ["#3fb950", "#4c9aff", "#bc8cff", "#39c5cf", "#f0883e", "#e3b341"];
  var IDLE_COLOR = "#3a474a";
  var DESKTOP_KEY = "__desktop__";

  // Nice names/colours for common window classes; everything else falls back below.
  var KNOWN = {
    code: { name: "VS Code", color: "#4c9aff" },
    firefox: { name: "Firefox", color: "#f0883e" },
    "org.kde.konsole": { name: "Konsole", color: "#3fb950" },
    konsole: { name: "Konsole", color: "#3fb950" },
    slack: { name: "Slack", color: "#bc8cff" },
    obsidian: { name: "Obsidian", color: "#db61a2" },
    thunderbird: { name: "Thunderbird", color: "#39c5cf" },
    gimp: { name: "GIMP", color: "#e3b341" },
    "com.anthropic.claude": { name: "Claude", color: "#3fb950" },
  };

  // -- helpers ---------------------------------------------------------------

  function keyOf(cls) {
    return cls === null || cls === undefined ? DESKTOP_KEY : cls;
  }
  function prettify(cls) {
    if (cls === null || cls === undefined) return "(desktop)";
    var k = KNOWN[cls.toLowerCase()];
    if (k) return k.name;
    var seg = cls.split(".").pop();
    return seg ? seg.charAt(0).toUpperCase() + seg.slice(1) : cls;
  }
  function fmtDur(sec) {
    var min = Math.round(sec / 60);
    var h = Math.floor(min / 60);
    var m = min % 60;
    if (h) return m ? h + "h " + m + "m" : h + "h";
    return m + "m";
  }
  function fmtSec(sec) {
    sec = Math.max(0, Math.floor(sec));
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    return h + "h " + String(m).padStart(2, "0") + "m " + String(s).padStart(2, "0") + "s";
  }
  function el(id) {
    return document.getElementById(id);
  }

  // -- state -----------------------------------------------------------------

  var range = "today";
  var online = false;
  var live = { active: false, sessionSec: 0, todaySec: 0 };
  var colorMap = {}; // key -> colour, stable within a render
  var charts = { hero: null, donut: null, trend: null };

  function colorFor(key) {
    if (key === DESKTOP_KEY) return IDLE_COLOR;
    return colorMap[key] || "#8a9a9d";
  }

  function buildColorMap(apps) {
    colorMap = {};
    apps.forEach(function (a, i) {
      var key = keyOf(a.app_class);
      var known = a.app_class && KNOWN[a.app_class.toLowerCase()];
      colorMap[key] = known ? known.color : PALETTE[i % PALETTE.length];
    });
  }

  // -- bucketing (client-side, from the raw timeline spans) ------------------

  function makeBuckets(win) {
    var buckets = [];
    if (range === "today") {
      for (var h = 0; h < 24; h++) {
        var s = win.start + h * 3600;
        buckets.push({ start: s, end: s + 3600, label: String(h).padStart(2, "0") });
      }
    } else {
      var wk = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
      var day = 86400,
        t = win.start,
        i = 0;
      while (t < win.end - 1) {
        buckets.push({
          start: t,
          end: t + day,
          label: range === "week" ? wk[i % 7] : String(i + 1),
        });
        t += day;
        i++;
      }
    }
    return buckets;
  }

  // Returns { buckets, perApp: {key:[sec per bucket]}, active:[sec], appKeys:[...] }
  function bucketize(spans, buckets) {
    var perApp = {};
    var active = buckets.map(function () {
      return 0;
    });
    spans.forEach(function (sp) {
      var key = keyOf(sp.app_class);
      if (!perApp[key])
        perApp[key] = buckets.map(function () {
          return 0;
        });
      for (var i = 0; i < buckets.length; i++) {
        var b = buckets[i];
        var ov = Math.min(sp.end, b.end) - Math.max(sp.start, b.start);
        if (ov > 0) {
          perApp[key][i] += ov;
          active[i] += ov;
        }
      }
    });
    return { buckets: buckets, perApp: perApp, active: active, appKeys: Object.keys(perApp) };
  }

  // -- ECharts (vendored) ----------------------------------------------------

  function ensureCharts() {
    if (charts.hero || !window.echarts) return;
    charts.hero = echarts.init(el("hero"), null, { renderer: "canvas" });
    charts.donut = echarts.init(el("donut"), null, { renderer: "canvas" });
    charts.trend = echarts.init(el("trend"), null, { renderer: "canvas" });
    window.addEventListener("resize", function () {
      ["hero", "donut", "trend"].forEach(function (k) {
        if (charts[k]) charts[k].resize();
      });
    });
  }

  var TT = {
    backgroundColor: "#0d1416",
    borderColor: "#1c2527",
    borderWidth: 1,
    textStyle: { color: "#c8d3d5", fontFamily: "JetBrains Mono", fontSize: 11 },
    padding: [8, 11],
  };
  function axis(unit) {
    return {
      grid: { left: 6, right: 14, top: 16, bottom: 4, containLabel: true },
      xAxis: {
        type: "category",
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#1c2527" } },
        axisLabel: { color: "#5f6f71", fontFamily: "JetBrains Mono", fontSize: 10 },
      },
      yAxis: {
        type: "value",
        name: unit,
        nameTextStyle: { color: "#4a5759", fontSize: 9, align: "right" },
        splitLine: { lineStyle: { color: "#141b1c" } },
        axisLabel: { color: "#5f6f71", fontFamily: "JetBrains Mono", fontSize: 10 },
      },
    };
  }

  function renderCharts(summary, bkt) {
    ensureCharts();
    if (!charts.hero) return;
    var toH = range !== "today";
    var unit = toH ? "h" : "min";
    var conv = function (sec) {
      return toH ? +(sec / 3600).toFixed(2) : +(sec / 60).toFixed(1);
    };
    var fmtV = function (v) {
      return toH ? Math.round(v * 10) / 10 + "h" : Math.round(v) + "m";
    };
    var ax = axis(unit);
    var labels = bkt.buckets.map(function (b) {
      return b.label;
    });

    // Stacked distribution: one series per app, in the summary's (longest-first) order.
    var series = summary.apps.map(function (a) {
      var key = keyOf(a.app_class);
      return {
        name: prettify(a.app_class),
        type: "bar",
        stack: "t",
        barMaxWidth: 30,
        itemStyle: { color: colorFor(key) },
        emphasis: { focus: "series" },
        data: (bkt.perApp[key] || labels.map(function () { return 0; })).map(conv),
      };
    });
    charts.hero.setOption(
      {
        tooltip: Object.assign({}, TT, { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: fmtV }),
        grid: ax.grid,
        xAxis: Object.assign({}, ax.xAxis, { data: labels }),
        yAxis: ax.yAxis,
        series: series,
      },
      true
    );

    // Application share donut.
    charts.donut.setOption(
      {
        tooltip: Object.assign({}, TT, { trigger: "item", valueFormatter: fmtV }),
        title: {
          text: fmtDur(summary.active_seconds),
          subtext: "active · " + range,
          left: "center",
          top: "40%",
          textStyle: { color: "#e8f0f1", fontFamily: "JetBrains Mono", fontSize: 22, fontWeight: 700 },
          subtextStyle: { color: "#5f6f71", fontFamily: "JetBrains Mono", fontSize: 10 },
        },
        series: [
          {
            type: "pie",
            radius: ["58%", "82%"],
            center: ["50%", "50%"],
            avoidLabelOverlap: true,
            label: { show: false },
            labelLine: { show: false },
            itemStyle: { borderColor: "#0d1213", borderWidth: 2 },
            data: summary.apps.map(function (a) {
              return {
                name: prettify(a.app_class),
                value: conv(a.seconds),
                itemStyle: { color: colorFor(keyOf(a.app_class)) },
              };
            }),
          },
        ],
      },
      true
    );

    // Active vs. idle over time. Idle per bucket = elapsed-in-bucket minus active (context
    // only; idle is never stored or counted in totals).
    var nowMs = Date.now() / 1000;
    var idle = bkt.buckets.map(function (b, i) {
      var elapsed = Math.max(0, Math.min(nowMs, b.end) - b.start);
      return Math.max(0, elapsed - bkt.active[i]);
    });
    charts.trend.setOption(
      {
        tooltip: Object.assign({}, TT, { trigger: "axis", valueFormatter: fmtV }),
        grid: { left: 6, right: 14, top: 16, bottom: 4, containLabel: true },
        xAxis: Object.assign({}, ax.xAxis, { boundaryGap: false, data: labels }),
        yAxis: ax.yAxis,
        series: [
          {
            name: "active",
            type: "line",
            smooth: true,
            stack: "x",
            symbol: "none",
            lineStyle: { color: "#3fb950", width: 2 },
            areaStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: "rgba(63,185,80,.38)" },
                { offset: 1, color: "rgba(63,185,80,.02)" },
              ]),
            },
            data: bkt.active.map(conv),
          },
          {
            name: "idle",
            type: "line",
            smooth: true,
            stack: "x",
            symbol: "none",
            lineStyle: { color: "#3a474a", width: 1.5 },
            areaStyle: { color: "rgba(58,71,74,.28)" },
            data: idle.map(conv),
          },
        ],
      },
      true
    );

    // ECharts captures container width at init; if the layout wasn't settled then, the
    // canvas can be born narrow. Re-fit to the real container on every render.
    ["hero", "donut", "trend"].forEach(function (k) {
      if (charts[k]) charts[k].resize();
    });
  }

  // -- panels ----------------------------------------------------------------

  function renderCurrent(cur) {
    live.active = !!cur.active;
    live.sessionSec = cur.session_seconds || 0;
    var app = cur.active ? prettify(cur.app_class) : "—";
    var cls = cur.active ? (cur.app_class || "desktop") : "no active session";
    el("cur-app").textContent = app;
    el("cur-cls").textContent = cls;
    var swatchColor = cur.active ? colorFor(keyOf(cur.app_class)) : "#5f6f71";
    var sw = el("cur-swatch");
    sw.style.background = swatchColor;
    sw.style.boxShadow = "0 0 10px " + swatchColor;

    var state = el("state");
    if (cur.active) {
      state.className = "state-pill state-active";
      state.innerHTML = '<span class="dot"></span>ACTIVE';
    } else {
      state.className = "state-pill state-idle";
      state.innerHTML = '<span class="dot"></span>IDLE';
    }
    el("session").textContent = cur.active ? fmtSec(live.sessionSec) : "—";
  }

  function renderKpis(summary, timeline, bkt) {
    var apps = summary.apps;
    var switches = 0,
      prev = null;
    var sorted = timeline.spans.slice().sort(function (a, b) {
      return a.start - b.start;
    });
    var longest = 0,
      run = 0,
      runKey = null,
      runEnd = null;
    sorted.forEach(function (sp) {
      var key = keyOf(sp.app_class);
      if (prev !== null && key !== prev) switches++;
      prev = key;
      // Longest single-app streak: merge contiguous same-app spans.
      if (key === runKey && runEnd !== null && sp.start - runEnd <= 2) {
        run += sp.seconds;
      } else {
        run = sp.seconds;
        runKey = key;
      }
      runEnd = sp.end;
      if (run > longest) longest = run;
    });

    var cards;
    if (range === "today") {
      var idleTotal = bkt.buckets.reduce(function (acc, b, i) {
        var elapsed = Math.max(0, Math.min(Date.now() / 1000, b.end) - b.start);
        return acc + Math.max(0, elapsed - bkt.active[i]);
      }, 0);
      cards = [
        { label: "Active time", value: fmtDur(summary.active_seconds), sub: "tracked today", accent: "#3fb950" },
        { label: "Idle time", value: fmtDur(idleTotal), sub: "excluded from totals", accent: IDLE_COLOR },
        { label: "Focus switches", value: switches, sub: "app changes", accent: "#4c9aff" },
        { label: "Apps used", value: apps.length, sub: "distinct windows", accent: "#bc8cff" },
        { label: "Longest session", value: fmtDur(longest), sub: "single-app streak", accent: "#e3b341" },
      ];
    } else {
      var activeDays = bkt.active.filter(function (s) {
        return s > 0;
      }).length;
      var avg = summary.active_seconds / Math.max(1, activeDays);
      var busiest = bkt.active.reduce(function (m, s) {
        return Math.max(m, s);
      }, 0);
      cards = [
        { label: "Active time", value: fmtDur(summary.active_seconds), sub: "this " + range, accent: "#3fb950" },
        { label: "Daily average", value: fmtDur(avg), sub: "per active day", accent: "#39c5cf" },
        { label: "Focus switches", value: switches, sub: "app changes", accent: "#4c9aff" },
        { label: "Apps used", value: apps.length, sub: "distinct windows", accent: "#bc8cff" },
        { label: "Busiest day", value: fmtDur(busiest), sub: "peak active total", accent: "#e3b341" },
      ];
    }
    el("kpis").innerHTML = cards
      .map(function (k) {
        return (
          '<div class="kpi"><div class="stripe" style="background:' +
          k.accent +
          '"></div><div class="k-label">' +
          k.label +
          '</div><div class="k-value">' +
          k.value +
          '</div><div class="k-sub">' +
          k.sub +
          "</div></div>"
        );
      })
      .join("");
  }

  function renderLegend(summary) {
    el("dist-legend").innerHTML = summary.apps
      .slice(0, 6)
      .map(function (a) {
        return (
          '<span class="item"><span class="sw" style="background:' +
          colorFor(keyOf(a.app_class)) +
          '"></span>' +
          prettify(a.app_class) +
          "</span>"
        );
      })
      .join("");
  }

  function renderTable(summary) {
    var apps = summary.apps;
    var rows = el("app-rows");
    if (!apps.length) {
      rows.innerHTML = '<div class="empty">No activity recorded in this range yet.</div>';
      return;
    }
    var max = apps[0].seconds || 1;
    rows.innerHTML = apps
      .map(function (a) {
        var key = keyOf(a.app_class);
        var color = colorFor(key);
        return (
          '<div class="table-row">' +
          '<span class="sw" style="background:' + color + '"></span>' +
          '<div><div class="app-name">' + prettify(a.app_class) + "</div>" +
          '<div class="app-cls">' + (a.app_class || "—") + "</div></div>" +
          '<span class="num">' + a.sessions + "</span>" +
          '<span class="time">' + fmtDur(a.seconds) + "</span>" +
          '<span class="num">' + Math.round(a.share * 100) + "%</span>" +
          '<div class="bar"><div style="width:' + Math.round((a.seconds / max) * 100) + "%;background:" + color + '"></div></div>' +
          "</div>"
        );
      })
      .join("");
  }

  function renderFocusBand(bkt) {
    var panel = el("focus-panel");
    if (range !== "today") {
      panel.style.display = "none";
      return;
    }
    panel.style.display = "";
    // Daytime hours 07..20, dominant app colour per hour (matches the comp).
    var band = el("focus-band");
    var hours = el("focus-hours");
    var segs = [],
      labels = [];
    for (var h = 7; h <= 20; h++) {
      var domKey = null,
        domV = 0,
        activeSec = bkt.active[h] || 0;
      bkt.appKeys.forEach(function (key) {
        var v = bkt.perApp[key][h] || 0;
        if (v > domV) {
          domV = v;
          domKey = key;
        }
      });
      var color = activeSec > 60 ? colorFor(domKey) : "#232d2c";
      var title = String(h).padStart(2, "0") + ":00 · " + (domKey ? prettify(domKey === DESKTOP_KEY ? null : domKey) : "idle");
      segs.push('<div class="seg" title="' + title + '" style="background:' + color + '"></div>');
      labels.push("<span>" + String(h).padStart(2, "0") + "</span>");
    }
    band.innerHTML = segs.join("");
    hours.innerHTML = labels.join("");
  }

  // -- connection + polling --------------------------------------------------

  function setOnline(ok) {
    online = ok;
    var conn = el("conn");
    if (ok) {
      conn.className = "badge badge-live";
      conn.innerHTML = '<span class="dot"></span>local-only';
    } else {
      conn.className = "badge badge-offline";
      conn.innerHTML = '<span class="dot"></span>offline · retrying';
    }
  }

  function getJSON(path) {
    return fetch(path, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function refresh() {
    Promise.all([
      getJSON("/api/current"),
      getJSON("/api/summary?range=" + range),
      getJSON("/api/timeline?range=" + range),
    ])
      .then(function (res) {
        var cur = res[0],
          summary = res[1],
          timeline = res[2];
        setOnline(true);
        buildColorMap(summary.apps);
        var bkt = bucketize(timeline.spans, makeBuckets(summary.window));
        live.todaySec = summary.active_seconds; // resync the ticking counter
        renderCurrent(cur);
        el("today").textContent = fmtDur(live.todaySec);
        renderKpis(summary, timeline, bkt);
        renderLegend(summary);
        renderCharts(summary, bkt);
        renderFocusBand(bkt);
        renderTable(summary);
      })
      .catch(function () {
        setOnline(false); // freeze counters, keep the last view, keep retrying
      });
  }

  function tick() {
    if (!online || !live.active) return; // frozen while idle or offline
    live.sessionSec += 1;
    live.todaySec += 1;
    el("session").textContent = fmtSec(live.sessionSec);
    el("today").textContent = fmtDur(live.todaySec);
  }

  function setRange(r) {
    if (r === range) return;
    range = r;
    el("range-label").textContent = r === "today" ? "today" : r === "week" ? "this week" : "this month";
    Array.prototype.forEach.call(el("toggle").children, function (b) {
      b.classList.toggle("active", b.getAttribute("data-range") === r);
    });
    refresh();
  }

  function init() {
    el("toggle").addEventListener("click", function (e) {
      var r = e.target.getAttribute("data-range");
      if (r) setRange(r);
    });
    refresh();
    setInterval(refresh, POLL_MS);
    setInterval(tick, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
