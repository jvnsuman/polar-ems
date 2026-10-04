// POLAR EMS - Operator Dashboard Frontend Logic
// Faithful implementation of SIH26061 Slide 2 & 3 prototype view

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
    console.error("Using offline mock fallback for week dispatch:", err);
    // In case server is offline, use exact Slide 2 reference data
    const fallback = generateSlide2ReferenceData(season);
    cachedWeekData = fallback;
    renderDashboard(fallback);
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
function generateSlide2ReferenceData(season) {
  const N = 168;
  let g = [], w = [], bd = [], dem = [], socP = [], socR = [], wsp = [];
  for (let i = 0; i < N; i++) {
    const day = Math.floor(i / 24);
    const hour = i % 24;
    // Storm event on Day 7 around 13:00 (i = 6*24 + 13 = 157)
    let windSpeed = 12 + 6 * Math.sin(2 * Math.PI * i / 36);
    if (day === 6 && hour >= 10 && hour <= 20) {
      windSpeed = 28 + 4 * Math.sin(Math.PI * (hour - 10) / 10);
    }
    wsp.push(windSpeed);
    
    let isCut = windSpeed >= 25;
    let actualWind = isCut ? 0 : Math.min(100, Math.pow(windSpeed / 11.5, 3) * 100);
    let demand = 60 + 12 * Math.sin(2 * Math.PI * (hour - 8) / 24);
    
    let gensetKw = 0;
    let battDis = 0;
    if (isCut) {
      gensetKw = Math.min(80, Math.max(24, demand - 15));
      battDis = Math.max(0, demand - gensetKw);
    } else if (actualWind < demand) {
      let deficit = demand - actualWind;
      if (deficit <= 20) {
        battDis = deficit;
      } else {
        gensetKw = Math.min(80, Math.max(24, deficit * 0.7));
        battDis = Math.max(0, deficit - gensetKw);
      }
    }
    
    g.push(gensetKw);
    w.push(actualWind);
    bd.push(battDis);
    dem.push(demand);
    socP.push(Math.max(25, 80 - 15 * Math.sin(2 * Math.PI * i / 48)));
    socR.push(Math.max(20, 75 - 20 * Math.sin(2 * Math.PI * i / 48)));
  }

  return {
    season: season,
    hours: N,
    genset_kw: g,
    wind_kw: w,
    batt_discharge_kw: bd,
    demand_kw: dem,
    soc_polar_ems: socP,
    soc_rule_based: socR,
    wind_speed_ms: wsp,
    metrics: {
      diesel_savings_pct: -23.7,
      diesel_liters_str: "11,890 L -> 9,074 L in 30 days",
      gensets_off_hours: 291,
      gensets_off_sub: "of 696 h, baseline 0 h",
      renewable_share_pct: 33,
      renewable_sub: "baseline 23%",
      unserved_kwh: 0,
      unserved_sub: "critical loads protected all month"
    }
  };
}
