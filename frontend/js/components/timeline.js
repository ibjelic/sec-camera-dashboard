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
    this.recordingSegments = [];
    this.coverage = [];
    this.playheadTime = null;
    this.playbackSegments = [];
    this.playbackIndex = -1;
    this.scrubCanvas = null;
    this.scrubCtx = null;
    this.animationFrameId = null;
    this.isPlaying = false;
    this.currentVideo = null;
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
    this.setupScrub();
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

  setupScrub() {
    this.scrubCanvas = document.getElementById('timeline-scrub-canvas');
    if (!this.scrubCanvas) return;
    this.scrubCtx = this.scrubCanvas.getContext('2d');
    this.isScrubbing = false;

    // Convert click position to time and seek
    const seekToPosition = (clientX) => {
      if (!this.chartData || this.chartData.length === 0) return;
      if (!this.currentVideo || !this.currentSegment) return;

      const rect = this.scrubCanvas.getBoundingClientRect();
      const x = clientX - rect.left;
      const ratio = Math.max(0, Math.min(1, x / rect.width));

      // Calculate target time from chart data range
      const startTime = new Date(this.chartData[0].minute).getTime();
      const endTime = new Date(this.chartData[this.chartData.length - 1].minute).getTime();
      const targetTime = new Date(startTime + ratio * (endTime - startTime));

      // Check if target is within current segment - just seek
      if (targetTime >= this.currentSegment.start && targetTime < this.currentSegment.end) {
        const seekOffset = (targetTime - this.currentSegment.start) / 1000;
        if (Number.isFinite(this.currentVideo.duration) && seekOffset <= this.currentVideo.duration) {
          this.currentVideo.currentTime = seekOffset;
          this.playheadTime = targetTime;
          this.renderScrub();
          return;
        }
      }

      // Outside current segment - load new recording
      this.playRecordingAtTime(targetTime);
    };

    // Click to seek (single click loads recording at that time)
    this.scrubCanvas.addEventListener('click', (event) => {
      if (!this.currentVideo) {
        // No video loaded yet - load one
        const rect = this.scrubCanvas.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const ratio = Math.max(0, Math.min(1, x / rect.width));
        const index = Math.round(ratio * (this.chartData.length - 1));
        const label = this.chartData[index]?.minute;
        if (label) {
          this.playRecordingAtTime(new Date(label));
        }
      }
    });

    // Drag to scrub within loaded video
    this.scrubCanvas.addEventListener('mousedown', (event) => {
      if (!this.currentVideo) return;
      this.isScrubbing = true;
      this.wasPlaying = !this.currentVideo.paused;
      this.currentVideo.pause();
      seekToPosition(event.clientX);
    });

    document.addEventListener('mousemove', (event) => {
      if (this.isScrubbing) {
        seekToPosition(event.clientX);
      }
    });

    document.addEventListener('mouseup', () => {
      if (this.isScrubbing) {
        this.isScrubbing = false;
        if (this.wasPlaying && this.currentVideo) {
          this.currentVideo.play().catch(() => {});
        }
      }
    });

    // Touch support
    this.scrubCanvas.addEventListener('touchstart', (event) => {
      if (!this.currentVideo) return;
      this.isScrubbing = true;
      this.wasPlaying = !this.currentVideo.paused;
      this.currentVideo.pause();
      seekToPosition(event.touches[0].clientX);
    }, { passive: true });

    this.scrubCanvas.addEventListener('touchmove', (event) => {
      if (this.isScrubbing) {
        seekToPosition(event.touches[0].clientX);
      }
    }, { passive: true });

    this.scrubCanvas.addEventListener('touchend', () => {
      if (this.isScrubbing) {
        this.isScrubbing = false;
        if (this.wasPlaying && this.currentVideo) {
          this.currentVideo.play().catch(() => {});
        }
      }
    });

    window.addEventListener('resize', () => {
      this.renderScrub();
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
      const segments = await this.loadRecordings();

      if (!segments || segments.length === 0) {
        showToast('No recordings available for this time', 'error');
        return;
      }

      // Find the recording that contains this time
      // Recordings are named YYYYMMDD_HHMMSS.mp4 and are 10 minutes long
      let bestIndex = -1;
      let seekOffset = 0;

      for (let i = 0; i < segments.length; i += 1) {
        const seg = segments[i];
        if (targetTime >= seg.start && targetTime < seg.end) {
          bestIndex = i;
          seekOffset = (targetTime - seg.start) / 1000; // Offset in seconds
          break;
        }
      }

      if (bestIndex === -1) {
        for (let i = segments.length - 1; i >= 0; i -= 1) {
          const seg = segments[i];
          if (seg.start <= targetTime) {
            bestIndex = i;
            seekOffset = Math.min((targetTime - seg.start) / 1000, 600);
            break;
          }
        }
      }

      if (bestIndex === -1) {
        showToast('No recording found for this time', 'error');
        return;
      }

      this.playRecordingSegment(bestIndex, seekOffset, targetTime);

    } catch (error) {
      console.error('Failed to load recording:', error);
      showToast('Failed to load recording', 'error');
    }
  }

  playRecordingSegment(index, seekOffset = 0, targetTime = null) {
    const segments = this.recordingSegments;
    if (!segments || !segments[index]) return;

    const segment = segments[index];
    const player = document.getElementById('timeline-player');
    const video = document.getElementById('timeline-video');
    const info = document.getElementById('timeline-video-info');

    const videoUrl = API.recordings.getFileUrl(segment.recording.date, segment.recording.name);

    // Stop any existing animation loop
    this.stopPlayheadAnimation();

    player.style.display = 'block';
    video.pause();
    video.src = videoUrl;
    video.load();

    const timeStr = (targetTime || segment.start).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
    info.textContent = `Playing: ${segment.recording.name} | ${timeStr}`;

    this.playbackSegments = segments;
    this.playbackIndex = index;
    this.currentVideo = video;
    this.currentSegment = segment;
    this.playheadTime = new Date(segment.start.getTime() + seekOffset * 1000);
    this.renderScrub();

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

    // Start smooth playhead animation
    video.onplay = () => {
      this.isPlaying = true;
      this.startPlayheadAnimation();
    };

    video.onpause = () => {
      this.isPlaying = false;
      this.stopPlayheadAnimation();
    };

    video.onended = () => {
      this.isPlaying = false;
      this.stopPlayheadAnimation();
      const nextIndex = index + 1;
      if (segments[nextIndex]) {
        // Seamlessly transition to next segment
        this.playRecordingSegment(nextIndex, 0, segments[nextIndex].start);
      }
    };
  }

  startPlayheadAnimation() {
    const animate = () => {
      if (!this.isPlaying || !this.currentVideo || !this.currentSegment) return;

      const currentTime = this.currentVideo.currentTime;
      const minutes = Math.floor((currentTime % 3600) / 60);
      const seconds = Math.floor(currentTime % 60);
      document.getElementById('timeline-video-time').textContent =
        `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
      this.playheadTime = new Date(this.currentSegment.start.getTime() + currentTime * 1000);
      this.renderScrub();

      this.animationFrameId = requestAnimationFrame(animate);
    };
    this.animationFrameId = requestAnimationFrame(animate);
  }

  stopPlayheadAnimation() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
  }

  closePlayer() {
    const player = document.getElementById('timeline-player');
    const video = document.getElementById('timeline-video');
    const info = document.getElementById('timeline-video-info');
    const time = document.getElementById('timeline-video-time');

    // Stop animation loop
    this.stopPlayheadAnimation();
    this.isPlaying = false;
    this.currentVideo = null;
    this.currentSegment = null;

    video.pause();
    video.removeAttribute('src');
    video.load();
    player.style.display = 'block';
    info.textContent = 'Click on timeline to load recording';
    time.textContent = '--:--:--';
    this.playheadTime = null;
    this.playbackSegments = [];
    this.playbackIndex = -1;
    this.renderScrub();
  }

  async loadData() {
    try {
      const [response, recordingsResponse] = await Promise.all([
        API.detections.getGraphData(this.currentRange),
        API.recordings.list()
      ]);
      this.chartData = response.data;
      this.recordings = recordingsResponse.recordings || [];
      this.buildRecordingSegments();
      this.updateCoverage();
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
    this.renderScrub();
  }

  updateRuler(data) {
    const ruler = document.getElementById('timeline-scrub-labels');
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

  buildRecordingSegments() {
    this.recordingSegments = this.recordings
      .map((rec) => {
        const match = rec.name.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
        if (!match) return null;
        const [, year, month, day, hour, minute, second] = match;
        const start = new Date(year, month - 1, day, hour, minute, second);
        const end = new Date(start.getTime() + 10 * 60 * 1000);
        return { recording: rec, start, end };
      })
      .filter(Boolean)
      .sort((a, b) => a.start - b.start);
  }

  updateCoverage() {
    if (!this.chartData || this.chartData.length === 0) {
      this.coverage = [];
      return;
    }

    const segments = this.recordingSegments;
    const labels = this.chartData.map((d) => new Date(d.minute));
    const coverage = new Array(labels.length).fill(false);

    let segIndex = 0;
    for (let i = 0; i < labels.length; i += 1) {
      const ts = labels[i];
      while (
        segIndex < segments.length &&
        segments[segIndex].end < ts
      ) {
        segIndex += 1;
      }
      const seg = segments[segIndex];
      if (seg && ts >= seg.start && ts < seg.end) {
        coverage[i] = true;
      }
    }

    this.coverage = coverage;
  }

  async loadRecordings() {
    if (this.recordingSegments && this.recordingSegments.length > 0) {
      return this.recordingSegments;
    }
    const response = await API.recordings.list();
    this.recordings = response.recordings || [];
    this.buildRecordingSegments();
    this.updateCoverage();
    return this.recordingSegments;
  }

  renderScrub() {
    if (!this.scrubCanvas || !this.scrubCtx || !this.chartData || this.chartData.length === 0) {
      return;
    }

    const rect = this.scrubCanvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    const dpr = window.devicePixelRatio || 1;
    this.scrubCanvas.width = rect.width * dpr;
    this.scrubCanvas.height = rect.height * dpr;
    this.scrubCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const ctx = this.scrubCtx;
    ctx.clearRect(0, 0, rect.width, rect.height);

    const values = this.chartData.map((d) => d.max_confidence || 0);
    const coverage = this.coverage && this.coverage.length === values.length
      ? this.coverage
      : new Array(values.length).fill(true);
    const barWidth = rect.width / values.length;

    const styles = getComputedStyle(document.documentElement);
    const detectionColor = styles.getPropertyValue('--chart-detection').trim() || '#d66c53';
    const mutedColor = styles.getPropertyValue('--muted').trim() || 'rgba(0,0,0,0.4)';
    const grayColor = 'rgba(128, 128, 128, 0.3)';
    const grayStripeColor = 'rgba(128, 128, 128, 0.15)';

    // First pass: draw background for unavailable areas (gray stripes)
    for (let i = 0; i < values.length; i += 1) {
      const x = i * barWidth;
      const available = coverage[i];

      if (!available) {
        // Draw diagonal stripe pattern for missing data
        ctx.fillStyle = grayColor;
        ctx.fillRect(x, 0, barWidth, rect.height);

        // Add subtle diagonal stripes
        ctx.strokeStyle = grayStripeColor;
        ctx.lineWidth = 1;
        const stripeSpacing = 4;
        for (let sy = -rect.height; sy < barWidth; sy += stripeSpacing) {
          ctx.beginPath();
          ctx.moveTo(x + sy, 0);
          ctx.lineTo(x + sy + rect.height, rect.height);
          ctx.stroke();
        }
      }
    }

    // Second pass: draw detection bars
    for (let i = 0; i < values.length; i += 1) {
      const x = i * barWidth;
      const available = coverage[i];
      const value = values[i];
      const barHeight = Math.max(2, (value / 100) * (rect.height - 8));

      if (available && value > 0) {
        ctx.fillStyle = detectionColor;
        ctx.fillRect(x, rect.height - barHeight, Math.max(1, barWidth * 0.8), barHeight);
      } else if (!available && value > 0) {
        // Show muted detection for unavailable times
        ctx.fillStyle = mutedColor;
        ctx.fillRect(x, rect.height - barHeight, Math.max(1, barWidth * 0.8), barHeight);
      }
    }

    // Draw playhead line with glow effect
    if (this.playheadTime) {
      const start = new Date(this.chartData[0].minute).getTime();
      const end = new Date(this.chartData[this.chartData.length - 1].minute).getTime();
      const t = this.playheadTime.getTime();
      if (end > start) {
        const ratio = Math.min(1, Math.max(0, (t - start) / (end - start)));
        const x = ratio * rect.width;

        // Draw glow
        ctx.shadowColor = detectionColor;
        ctx.shadowBlur = 6;
        ctx.strokeStyle = detectionColor;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, rect.height);
        ctx.stroke();

        // Draw playhead triangle
        ctx.shadowBlur = 0;
        ctx.fillStyle = detectionColor;
        ctx.beginPath();
        ctx.moveTo(x - 5, 0);
        ctx.lineTo(x + 5, 0);
        ctx.lineTo(x, 6);
        ctx.closePath();
        ctx.fill();
      }
    }
  }

  startAutoRefresh() {
    // Refresh every 30 seconds
    this.refreshInterval = setInterval(() => {
      this.loadData();
      this.loadStats();
    }, 30000);
  }

  destroy() {
    this.stopPlayheadAnimation();
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
