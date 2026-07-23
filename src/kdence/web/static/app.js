/* KDence live view + historical navigation (Phase 6 + Phase 9, refined).
 *
 * The top strip's last four tiles (Focus window / Stage / Current session / Active today) are a
 * permanent "right now" status: they poll /api/current + today's summary every ~2s and tick
 * each second, whatever window you're browsing below. The first five tiles + the charts + the
 * table reflect the *selected* window (Day/Week/Month/Year/Custom), fetched on navigation (and
 * live-refreshed while viewing today). Charts read the server-bucketed /api/buckets; the two
 * old time-series panels are merged into one (stacked bars + an idle line).
 *
 * The APPS/GROUPS toggle (left of the period toggle) segments the bars + application-share donut
 * either per individual app or rolled up per category. Either way the colours are the
 * category-derived colours the server computes for the "by category" table, so a graph item
 * always matches the swatch it wears there (no more app-palette vs. category-palette mismatch).
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
    librewolf: { name: "LibreWolf", color: "#00acff" },
    "brave-browser": { name: "Brave", color: "#fb542b" },
    brave: { name: "Brave", color: "#fb542b" },
    chromium: { name: "Chromium", color: "#6f9bf7" },
    "google-chrome": { name: "Chrome", color: "#6f9bf7" },
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
  // Single-unit, one-decimal reading: "4.3 h" once we're past an hour, otherwise "1.1 m".
  // Deliberately never mixes h+m in one figure -- easier to eyeball at a glance.
  function fmt1(sec) {
    sec = Math.max(0, sec || 0);
    return sec >= 3600 ? (sec / 3600).toFixed(1) + " h" : (sec / 60).toFixed(1) + " m";
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
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function siteLabel(site) {
    return site === null || site === undefined ? "(other)" : site;
  }

  // A generic in-app detail label (site host, document, or media track). Null == the app's
  // time with no detail attributed (an internal browser page, a moment before a report, etc.).
  function detailLabel(detail) {
    return detail === null || detail === undefined ? "(other)" : detail;
  }

  // Tag a drill-down row with its provider unless it's a browser site (the long-standing,
  // self-evident case). So documents read "… caption" and tracks "… mpris".
  function detailSourceTag(source) {
    return source && source !== "site" ? source : "";
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
  // Snapshot the last hero render so hover handlers can resolve a bar to its app + bucket totals.
  var heroCtx = null;
  // True while the pointer is over the hero chart: a background poll must not tear the chart down
  // under the user (that would drop the open tooltip / per-bar side popup mid-hover).
  var heroHot = false;
  // Locked breakdown bucket (a hero dataIndex) when the user clicks a bar to pin it; null means the
  // side breakdown panel follows the hovered bar instead. Survives live re-renders (re-applied).
  var heroLock = null;
  var expanded = {}; // app/group key -> is its drill-down open (survives live re-renders)
  var tableSummary = null; // last summary rendered, so a click can re-render in place
  var tableMode = "app"; // 'app' | 'group'
  var chartMode = "app"; // 'app' | 'group' -- colour/segment the charts by app or by category
  var lastRender = null; // {summary, bkt} of the last chart render, so the toggle can re-draw in place
  var catConfig = null; // /api/categories payload (palette, categories, assignments, defaults)
  var editing = false; // is the group editor open
  var draft = null; // working copy of the config while editing
  var pickedColor = null; // selected swatch for a new category

  function isLive() {
    return state.period === "today" && state.anchor === null;
  }
  function effectivePeriod() {
    return state.period === "today" ? "day" : state.period;
  }

  var UNCAT = { id: "uncategorized", name: "Uncategorized", color: "#8a9a9d" };

  function colorFor(key) {
    if (key === DESKTOP_KEY) return "#3a474a";
    return colorMap[key] || "#8a9a9d";
  }
  // Per-app colours come straight from the server-computed category breakdown, so a bar/slice
  // is always the same colour its app wears in the "by category" table. An app appears once per
  // category (a browser can span several by site); we keep the shade of its largest member.
  function buildColorMap(summary) {
    colorMap = {};
    var pick = {};
    (summary.groups || []).forEach(function (g) {
      g.apps.forEach(function (m) {
        var key = keyOf(m.app_class);
        if (colorMap[key] === undefined || m.seconds > pick[key]) {
          colorMap[key] = m.color;
          pick[key] = m.seconds;
        }
      });
    });
    // Safety net for any app not present in the group rollup (shouldn't happen).
    (summary.apps || []).forEach(function (a, i) {
      var key = keyOf(a.app_class);
      if (colorMap[key] === undefined) colorMap[key] = PALETTE[i % PALETTE.length];
    });
  }

  // The category an app_class belongs to, from the loaded config's single assignment (browsers
  // resolve to their app's category here -- the per-site split lives only in the table/rollup).
  function catForApp(appClass) {
    if (!catConfig) return UNCAT;
    var byId = {};
    (catConfig.categories || []).forEach(function (c) {
      byId[c.id] = c;
    });
    var cid = (appClass && catConfig.assignments[appClass]) || catConfig.uncategorized_id;
    return byId[cid] || byId[catConfig.uncategorized_id] || UNCAT;
  }
  function catIdForKey(key) {
    return catForApp(key === DESKTOP_KEY ? null : key).id;
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
    // Freeze the hero chart against background re-renders while the pointer is engaged with it, so
    // an open breakdown popup survives the poll cycle and closes only when the user moves away.
    var heroEl = el("hero");
    heroEl.addEventListener("mouseenter", function () {
      heroHot = true;
    });
    heroEl.addEventListener("mouseleave", function () {
      heroHot = false;
      if (heroLock == null) showBreakdownPlaceholder();
    });
    var unpinBtn = el("bd-unpin");
    if (unpinBtn) unpinBtn.addEventListener("click", unpinBreakdown);
    showBreakdownPlaceholder();
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

  // Small square colour chip used inline in the tooltip + side popup.
  function swatchHTML(color) {
    return (
      '<span style="display:inline-block;margin-right:6px;border-radius:2px;width:9px;height:9px;' +
      'vertical-align:middle;background-color:' + color + '"></span>'
    );
  }

  // Side breakdown panel: the full per-bucket breakdown (the same content the old mouse-following
  // axis tooltip carried) rendered into a fixed, scrollable panel beside the chart instead of
  // chasing the cursor. Hovering a bar previews that bucket; clicking a bar pins it (heroLock) so
  // the pointer can leave and the details can be scrolled. Bound once per chart instance.
  function bindHeroBreakdown() {
    if (!charts.hero || charts.hero.__bdBound) return;
    charts.hero.__bdBound = true;
    charts.hero.on("mouseover", function (p) {
      if (heroLock != null || !heroCtx) return;
      if (p.componentType !== "series" || p.seriesType !== "bar") return;
      renderBreakdown(p.dataIndex);
    });
    charts.hero.on("mouseout", function () {
      if (heroLock == null) showBreakdownPlaceholder();
    });
    charts.hero.on("globalout", function () {
      if (heroLock == null) showBreakdownPlaceholder();
    });
    charts.hero.on("click", function (p) {
      if (!heroCtx || p.componentType !== "series" || p.seriesType !== "bar") return;
      if (heroLock === p.dataIndex) {
        unpinBreakdown();
      } else {
        heroLock = p.dataIndex;
        renderBreakdown(p.dataIndex);
        setPinned(true);
      }
    });
    // Clicking blank chart area (not a bar) releases any pin.
    charts.hero.getZr().on("click", function (e) {
      if (!e.target && heroLock != null) unpinBreakdown();
    });
  }
  // Rebuild the tooltip formatter's params for a whole bucket column, then reuse the exact same
  // HTML the axis tooltip produced.
  function breakdownHTMLFor(dataIndex) {
    if (!heroCtx || !heroCtx.fmt || dataIndex == null) return "";
    var params = heroCtx.seriesInfo.map(function (info, i) {
      return { seriesIndex: i, dataIndex: dataIndex, axisValueLabel: heroCtx.labels[dataIndex] || "" };
    });
    return heroCtx.fmt(params);
  }
  function renderBreakdown(dataIndex) {
    var body = el("hero-breakdown");
    if (!body) return;
    body.innerHTML =
      breakdownHTMLFor(dataIndex) || '<div class="bd-empty">No activity in this bucket.</div>';
  }
  function showBreakdownPlaceholder() {
    var body = el("hero-breakdown");
    if (body) {
      body.innerHTML =
        '<div class="bd-empty">Hover a bar to preview its breakdown · click to pin it.</div>';
    }
    setPinned(false);
  }
  function setPinned(on) {
    var title = el("bd-title"),
      btn = el("bd-unpin"),
      panel = document.querySelector(".bd-panel");
    if (title) title.textContent = on ? "Breakdown · pinned" : "Breakdown";
    if (btn) btn.hidden = !on;
    if (panel) panel.classList.toggle("pinned", !!on);
  }
  function unpinBreakdown() {
    heroLock = null;
    showBreakdownPlaceholder();
  }

  // Combined chart: active as stacked bars + total idle as an overlaid line, on the shared
  // bucket x-axis (the two old panels merged), plus the share donut. The bars/slices are
  // segmented either per-app or per-category (chartMode); either way their colours come from
  // the category config, so a graph item matches the colour it wears in the "by category" table.
  function renderCharts(summary, bkt) {
    ensureCharts();
    if (!charts.hero) return;
    lastRender = { summary: summary, bkt: bkt };
    var toH = bkt.granularity !== "hour";
    var unit = toH ? "h" : "min";
    var conv = function (sec) {
      return toH ? +(sec / 3600).toFixed(2) : +(sec / 60).toFixed(1);
    };
    var ax = axis(unit);
    var labels = bkt.buckets.map(function (b) {
      return b.label;
    });
    var zeros = function () {
      return labels.map(function () { return 0; });
    };

    // Idle per bucket = elapsed-in-bucket minus active (context only; never stored/counted).
    var nowS = Date.now() / 1000;
    var idle = bkt.buckets.map(function (b, i) {
      var elapsed = Math.max(0, Math.min(nowS, b.end) - b.start);
      return Math.max(0, elapsed - bkt.active[i]);
    });

    // Build the stacked segments + the metadata hover handlers recover from a seriesIndex.
    var built = chartMode === "group" ? buildGroupSegments(summary, bkt, zeros) : buildAppSegments(summary, bkt, zeros);
    var seriesInfo = built.seriesInfo;
    var series = built.seriesInfo
      .filter(function (info) { return !info.isIdle; })
      .map(function (info) {
        return {
          name: info.name,
          type: "bar",
          stack: "t",
          barMaxWidth: 34,
          itemStyle: { color: info.itemColor },
          emphasis: { focus: "series" },
          data: info.secs.map(conv),
        };
      });
    seriesInfo.push({ key: null, name: "idle", itemColor: IDLE_COLOR, isIdle: true, secs: idle });
    series.push({
      name: "idle",
      type: "line",
      smooth: true,
      symbol: "none",
      z: 5,
      // Non-interactive: its area fill overlays the bars, so let pointer events fall through to
      // the bar underneath (drives the per-bar popup). Still shown in the axis tooltip.
      silent: true,
      lineStyle: { color: IDLE_COLOR, width: 1.5, type: "dashed" },
      areaStyle: { color: "rgba(227,179,65,.05)" },
      data: idle.map(conv),
    });

    var heroTooltipFmt =
      chartMode === "group" ? groupTooltipFmt(seriesInfo) : appTooltipFmt(seriesInfo);
    heroCtx = { seriesInfo: seriesInfo, labels: labels, granularity: bkt.granularity, fmt: heroTooltipFmt };

    charts.hero.setOption(
      {
        // No floating tooltip box (its content now lives in the fixed side breakdown panel); keep
        // the shadow axisPointer so the hovered column still highlights.
        tooltip: { trigger: "axis", showContent: false, axisPointer: { type: "shadow" } },
        grid: ax.grid,
        xAxis: Object.assign({}, ax.xAxis, { data: labels }),
        yAxis: ax.yAxis,
        series: series,
      },
      true
    );
    bindHeroBreakdown();
    // Re-apply a pinned bucket across re-renders; drop it if the window/granularity shrank away.
    if (heroLock != null && heroLock < labels.length) {
      renderBreakdown(heroLock);
      setPinned(true);
    } else {
      heroLock = null;
      showBreakdownPlaceholder();
    }

    charts.donut.setOption(
      {
        tooltip: Object.assign({}, TT, {
          trigger: "item",
          valueFormatter: function (v) {
            return fmt1(toH ? v * 3600 : v * 60); // donut data is display units; back to seconds
          },
        }),
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
            data: built.donut.map(function (d) {
              return { name: d.name, value: conv(d.seconds), itemStyle: { color: d.color } };
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

  // Per-app segments: one series per app, coloured by its category shade; the donut mirrors the
  // per-app share. seriesInfo carries each app's category so the tooltip/popup can name it.
  function buildAppSegments(summary, bkt, zeros) {
    var appCat = {};
    (summary.groups || []).forEach(function (g) {
      g.apps.forEach(function (m) {
        var k = keyOf(m.app_class);
        if (!appCat[k]) appCat[k] = { catName: g.name, catColor: g.color };
      });
    });
    var seriesInfo = summary.apps.map(function (a) {
      var key = keyOf(a.app_class);
      var cat = appCat[key] || { catName: "Uncategorized", catColor: "#8a9a9d" };
      return {
        key: key,
        name: prettify(a.app_class),
        itemColor: colorFor(key),
        catName: cat.catName,
        catColor: cat.catColor,
        secs: bkt.perApp[key] || zeros(),
        isIdle: false,
        isGroup: false,
      };
    });
    var donut = summary.apps.map(function (a) {
      return { name: prettify(a.app_class), seconds: a.seconds, color: colorFor(keyOf(a.app_class)) };
    });
    return { seriesInfo: seriesInfo, donut: donut };
  }

  // Per-category segments: bucket time is rolled up by the app's configured category (the
  // per-site browser split lives only in the table, so a browser sits in its app's category
  // here). Categories, colours, and the donut all come from that same rollup so they reconcile.
  function buildGroupSegments(summary, bkt, zeros) {
    var meta = {}; // catId -> {name, color}
    var secs = {}; // catId -> per-bucket seconds
    var order = [];
    Object.keys(bkt.perApp).forEach(function (key) {
      var cat = catForApp(key === DESKTOP_KEY ? null : key);
      if (!secs[cat.id]) {
        secs[cat.id] = zeros();
        meta[cat.id] = { name: cat.name, color: cat.color };
        order.push(cat.id);
      }
      var arr = bkt.perApp[key];
      for (var i = 0; i < arr.length; i++) secs[cat.id][i] += arr[i] || 0;
    });
    var total = function (id) {
      return secs[id].reduce(function (s, v) { return s + v; }, 0);
    };
    order.sort(function (a, b) { return total(b) - total(a); });
    var seriesInfo = order.map(function (id) {
      return {
        key: id,
        name: meta[id].name,
        itemColor: meta[id].color,
        secs: secs[id],
        isIdle: false,
        isGroup: true,
      };
    });
    var donut = order.map(function (id) {
      return { name: meta[id].name, seconds: total(id), color: meta[id].color };
    });
    return { seriesInfo: seriesInfo, donut: donut };
  }

  // Full-column axis tooltip (per-app mode): group the bucket's apps by category (category name
  // + total on top, category base colour), list member apps >1 min under it in their own shade,
  // and roll each category's sub-minute members into one "Other" line. Idle trails as its own
  // contextual row. Categories and members both ordered by time spent, most first.
  function appTooltipFmt(seriesInfo) {
    return function (params) {
      var arr = params || [];
      if (!arr.length) return "";
      var idx = arr[0].dataIndex;
      var cats = {}; // catName -> { color, total, members: [{name,color,sec}] }
      var idleSec = 0;
      arr.forEach(function (p) {
        var info = seriesInfo[p.seriesIndex];
        if (!info) return;
        var sec = info.secs[idx] || 0;
        if (info.isIdle) { idleSec = sec; return; }
        if (sec <= 0) return;
        var c = cats[info.catName] || (cats[info.catName] = { color: info.catColor, total: 0, members: [] });
        c.total += sec;
        c.members.push({ name: info.name, color: info.itemColor, sec: sec });
      });
      var catList = Object.keys(cats).map(function (name) {
        return { name: name, color: cats[name].color, total: cats[name].total, members: cats[name].members };
      });
      if (!catList.length && idleSec <= 0) return "";
      catList.sort(function (a, b) { return b.total - a.total; });
      var head = '<div style="margin-bottom:5px;font-weight:600;color:#e8f0f1">' + esc(arr[0].axisValueLabel) + "</div>";
      var blocks = catList
        .map(function (c) {
          var shown = [];
          var otherSec = 0;
          c.members.forEach(function (m) {
            if (m.sec > 60) shown.push(m); // strictly more than one minute
            else otherSec += m.sec;
          });
          shown.sort(function (a, b) { return b.sec - a.sec; });
          if (otherSec > 0) shown.push({ name: "Other", color: "#5f6f71", sec: otherSec });
          var header =
            '<div style="margin-top:3px">' + swatchHTML(c.color) +
            '<span style="font-weight:700;color:#e8f0f1">' + esc(c.name) + "</span>" +
            '<span style="float:right;margin-left:26px;font-weight:700;color:#e8f0f1">' + fmt1(c.total) + "</span></div>";
          var rows = shown
            .map(function (m) {
              return (
                '<div style="padding-left:15px">' + swatchHTML(m.color) + esc(m.name) +
                '<span style="float:right;margin-left:26px">' + fmt1(m.sec) + "</span></div>"
              );
            })
            .join("");
          return header + rows;
        })
        .join("");
      if (idleSec > 0) {
        blocks +=
          '<div style="margin-top:4px">' + swatchHTML(IDLE_COLOR) + "idle" +
          '<span style="float:right;margin-left:26px">' + fmt1(idleSec) + "</span></div>";
      }
      return head + blocks;
    };
  }

  // Full-column axis tooltip (per-category mode): each series is already a category, so just
  // list the bucket's categories by time (base colour + total), idle trailing.
  function groupTooltipFmt(seriesInfo) {
    return function (params) {
      var arr = params || [];
      if (!arr.length) return "";
      var idx = arr[0].dataIndex;
      var rows = [];
      var idleSec = 0;
      arr.forEach(function (p) {
        var info = seriesInfo[p.seriesIndex];
        if (!info) return;
        var sec = info.secs[idx] || 0;
        if (info.isIdle) { idleSec = sec; return; }
        if (sec > 0) rows.push({ name: info.name, color: info.itemColor, sec: sec });
      });
      if (!rows.length && idleSec <= 0) return "";
      rows.sort(function (a, b) { return b.sec - a.sec; });
      var head = '<div style="margin-bottom:5px;font-weight:600;color:#e8f0f1">' + esc(arr[0].axisValueLabel) + "</div>";
      var blocks = rows
        .map(function (m) {
          return (
            '<div style="margin-top:3px">' + swatchHTML(m.color) +
            '<span style="font-weight:700;color:#e8f0f1">' + esc(m.name) + "</span>" +
            '<span style="float:right;margin-left:26px;font-weight:700;color:#e8f0f1">' + fmt1(m.sec) + "</span></div>"
          );
        })
        .join("");
      if (idleSec > 0) {
        blocks +=
          '<div style="margin-top:4px">' + swatchHTML(IDLE_COLOR) + "idle" +
          '<span style="float:right;margin-left:26px">' + fmt1(idleSec) + "</span></div>";
      }
      return head + blocks;
    };
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
    var items;
    if (chartMode === "group") {
      items = (summary.groups || [])
        .slice(0, 8)
        .map(function (g) {
          return '<span class="item"><span class="sw" style="background:' + g.color + '"></span>' + esc(g.name) + "</span>";
        })
        .join("");
    } else {
      items = summary.apps
        .slice(0, 6)
        .map(function (a) {
          return '<span class="item"><span class="sw" style="background:' + colorFor(keyOf(a.app_class)) + '"></span>' + prettify(a.app_class) + "</span>";
        })
        .join("");
    }
    items += '<span class="item"><span class="sw" style="background:' + IDLE_COLOR + '"></span>idle</span>';
    el("dist-legend").innerHTML = items;
  }

  // The chart-entity toggle: redraw the charts (and legend) from the last window's data, no
  // refetch needed. Falls back to a full refresh if nothing has been rendered yet.
  function setChartEntity(mode) {
    if (mode !== "app" && mode !== "group") return;
    chartMode = mode;
    syncChartEntity();
    if (lastRender) {
      renderCharts(lastRender.summary, lastRender.bkt);
      renderLegend(lastRender.summary);
    } else {
      refreshWindow();
    }
  }
  function syncChartEntity() {
    Array.prototype.forEach.call(el("chart-entity").children, function (b) {
      b.classList.toggle("active", b.getAttribute("data-entity") === chartMode);
    });
  }

  // A compact horizontal bar chart for a drill-down: each item {label, secondary?, seconds,
  // share, color}. Bars are scaled to the largest share so the top item reads full-width.
  function barRows(items) {
    if (!items.length) return "";
    var maxShare = items.reduce(function (m, it) {
      return Math.max(m, it.share || 0);
    }, 0) || 1;
    return items
      .map(function (it) {
        var w = Math.round(((it.share || 0) / maxShare) * 100);
        var tag = it.secondary ? '<span class="bc-tag">' + esc(it.secondary) + "</span>" : "";
        return (
          '<div class="bc-row">' +
          '<div class="bc-head"><span class="bc-dot" style="background:' + it.color + '"></span>' +
          '<span class="bc-label" title="' + esc(it.label) + '">' + esc(it.label) + "</span>" +
          tag +
          '<span class="bc-time">' + fmtDur(it.seconds) + "</span>" +
          '<span class="bc-pct">' + Math.round((it.share || 0) * 100) + "%</span></div>" +
          '<div class="bc-bar"><div style="width:' + w + "%;background:" + it.color + '"></div></div>' +
          "</div>"
        );
      })
      .join("");
  }

  function renderTable(summary) {
    tableSummary = summary;
    updateTableChrome();
    if (tableMode === "group") renderGroupRows(summary);
    else renderAppRows(summary);
    // Deliberately NOT re-rendering the editor here: renderTable runs on every background poll, and
    // rebuilding the editor's DOM would collapse an open <select> and wipe half-typed input. The
    // editor renders on open and re-renders itself after each of its own actions instead.
  }

  function updateTableChrome() {
    el("table-title").textContent =
      tableMode === "group" ? "Totals by category" : "Per-application totals";
    el("col-app").textContent = tableMode === "group" ? "Category" : "Application";
    var btns = el("table-mode").querySelectorAll("button");
    btns.forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-mode") === tableMode);
    });
  }

  function renderGroupRows(summary) {
    var groups = summary.groups || [];
    var rows = el("app-rows");
    if (!groups.length) {
      rows.innerHTML = '<div class="empty">No activity recorded in this range yet.</div>';
      return;
    }
    var max = groups[0].seconds || 1;
    rows.innerHTML = groups
      .map(function (g) {
        var key = "grp:" + g.id;
        var open = !!expanded[key];
        var caret = '<span class="caret' + (open ? " open" : "") + '">▸</span>';
        var count = g.apps.length + " app" + (g.apps.length === 1 ? "" : "s");
        var head =
          '<div class="table-row row-app has-sites" data-key="' + esc(key) + '" role="button" tabindex="0" aria-expanded="' + open + '">' +
          '<span class="sw" style="background:' + g.color + '"></span>' +
          '<div class="app-cell">' + caret +
          '<div class="app-id"><div class="app-name">' + esc(g.name) + "</div>" +
          '<div class="app-cls">' + count + "</div></div></div>" +
          '<span class="num">' + g.sessions + "</span>" +
          '<span class="time">' + fmtDur(g.seconds) + "</span>" +
          '<span class="num">' + Math.round(g.share * 100) + "%</span>" +
          '<div class="bar"><div style="width:' + Math.round((g.seconds / max) * 100) + "%;background:" + g.color + '"></div></div>' +
          "</div>";
        // Members can be whole apps or individual browser sites (browser set); a site member
        // shows its host + a small parent-browser tag.
        var items = g.apps.map(function (m) {
          return {
            label: m.browser ? m.site || "(other)" : prettify(m.app_class),
            secondary: m.browser ? prettify(m.browser) : null,
            seconds: m.seconds,
            share: m.share,
            color: m.color,
          };
        });
        var sub =
          '<div class="site-rows bc"' + (open ? "" : " hidden") + ">" + barRows(items) + "</div>";
        return '<div class="app-group">' + head + sub + "</div>";
      })
      .join("");
  }

  function renderAppRows(summary) {
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
        // Any app with an in-app detail breakdown (browser site, document, or media track)
        // gets a drill-down; plain apps don't. `has-sites` is the CSS/handler hook for
        // "has a drill-down" (kept for back-compat since the browser-site feature).
        var details = a.details && a.details.length ? a.details : null;
        var open = !!(details && expanded[key]);
        var lead = details
          ? '<span class="caret' + (open ? " open" : "") + '">▸</span>'
          : '<span class="caret-none"></span>';
        var head =
          '<div class="table-row row-app' + (details ? " has-sites" : "") + '" data-key="' + esc(key) + '"' +
          (details ? ' role="button" tabindex="0" aria-expanded="' + open + '"' : "") + ">" +
          '<span class="sw" style="background:' + color + '"></span>' +
          '<div class="app-cell">' + lead +
          '<div class="app-id"><div class="app-name">' + esc(prettify(a.app_class)) + "</div>" +
          '<div class="app-cls">' + esc(a.app_class || "—") + "</div></div></div>" +
          '<span class="num">' + a.sessions + "</span>" +
          '<span class="time">' + fmtDur(a.seconds) + "</span>" +
          '<span class="num">' + Math.round(a.share * 100) + "%</span>" +
          '<div class="bar"><div style="width:' + Math.round((a.seconds / max) * 100) + "%;background:" + color + '"></div></div>' +
          "</div>";
        var sub = "";
        if (details) {
          var items = details.map(function (d) {
            return {
              label: detailLabel(d.detail),
              secondary: detailSourceTag(d.source),
              seconds: d.seconds,
              share: d.share,
              color: color,
            };
          });
          sub =
            '<div class="site-rows bc"' + (open ? "" : " hidden") + ">" + barRows(items) + "</div>";
        }
        return '<div class="app-group">' + head + sub + "</div>";
      })
      .join("");
  }

  function toggleRow(row) {
    var key = row.getAttribute("data-key");
    expanded[key] = !expanded[key];
    if (tableSummary) renderTable(tableSummary);
  }

  // -- category grouping: mode toggle + inline editor -------------------------

  function fetchCategories() {
    return getJSON("/api/categories")
      .then(function (c) {
        catConfig = c;
      })
      .catch(function () {});
  }

  function setTableMode(mode) {
    tableMode = mode;
    if (tableSummary) renderTable(tableSummary);
  }

  function slug(name) {
    return (
      name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "") || "cat"
    );
  }
  function uniqueId(base, cats) {
    var id = base;
    var n = 2;
    var taken = {};
    cats.forEach(function (c) {
      taken[c.id] = true;
    });
    while (taken[id]) id = base + "-" + n++;
    return id;
  }
  function flash(msg) {
    var m = el("editor-msg");
    if (m) m.textContent = msg || "";
  }

  function openEditor() {
    if (!catConfig) {
      fetchCategories().then(openEditor);
      return;
    }
    draft = {
      categories: catConfig.categories.map(function (c) {
        return { id: c.id, name: c.name, color: c.color };
      }),
      assignments: Object.assign({}, catConfig.assignments),
      site_assignments: Object.assign({}, catConfig.site_assignments || {}),
    };
    pickedColor = null;
    editing = true;
    renderEditor();
  }
  function closeEditor() {
    editing = false;
    draft = null;
    el("group-modal").hidden = true;
    el("group-editor").innerHTML = "";
  }

  function renderEditor() {
    var ed = el("group-editor");
    var modal = el("group-modal");
    if (!editing || !draft || !catConfig) {
      modal.hidden = true;
      ed.innerHTML = "";
      return;
    }
    modal.hidden = false;
    ed.scrollTop = 0;
    var uncat = catConfig.uncategorized_id;
    // Existing categories are inline-editable: a colour picker + a name field. Uncategorized is
    // reserved so it keeps its row (editable) but loses the delete button.
    var chips = draft.categories
      .map(function (c) {
        var del =
          c.id === uncat
            ? '<span class="cat-del-spacer"></span>'
            : '<button class="cat-del" data-del="' + esc(c.id) + '" title="delete category">×</button>';
        return (
          '<div class="cat-edit-row">' +
          '<input type="color" class="cat-color" data-editcolor="' + esc(c.id) +
          '" value="' + esc(c.color) + '" title="category colour">' +
          '<input class="cat-name" data-editname="' + esc(c.id) + '" value="' + esc(c.name) +
          '" maxlength="40" spellcheck="false" title="category name">' +
          del + "</div>"
        );
      })
      .join("");
    var swatches = catConfig.palette
      .map(function (col) {
        return (
          '<button class="pal-sw' + (pickedColor === col ? " picked" : "") +
          '" data-color="' + col + '" style="background:' + col + '" title="' + col + '"></button>'
        );
      })
      .join("");
    function catOptions(cur) {
      return draft.categories
        .map(function (c) {
          return '<option value="' + esc(c.id) + '"' + (c.id === cur ? " selected" : "") + ">" + esc(c.name) + "</option>";
        })
        .join("");
    }
    var apps = (tableSummary && tableSummary.apps ? tableSummary.apps : []).filter(function (a) {
      return a.app_class !== null && a.app_class !== undefined;
    });
    var assignRows = apps
      .map(function (a) {
        return (
          '<div class="assign-row"><span class="assign-name">' + esc(prettify(a.app_class)) + "</span>" +
          '<select class="assign-select" data-app="' + esc(a.app_class) + '">' +
          catOptions(draft.assignments[a.app_class] || uncat) + "</select></div>"
        );
      })
      .join("");
    // Browser sites seen in this window (unique hosts across all browsers).
    var hostSet = {};
    apps.forEach(function (a) {
      (a.sites || []).forEach(function (s) {
        if (s.site) hostSet[s.site] = true;
      });
    });
    var siteRows = Object.keys(hostSet)
      .sort()
      .map(function (host) {
        return (
          '<div class="assign-row"><span class="assign-name" title="' + esc(host) + '">' + esc(host) + "</span>" +
          '<select class="assign-select site-select" data-site="' + esc(host) + '">' +
          catOptions(draft.site_assignments[host] || uncat) + "</select></div>"
        );
      })
      .join("");
    var sitesSection = siteRows
      ? '<div class="assign-subhead">Browser sites</div><div class="assign-grid">' + siteRows + "</div>"
      : "";
    ed.innerHTML =
      '<div class="editor-head"><div class="panel-title">Edit categories</div>' +
      '<div class="editor-actions"><span id="editor-msg" class="editor-msg"></span>' +
      '<button id="auto-cat" class="nav-btn">Auto-categorize</button>' +
      '<button id="cancel-edit" class="nav-btn">Cancel</button>' +
      '<button id="save-edit" class="nav-btn primary">Save</button></div></div>' +
      '<div class="cat-list">' + chips + "</div>" +
      '<div class="new-cat"><input id="new-cat-name" class="date-input" placeholder="New category name" maxlength="40">' +
      '<div class="pal">' + swatches + "</div>" +
      '<button id="add-cat" class="nav-btn">Add category</button></div>' +
      '<div class="assign-subhead">Applications</div><div class="assign-grid">' + assignRows + "</div>" +
      sitesSection;
  }

  function addCategory() {
    var name = (el("new-cat-name").value || "").trim();
    if (!name) return flash("Enter a category name.");
    if (!pickedColor) return flash("Pick a colour.");
    var id = uniqueId(slug(name), draft.categories);
    // Keep Uncategorized last.
    var uncatIdx = draft.categories.findIndex(function (c) {
      return c.id === catConfig.uncategorized_id;
    });
    draft.categories.splice(uncatIdx < 0 ? draft.categories.length : uncatIdx, 0, {
      id: id,
      name: name,
      color: pickedColor,
    });
    pickedColor = null;
    renderEditor();
  }
  function deleteCategory(id) {
    if (id === catConfig.uncategorized_id) return;
    draft.categories = draft.categories.filter(function (c) {
      return c.id !== id;
    });
    Object.keys(draft.assignments).forEach(function (app) {
      if (draft.assignments[app] === id) delete draft.assignments[app];
    });
    Object.keys(draft.site_assignments).forEach(function (host) {
      if (draft.site_assignments[host] === id) delete draft.site_assignments[host];
    });
    renderEditor();
  }
  function autoCategorize() {
    var defaults = catConfig.defaults || {};
    var siteDefaults = catConfig.site_defaults || {};
    var ids = {};
    draft.categories.forEach(function (c) {
      ids[c.id] = true;
    });
    (tableSummary && tableSummary.apps ? tableSummary.apps : []).forEach(function (a) {
      var app = a.app_class;
      if (app && !draft.assignments[app]) {
        var d = defaults[app.toLowerCase()];
        if (d && ids[d]) draft.assignments[app] = d;
      }
      (a.sites || []).forEach(function (s) {
        var host = s.site;
        if (!host || draft.site_assignments[host]) return;
        var sd = siteDefaults[host.toLowerCase()];
        if (sd && ids[sd]) draft.site_assignments[host] = sd;
      });
    });
    renderEditor();
    flash("Filled from defaults.");
  }
  function saveEditor() {
    if (
      draft.categories.some(function (c) {
        return !(c.name || "").trim();
      })
    ) {
      return flash("Category names can't be empty.");
    }
    var body = JSON.stringify({
      categories: draft.categories.map(function (c) {
        return { id: c.id, name: (c.name || "").trim(), color: c.color };
      }),
      assignments: draft.assignments,
      site_assignments: draft.site_assignments,
    });
    fetch("/api/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body,
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (saved) {
        catConfig = saved;
        closeEditor();
        tableMode = "group"; // show the result rolled up
        refresh(); // refetch so groups reflect the new assignments
      })
      .catch(function () {
        flash("Save failed.");
      });
  }

  function editorClick(e) {
    var t = e.target;
    if (t.dataset && t.dataset.color) {
      pickedColor = t.dataset.color;
      el("group-editor")
        .querySelectorAll(".pal-sw")
        .forEach(function (s) {
          s.classList.toggle("picked", s.dataset.color === pickedColor);
        });
      return;
    }
    if (t.dataset && t.dataset.del) return deleteCategory(t.dataset.del);
    if (t.id === "add-cat") return addCategory();
    if (t.id === "auto-cat") return autoCategorize();
    if (t.id === "cancel-edit") return closeEditor();
    if (t.id === "save-edit") return saveEditor();
  }
  // Live-edit an existing category's name/colour in the draft without re-rendering (which would
  // steal focus from the field being typed into).
  function updateCat(id, field, value) {
    for (var i = 0; i < draft.categories.length; i++) {
      if (draft.categories[i].id === id) {
        draft.categories[i][field] = value;
        return;
      }
    }
  }
  function editorInput(e) {
    var t = e.target;
    if (!t.dataset) return;
    if (t.dataset.editname !== undefined) return updateCat(t.dataset.editname, "name", t.value);
    if (t.dataset.editcolor !== undefined) return updateCat(t.dataset.editcolor, "color", t.value);
  }
  function editorChange(e) {
    var t = e.target;
    if (!t.classList.contains("assign-select")) return;
    var isUncat = t.value === catConfig.uncategorized_id;
    if (t.classList.contains("site-select")) {
      var host = t.getAttribute("data-site");
      if (isUncat) delete draft.site_assignments[host];
      else draft.site_assignments[host] = t.value;
    } else {
      var app = t.getAttribute("data-app");
      if (isUncat) delete draft.assignments[app];
      else draft.assignments[app] = t.value;
    }
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
  function refreshWindow(isPoll) {
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
        buildColorMap(summary);
        var bkt = toBkt(bucketsResp, effectivePeriod());
        renderRangeTiles(summary, bkt, timeline);
        renderLegend(summary);
        // A background poll must not rebuild the hero chart while the user is hovering it (it would
        // drop their live breakdown preview); explicit navigation always re-renders regardless.
        if (!(isPoll && heroHot)) renderCharts(summary, bkt);
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
    if (isLive()) refreshWindow(true); // the live day keeps its charts/table current
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
    el("chart-entity").addEventListener("click", function (e) {
      var m = e.target.getAttribute("data-entity");
      if (m) setChartEntity(m);
    });
    el("date-picker").addEventListener("change", function (e) {
      jumpToDate(e.target.value);
    });
    el("custom-apply").addEventListener("click", applyCustom);
    // Expand/collapse a browser's per-site drill-down (delegated: rows are re-rendered often).
    el("app-rows").addEventListener("click", function (e) {
      var row = e.target.closest(".row-app.has-sites");
      if (row) toggleRow(row);
    });
    el("app-rows").addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var row = e.target.closest(".row-app.has-sites");
      if (row) {
        e.preventDefault();
        toggleRow(row);
      }
    });
    // Category grouping: table-mode toggle, edit button, and the editor's delegated handlers.
    el("table-mode").addEventListener("click", function (e) {
      var m = e.target.getAttribute("data-mode");
      if (m) setTableMode(m);
    });
    el("edit-groups").addEventListener("click", function () {
      if (editing) closeEditor();
      else openEditor();
    });
    el("group-editor").addEventListener("click", editorClick);
    el("group-editor").addEventListener("change", editorChange);
    el("group-editor").addEventListener("input", editorInput);
    // Dismiss the modal by clicking the backdrop (outside the card) or pressing Escape.
    el("group-modal").addEventListener("click", function (e) {
      if (e.target === el("group-modal")) closeEditor();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && editing) closeEditor();
    });
    fetchCategories();
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
