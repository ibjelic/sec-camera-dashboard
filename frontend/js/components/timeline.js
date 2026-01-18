/**
 * Detection Timeline Component - Chart.js graph with video playback
 */
class Timeline {
  constructor() {
    this.chart = null;
    this.currentRange = '24h';
    this.refreshInterval = null;
    this.chartData = [];
    this.recordings = [];
    this.rulerStepMinutes = {
      '10m': 2,
      '30m': 5,
      '1h': 10,
      '6h': 60,
      '12h': 120,
      '24h': 240,
      '48h': 360,
    };
  }

  init() {
    this.setupChart();
    this.setupRangeButtons();
    this.syncRangeButtons();
    this.loadData();
    this.loadStats();
    this.startAutoRefresh();

    // Listen for real-time detection events
    wsClient.on('detection', () => {
      this.loadData();
      this.loadStats();
    });
  }

  setupChart() {
    const ctx = document.getElementById('detection-chart').getContext('2d');
    const self = this;

    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Person Detection',
            data: [],
            borderColor: getComputedStyle(document.documentElement)
              .getPropertyValue('--chart-detection')
              .trim(),
            backgroundColor: 'rgba(214, 108, 83, 0.12)',
            fill: false,
            tension: 0.4,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 6,
            pointHitRadius: 10,
            pointHoverBackgroundColor: getComputedStyle(document.documentElement)
              .getPropertyValue('--chart-detection')
              .trim(),
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          intersect: false,
          mode: 'index',
        },
        onClick: (event, elements, chart) => {
          self.handleChartClick(event, chart);
        },
        plugins: {
          legend: {
            display: false,
          },
          tooltip: {
            enabled: true,
            callbacks: {
              title: (context) => {
                const label = context[0].label;
                if (label) {
                  const date = new Date(label);
                  return date.toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false,
                  });
                }
                return '';
              },
              label: (context) => {
                if (context.raw > 0) {
                  return `Confidence: ${context.raw}%`;
                }
                return 'No detection';
              },
              footer: () => 'Click to play recording',
            },
          },
        },
        scales: {
          x: {
            display: true,
            grid: {
              color: getComputedStyle(document.documentElement)
                .getPropertyValue('--chart-grid')
                .trim(),
            },
            ticks: {
              display: false,
              color: getComputedStyle(document.documentElement)
                .getPropertyValue('--chart-text')
                .trim(),
              maxTicksLimit: 10,
            },
          },
          y: {
            display: true,
            min: 0,
            max: 100,
            grid: {
              color: getComputedStyle(document.documentElement)
                .getPropertyValue('--chart-grid')
                .trim(),
            },
            ticks: {
              color: getComputedStyle(document.documentElement)
                .getPropertyValue('--chart-text')
                .trim(),
              stepSize: 25,
              callback: (value) => `${value}%`,
            },
          },
        },
      },
    });
  }

  setupRangeButtons() {
    const buttons = document.querySelectorAll('.range-btn');
    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        this.currentRange = btn.dataset.range;
        this.syncRangeButtons();
        this.loadData();
      });
    });
  }

  syncRangeButtons() {
    const buttons = document.querySelectorAll('.range-btn');
    buttons.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.range === this.currentRange);
    });
  }

  async handleChartClick(event, chart) {
    const points = chart.getElementsAtEventForMode(event, 'index', { intersect: false }, true);

    if (points.length > 0) {
      const index = points[0].index;
      const label = chart.data.labels[index];

      if (label) {
        const clickedTime = new Date(label);
        await this.playRecordingAtTime(clickedTime);
      }
    }
  }

  async playRecordingAtTime(targetTime) {
    try {
      // Format date for API
      const dateStr = targetTime.toISOString().split('T')[0];

      // Get recordings for this date
      const response = await API.recordings.list(dateStr);
      const recordings = response.recordings;

      if (!recordings || recordings.length === 0) {
        showToast('No recordings available for this time', 'error');
        return;
      }

      // Find the recording that contains this time
      // Recordings are named YYYYMMDD_HHMMSS.mp4 and are 10 minutes long
      let bestRecording = null;
      let seekOffset = 0;

      for (const rec of recordings) {
        // Parse recording start time from filename
        const match = rec.name.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
        if (match) {
          const [, year, month, day, hour, minute, second] = match;
          const recStart = new Date(year, month - 1, day, hour, minute, second);
          const recEnd = new Date(recStart.getTime() + 10 * 60 * 1000); // +10 minutes

          if (targetTime >= recStart && targetTime < recEnd) {
            bestRecording = rec;
            seekOffset = (targetTime - recStart) / 1000; // Offset in seconds
            break;
          }
        }
      }

      if (!bestRecording) {
        // If no exact match, find the closest recording before the target time
        for (const rec of recordings) {
          const match = rec.name.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
          if (match) {
            const [, year, month, day, hour, minute, second] = match;
            const recStart = new Date(year, month - 1, day, hour, minute, second);

            if (recStart <= targetTime) {
              bestRecording = rec;
              seekOffset = Math.min((targetTime - recStart) / 1000, 600); // Max 10 minutes
              break;
            }
          }
        }
      }

      if (!bestRecording) {
        showToast('No recording found for this time', 'error');
        return;
      }

      // Show and load video
      const player = document.getElementById('timeline-player');
      const video = document.getElementById('timeline-video');
      const info = document.getElementById('timeline-video-info');

      const videoUrl = API.recordings.getFileUrl(bestRecording.date, bestRecording.name);

      player.style.display = 'block';
      video.pause();
      video.src = videoUrl;
      video.load();

      // Format time for display
      const timeStr = targetTime.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
      info.textContent = `Playing: ${bestRecording.name} | Seeking to ${timeStr}`;

      // Wait for video to load then seek
      video.onloadedmetadata = () => {
        if (seekOffset > 0) {
          if (!Number.isFinite(video.duration) || seekOffset < video.duration) {
            video.currentTime = seekOffset;
          }
        }
        video.play().catch((e) => {
          console.warn('Playback blocked:', e);
          showToast('Tap play to start playback', 'error');
        });
      };

      video.onerror = () => {
        showToast('Failed to load recording', 'error');
      };

      // Update time display during playback
      video.ontimeupdate = () => {
        const currentTime = video.currentTime;
        const hours = Math.floor(currentTime / 3600);
        const minutes = Math.floor((currentTime % 3600) / 60);
        const seconds = Math.floor(currentTime % 60);
        document.getElementById('timeline-video-time').textContent =
          `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
      };

    } catch (error) {
      console.error('Failed to load recording:', error);
      showToast('Failed to load recording', 'error');
    }
  }

  closePlayer() {
    const player = document.getElementById('timeline-player');
    const video = document.getElementById('timeline-video');
    const info = document.getElementById('timeline-video-info');
    const time = document.getElementById('timeline-video-time');

    video.pause();
    video.removeAttribute('src');
    video.load();
    player.style.display = 'block';
    info.textContent = 'Click on timeline to load recording';
    time.textContent = '--:--:--';
  }

  async loadData() {
    try {
      const response = await API.detections.getGraphData(this.currentRange);
      this.chartData = response.data;
      this.updateChart(response.data);
    } catch (error) {
      console.error('Failed to load detection data:', error);
    }
  }

  async loadStats() {
    try {
      const stats = await API.detections.getStats();
      document.getElementById('stat-1h').textContent = stats.detections_1h;
      document.getElementById('stat-24h').textContent = stats.detections_24h;
    } catch (error) {
      console.error('Failed to load detection stats:', error);
    }
  }

  updateChart(data) {
    const labels = data.map((d) => d.minute);
    const values = data.map((d) => d.max_confidence);

    this.chart.data.labels = labels;
    this.chart.data.datasets[0].data = values;
    this.chart.update('none');
    this.updateRuler(data);
  }

  updateRuler(data) {
    const ruler = document.getElementById('timeline-ruler');
    if (!ruler) return;

    if (!data || data.length === 0) {
      ruler.innerHTML = '';
      return;
    }

    const stepMinutes = this.rulerStepMinutes[this.currentRange] || 60;
    const start = new Date(data[0].minute);
    const end = new Date(data[data.length - 1].minute);
    const stepMs = stepMinutes * 60 * 1000;
    let cursor = new Date(start);

    const labels = [];
    while (cursor.getTime() <= end.getTime()) {
      labels.push(this.formatRulerLabel(cursor));
      cursor = new Date(cursor.getTime() + stepMs);
    }

    ruler.innerHTML = labels.map((label) => `<span>${label}</span>`).join('');
  }

  formatRulerLabel(date) {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }

  startAutoRefresh() {
    // Refresh every 30 seconds
    this.refreshInterval = setInterval(() => {
      this.loadData();
      this.loadStats();
    }, 30000);
  }

  destroy() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
    if (this.chart) {
      this.chart.destroy();
    }
  }
}

// Global instance
let timeline = null;
