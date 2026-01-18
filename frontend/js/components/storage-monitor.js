/**
 * Storage Monitor Component
 */
class StorageMonitor {
  constructor() {
    this.refreshInterval = null;
  }

  init() {
    this.loadStats();
    this.startAutoRefresh();

    // Listen for WebSocket storage updates
    wsClient.on('storage', (data) => {
      this.updateDisplay(data);
    });
  }

  async loadStats() {
    try {
      const stats = await API.storage.getStats();
      this.updateDisplay(stats);
    } catch (error) {
      console.error('Failed to load storage stats:', error);
    }
  }

  updateDisplay(stats) {
    const usedPercent = stats.used_percent || 0;
    const fillElement = document.getElementById('storage-fill');

    fillElement.style.width = `${usedPercent}%`;

    // Update color based on usage
    fillElement.classList.remove('warning', 'danger');
    if (usedPercent > 90) {
      fillElement.classList.add('danger');
    } else if (usedPercent > 75) {
      fillElement.classList.add('warning');
    }

    // Update text values
    document.getElementById('storage-used').textContent = `${stats.used_gb} GB`;
    document.getElementById('storage-free').textContent = `${stats.free_gb} GB`;
    document.getElementById('storage-recordings').textContent = `${stats.recordings_size_gb} GB`;
  }

  startAutoRefresh() {
    // Refresh every 60 seconds
    this.refreshInterval = setInterval(() => {
      this.loadStats();
    }, 60000);
  }

  destroy() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  }
}

// Global instance
let storageMonitor = null;
