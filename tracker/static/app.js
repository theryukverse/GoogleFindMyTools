// Global State
let currentDevices = [];
let leafletMap = null;
let mapLayersGroup = null;
let appConfig = {
  tile_url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  tile_attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
};

// Initialize app when DOM is ready
document.addEventListener("DOMContentLoaded", async () => {
  initClock();
  await fetchConfig();
  initMap();
  initTimePresets();
  await checkHealth();
  await loadDevices();

  // Periodic health check every 30s
  setInterval(checkHealth, 30000);
});

// Tab Switching
function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".view-panel").forEach(panel => panel.classList.remove("active"));

  if (tabName === "devices") {
    document.getElementById("tab-devices-btn").classList.add("active");
    document.getElementById("view-devices").classList.add("active");
    loadDevices();
  } else if (tabName === "map") {
    document.getElementById("tab-map-btn").classList.add("active");
    document.getElementById("view-map").classList.add("active");
    updateMapDeviceDropdown();
    // Leaflet needs invalidateSize when tab becomes visible
    setTimeout(() => {
      if (leafletMap) leafletMap.invalidateSize();
    }, 100);
  }
}

// Live Local Clock
function initClock() {
  const clockEl = document.getElementById("local-clock");
  function tick() {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString();
  }
  tick();
  setInterval(tick, 1000);
}

// Fetch App Config (Tile URL & Attribution)
async function fetchConfig() {
  try {
    const res = await fetch("/api/config");
    if (res.ok) {
      appConfig = await res.json();
    }
  } catch (err) {
    console.warn("Could not fetch runtime config, using defaults:", err);
  }
}

// Health Check
async function checkHealth() {
  const dot = document.querySelector(".status-dot");
  const text = document.getElementById("system-status-text");
  try {
    const res = await fetch("/api/health");
    if (res.ok) {
      const data = await res.json();
      dot.className = "status-dot healthy";
      text.textContent = "Poller Running";
    } else {
      dot.className = "status-dot error";
      text.textContent = "Service Error";
    }
  } catch (e) {
    dot.className = "status-dot error";
    text.textContent = "Offline";
  }
}

// Initialize Leaflet Map
function initMap() {
  // Default centered at world view
  leafletMap = L.map("map-history").setView([20, 0], 2);

  L.tileLayer(appConfig.tile_url, {
    maxZoom: 19,
    attribution: appConfig.tile_attribution
  }).addTo(leafletMap);

  mapLayersGroup = L.featureGroup().addTo(leafletMap);

  const footerAttr = document.getElementById("footer-osm-attr");
  if (footerAttr && appConfig.tile_attribution) {
    footerAttr.innerHTML = appConfig.tile_attribution;
  }
}

// Helper: Format Epoch Seconds into Viewer's Local Time
function formatLocalTime(epochSec) {
  if (!epochSec) return "Never";
  const date = new Date(epochSec * 1000);
  return date.toLocaleString();
}

// Helper: Format relative time
function formatRelativeTime(epochSec) {
  if (!epochSec) return "Never";
  const now = Math.floor(Date.now() / 1000);
  const diff = now - epochSec;
  if (diff < 60) return "Just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// Sync Devices directly from Google Find My network
async function syncDevicesFromGoogle() {
  const syncBtn = document.getElementById("btn-sync-devices");
  const origText = syncBtn ? syncBtn.innerHTML : "Sync Find My Devices";
  if (syncBtn) {
    syncBtn.disabled = true;
    syncBtn.innerHTML = `
      <div class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;margin-right:6px;"></div>
      Syncing with Google...
    `;
  }
  showToast("Fetching devices from Google Find My...", "info");

  try {
    const res = await fetch("/api/devices/sync", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || `HTTP ${res.status}`);
    }
    const sum = data.summary || {};
    showToast(
      `Sync complete: ${sum.total || 0} device(s) found (${sum.new || 0} new, ${sum.updated || 0} updated)`,
      "success"
    );
    await loadDevices(false);
  } catch (err) {
    console.error("Failed to sync devices from Google:", err);
    showToast(`Google Find My sync failed: ${err.message}`, "error");
  } finally {
    if (syncBtn) {
      syncBtn.disabled = false;
      syncBtn.innerHTML = origText;
    }
  }
}

// Load Devices from API
async function loadDevices(isUserTriggered = false) {
  const grid = document.getElementById("devices-grid");
  if (!isUserTriggered && currentDevices.length === 0) {
    grid.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <span>Loading devices...</span>
      </div>`;
  }

  try {
    const res = await fetch("/api/devices");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    currentDevices = await res.json();
    renderDevices(currentDevices);
    updateMapDeviceDropdown();

    // Update nav counter with count of tracked devices
    const trackedCount = currentDevices.filter(d => d.tracking_enabled).length;
    document.getElementById("nav-device-count").textContent = `${trackedCount}/${currentDevices.length}`;

    if (isUserTriggered) {
      showToast("Devices refreshed", "success");
    }
  } catch (err) {
    console.error("Failed to load devices:", err);
    grid.innerHTML = `
      <div class="loading-state">
        <p style="color: var(--danger-color)">Failed to load devices: ${err.message}</p>
        <button class="btn btn-secondary" onclick="loadDevices()">Try Again</button>
      </div>`;
    showToast("Error loading devices", "error");
  }
}

// Render Device Cards
function renderDevices(devices) {
  const grid = document.getElementById("devices-grid");
  if (!devices || devices.length === 0) {
    grid.innerHTML = `
      <div class="loading-state">
        <p>No devices found in database.</p>
        <small class="panel-desc">Click <strong>Sync Find My Devices</strong> to fetch your trackers directly from Google Find My network.</small>
        <div style="margin-top: 14px;">
          <button class="btn btn-primary" onclick="syncDevicesFromGoogle()">Sync Find My Devices</button>
        </div>
      </div>`;
    return;
  }

  const nowSec = Math.floor(Date.now() / 1000);
  const fifteenMinutes = 15 * 60;

  grid.innerHTML = devices.map(device => {
    const isTracked = device.tracking_enabled;
    const isAvailable = device.is_available;
    const lastSeen = device.last_seen_at;

    // Check if device is tracked but stale (nothing reported in last 15 minutes)
    let isStale = false;
    let statusClass = "inactive";
    let statusText = "○ Tracking Off";

    if (!isAvailable) {
      statusClass = "unavailable";
      statusText = "✕ Unavailable";
    } else if (isTracked) {
      if (!lastSeen || (nowSec - lastSeen) > fifteenMinutes) {
        isStale = true;
        statusClass = "stale";
        statusText = "⚠️ No recent report (>15m)";
      } else {
        statusClass = "active";
        statusText = "● Tracking Active";
      }
    }

    return `
      <div class="device-card ${isStale ? 'stale' : ''}" id="card-${device.device_id}">
        <div class="device-card-header">
          <div class="device-title">
            <span class="device-name">${escapeHtml(device.name)}</span>
            <span class="device-id">${escapeHtml(device.device_id)}</span>
          </div>
          <div class="switch-container">
            <label class="switch" title="Toggle Tracking">
              <input type="checkbox" 
                     id="toggle-${device.device_id}" 
                     ${isTracked ? 'checked' : ''} 
                     ${!isAvailable ? 'disabled' : ''}
                     onchange="handleTrackingToggle('${device.device_id}', this.checked)">
              <span class="slider"></span>
            </label>
          </div>
        </div>

        <div class="device-meta">
          <div class="meta-row">
            <span class="meta-label">Status</span>
            <span class="status-pill ${statusClass}">${statusText}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Last Seen</span>
            <span class="meta-value" title="${formatLocalTime(lastSeen)}">${formatRelativeTime(lastSeen)}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">First Added</span>
            <span class="meta-value">${formatLocalTime(device.created_at)}</span>
          </div>
        </div>

        <div class="card-actions">
          ${isTracked ? `
            <button class="btn btn-secondary btn-sm" onclick="viewDeviceOnMap('${device.device_id}')">
              <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none">
                <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon>
              </svg>
              View on Map
            </button>
          ` : ''}
        </div>
      </div>
    `;
  }).join("");
}

// Toggle Tracking for a Device
async function handleTrackingToggle(deviceId, isEnabled) {
  const toggleEl = document.getElementById(`toggle-${deviceId}`);
  try {
    const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/tracking`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracking_enabled: isEnabled })
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || `Server returned ${res.status}`);
    }

    const updated = await res.json();
    showToast(
      `Tracking ${isEnabled ? 'enabled' : 'disabled'} for ${updated.name}`,
      "success"
    );

    // Refresh devices to update statuses
    await loadDevices();
  } catch (err) {
    console.error("Toggle tracking error:", err);
    showToast(`Error: ${err.message}`, "error");
    // Revert checkbox state
    if (toggleEl) {
      toggleEl.checked = !isEnabled;
    }
  }
}

// Jump from Device Card directly to Map View
function viewDeviceOnMap(deviceId) {
  switchTab("map");
  const select = document.getElementById("device-select");
  select.value = deviceId;
  setTimePreset(24);
  fetchAndDisplayHistory();
}

// Update Tracked Devices Dropdown in Map View
function updateMapDeviceDropdown() {
  const select = document.getElementById("device-select");
  const previousValue = select.value;

  // Filter only devices with tracking enabled and available
  const trackedDevices = currentDevices.filter(d => d.is_available && d.tracking_enabled);

  select.innerHTML = '<option value="">Select a tracked device...</option>';
  trackedDevices.forEach(d => {
    const opt = document.createElement("option");
    opt.value = d.device_id;
    opt.textContent = `${d.name} (${d.device_id})`;
    select.appendChild(opt);
  });

  if (previousValue && trackedDevices.some(d => d.device_id === previousValue)) {
    select.value = previousValue;
  }
}

function onTrackedDeviceChange() {
  const select = document.getElementById("device-select");
  if (select.value) {
    fetchAndDisplayHistory();
  }
}

// Initialize Datetime Presets (Default: Last 24 Hours)
function initTimePresets() {
  setTimePreset(24);
}

function setTimePreset(hours) {
  const now = new Date();
  const start = new Date(now.getTime() - hours * 60 * 60 * 1000);

  document.getElementById("start-datetime").value = formatForDateTimeInput(start);
  document.getElementById("end-datetime").value = formatForDateTimeInput(now);

  // Update active chip
  document.querySelectorAll(".btn-chip").forEach(chip => chip.classList.remove("active"));
  const presetBtn = document.querySelector(`.btn-chip[onclick*="setTimePreset(${hours})"]`);
  if (presetBtn) {
    presetBtn.classList.add("active");
  }
}

function formatForDateTimeInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

// Fetch and Display Location History on Map
async function fetchAndDisplayHistory() {
  const deviceId = document.getElementById("device-select").value;
  if (!deviceId) {
    showToast("Please select a tracked device first", "error");
    return;
  }

  const startVal = document.getElementById("start-datetime").value;
  const endVal = document.getElementById("end-datetime").value;

  let query = "";
  if (startVal) {
    const startIso = new Date(startVal).toISOString();
    query += `start=${encodeURIComponent(startIso)}`;
  }
  if (endVal) {
    const endIso = new Date(endVal).toISOString();
    query += (query ? "&" : "") + `end=${encodeURIComponent(endIso)}`;
  }

  const btn = document.getElementById("btn-load-history");
  const originalBtnHtml = btn.innerHTML;
  btn.innerHTML = `<span class="spinner" style="width:16px;height:16px;"></span> Loading...`;
  btn.disabled = true;

  const noDataOverlay = document.getElementById("no-data-alert");
  const infoBar = document.getElementById("map-info-bar");

  try {
    const res = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/history?${query}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `Server returned ${res.status}`);
    }

    const data = await res.json();
    renderHistoryOnMap(data);
  } catch (err) {
    console.error("Failed to load history:", err);
    showToast(`Error: ${err.message}`, "error");
  } finally {
    btn.innerHTML = originalBtnHtml;
    btn.disabled = false;
  }
}

// Draw Route and Markers on Leaflet Map
function renderHistoryOnMap(historyData) {
  const points = historyData.points || [];
  const noDataOverlay = document.getElementById("no-data-alert");
  const infoBar = document.getElementById("map-info-bar");

  mapLayersGroup.clearLayers();

  if (points.length === 0) {
    noDataOverlay.classList.remove("hidden");
    infoBar.classList.add("hidden");
    document.getElementById("no-data-message").textContent =
      `No location readings found for "${historyData.device_name}" in the selected time range.`;
    return;
  }

  noDataOverlay.classList.add("hidden");
  infoBar.classList.remove("hidden");

  // Update info bar stats
  document.getElementById("stat-points-count").textContent = points.length;
  const startTimeStr = formatRelativeTime(points[0].recorded_at);
  const endTimeStr = formatRelativeTime(points[points.length - 1].recorded_at);
  document.getElementById("stat-timespan").textContent = `${startTimeStr} -> ${endTimeStr}`;
  const latestPt = points[points.length - 1];
  document.getElementById("stat-latest-pos").textContent = `${latestPt.latitude.toFixed(4)}, ${latestPt.longitude.toFixed(4)}`;

  const latlngs = points.map(pt => [pt.latitude, pt.longitude]);

  // 1. Draw Polyline Connecting Points in Time Order
  const polyline = L.polyline(latlngs, {
    color: "#3b82f6",
    weight: 4,
    opacity: 0.85,
    smoothFactor: 1.0,
    dashArray: points.length === 1 ? null : null
  }).addTo(mapLayersGroup);

  // 2. Add Point Markers
  points.forEach((pt, index) => {
    const isStart = index === 0;
    const isEnd = index === points.length - 1;
    const latlng = [pt.latitude, pt.longitude];
    const localTime = formatLocalTime(pt.recorded_at);

    const popupContent = `
      <div style="font-family: var(--font-sans); min-width: 180px;">
        <div style="font-weight: 700; margin-bottom: 4px; color: ${isEnd ? '#ef4444' : isStart ? '#10b981' : '#3b82f6'};">
          ${isEnd ? '🏁 Latest Reading' : isStart ? '🚩 Route Start' : `📍 Point #${index + 1}`}
        </div>
        <div style="font-size: 0.8rem; margin-bottom: 4px;">
          <strong>Time:</strong> ${localTime}
        </div>
        <div style="font-size: 0.75rem; color: #64748b; font-family: var(--font-mono);">
          Lat: ${pt.latitude.toFixed(6)}<br>
          Lon: ${pt.longitude.toFixed(6)}
        </div>
      </div>
    `;

    if (isStart || isEnd) {
      // Custom styled Start and End markers
      const pinClass = isEnd ? "pin-end" : "pin-start";
      const pinLabel = isEnd ? "END" : "START";
      const icon = L.divIcon({
        className: "",
        html: `<div class="custom-marker-pin ${pinClass}">${pinLabel}</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14]
      });

      L.marker(latlng, { icon }).bindPopup(popupContent).addTo(mapLayersGroup);
    } else {
      // Subtle intermediate circle marker
      L.circleMarker(latlng, {
        radius: 4,
        fillColor: "#3b82f6",
        color: "#ffffff",
        weight: 1.5,
        opacity: 0.9,
        fillOpacity: 0.9
      }).bindPopup(popupContent).addTo(mapLayersGroup);
    }
  });

  // Automatically zoom and pan to fit the whole track
  if (latlngs.length === 1) {
    leafletMap.setView(latlngs[0], 15);
  } else {
    leafletMap.fitBounds(polyline.getBounds(), { padding: [50, 50] });
  }
}

// Toast Notifications Helper
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : '⚠️'}</span>
    <span>${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(20px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Helper: Escape HTML strings
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
