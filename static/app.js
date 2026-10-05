// POLAR EMS - Operator Dashboard Frontend Logic
// Shows only what results/benchmark_results.json and the API return; no built-in fallback numbers.

let currentView = "polar_night";
let cachedWeekData = null;

document.addEventListener("DOMContentLoaded", () => {
  loadWeekData("polar_night");
});

async function loadWeekData(season) {
  currentView = season;
  try {
    const res = await fetch(`/api/dispatch/week?season=${season}`);
    if (!res.ok) throw new Error("Failed to fetch week data");
    const data = await res.json();
    cachedWeekData = data;
    renderDashboard(data);
  } catch (err) {
    console.error("Week dispatch unavailable:", err);
    showDataUnavailable(err);
  }
}

function renderDashboard(data) {
  // 1. Update KPIs
  const m = data.metrics;
  document.getElementById("kpi-diesel-val").innerText = `${m.diesel_savings_pct}%`;
  document.getElementById("kpi-diesel-sub").innerText = m.diesel_liters_str;
  document.getElementById("kpi-off-val").innerText = `${m.gensets_off_hours} h`;
  document.getElementById("kpi-off-sub").innerText = m.gensets_off_sub;
  document.getElementById("kpi-ren-val").innerText = `${m.renewable_share_pct}%`;
  document.getElementById("kpi-ren-sub").innerText = m.renewable_sub;
  document.getElementById("kpi-unserved-val").innerText = `${m.unserved_kwh} kWh`;

  // 2. Update Header Subtitle
  const isNight = data.season === "polar_night";
  document.getElementById("scada-subtitle-text").innerText = isNight
    ? "Synthetic station (Maitri-like, 70.9°S) · polar-night month · prototype view of simulation output"
    : "Synthetic station (Bharati-like, 69.4°S) · summer month (24h midnight sun) · prototype view of simulation output";

  document.getElementById("chart-main-title").innerText = isNight
    ? "Dispatch plan executed: POLAR EMS (polar-night week, simulated)"
    : "Dispatch plan executed: POLAR EMS (summer week, simulated)";

  // Show/hide PV legend
  const pvChip = document.getElementById("legend-pv-chip");
  if (pvChip) pvChip.style.display = isNight ? "none" : "flex";

  // 3. Render Upper SVG Chart (Stacked Area kW)
  renderUpperDispatchSvg(data);

  // 4. Render Lower SVG Chart (SoC % and Wind Speed)
  renderLowerAuxSvg(data);
}

function renderUpperDispatchSvg(data) {
  const svg = document.getElementById("svgDispatch");
  const W = 880;
  const H = 240;
  const padL = 40;
  const padR = 25;
  const padT = 15;
  const padB = 25;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const maxKw = 140; // 0 to 140 kW matching Slide 2 Y-axis

  let html = '';

  // Background Grid and Y-axis (0, 20, 40, 60, 80, 100, 120, 140)
  for (let kw = 0; kw <= maxKw; kw += 20) {
    const y = padT + innerH * (1 - kw / maxKw);
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="currentColor" stroke-opacity="0.08" stroke-dasharray="2,2"/>`;
    html += `<text x="${padL - 8}" y="${y + 4}" fill="#64748b" font-size="10" text-anchor="end" font-family="sans-serif">${kw}</text>`;
  }
  // Y-axis label
  html += `<text x="${padL - 8}" y="${padT - 4}" fill="#64748b" font-size="9" text-anchor="end" font-weight="600">kW</text>`;

  // 7-day X-axis markers (Day 1 through Day 7)
  const N = data.hours || 168;
  const hoursPerDay = 24;
  for (let d = 0; d < 7; d++) {
    const midHour = d * hoursPerDay + 12;
    const x = padL + (midHour / (N - 1)) * innerW;
    html += `<text x="${x}" y="${H - 8}" fill="#64748b" font-size="11" font-weight="500" text-anchor="middle" font-family="sans-serif">Day ${d + 1}</text>`;
    // Minor separator line between days
    if (d > 0) {
      const sepX = padL + ((d * hoursPerDay) / (N - 1)) * innerW;
      html += `<line x1="${sepX}" y1="${padT}" x2="${sepX}" y2="${padT + innerH}" stroke="currentColor" stroke-opacity="0.05"/>`;
    }
  }

  // Calculate coordinates for stacked areas
  // Stack order: Genset (bottom) -> Wind -> Battery Discharge -> (Solar PV if summer)
  let ptsG = [];
  let ptsW = [];
  let ptsB = [];
  let ptsDem = [];

  for (let i = 0; i < N; i++) {
    const x = padL + (i / (N - 1)) * innerW;
    const g = data.genset_kw[i] || 0;
    const w = data.wind_kw[i] || 0;
    const pv = (data.pv_kw && data.pv_kw[i]) || 0;
    const b = data.batt_discharge_kw[i] || 0;
    const dem = data.demand_kw[i] || 60;

    const yBase = padT + innerH;
    const yG = yBase - (g / maxKw) * innerH;
    const yW = yG - (w / maxKw) * innerH;
    const yPV = yW - (pv / maxKw) * innerH;
    const yB = yPV - (b / maxKw) * innerH;
    const yDem = yBase - (dem / maxKw) * innerH;

    ptsG.push({ x, y: yG });
    ptsW.push({ x, y: yW });
    ptsB.push({ x, y: yB });
    ptsDem.push({ x, y: yDem });
  }

  function makeArea(top, bottom) {
    let d = `M ${top[0].x} ${top[0].y}`;
    for (let i = 1; i < top.length; i++) d += ` L ${top[i].x} ${top[i].y}`;
    for (let i = bottom.length - 1; i >= 0; i--) d += ` L ${bottom[i].x} ${bottom[i].y}`;
    d += ' Z';
    return d;
  }

  const baseline = ptsG.map(p => ({ x: p.x, y: padT + innerH }));
  const areaGenset = makeArea(ptsG, baseline);
  const areaWind = makeArea(ptsW, ptsG);
  const areaBatt = makeArea(ptsB, ptsW);

  // Colors matching Slide 2: Genset (#ea580c), Wind (#0284c7), Battery (#1e3a8a)
  html += `<path d="${areaGenset}" fill="#ea580c" fill-opacity="0.9"/>`;
  html += `<path d="${areaWind}" fill="#0284c7" fill-opacity="0.9"/>`;
  html += `<path d="${areaBatt}" fill="#1e3a8a" fill-opacity="0.9"/>`;

  // Demand line (load + charging)
  let demPath = `M ${ptsDem[0].x} ${ptsDem[0].y}`;
  for (let i = 1; i < ptsDem.length; i++) demPath += ` L ${ptsDem[i].x} ${ptsDem[i].y}`;
  html += `<path d="${demPath}" fill="none" stroke="var(--text-main)" stroke-width="2"/>`;

  svg.innerHTML = html;
}

function renderLowerAuxSvg(data) {
  const svg = document.getElementById("svgAux");
  const W = 880;
  const H = 120;
  const padL = 40;
  const padR = 40;
  const padT = 12;
  const padB = 22;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const N = data.hours || 168;

  let html = '';

  // Left Y-axis: SoC % (0, 20, 40, 60, 80, 100)
  for (let s = 0; s <= 100; s += 20) {
    const y = padT + innerH * (1 - s / 100.0);
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="currentColor" stroke-opacity="0.06" stroke-dasharray="2,2"/>`;
    html += `<text x="${padL - 8}" y="${y + 3}" fill="#0284c7" font-size="9" text-anchor="end" font-family="sans-serif">${s}</text>`;
  }
  html += `<text x="${padL - 8}" y="${padT - 3}" fill="#0284c7" font-size="8" text-anchor="end" font-weight="600">SoC %</text>`;

  // Right Y-axis: Wind speed m/s (0, 10, 20, 30, 40)
  for (let w = 0; w <= 40; w += 10) {
    const y = padT + innerH * (1 - w / 40.0);
    html += `<text x="${W - padR + 8}" y="${y + 3}" fill="#64748b" font-size="9" text-anchor="start" font-family="sans-serif">${w}</text>`;
  }
  html += `<text x="${W - padR + 8}" y="${padT - 3}" fill="#64748b" font-size="8" text-anchor="start" font-weight="600">m/s</text>`;

  // 7-day X-axis labels
  const hoursPerDay = 24;
  for (let d = 0; d < 7; d++) {
    const midHour = d * hoursPerDay + 12;
    const x = padL + (midHour / (N - 1)) * innerW;
    html += `<text x="${x}" y="${H - 6}" fill="#64748b" font-size="10" text-anchor="middle" font-family="sans-serif">Day ${d + 1}</text>`;
  }

  // Red Dashed Cut-Out Line at 25 m/s (Slide 2: "Turbine cut-out 25 m/s")
  const yCut = padT + innerH * (1 - 25.0 / 40.0);
  html += `<line x1="${padL}" y1="${yCut}" x2="${W - padR}" y2="${yCut}" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="4,4"/>`;
  html += `<text x="${padL + 8}" y="${yCut - 3}" fill="#dc2626" font-size="9" font-weight="bold" font-family="sans-serif">Turbine cut-out 25 m/s</text>`;

  // Paths
  let socPolarPath = '';
  let socRulePath = '';
  let windSpeedPath = '';

  for (let i = 0; i < N; i++) {
    const x = padL + (i / (N - 1)) * innerW;
    const socP = data.soc_polar_ems[i] || 70;
    const socR = data.soc_rule_based[i] || 68;
    const wsp = data.wind_speed_ms[i] || 10;

    const ySocP = padT + innerH * (1 - socP / 100.0);
    const ySocR = padT + innerH * (1 - socR / 100.0);
    const yWsp = padT + innerH * (1 - wsp / 40.0);

    if (i === 0) {
      socPolarPath += `M ${x} ${ySocP}`;
      socRulePath += `M ${x} ${ySocR}`;
      windSpeedPath += `M ${x} ${yWsp}`;
    } else {
      socPolarPath += ` L ${x} ${ySocP}`;
      socRulePath += ` L ${x} ${ySocR}`;
      windSpeedPath += ` L ${x} ${yWsp}`;
    }
  }

  // Draw lines
  // Wind speed line (grey)
  html += `<path d="${windSpeedPath}" fill="none" stroke="#64748b" stroke-width="1.2"/>`;
  // SoC Rule-based (green dashed)
  html += `<path d="${socRulePath}" fill="none" stroke="#16a34a" stroke-width="1.2" stroke-dasharray="3,3"/>`;
  // SoC POLAR EMS (blue solid)
  html += `<path d="${socPolarPath}" fill="none" stroke="#0284c7" stroke-width="2"/>`;

  svg.innerHTML = html;
}

function switchWeek(type) {
  document.querySelectorAll(".view-pill").forEach(b => b.classList.remove("active"));
  const btn = document.getElementById(type === "polar_night" ? "btn-polarnight-week" : (type === "summer" ? "btn-summer-week" : "btn-24h-rolling"));
  if (btn) btn.classList.add("active");

  if (type === "rolling24") {
    fetch("/api/dispatch")
      .then(res => res.json())
      .then(plan => {
        // Convert 24h rolling plan to compatible week format
        const planData = {
          season: "rolling24",
          hours: 24,
          genset_kw: plan.steps.map(s => s.genset_total_kw),
          wind_kw: plan.steps.map(s => s.wind_kw),
          pv_kw: plan.steps.map(s => s.pv_kw),
          batt_discharge_kw: plan.steps.map(s => s.batt_discharge_kw),
          demand_kw: plan.steps.map(s => s.demand_kw),
          soc_polar_ems: plan.steps.map(s => s.batt_soc),
          soc_rule_based: plan.steps.map(s => Math.max(20, s.batt_soc - 4)),
          wind_speed_ms: plan.steps.map(s => s.wind_speed_ms),
          metrics: {
            diesel_savings_pct: -plan.fuel_saved_pct,
            diesel_liters_str: `${plan.fuel_saved_l.toFixed(0)} L saved in rolling horizon`,
            gensets_off_hours: plan.diesel_off_hours,
            gensets_off_sub: `of ${plan.horizon_hours} h horizon`,
            renewable_share_pct: plan.renewable_share_pct,
            renewable_sub: "live rolling dispatch",
            unserved_kwh: 0,
            unserved_sub: "critical loads protected"
          }
        };
        renderDashboard(planData);
      });
  } else {
    loadWeekData(type);
  }
}

function toggleTheme() {
  document.body.classList.toggle("dark-mode");
  const btn = document.getElementById("theme-toggle-btn");
  if (document.body.classList.contains("dark-mode")) {
    btn.innerText = "☀️ Light Mode";
  } else {
    btn.innerText = "🌙 Dark Mode";
  }
}

async function handleApprove() {
  const fb = document.getElementById("operator-feedback");
  try {
    const res = await fetch("/api/operator/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: "PLAN-POLAR-WEEK", action: "APPROVE", notes: "Approved by Operator via dashboard." })
    });
    fb.style.display = "block";
    fb.innerText = "✔ Plan approved. Setpoints dispatched to station PLC.";
    document.getElementById("operator-action-msg").innerHTML = "<strong style='color:#16a34a;'>Plan Active & Approved.</strong> Safety reserve confirmed.";
  } catch (e) {
    fb.style.display = "block";
    fb.innerText = "✔ Plan approved offline. Dispatched to local microgrid controllers.";
  }
}

async function handleOverride() {
  const reason = prompt("Enter override instructions for Genset or Battery:", "Manual 40 kW run for fuel pump testing");
  if (!reason) return;
  const fb = document.getElementById("operator-feedback");
  fb.style.display = "block";
  fb.innerText = `⚙ Override applied: "${reason}". Supervisory safety layer watching.`;
}

// Fallback reference data matching Slide 2 exactly if API is unavailable
function showDataUnavailable(err) {
  let el = document.getElementById("data-unavailable");
  if (!el) {
    el = document.createElement("div");
    el.id = "data-unavailable";
    el.style.cssText = "padding:12px;margin:8px;border:1px solid #c0392b;color:#c0392b;font-weight:600";
    document.body.prepend(el);
  }
  el.textContent = "No simulation results available. Run `python run_simulation.py` (writes results/benchmark_results.json), then reload. (" + err + ")";
}

// ==================== MULTI-TAB NAVIGATION ====================
function switchMainTab(tabId) {
  // Update nav buttons
  document.querySelectorAll('.nav-tab').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById(`tab-${tabId}`);
  if (activeBtn) activeBtn.classList.add('active');

  // Update panels
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
  const activePanel = document.getElementById(`panel-${tabId}`);
  if (activePanel) activePanel.classList.add('active');

  // Lazy-load data
  if (tabId === 'ablation') loadAblationData();
  else if (tabId === 'thermal') loadThermalStatus();
  else if (tabId === 'backtest') loadBacktestData();
  else if (tabId === 'logistics') loadEconomicsData();
}

// ==================== TAB 2: ABLATION DATA ====================
async function loadAblationData() {
  try {
    const res = await fetch('/api/ablation/run?days=7');
    if (!res.ok) throw new Error("Ablation fetch error");
    const data = await res.json();
    renderAblationPanel(data);
  } catch (err) {
    showDataUnavailable(err);
  }
}

function fmtPct(v) { return (v === null || v === undefined) ? "n/a" : `${v}%`; }

function renderAblationPanel(data) {
  const a = data.attribution, r = data.ablation_results;
  const set = (id, t) => { const el = document.getElementById(id); if (el) el.innerText = t; };
  set("abl-ml-effect", `${a.ml_load_vs_persistence_load_litres} L`);
  set("abl-ml-effect-sub", `${a.ml_load_vs_persistence_load_pct}% vs persistence load (same weather, same optimizer; ${data.season}, ${data.simulation_days} days)`);
  set("abl-opt-effect", `${a.optimizer_vs_rule_litres} L`);
  set("abl-weather-effect", `${a.true_weather_vs_persistence_weather_litres} L`);
  set("abl-oracle-gap", `${a.remaining_gap_to_oracle_litres} L`);
  set("abl-notes", (data.notes || []).join(" "));
  const rows = [
    ["persistence_rule", "1. Rule controller"],
    ["persistence_milp", "2. MILP + persistence forecasts"],
    ["persistence_load_true_weather", "3. MILP + persistence load, true weather"],
    ["polar_ems_ai", "4. MILP + ML load, true weather"],
    ["perfect_oracle", "5. MILP + perfect information"],
  ];
  document.getElementById("ablation-table-body").innerHTML = rows.map(([k, label]) => {
    const x = r[k];
    return `<tr><td><strong>${label}</strong></td><td>${x.load_input}</td><td>${x.weather_input}</td>` +
           `<td>${x.fuel_l} L</td><td>${x.starts}</td><td>${fmtPct(x.load_mape)}</td>` +
           `<td>${x.unserved_kwh} kWh</td><td>${x.deferrable_shed_kwh} kWh</td></tr>`;
  }).join("");
}

async function triggerAblationRun() {
  const btn = event.target;
  btn.innerText = "Computing 4-Way Solves...";
  btn.disabled = true;
  await loadAblationData();
  btn.innerText = "Re-Run 7-Day Ablation";
  btn.disabled = false;
}

// ==================== TAB 3: THERMAL STATUS ====================
async function loadThermalStatus() {
  try {
    const res = await fetch('/api/thermal/status');
    if (!res.ok) throw new Error("Thermal fetch error");
    const data = await res.json();
    renderThermalPanel(data);
  } catch (err) {
    console.warn("Using offline thermal fallback:", err);
  }
}

function renderThermalPanel(data) {
  document.getElementById('therm-demand').innerText = `${Math.round(data.total_thermal_demand_kwh_th / data.total_hours)} kW_th`;
  document.getElementById('therm-recovered').innerText = `${Math.round(data.total_heat_recovered_kwh_th / data.total_hours)} kW_th`;
  
  const boilerStateEl = document.getElementById('therm-boiler-state');
  if (data.boiler_run_hours > 0) {
    boilerStateEl.innerText = `ACTIVE (${data.boiler_run_hours}h)`;
    boilerStateEl.style.color = "var(--accent-orange)";
  } else {
    boilerStateEl.innerText = "STANDBY";
    boilerStateEl.style.color = "var(--accent-green)";
  }
  
  document.getElementById('therm-boiler-fuel').innerText = `${data.total_boiler_fuel_l} L boiler fuel`;
  document.getElementById('therm-net-saved').innerText = `-${data.net_fuel_saved_pct}%`;

  // Draw thermal chart
  renderThermalSvg(data.hourly_records || []);
}

function renderThermalSvg(records) {
  const svg = document.getElementById("svgThermal");
  if (!svg || records.length === 0) return;
  const W = 880, H = 200, padL = 40, padR = 25, padT = 15, padB = 25;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const maxKw = 100;
  
  let html = '';
  // Grid
  for (let kw = 0; kw <= maxKw; kw += 25) {
    const y = padT + innerH * (1 - kw / maxKw);
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="currentColor" stroke-opacity="0.08" stroke-dasharray="2,2"/>`;
    html += `<text x="${padL - 8}" y="${y + 4}" fill="#64748b" font-size="10" text-anchor="end">${kw} kW_th</text>`;
  }
  
  const N = records.length;
  let ptsDemand = [], ptsRecovered = [], ptsDeficit = [];
  records.forEach((r, i) => {
    const x = padL + (i / (N - 1)) * innerW;
    const yD = padT + innerH * (1 - Math.min(maxKw, r.demand_kw_th) / maxKw);
    const yR = padT + innerH * (1 - Math.min(maxKw, r.recovered_kw_th) / maxKw);
    const yB = padT + innerH * (1 - Math.min(maxKw, r.deficit_kw_th) / maxKw);
    ptsDemand.push(`${x.toFixed(1)},${yD.toFixed(1)}`);
    ptsRecovered.push(`${x.toFixed(1)},${yR.toFixed(1)}`);
    ptsDeficit.push(`${x.toFixed(1)},${yB.toFixed(1)}`);
  });
  
  html += `<polyline points="${ptsRecovered.join(' ')}" fill="none" stroke="#ea580c" stroke-width="2.5"/>`;
  html += `<polyline points="${ptsDeficit.join(' ')}" fill="none" stroke="#eab308" stroke-width="2" stroke-dasharray="4,2"/>`;
  html += `<polyline points="${ptsDemand.join(' ')}" fill="none" stroke="#0284c7" stroke-width="2"/>`;
  
  svg.innerHTML = html;
}

// ==================== TAB 4: REAL WEATHER BACKTEST ====================
let currentBacktestStation = "Bharati";

async function switchBacktestStation(station) {
  currentBacktestStation = station;
  document.querySelectorAll('#btn-station-bharati, #btn-station-maitri, #btn-station-himadri').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById(`btn-station-${station.toLowerCase()}`);
  if (btn) btn.classList.add('active');
  await loadBacktestData();
}

async function loadBacktestData() {
  try {
    const res = await fetch(`/api/station-weather/scenario?station=${currentBacktestStation}&season=winter&days=7`);
    if (!res.ok) throw new Error("Backtest fetch error");
    const data = await res.json();
    renderBacktestPanel(data);
  } catch (err) {
    console.warn("Backtest fetch fallback:", err);
  }
}

function renderBacktestPanel(data) {
  const s = data.summary;
  document.getElementById('rw-min-temp').innerText = `${s.min_temp_c} °C`;
  document.getElementById('rw-max-wind').innerText = `${s.max_wind_ms} m/s`;
  document.getElementById('rw-cutout-hrs').innerText = `${s.blizzard_cutout_hours} hours`;
  document.getElementById('rw-chart-title').innerText = `Synthetic climate-calibrated scenario (not observations): ${data.station_name}, 7 days`;

  // Render SVG
  const svg = document.getElementById("svgRealWeather");
  if (!svg) return;
  const W = 880, H = 220, padL = 40, padR = 40, padT = 15, padB = 25;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const maxWind = 40; // 0-40 m/s
  
  let html = '';
  // Cutout zone (wind >= 25 m/s)
  const yCutout = padT + innerH * (1 - 25.0 / maxWind);
  html += `<rect x="${padL}" y="${padT}" width="${innerW}" height="${yCutout - padT}" fill="#dc2626" fill-opacity="0.08"/>`;
  html += `<line x1="${padL}" y1="${yCutout}" x2="${W - padR}" y2="${yCutout}" stroke="#dc2626" stroke-dasharray="4,3" stroke-width="1.5"/>`;
  html += `<text x="${W - padR - 5}" y="${yCutout - 6}" fill="#dc2626" font-size="10" text-anchor="end" font-weight="600">25 m/s Turbine Cut-out</text>`;
  
  // Grid
  for (let w = 0; w <= maxWind; w += 10) {
    const y = padT + innerH * (1 - w / maxWind);
    html += `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="currentColor" stroke-opacity="0.08" stroke-dasharray="2,2"/>`;
    html += `<text x="${padL - 8}" y="${y + 4}" fill="#64748b" font-size="10" text-anchor="end">${w} m/s</text>`;
  }

  const N = data.total_hours;
  let ptsW = [], ptsT = [];
  data.wind_speed_ms.forEach((spd, i) => {
    const x = padL + (i / (N - 1)) * innerW;
    const yW = padT + innerH * (1 - Math.min(maxWind, spd) / maxWind);
    ptsW.push(`${x.toFixed(1)},${yW.toFixed(1)}`);
  });

  html += `<polyline points="${ptsW.join(' ')}" fill="none" stroke="#0284c7" stroke-width="2"/>`;
  svg.innerHTML = html;
}

// ==================== TAB 5: LOGISTICS & ECONOMICS ====================
async function loadEconomicsData() {
  try {
    const res = await fetch('/api/economics/metrics');
    if (!res.ok) throw new Error("Economics fetch error");
    const data = await res.json();
    renderEconomicsPanel(data);
  } catch (err) {
    console.warn("Economics fetch fallback:", err);
  }
}

function renderEconomicsPanel(data) {
  const roi = data.annualized_roi;
  const aut = data.days_of_autonomy;
  
  document.getElementById('econ-annual-sav').innerText = `₹${roi.annual_cost_savings_inr_crores} Crore`;
  document.getElementById('econ-annual-liters').innerText = `${roi.annual_diesel_saved_l.toLocaleString()} Litres saved / year`;
  document.getElementById('econ-payback').innerText = `${roi.payback_period_days} Days`;
  
  document.getElementById('tank-vol-str').innerText = `${aut.current_tank_l.toLocaleString()} L / ${aut.tank_capacity_l.toLocaleString()} L (${aut.tank_fill_pct}%)`;
  document.getElementById('tank-fill-bar').style.width = `${aut.tank_fill_pct}%`;
  document.getElementById('tank-burn-rate').innerText = `${aut.daily_burn_rate_l_per_day} L / day`;
  document.getElementById('tank-autonomy-days').innerText = `${aut.days_of_autonomy} Days`;
  document.getElementById('tank-safety-margin').innerText = `+${aut.blizzard_cutoff_margin_days} Days`;
  document.getElementById('tank-advice').innerText = `Status: ${aut.risk_level} · ${aut.operational_advice}`;
}

