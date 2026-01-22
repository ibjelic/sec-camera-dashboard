/**
 * Live Preview Component - HLS video player with zoom
 */
class LivePreview {
  constructor() {
    this.video = document.getElementById('live-video');
    this.container = document.getElementById('live-video-container');
    this.timeDisplay = document.getElementById('video-time');
    this.zoomDisplay = document.getElementById('zoom-level');
    this.hls = null;
    this.retryTimeout = null;
    this.zoomLevel = 1;
    this.minZoom = 1;
    this.maxZoom = 4;
    this.zoomStep = 0.5;
    this.isDragging = false;
    this.dragStart = { x: 0, y: 0 };
    this.scrollStart = { x: 0, y: 0 };
  }

  init() {
    this.setupPlayer();
    this.startTimeUpdate();
    this.setupZoomControls();
  }

  setupZoomControls() {
    // Mouse wheel zoom
    this.container.addEventListener('wheel', (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        if (e.deltaY < 0) {
          this.zoomIn();
        } else {
          this.zoomOut();
        }
      }
    }, { passive: false });

    // Drag to pan when zoomed
    this.container.addEventListener('mousedown', (e) => {
      if (this.zoomLevel > 1) {
        this.isDragging = true;
        this.dragStart = { x: e.clientX, y: e.clientY };
        this.scrollStart = { x: this.container.scrollLeft, y: this.container.scrollTop };
        this.container.style.cursor = 'grabbing';
      }
    });

    document.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        const dx = e.clientX - this.dragStart.x;
        const dy = e.clientY - this.dragStart.y;
        this.container.scrollLeft = this.scrollStart.x - dx;
        this.container.scrollTop = this.scrollStart.y - dy;
      }
    });

    document.addEventListener('mouseup', () => {
      if (this.isDragging) {
        this.isDragging = false;
        this.container.style.cursor = this.zoomLevel > 1 ? 'grab' : '';
      }
    });

    // Double-click to zoom
    this.container.addEventListener('dblclick', (e) => {
      if (this.zoomLevel === 1) {
        this.setZoom(2);
      } else {
        this.zoomReset();
      }
    });

    // Keyboard shortcuts for fullscreen
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.container.classList.contains('fullscreen-active')) {
        this.exitFullscreen();
      }
    });
  }

  zoomIn() {
    this.setZoom(Math.min(this.zoomLevel + this.zoomStep, this.maxZoom));
  }

  zoomOut() {
    this.setZoom(Math.max(this.zoomLevel - this.zoomStep, this.minZoom));
  }

  zoomReset() {
    this.setZoom(1);
    this.container.scrollLeft = 0;
    this.container.scrollTop = 0;
  }

  setZoom(level) {
    this.zoomLevel = level;
    this.video.style.transform = `scale(${level})`;
    this.zoomDisplay.textContent = `${Math.round(level * 100)}%`;

    if (level > 1) {
      this.container.classList.add('zoomed');
      this.video.style.width = `${100 * level}%`;
      this.video.style.height = `${100 * level}%`;
    } else {
      this.container.classList.remove('zoomed');
      this.video.style.width = '100%';
      this.video.style.height = '100%';
      this.video.style.transform = '';
    }
  }

  toggleFullscreen() {
    if (this.container.classList.contains('fullscreen-active')) {
      this.exitFullscreen();
    } else {
      this.enterFullscreen();
    }
  }

  enterFullscreen() {
    this.container.classList.add('fullscreen-active');
    document.body.style.overflow = 'hidden';
  }

  exitFullscreen() {
    this.container.classList.remove('fullscreen-active');
    document.body.style.overflow = '';
  }

  setupPlayer() {
    const hlsUrl = API.stream.getHlsUrl();

    if (Hls.isSupported()) {
      this.hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false,         // Disable low-latency mode for stability
        backBufferLength: 60,          // 60 seconds buffer (was 30)
        maxBufferLength: 30,           // Add max buffer
        liveSyncDuration: 5,           // 5 sec behind live (was 3)
        liveMaxLatencyDuration: 15,    // Allow up to 15 sec (was 10)
        liveDurationInfinity: true,
        highBufferWatchdogPeriod: 2,   // Check every 2 sec (was 1)
      });

      this.hls.loadSource(hlsUrl);
      this.hls.attachMedia(this.video);

      this.hls.on(Hls.Events.MANIFEST_PARSED, () => {
        console.log('HLS manifest parsed');
        this.video.play().catch((e) => console.log('Autoplay blocked:', e));
      });

      this.hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          console.error('HLS fatal error:', data);
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              this.scheduleRetry();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              this.hls.recoverMediaError();
              break;
            default:
              this.scheduleRetry();
              break;
          }
        }
      });
    } else if (this.video.canPlayType('application/vnd.apple.mpegurl')) {
      // Native HLS support (Safari)
      this.video.src = hlsUrl;
      this.video.addEventListener('loadedmetadata', () => {
        this.video.play().catch((e) => console.log('Autoplay blocked:', e));
      });
    } else {
      console.error('HLS not supported');
    }
  }

  scheduleRetry() {
    if (this.retryTimeout) {
      clearTimeout(this.retryTimeout);
    }

    this.retryTimeout = setTimeout(() => {
      console.log('Retrying HLS connection...');
      if (this.hls) {
        this.hls.destroy();
      }
      this.setupPlayer();
    }, 3000);
  }

  startTimeUpdate() {
    setInterval(() => {
      const now = new Date();
      this.timeDisplay.textContent = now.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    }, 1000);
  }

  restart() {
    if (this.hls) {
      this.hls.destroy();
    }
    this.setupPlayer();
  }

  destroy() {
    if (this.hls) {
      this.hls.destroy();
      this.hls = null;
    }
    if (this.retryTimeout) {
      clearTimeout(this.retryTimeout);
    }
  }
}

// Global instance
let livePreview = null;
