/**
 * Live Preview Component - HLS video player
 */
class LivePreview {
  constructor() {
    this.video = document.getElementById('live-video');
    this.timeDisplay = document.getElementById('video-time');
    this.hls = null;
    this.retryTimeout = null;
  }

  init() {
    this.setupPlayer();
    this.startTimeUpdate();
  }

  setupPlayer() {
    const hlsUrl = API.stream.getHlsUrl();

    if (Hls.isSupported()) {
      this.hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
        backBufferLength: 30,
        liveSyncDuration: 3,
        liveMaxLatencyDuration: 10,
        liveDurationInfinity: true,
        highBufferWatchdogPeriod: 1,
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
