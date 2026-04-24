import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import airportMap from "./assets/UpScaled.png";
import chsLogo from "./assets/CHS.png"; 

const API_BASE = "http://127.0.0.1:8000";

const GATES = [
  { id: "B1", cx: 546, cy: 401, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B3", cx: 513, cy: 318, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B2", cx: 395, cy: 502, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B4", cx: 335, cy: 391, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B5", cx: 444, cy: 154, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B6", cx: 275, cy: 229, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B7", cx: 424, cy: 93, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B8", cx: 242, cy: 165, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B9", cx: 351, cy: 78, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "B10", cx: 283, cy: 105, rx: 35, ry: 27.5, transform: "rotate(-27)" },
  { id: "A1", cx: 1326, cy: 548, rx: 35, ry: 27.5, transform: "rotate(27)" },
  { id: "A2", cx: 1160, cy: 437, rx: 35, ry: 27.5, transform: "rotate(27)" },
  { id: "A3", cx: 1354, cy: 475, rx: 35, ry: 27.5, transform: "rotate(27)" },
  { id: "A4", cx: 1230, cy: 366, rx: 35, ry: 27.5, transform: "rotate(27)" },
  { id: "A5", cx: 1341, cy: 408, rx: 35, ry: 27.5, transform: "rotate(27)" }
];

function App() {
  const [activeView, setActiveView] = useState("map");

  const [month, setMonth] = useState(1);
  const [day, setDay] = useState(1);
  const [year, setYear] = useState(2025);
  const [time, setTime] = useState("14:00");

  const [scheduleRows, setScheduleRows] = useState([]);
  const [currentPlaybackTime, setCurrentPlaybackTime] = useState(null);
  const [isPlayingTimeline, setIsPlayingTimeline] = useState(false);
  const [timelineBounds, setTimelineBounds] = useState(null);

  const [uploadedCSV, setUploadedCSV] = useState(null);
  const [uploadedNormalized, setUploadedNormalized] = useState(false);
  const [dropZoneDragging, setDropZoneDragging] = useState(false);

  const [playbackDate, setPlaybackDate] = useState("2025-01-01");
  const [buildStartDate, setBuildStartDate] = useState("2025-01-01");
  const [buildEndDate, setBuildEndDate] = useState("2025-01-01");

  const [buildStatus, setBuildStatus] = useState("Schedule has not been built yet.");
  const [uploadTitle, setUploadTitle] = useState("Drag and drop file or click to browse");
  const [uploadSubtitle, setUploadSubtitle] = useState("Supported format: CSV");

  const [analyticsLoaded, setAnalyticsLoaded] = useState(false);
  const [analyticsStatus, setAnalyticsStatus] = useState("Analytics view loaded.");
  const [latestScheduleBuild, setLatestScheduleBuild] = useState("Not built yet");
  const [analyticsWindowValue, setAnalyticsWindowValue] = useState("1 day");
  const [analyticsUtilizationValue, setAnalyticsUtilizationValue] = useState("--");
  const [analyticsUtilizationDetail, setAnalyticsUtilizationDetail] = useState("Waiting for latest schedule data");
  const [analyticsTurnaroundValue, setAnalyticsTurnaroundValue] = useState("--");
  const [analyticsTurnaroundDetail, setAnalyticsTurnaroundDetail] = useState("Waiting for latest schedule data");
  const [analyticsConflictValue, setAnalyticsConflictValue] = useState("--");
  const [analyticsConflictDetail, setAnalyticsConflictDetail] = useState("Waiting for latest schedule data");
  const [analyticsSourceText, setAnalyticsSourceText] = useState("Latest database-backed Power BI report");

  const [clickedPoints, setClickedPoints] = useState([]);
  const [gateColors, setGateColors] = useState({});

  const fileInputRef = useRef(null);
  const powerbiContainerRef = useRef(null);

  const daysInMonth = useMemo(() => new Date(year, month + 1, 0).getDate(), [year, month]);

  function getTimePart(isoString) {
    return isoString.slice(11, 19);
  }

  function timeToSeconds(hhmmss) {
    const [h, m, s] = hhmmss.split(":").map(Number);
    return h * 3600 + m * 60 + s;
  }

  function secondsToTime(totalSeconds) {
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    return [h, m, s].map((v) => String(v).padStart(2, "0")).join(":");
  }

  function formatPlaybackDisplay(hhmmss) {
    let [hours, minutes] = hhmmss.split(":").map(Number);
    const suffix = hours >= 12 ? "PM" : "AM";
    hours = hours % 12;
    if (hours === 0) hours = 12;
    return `${hours}:${String(minutes).padStart(2, "0")} ${suffix}`;
  }

  function getSelectedDateIso() {
    return new Date(year, month, day).toISOString().slice(0, 10);
  }

  useEffect(() => {
    const nextSelectedDate = getSelectedDateIso();
    setPlaybackDate((prev) => prev || nextSelectedDate);
    setBuildStartDate((prev) => prev || nextSelectedDate);
    setBuildEndDate((prev) => prev || nextSelectedDate);
  }, [year, month, day]);

  useEffect(() => {
    if (day > daysInMonth) {
      setDay(daysInMonth);
    }
  }, [daysInMonth, day]);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Enter") {
        console.log(clickedPoints.map((p) => `${p.x},${p.y}`).join(" "));
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [clickedPoints]);

  async function loadGateStatusForSelectedTime(playbackTime = null) {
    const response = await fetch(`${API_BASE}/powerbi/optimized-schedule`);
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || "Failed to load optimized schedule.");
    }

    const payload = await response.json();
    const rows = payload.data || [];
    setScheduleRows(rows);

    const selectedDate = playbackDate;
    const selectedTime = playbackTime || (time.length === 5 ? `${time}:00` : time);

    const nextColors = {};
    GATES.forEach((gate) => {
      nextColors[gate.id] = "rgba(0, 200, 0, 0.4)";
    });

    const activeRows = rows
      .filter((row) => row.service_date === selectedDate && row.scheduled_at_gate)
      .filter((row) => {
        const arrival = getTimePart(row.arrival_time);
        const departure = getTimePart(row.departure_time);
        return selectedTime >= arrival && selectedTime <= departure;
      })
      .slice(0, 10);

    activeRows.forEach((row) => {
      nextColors[row.gate_id] = "rgba(255, 0, 0, 0.4)";
    });

    setGateColors(nextColors);
  }

  async function handleCSVFile(file) {
    if (!file) return;

    const isCSV =
      file.name.toLowerCase().endsWith(".csv") ||
      file.type === "text/csv" ||
      file.type === "application/vnd.ms-excel";

    if (!isCSV) {
      alert("Please upload a CSV file.");
      return;
    }

    setUploadedCSV(file);
    setUploadTitle(`Loaded: ${file.name}`);
    setUploadSubtitle("Uploading and normalizing...");
    setBuildStatus("Schedule has not been built yet.");
    setUploadedNormalized(false);
    setIsPlayingTimeline(false);
    setCurrentPlaybackTime(null);
    setTimelineBounds(null);
    setScheduleRows([]);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_BASE}/pipeline/upload-and-run`, {
        method: "POST",
        body: formData
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Upload failed: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      console.log("Backend result:", result);

      setUploadedNormalized(true);
      setUploadSubtitle("Upload complete. Ready to build a schedule.");
      setLatestScheduleBuild("Raw and normalized tables refreshed");
    } catch (error) {
      console.error(error);
      setUploadSubtitle("Upload failed");
      setUploadedNormalized(false);
      setBuildStatus("Schedule has not been built yet.");
    }
  }

  async function buildScheduleForSelectedDay() {
    if (!uploadedNormalized) {
      setBuildStatus("Upload a CSV first.");
      return;
    }

    if (!buildStartDate || !buildEndDate) {
      setBuildStatus("Choose both a start date and an end date.");
      return;
    }

    if (buildStartDate > buildEndDate) {
      setBuildStatus("Start date must be on or before end date.");
      return;
    }

    setBuildStatus("Building schedule...");
    setIsPlayingTimeline(false);
    setCurrentPlaybackTime(null);
    setTimelineBounds(null);

    try {
      const response = await fetch(`${API_BASE}/pipeline/build-schedule`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          start_date: buildStartDate,
          end_date: buildEndDate
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Build failed: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      setBuildStatus(
        `Schedule ready for ${buildStartDate}${buildStartDate === buildEndDate ? "" : ` to ${buildEndDate}`}. Download: ${API_BASE}${result.download_url}`
      );
      setLatestScheduleBuild(buildStartDate === buildEndDate ? buildStartDate : `${buildStartDate} to ${buildEndDate}`);      
      setAnalyticsWindowValue(buildStartDate === buildEndDate ? buildStartDate : `${buildStartDate} → ${buildEndDate}`);
      await loadAnalyticsSummary();
      await loadGateStatusForSelectedTime();
      console.log("Schedule build result:", result);
    } catch (error) {
      console.error(error);
      setBuildStatus(`Schedule build failed: ${error.message}`);
    }
  }

  async function loadAnalyticsSummary() {
    try {
      const response = await fetch(`${API_BASE}/powerbi/optimized-schedule`);
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText);
      }

      const payload = await response.json();
      const rows = payload.data || [];
      const totalAssignments = rows.length;
      const scheduledAssignments = rows.filter((row) => Number(row.is_conflict) === 0).length;
      const conflicts = rows.filter((row) => Number(row.is_conflict) !== 0).length;
      const gateIds = new Set(rows.map((row) => row.gate_id).filter(Boolean));
      const avgTurnaround = totalAssignments
        ? Math.round(rows.reduce((sum, row) => sum + Number(row.turnaround_minutes || 0), 0) / totalAssignments)
        : 0;
      const utilization = gateIds.size
        ? Math.round((scheduledAssignments / gateIds.size) * 10) / 10
        : 0;

      setAnalyticsUtilizationValue(`${utilization}`);
      setAnalyticsUtilizationDetail(`${scheduledAssignments} assigned turns across ${gateIds.size || 0} active gates`);
      setAnalyticsTurnaroundValue(`${avgTurnaround}m`);
      setAnalyticsTurnaroundDetail(payload.scenario?.name || "Latest available scenario");
      setAnalyticsConflictValue(`${conflicts}`);
      setAnalyticsConflictDetail(`${totalAssignments} total assignment rows from flights_assignment_test`);
      setAnalyticsSourceText("Live summary from /powerbi/optimized-schedule and embedded Power BI report");
    } catch (error) {
      console.error("Analytics summary load failed:", error);
      setAnalyticsUtilizationValue("--");
      setAnalyticsTurnaroundValue("--");
      setAnalyticsConflictValue("--");
      setAnalyticsUtilizationDetail("Unable to load latest analytics summary");
      setAnalyticsTurnaroundDetail("Unable to load latest analytics summary");
      setAnalyticsConflictDetail("Unable to load latest analytics summary");
      setAnalyticsSourceText("Power BI report only");
    }
  }

  async function loadPowerBIAnalytics() {
    setAnalyticsStatus("Loading Power BI analytics...");

    try {
      const response = await fetch(`${API_BASE}/get-embed-token`);
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText);
      }

      const embedConfig = await response.json();

      if (!window.powerbi || !window["powerbi-client"]) {
        throw new Error("Power BI client library is unavailable.");
      }

      const models = window["powerbi-client"].models;
      const container = powerbiContainerRef.current;

      if (!container) {
        throw new Error("Power BI container not ready.");
      }

      window.powerbi.reset(container);
      window.powerbi.embed(container, {
        type: "report",
        tokenType: models.TokenType.Embed,
        accessToken: embedConfig.embedToken,
        embedUrl: embedConfig.embedUrl,
        id: embedConfig.reportId,
        permissions: models.Permissions.All,
        settings: {
          panes: {
            filters: { visible: false },
            pageNavigation: { visible: true }
          },
          background: models.BackgroundType.Transparent
        }
      });

      setAnalyticsLoaded(true);
      setAnalyticsStatus("Live Power BI analytics loaded from the latest database-backed report.");
    } catch (error) {
      console.error("Power BI load failed:", error);
      setAnalyticsLoaded(false);
      setAnalyticsStatus("Power BI analytics unavailable.");
    }
  }

  async function handleAnalyticsViewClick() {
    setActiveView("analytics");
    await loadAnalyticsSummary();
    if (!analyticsLoaded) {
      await loadPowerBIAnalytics();
    }
  }

  function startTimelinePlayback() {
    const rowsForDate = scheduleRows.filter(
      (row) => row.service_date === playbackDate && row.scheduled_at_gate
    );

    if (!rowsForDate.length) {
      setBuildStatus("No schedule rows available for timeline playback on that date.");
      return;
    }

    const firstTime = Math.min(
      ...rowsForDate.map((row) => timeToSeconds(getTimePart(row.arrival_time)))
    );

    const lastTime = Math.max(
      ...rowsForDate.map((row) => timeToSeconds(getTimePart(row.departure_time)))
    );

    setTimelineBounds({ firstTime, lastTime });
    setCurrentPlaybackTime(secondsToTime(firstTime));
    setIsPlayingTimeline(true);
    setActiveView("map");
  }

  function stopTimelinePlayback() {
    setIsPlayingTimeline(false);
  }

  useEffect(() => {
    if (!isPlayingTimeline || !currentPlaybackTime || !timelineBounds) return;

    const interval = setInterval(() => {
      setCurrentPlaybackTime((prev) => {
        if (!prev) return prev;

        const next = timeToSeconds(prev) + 1800;
        if (next > timelineBounds.lastTime) {
          setIsPlayingTimeline(false);
          return secondsToTime(timelineBounds.lastTime);
        }

        return secondsToTime(next);
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isPlayingTimeline, currentPlaybackTime, timelineBounds]);

  useEffect(() => {
    if (!currentPlaybackTime || !scheduleRows.length) return;

    loadGateStatusForSelectedTime(currentPlaybackTime).catch((error) => {
      console.error("Gate status playback failed:", error);
    });
  }, [currentPlaybackTime, scheduleRows.length, playbackDate]);

  function handleSvgClick(e) {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const vb = svg.viewBox.baseVal;

    const x = ((e.clientX - rect.left) / rect.width) * vb.width + vb.x;
    const y = ((e.clientY - rect.top) / rect.height) * vb.height + vb.y;

    const point = {
      x: Math.round(x),
      y: Math.round(y)
    };

  }

  return (
    <div className="app-shell">
      <div className="Header">
        <div className="header-left">
          <button
            className={`nav-btn ${activeView === "map" ? "active" : ""}`}
            onClick={() => setActiveView("map")}
          >
            ✈︎ Gate View
          </button>

          <button
            className={`nav-btn ${activeView === "analytics" ? "active" : ""}`}
            onClick={handleAnalyticsViewClick}
          >
            Analytics
          </button>
        </div>

        <div className="header-center">
          <img src={chsLogo} alt="CHS Logo" className="header-logo" />
        </div>

        <div className="header-right">

          <div className="header-date-group">

          <button className="nav-btn timeline-btn" onClick={startTimelinePlayback}>
            Play ▶
          </button>

          <button className="nav-btn timeline-btn"onClick={stopTimelinePlayback}>
            Pause ❚❚
          </button>
            <label>
              {/* <span>Date</span> */}
              <input
                type="date"
                value={playbackDate}
                onChange={(e) => setPlaybackDate(e.target.value)}
              />
            </label>


            <label>
              <span>Playback Date</span>
              <div style={{ color: "white", paddingTop: "6px", minWidth: "90px" }}>
                {currentPlaybackTime ? formatPlaybackDisplay(currentPlaybackTime) : "--"}
              </div>
            </label>
          </div>
        </div>
      </div>

      <div className={`view ${activeView === "analytics" ? "active" : ""}`}>
        <div className="map-wrapper analytics-page">
          <div className="upload-card">
            <div
              className={`csv-drop-zone ${dropZoneDragging ? "dragover" : ""}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDropZoneDragging(true);
              }}
              onDragLeave={() => setDropZoneDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDropZoneDragging(false);
                const file = e.dataTransfer.files?.[0];
                handleCSVFile(file);
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={(e) => handleCSVFile(e.target.files?.[0])}
              />

              <div className="upload-content">
                <div className="upload-icon">⇪</div>
                <div className="upload-text">
                  <div className="upload-title">{uploadTitle}</div>
                  <div className="upload-subtitle">{uploadSubtitle}</div>
                </div>
              </div>
            </div>

            <div className="range-controls">
              <label className="range-field">
                <span>Schedule Start</span>
                <input
                  type="date"
                  value={buildStartDate}
                  onChange={(e) => setBuildStartDate(e.target.value)}
                />
              </label>

              <label className="range-field">
                <span>Schedule End</span>
                <input
                  type="date"
                  value={buildEndDate}
                  onChange={(e) => setBuildEndDate(e.target.value)}
                />
              </label>
            </div>

            <div className="upload-actions">
              <button
                className="build-btn"
                disabled={!uploadedNormalized}
                onClick={buildScheduleForSelectedDay}
              >
                Build Schedule For Date Range
              </button>
            </div>

            <div className="build-status">{buildStatus}</div>

            {buildStatus.includes("http://127.0.0.1:8000") && (
              <div className="build-status">
                <a
                  href={buildStatus.split("Download: ")[1]}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Download optimal schedule CSV
                </a>
              </div>
            )}
          </div>

          <div className="analytics-header">
            <div>
              <div className="analytics-title">Operations Analytics</div>
              <div className="analytics-copy">Operations report</div>
            </div>
            <div className="analytics-status">{analyticsStatus}</div>
          </div>

          <div className="analytics-grid">
            <div className="stat-card">
              <div className="stat-label">Schedule Window</div>
              <div className="stat-value">{analyticsWindowValue}</div>
              <div className="stat-detail">Current reporting period</div>
            </div>

            <div className="stat-card">
              <div className="stat-label">Gate Utilization</div>
              <div className="stat-value">{analyticsUtilizationValue}</div>
              <div className="stat-detail">{analyticsUtilizationDetail}</div>
            </div>

            <div className="stat-card">
              <div className="stat-label">Avg Turnaround</div>
              <div className="stat-value">{analyticsTurnaroundValue}</div>
              <div className="stat-detail">{analyticsTurnaroundDetail}</div>
            </div>

            <div className="stat-card">
              <div className="stat-label">Conflicts</div>
              <div className="stat-value">{analyticsConflictValue}</div>
              <div className="stat-detail">{analyticsConflictDetail}</div>
            </div>
          </div>

          <div className="analytics-panel">
            {!analyticsLoaded && (
              <div className="analytics-fallback">
                <h3>Power BI</h3>
                <p>Power BI dashboard will appear here when available.</p>

                <div className="analytics-list">
                  <div className="analytics-list-item">
                    <span>Latest schedule.</span>
                    <strong>{latestScheduleBuild}</strong>
                  </div>

                  <div className="analytics-list-item">
                    <span>Analytics source</span>
                    <strong>{analyticsSourceText}</strong>
                  </div>
                </div>
              </div>
            )}

            <div
              ref={powerbiContainerRef}
              className="analytics-embed"
              style={{ display: analyticsLoaded ? "block" : "none" }}
            />
          </div>
        </div>
      </div>

      <div className={`view ${activeView === "map" ? "active" : ""}`}>
        <div className="map-wrapper">
          <img src={airportMap} alt="Airport map" className="map-image" />

          <svg
            className="map-overlay"
            viewBox="0 0 1600 742"
            preserveAspectRatio="xMidYMid meet"
            onClick={handleSvgClick}
          >
            {GATES.map((gate) => (
              <ellipse
                key={gate.id}
                id={gate.id}
                className="region"
                cx={gate.cx}
                cy={gate.cy}
                rx={gate.rx}
                ry={gate.ry}
                transform={gate.transform}
                style={{ fill: gateColors[gate.id] || "rgba(140, 140, 140, 0.4)" }}
              />
            ))}
          </svg>
        </div>
      </div>
    </div>
  );
}

export default App;