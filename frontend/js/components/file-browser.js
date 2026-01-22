/**
 * File Browser Component - Recording file list and playback
 */
class FileBrowser {
  constructor() {
    this.dates = [];
    this.currentDateIndex = 0;
    this.recordings = [];
    this.currentRecording = null;
  }

  init() {
    this.loadDates();

    // Listen for new recordings - refresh both dates and recordings
    wsClient.on('status', (data) => {
      if (data.service === 'recorder') {
        this.loadDates();
      }
    });

    // Auto-refresh every 30 seconds to catch new recordings
    this.refreshInterval = setInterval(() => {
      this.loadDates();
    }, 30000);
  }

  async loadDates() {
    try {
      const response = await API.recordings.getDates();
      this.dates = response.dates;

      if (this.dates.length > 0) {
        this.currentDateIndex = 0;
        this.updateDateDisplay();
        this.loadRecordings();
      } else {
        document.getElementById('current-date').textContent = 'No recordings';
        document.getElementById('file-list').innerHTML =
          '<div class="file-item" style="color: var(--muted); justify-content: center;">No recordings available</div>';
      }
    } catch (error) {
      console.error('Failed to load dates:', error);
    }
  }

  async loadRecordings() {
    if (this.dates.length === 0) return;

    const date = this.dates[this.currentDateIndex];

    try {
      const response = await API.recordings.list(date);
      this.recordings = response.recordings;
      this.renderFileList();
    } catch (error) {
      console.error('Failed to load recordings:', error);
    }
  }

  renderFileList() {
    const container = document.getElementById('file-list');

    if (this.recordings.length === 0) {
      container.innerHTML =
        '<div class="file-item" style="color: var(--muted); justify-content: center;">No recordings for this date</div>';
      return;
    }

    container.innerHTML = this.recordings
      .map(
        (rec) => `
      <div class="file-item" data-file="${rec.name}" data-date="${rec.date}">
        <div class="file-info">
          <span class="file-name">${this.formatFilename(rec.name)}</span>
          <span class="file-meta">${rec.size_mb} MB</span>
        </div>
        <div class="file-actions">
          <button class="btn-icon" onclick="fileBrowser.playRecording('${rec.date}', '${rec.name}')" title="Play">
            &#9658;
          </button>
          <button class="btn-icon" onclick="fileBrowser.downloadRecording('${rec.date}', '${rec.name}')" title="Download">
            &#8595;
          </button>
          <button class="btn-icon" onclick="fileBrowser.deleteRecording('${rec.date}', '${rec.name}')" title="Delete">
            &#10005;
          </button>
        </div>
      </div>
    `
      )
      .join('');
  }

  formatFilename(filename) {
    // Convert YYYYMMDD_HHMMSS.mp4 to readable format
    const match = filename.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
    if (match) {
      const [, year, month, day, hour, minute, second] = match;
      return `${hour}:${minute}:${second}`;
    }
    return filename;
  }

  updateDateDisplay() {
    if (this.dates.length === 0) {
      document.getElementById('current-date').textContent = 'No recordings';
      return;
    }

    const date = this.dates[this.currentDateIndex];
    const formatted = new Date(date).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
    document.getElementById('current-date').textContent = formatted;
  }

  navigateDate(direction) {
    const newIndex = this.currentDateIndex + direction;
    if (newIndex >= 0 && newIndex < this.dates.length) {
      this.currentDateIndex = newIndex;
      this.updateDateDisplay();
      this.loadRecordings();
    }
  }

  playRecording(date, filename) {
    const video = document.getElementById('recording-video');
    const player = document.getElementById('recording-player');
    const url = API.recordings.getFileUrl(date, filename);

    video.pause();
    video.src = url;
    player.style.display = 'block';
    video.load();

    video.onloadedmetadata = () => {
      video.currentTime = 0;
      video.play().catch((error) => {
        console.warn('Playback blocked:', error);
        showToast('Tap play to start playback', 'error');
      });
    };

    video.onerror = () => {
      showToast('Failed to load recording', 'error');
    };

    this.currentRecording = { date, filename };

    // Highlight active file
    document.querySelectorAll('.file-item').forEach((item) => {
      item.classList.remove('active');
      if (item.dataset.file === filename && item.dataset.date === date) {
        item.classList.add('active');
      }
    });
  }

  downloadRecording(date, filename) {
    const url = API.recordings.getFileUrl(date, filename);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  async deleteRecording(date, filename) {
    if (!confirm(`Delete recording ${filename}?`)) {
      return;
    }

    try {
      await API.recordings.delete(date, filename);
      showToast('Recording deleted', 'success');
      this.loadRecordings();

      // If deleted file was playing, stop playback
      if (this.currentRecording?.filename === filename) {
        document.getElementById('recording-player').style.display = 'none';
        document.getElementById('recording-video').src = '';
        this.currentRecording = null;
      }
    } catch (error) {
      console.error('Failed to delete recording:', error);
      showToast('Failed to delete recording', 'error');
    }
  }
}

// Global instance and navigation function
let fileBrowser = null;

function navigateDate(direction) {
  if (fileBrowser) {
    fileBrowser.navigateDate(direction);
  }
}
