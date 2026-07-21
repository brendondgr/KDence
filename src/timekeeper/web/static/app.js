/* TimeKeeper live view + historical navigation (Phase 6 + Phase 9).
 *
 * Polls the read-back API (~2s) for the live "today" view; between polls the two counters
 * tick locally each second, FROZEN while idle or offline (Step 6.1/6.2). Phase 9 adds date
 * navigation: a Day/Week/Month/Year/Custom selector, prev/next stepping, and a date picker
 * bounded by /api/extent, so any historical window can be scrubbed. Totals/table come from
 * /api/summary; the time-series charts come from the server-bucketed /api/buckets (so a year
 * view never ships every raw span); the focus band (day view only) uses /api/timeline.
 */
(function () {
  "use strict";

  var POLL_MS = 2000;
  var PALETTE = ["#3fb950", "#4c9aff", "#bc8cff", "#39c5cf", "#f0883e", "#e3b341"];
  var IDLE_COLOR = "#3a474a";
  var DESKTOP_KEY = "__desktop__";
  var WK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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
  function pad(n) {
    return String(n).padStart(2, "0");
  }
  function iso(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }
  function addDays(d, n) {
    var c = new Date(d);
    c.setDate(c.getDate() + n);
    return c;
  }
  function el(id) {
    return document.getElementById(id);
  }

  // -- state -----------------------------------------------------------------

  // period: today (live) | day | week | month | year | custom
  var state = {
    period: "today",
    anchor: null, // Date for an anchored period; null = the period containing now
    customStart: null,
    customEnd: null,
    extent: null, // { earliest, latest } (seconds) from /api/extent
  };
  var online = false;
  var live = { active: false, sessionSec: 0, windowSec: 0 };
  var lastWindow = null; // { start, end } from the last summary response
  var colorMap = {};
  var charts = { hero: null, donut: null, trend: null };

  function isLive() {
    return state.period === "today" && state.anchor === null;
  }
  function isDayView() {
    return state.period === "today" || state.period === "day";
  }
  function effectivePeriod() {
    return state.period === "today" ? "day" : state.period;
  }

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

  // -- window params + navigation --------------------------------------------

  // Build the query string for the current view, or null if a custom range is incomplete.
  function windowParams() {
    if (state.period === "custom") {
      if (!state.customStart || !state.customEnd) return null;
      // end is exclusive on the server; +1 day makes the picked end date inclusive.
      return "start=" + iso(state.customStart) + "&end=" + iso(addDays(state.customEnd, 1));
    }
    if (isLive()) return "range=today";
    var anchor = state.anchor || new Date();
    return "range=" + effectivePeriod() + "&date=" + iso(anchor);
  }

  function setPeriod(p) {
    if (p === "custom") {
      state.period = "custom";
      el("custom-row").style.display = "flex";
      seedCustomDefaults();
      syncToggle();
      // Only refresh once both bounds are set (via apply).
      updateNav();
      return;
    }
    el("custom-row").style.display = "none";
    // Anchor the currently-viewed date (or now) into the chosen granularity.
    if (state.anchor === null && !isLive()) state.anchor = new Date();
    if (state.period === "today" && state.anchor === null) state.anchor = new Date();
    state.period = p;
    refresh();
  }

  function goNow() {
    state.period = "today";
    state.anchor = null;
    el("custom-row").style.display = "none";
    refresh();
  }

  function step(dir) {
    var a = new Date(state.anchor || new Date());
    var p = effectivePeriod();
    if (p === "day") a.setDate(a.getDate() + dir);
    else if (p === "week") a.setDate(a.getDate() + 7 * dir);
    else if (p === "month") a.setMonth(a.getMonth() + dir);
    else if (p === "year") a.setFullYear(a.getFullYear() + dir);
    else return; // custom doesn't step
    if (state.period === "today") state.period = "day";
    state.anchor = a;
    refresh();
  }

  function jumpToDate(value) {
    if (!value) return;
    var parts = value.split("-");
    state.anchor = new Date(+parts[0], +parts[1] - 1, +parts[2]);
    if (state.period === "today" || state.period === "custom") state.period = "day";
    el("custom-row").style.display = "none";
    refresh();
  }

  function seedCustomDefaults() {
    if (!state.customEnd) state.customEnd = new Date();
    if (!state.customStart) state.customStart = addDays(state.customEnd, -7);
    el("custom-start").value = iso(state.customStart);
    el("custom-end").value = iso(state.customEnd);
  }

  function applyCustom() {
    var s = el("custom-start").value,
      e = el("custom-end").value;
    if (!s || !e) return;
    var sp = s.split("-"),
      ep = e.split("-");
    state.customStart = new Date(+sp[0], +sp[1] - 1, +sp[2]);
    state.customEnd = new Date(+ep[0], +ep[1] - 1, +ep[2]);
    if (state.customEnd < state.customStart) {
      el("custom-hint").textContent = "end must be on/after start";
      return;
    }
    el("custom-hint").textContent = "";
    refresh();
  }

  function syncToggle() {
    var p = state.period;
    Array.prototype.forEach.call(el("period-toggle").children, function (b) {
      b.classList.toggle("active", b.getAttribute("data-period") === p);
    });
    el("now-btn").classList.toggle("active", isLive());
  }

  // Label + stepper/picker bounds, driven by the resolved window and the data extent.
  function updateNav() {
    syncToggle();
    el("range-label").textContent = periodLabel();
    el("today-label").textContent = isLive() ? "Active today" : "Active · " + shortPeriod();

    var pick = el("date-picker");
    pick.disabled = state.period === "custom";
    if (state.extent && state.extent.earliest != null) {
      pick.min = iso(new Date(state.extent.earliest * 1000));
    }
    pick.max = iso(new Date());
    if (lastWindow) pick.value = iso(new Date(lastWindow.start * 1000));

    var nowSec = Date.now() / 1000;
    var atLatest = !lastWindow || lastWindow.end >= nowSec;
    var atEarliest =
      !lastWindow || !state.extent || state.extent.earliest == null
        ? false
        : lastWindow.start <= state.extent.earliest;
    el("next").disabled = state.period === "custom" || atLatest;
    el("prev").disabled = state.period === "custom" || atEarliest;
  }

  function shortPeriod() {
    return effectivePeriod();
  }

  function periodLabel() {
    if (isLive()) return "today · live";
    if (!lastWindow) return effectivePeriod();
    var s = new Date(lastWindow.start * 1000);
    var eInclusive = new Date(lastWindow.end * 1000 - 1000);
    switch (effectivePeriod()) {
      case "day":
        return WK[(s.getDay() + 6) % 7] + " " + MON[s.getMonth()] + " " + s.getDate() + ", " + s.getFullYear();
      case "week":
        return "week of " + MON[s.getMonth()] + " " + s.getDate() + ", " + s.getFullYear();
      case "month":
        return s.toLocaleString(undefined, { month: "long" }) + " " + s.getFullYear();
      case "year":
        return String(s.getFullYear());
      case "custom":
        return MON[s.getMonth()] + " " + s.getDate() + " → " + MON[eInclusive.getMonth()] + " " + eInclusive.getDate() + ", " + eInclusive.getFullYear();
      default:
        return effectivePeriod();
    }
  }

  // -- buckets from the server (charts source) -------------------------------

  function bucketLabel(startSec, gran, period) {
    var d = new Date(startSec * 1000);
    if (gran === "hour") return pad(d.getHours());
    if (gran === "day") return period === "week" ? WK[(d.getDay() + 6) % 7] : String(d.getDate());
    if (gran === "week") return MON[d.getMonth()] + " " + d.getDate();
    return MON[d.getMonth()] + (period === "custom" ? " '" + pad(d.getFullYear() % 100) : "");
  }

  // Server buckets -> { buckets:[{start,end,label}], perApp:{key:[sec]}, active:[sec], appKeys, granularity }
  function toBkt(resp, period) {
    var gran = resp.granularity;
    var buckets = resp.buckets.map(function (b) {
      return { start: b.start, end: b.end, label: bucketLabel(b.start, gran, period) };
    });
    var perApp = {};
    var active = resp.buckets.map(function (b) {
      return b.active_seconds;
    });
    resp.buckets.forEach(function (b, i) {
      b.apps.forEach(function (a) {
        var key = keyOf(a.app_class);
        if (!perApp[key])
          perApp[key] = resp.buckets.map(function () {
            return 0;
          });
        perApp[key][i] = a.seconds;
      });
    });
    return { buckets: buckets, perApp: perApp, active: active, appKeys: Object.keys(perApp), granularity: gran };
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
    var toH = bkt.granularity !== "hour"; // hourly -> minutes, coarser -> hours
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

    var series = summary.apps.map(function (a) {
      var key = keyOf(a.app_class);
      return {
        name: prettify(a.app_class),
        type: "bar",
        stack: "t",
        barMaxWidth: 30,
        itemStyle: { color: colorFor(key) },
        emphasis: { focus: "series" },
        data: (
          bkt.perApp[key] ||
          labels.map(function () {
            return 0;
          })
        ).map(conv),
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

    charts.donut.setOption(
      {
        tooltip: Object.assign({}, TT, { trigger: "item", valueFormatter: fmtV }),
        title: {
          text: fmtDur(summary.active_seconds),
          subtext: "active · " + shortPeriod(),
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
              return { name: prettify(a.app_class), value: conv(a.seconds), itemStyle: { color: colorFor(keyOf(a.app_class)) } };
            }),
          },
        ],
      },
      true
    );

    // Active vs. idle over time. Idle per bucket = elapsed-in-bucket minus active (context
    // only; idle is never stored or counted). Future buckets (end > now) contribute no idle.
    var nowS = Date.now() / 1000;
    var idle = bkt.buckets.map(function (b, i) {
      var elapsed = Math.max(0, Math.min(nowS, b.end) - b.start);
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

    ["hero", "donut", "trend"].forEach(function (k) {
      if (charts[k]) charts[k].resize();
    });
  }

  // -- panels ----------------------------------------------------------------

  function renderCurrent(cur, liveView) {
    var app = el("cur-app"),
      cls = el("cur-cls"),
      sw = el("cur-swatch"),
      stateEl = el("state"),
      session = el("session");
    if (!liveView) {
      // Historical view: no live session. Show what's being viewed instead of a fake state.
      live.active = false;
      app.textContent = "—";
      cls.textContent = "historical view";
      sw.style.background = "#5f6f71";
      sw.style.boxShadow = "none";
      stateEl.className = "state-pill state-idle";
      stateEl.innerHTML = '<span class="dot"></span>VIEWING';
      session.textContent = "—";
      return;
    }
    live.active = !!cur.active;
    live.sessionSec = cur.session_seconds || 0;
    app.textContent = cur.active ? prettify(cur.app_class) : "—";
    cls.textContent = cur.active ? cur.app_class || "desktop" : "no active session";
    var swatchColor = cur.active ? colorFor(keyOf(cur.app_class)) : "#5f6f71";
    sw.style.background = swatchColor;
    sw.style.boxShadow = cur.active ? "0 0 10px " + swatchColor : "none";
    if (cur.active) {
      stateEl.className = "state-pill state-active";
      stateEl.innerHTML = '<span class="dot"></span>ACTIVE';
    } else {
      stateEl.className = "state-pill state-idle";
      stateEl.innerHTML = '<span class="dot"></span>IDLE';
    }
    session.textContent = cur.active ? fmtSec(live.sessionSec) : "—";
  }

  function renderKpis(summary, bkt, timeline, dayView) {
    var apps = summary.apps;
    var nowS = Date.now() / 1000;
    var idleTotal = bkt.buckets.reduce(function (acc, b, i) {
      var elapsed = Math.max(0, Math.min(nowS, b.end) - b.start);
      return acc + Math.max(0, elapsed - bkt.active[i]);
    }, 0);

    var cards;
    if (dayView) {
      // Switches + longest streak need the raw spans (only fetched for a day).
      var switches = 0,
        prev = null,
        longest = 0,
        run = 0,
        runKey = null,
        runEnd = null;
      timeline.spans
        .slice()
        .sort(function (a, b) {
          return a.start - b.start;
        })
        .forEach(function (sp) {
          var key = keyOf(sp.app_class);
          if (prev !== null && key !== prev) switches++;
          prev = key;
          if (key === runKey && runEnd !== null && sp.start - runEnd <= 2) run += sp.seconds;
          else {
            run = sp.seconds;
            runKey = key;
          }
          runEnd = sp.end;
          if (run > longest) longest = run;
        });
      cards = [
        { label: "Active time", value: fmtDur(summary.active_seconds), sub: "tracked", accent: "#3fb950" },
        { label: "Idle time", value: fmtDur(idleTotal), sub: "excluded from totals", accent: IDLE_COLOR },
        { label: "Focus switches", value: switches, sub: "app changes", accent: "#4c9aff" },
        { label: "Apps used", value: apps.length, sub: "distinct windows", accent: "#bc8cff" },
        { label: "Longest session", value: fmtDur(longest), sub: "single-app streak", accent: "#e3b341" },
      ];
    } else {
      var activeBuckets = bkt.active.filter(function (s) {
        return s > 0;
      }).length;
      var avg = summary.active_seconds / Math.max(1, activeBuckets);
      var busiest = bkt.active.reduce(function (m, s) {
        return Math.max(m, s);
      }, 0);
      var unitName = bkt.granularity === "week" ? "week" : bkt.granularity === "month" ? "month" : "day";
      cards = [
        { label: "Active time", value: fmtDur(summary.active_seconds), sub: "this " + shortPeriod(), accent: "#3fb950" },
        { label: "Per-" + unitName + " avg", value: fmtDur(avg), sub: "active " + unitName + "s only", accent: "#39c5cf" },
        { label: "Active " + unitName + "s", value: activeBuckets, sub: "with tracked time", accent: "#4c9aff" },
        { label: "Apps used", value: apps.length, sub: "distinct windows", accent: "#bc8cff" },
        { label: "Busiest " + unitName, value: fmtDur(busiest), sub: "peak active total", accent: "#e3b341" },
      ];
    }
    el("kpis").innerHTML = cards
      .map(function (k) {
        return (
          '<div class="kpi"><div class="stripe" style="background:' + k.accent + '"></div><div class="k-label">' +
          k.label + '</div><div class="k-value">' + k.value + '</div><div class="k-sub">' + k.sub + "</div></div>"
        );
      })
      .join("");
  }

  function renderLegend(summary) {
    el("dist-legend").innerHTML = summary.apps
      .slice(0, 6)
      .map(function (a) {
        return '<span class="item"><span class="sw" style="background:' + colorFor(keyOf(a.app_class)) + '"></span>' + prettify(a.app_class) + "</span>";
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

  function renderFocusBand(bkt, dayView) {
    var panel = el("focus-panel");
    if (!dayView || bkt.granularity !== "hour") {
      panel.style.display = "none";
      return;
    }
    panel.style.display = "";
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
      var title = pad(h) + ":00 · " + (domKey ? prettify(domKey === DESKTOP_KEY ? null : domKey) : "idle");
      segs.push('<div class="seg" title="' + title + '" style="background:' + color + '"></div>');
      labels.push("<span>" + pad(h) + "</span>");
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
    var wp = windowParams();
    if (wp === null) {
      updateNav();
      return; // custom range not fully specified yet
    }
    var liveView = isLive();
    var dayView = isDayView();
    Promise.all([
      getJSON("/api/summary?" + wp),
      getJSON("/api/buckets?" + wp),
      liveView ? getJSON("/api/current") : Promise.resolve(null),
      dayView ? getJSON("/api/timeline?" + wp) : Promise.resolve({ spans: [] }),
      state.extent ? Promise.resolve(state.extent) : getJSON("/api/extent"),
    ])
      .then(function (res) {
        var summary = res[0],
          bucketsResp = res[1],
          cur = res[2],
          timeline = res[3],
          extent = res[4];
        state.extent = extent;
        setOnline(true);
        lastWindow = summary.window;
        buildColorMap(summary.apps);
        var bkt = toBkt(bucketsResp, effectivePeriod());
        live.windowSec = summary.active_seconds; // resync the ticking counter
        renderCurrent(cur, liveView);
        el("today").textContent = fmtDur(live.windowSec);
        renderKpis(summary, bkt, timeline, dayView);
        renderLegend(summary);
        renderCharts(summary, bkt);
        renderFocusBand(bkt, dayView);
        renderTable(summary);
        updateNav();
      })
      .catch(function () {
        setOnline(false); // freeze counters, keep the last view, keep retrying
      });
  }

  function tick() {
    if (!online || !isLive() || !live.active) return; // frozen while historical/idle/offline
    live.sessionSec += 1;
    live.windowSec += 1;
    el("session").textContent = fmtSec(live.sessionSec);
    el("today").textContent = fmtDur(live.windowSec);
  }

  function poll() {
    if (isLive()) refresh(); // only the live view needs periodic refresh
  }

  function init() {
    el("period-toggle").addEventListener("click", function (e) {
      var p = e.target.getAttribute("data-period");
      if (p) setPeriod(p);
    });
    el("prev").addEventListener("click", function () {
      step(-1);
    });
    el("next").addEventListener("click", function () {
      step(1);
    });
    el("now-btn").addEventListener("click", goNow);
    el("date-picker").addEventListener("change", function (e) {
      jumpToDate(e.target.value);
    });
    el("custom-apply").addEventListener("click", applyCustom);
    refresh();
    setInterval(poll, POLL_MS);
    setInterval(tick, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
