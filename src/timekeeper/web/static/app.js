/* TimeKeeper live view + historical navigation (Phase 6 + Phase 9, refined).
 *
 * The top strip's last four tiles (Focus window / Stage / Current session / Active today) are a
 * permanent "right now" status: they poll /api/current + today's summary every ~2s and tick
 * each second, whatever window you're browsing below. The first five tiles + the charts + the
 * table reflect the *selected* window (Day/Week/Month/Year/Custom), fetched on navigation (and
 * live-refreshed while viewing today). Charts read the server-bucketed /api/buckets; the two
 * old time-series panels are merged into one (per-app stacked bars + an idle line).
 */
(function () {
  "use strict";

  var POLL_MS = 2000;
  var PALETTE = ["#3fb950", "#4c9aff", "#bc8cff", "#39c5cf", "#f0883e", "#e3b341"];
  var IDLE_COLOR = "#e3b341";
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

  var state = {
    period: "today", // today (live) | day | week | month | year | custom
    anchor: null,
    customStart: null,
    customEnd: null,
    extent: null,
  };
  var online = false;
  var live = { active: false, sessionSec: 0, windowSec: 0, todaySec: 0 };
  var lastWindow = null;
  var colorMap = {};
  var charts = { hero: null, donut: null };

  function isLive() {
    return state.period === "today" && state.anchor === null;
  }
  function effectivePeriod() {
    return state.period === "today" ? "day" : state.period;
  }

  function colorFor(key) {
    if (key === DESKTOP_KEY) return "#3a474a";
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

  function windowParams() {
    if (state.period === "custom") {
      if (!state.customStart || !state.customEnd) return null;
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
      updateNav();
      return;
    }
    el("custom-row").style.display = "none";
    if (state.anchor === null) state.anchor = new Date();
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
    else return;
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

  function updateNav() {
    syncToggle();
    el("range-label").textContent = periodLabel();

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
    window.addEventListener("resize", function () {
      ["hero", "donut"].forEach(function (k) {
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
      grid: { left: 6, right: 14, top: 18, bottom: 4, containLabel: true },
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

  // Combined chart: per-app active as stacked bars + total idle as an overlaid line, on the
  // shared bucket x-axis (the two old panels merged). Plus the application-share donut.
  function renderCharts(summary, bkt) {
    ensureCharts();
    if (!charts.hero) return;
    var toH = bkt.granularity !== "hour";
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
        barMaxWidth: 34,
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

    // Idle per bucket = elapsed-in-bucket minus active (context only; never stored/counted).
    var nowS = Date.now() / 1000;
    var idle = bkt.buckets.map(function (b, i) {
      var elapsed = Math.max(0, Math.min(nowS, b.end) - b.start);
      return Math.max(0, elapsed - bkt.active[i]);
    });
    series.push({
      name: "idle",
      type: "line",
      smooth: true,
      symbol: "none",
      z: 5,
      lineStyle: { color: IDLE_COLOR, width: 1.5, type: "dashed" },
      areaStyle: { color: "rgba(227,179,65,.05)" },
      data: idle.map(conv),
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

    ["hero", "donut"].forEach(function (k) {
      if (charts[k]) charts[k].resize();
    });
  }

  // -- top-stat strip --------------------------------------------------------

  // The four "right now" tiles: focused window, stage, current session, + the active/idle live
  // flag driving the counters. Always reflects the present, regardless of the window viewed.
  function renderLiveTiles(cur) {
    live.active = !!(cur && cur.active);
    var app = el("cur-app"),
      sw = el("cur-swatch"),
      stateEl = el("state"),
      session = el("session");
    if (live.active) {
      live.sessionSec = cur.session_seconds || 0;
      app.textContent = prettify(cur.app_class);
      var color = colorFor(keyOf(cur.app_class));
      sw.style.background = color;
      sw.style.boxShadow = "0 0 8px " + color;
      stateEl.className = "state-pill state-active";
      stateEl.innerHTML = '<span class="dot"></span>ACTIVE';
      session.textContent = fmtSec(live.sessionSec);
    } else {
      app.textContent = "—";
      sw.style.background = "#5f6f71";
      sw.style.boxShadow = "none";
      stateEl.className = "state-pill state-idle";
      stateEl.innerHTML = '<span class="dot"></span>IDLE';
      session.textContent = "—";
    }
  }

  function setToday(todaySummary) {
    live.todaySec = todaySummary.active_seconds || 0;
    el("today").textContent = fmtDur(live.todaySec);
  }

  // The five window tiles: active/idle/switches/apps/longest for the *selected* window.
  function renderRangeTiles(summary, bkt, timeline) {
    live.windowSec = summary.active_seconds;
    el("v-active").textContent = fmtDur(summary.active_seconds);
    el("v-apps").textContent = summary.apps.length;

    var nowS = Date.now() / 1000;
    var idleTotal = bkt.buckets.reduce(function (acc, b, i) {
      var elapsed = Math.max(0, Math.min(nowS, b.end) - b.start);
      return acc + Math.max(0, elapsed - bkt.active[i]);
    }, 0);
    el("v-idle").textContent = fmtDur(idleTotal);

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
    el("v-switches").textContent = switches;
    el("v-longest").textContent = fmtDur(longest);
  }

  function renderLegend(summary) {
    var items = summary.apps
      .slice(0, 6)
      .map(function (a) {
        return '<span class="item"><span class="sw" style="background:' + colorFor(keyOf(a.app_class)) + '"></span>' + prettify(a.app_class) + "</span>";
      })
      .join("");
    items += '<span class="item"><span class="sw" style="background:' + IDLE_COLOR + '"></span>idle</span>';
    el("dist-legend").innerHTML = items;
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

  // -- connection + fetching -------------------------------------------------

  function setOnline(ok) {
    if (ok === online) return;
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

  // The always-live strip: current session + today's total. Runs every poll.
  function refreshLive() {
    return Promise.all([getJSON("/api/current"), getJSON("/api/summary?range=today")])
      .then(function (res) {
        setOnline(true);
        renderLiveTiles(res[0]);
        setToday(res[1]);
      })
      .catch(function () {
        setOnline(false);
      });
  }

  // The selected-window view: range tiles + charts + table. Runs on navigation (and each poll
  // while viewing today, so the live day keeps updating).
  function refreshWindow() {
    var wp = windowParams();
    if (wp === null) {
      updateNav();
      return Promise.resolve();
    }
    return Promise.all([
      getJSON("/api/summary?" + wp),
      getJSON("/api/buckets?" + wp),
      getJSON("/api/timeline?" + wp),
      state.extent ? Promise.resolve(state.extent) : getJSON("/api/extent"),
    ])
      .then(function (res) {
        var summary = res[0],
          bucketsResp = res[1],
          timeline = res[2];
        state.extent = res[3];
        setOnline(true);
        lastWindow = summary.window;
        buildColorMap(summary.apps);
        var bkt = toBkt(bucketsResp, effectivePeriod());
        renderRangeTiles(summary, bkt, timeline);
        renderLegend(summary);
        renderCharts(summary, bkt);
        renderTable(summary);
        updateNav();
      })
      .catch(function () {
        setOnline(false);
      });
  }

  function refresh() {
    refreshWindow();
    refreshLive();
  }

  function poll() {
    refreshLive();
    if (isLive()) refreshWindow(); // the live day keeps its charts/table current
  }

  function tick() {
    if (!online || !live.active) return; // frozen while idle or offline
    live.sessionSec += 1;
    live.todaySec += 1;
    el("session").textContent = fmtSec(live.sessionSec);
    el("today").textContent = fmtDur(live.todaySec);
    if (isLive()) {
      live.windowSec += 1;
      el("v-active").textContent = fmtDur(live.windowSec);
    }
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
