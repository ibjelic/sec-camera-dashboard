/**
 * Security Camera Dashboard - Main Application
 */

// Collapsible sections
function toggleCollapse(sectionId) {
  const header = document.querySelector(`#${sectionId}-card .collapsible-header`);
  const content = document.getElementById(`${sectionId}-content`);

  header.classList.toggle('collapsed');
  content.classList.toggle('collapsed');
}

// Toast notifications
function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast show ${type}`;

  setTimeout(() => {
    toast.classList.remove('show');
  }, 3000);
}

// Stream restart
function restartStream() {
  API.stream
    .restart()
    .then(() => {
      showToast('Restarting stream...', 'success');
      setTimeout(() => {
        if (livePreview) {
          livePreview.restart();
        }
      }, 2000);
    })
    .catch((error) => {
      console.error('Failed to restart stream:', error);
      showToast('Failed to restart stream', 'error');
    });
}

// Update service status indicators
function updateStatusIndicator(service, status) {
  const dot = document.getElementById(`status-${service}`);
  if (!dot) return;

  dot.classList.remove('active', 'error');

  if (status === 'running' || status === 'connected') {
    dot.classList.add('active');
  } else if (status === 'error' || status === 'stopped') {
    dot.classList.add('error');
  }
}

// Load recent detection events
async function loadRecentEvents() {
  try {
    const response = await API.detections.getRecent(10);
    renderEventList(response.events);
  } catch (error) {
    console.error('Failed to load recent events:', error);
  }
}

// Render event list
function renderEventList(events) {
  const container = document.getElementById('event-list');

  if (!events || events.length === 0) {
    container.innerHTML =
      '<div class="event-item" style="color: var(--muted); justify-content: center;">No detections yet</div>';
    return;
  }

  container.innerHTML = events
    .map((event) => {
      const time = new Date(event.timestamp);
      const timeStr = time.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
      const dateStr = time.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
      });

      const thumbnailSrc = event.thumbnail_path
        ? `/thumbnails/${event.thumbnail_path}`
        : '';
      const analysisText = event.analysis || '';
      const analysisHtml = analysisText
        ? `<div class="event-analysis">${analysisText}</div>`
        : '';
      const importanceValue = Number.isFinite(event.analysis_importance)
        ? event.analysis_importance
        : null;
      const importanceHtml = importanceValue
        ? `<div class="event-importance">Importance: ${importanceValue}/5</div>`
        : '';
      const badgeValue = Number.isFinite(event.analysis_confidence)
        ? Math.round(event.analysis_confidence)
        : Math.round(event.confidence);

      return `
        <div class="event-item">
          ${
            thumbnailSrc
              ? `<img class="event-thumbnail" src="${thumbnailSrc}" alt="Detection">`
              : '<div class="event-thumbnail"></div>'
          }
          <div class="event-details">
            <div class="event-time">${timeStr}</div>
            <div class="event-confidence">${dateStr}</div>
            ${analysisHtml}
            ${importanceHtml}
          </div>
          <span class="confidence-badge">${badgeValue}%</span>
        </div>
      `;
    })
    .join('');
}

// Initialize application
async function initApp() {
  console.log('Initializing Security Camera Dashboard...');

  // Connect WebSocket
  wsClient.connect();

  // WebSocket event handlers
  wsClient.on('status', (data) => {
    const serviceMap = {
      recorder: 'recorder',
      hls_streamer: 'stream',
      detector: 'detector',
    };
    const mappedService = serviceMap[data.service];
    if (mappedService) {
      updateStatusIndicator(mappedService, data.status);
    }
  });

  wsClient.on('detection', (data) => {
    console.log('Detection event:', data);
    loadRecentEvents();
  });

  wsClient.on('open', () => {
    // Check health on connection
    API.health()
      .then((health) => {
        updateStatusIndicator('recorder', health.services.recorder ? 'running' : 'stopped');
        updateStatusIndicator('stream', health.services.hls_streamer ? 'running' : 'stopped');
        updateStatusIndicator('detector', health.services.detector ? 'running' : 'stopped');
      })
      .catch(console.error);
  });

  // Initialize components
  livePreview = new LivePreview();
  livePreview.init();

  window.timeline = new Timeline();
  timeline = window.timeline;
  timeline.init();

  window.fileBrowser = new FileBrowser();
  fileBrowser = window.fileBrowser;
  fileBrowser.init();

  storageMonitor = new StorageMonitor();
  storageMonitor.init();

  settingsPanel = new SettingsPanel();
  settingsPanel.init();

  // Load initial data
  loadRecentEvents();

  // Theme toggle
  document.getElementById('theme-toggle').addEventListener('click', () => {
    settingsPanel.toggleTheme();
  });

  console.log('Dashboard initialized');
}

// Start app when DOM is ready
document.addEventListener('DOMContentLoaded', initApp);
