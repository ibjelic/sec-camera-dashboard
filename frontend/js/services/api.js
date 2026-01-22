/**
 * API client for Security Camera Dashboard
 */
const API = {
  baseUrl: '/api',

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  },

  // Stream endpoints
  stream: {
    getStatus() {
      return API.request('/stream/status');
    },

    restart() {
      return API.request('/stream/restart', { method: 'POST' });
    },

    getHlsUrl() {
      return '/hls/stream.m3u8';
    },

    switchStream(streamType) {
      return API.request(`/stream/switch/${streamType}`, { method: 'POST' });
    },

    compareStreams() {
      return API.request('/stream/compare');
    },
  },

  // Recordings endpoints
  recordings: {
    list(date = null) {
      const params = date ? `?date=${date}` : '';
      return API.request(`/recordings${params}`);
    },

    getDates() {
      return API.request('/recordings/dates');
    },

    getFileUrl(date, filename) {
      return `/api/recordings/file/${date}/${filename}`;
    },

    delete(date, filename) {
      return API.request(`/recordings/file/${date}/${filename}`, { method: 'DELETE' });
    },
  },

  // Detection endpoints
  detections: {
    getEvents(start = null, end = null, limit = 100) {
      const params = new URLSearchParams();
      if (start) params.append('start', start);
      if (end) params.append('end', end);
      params.append('limit', limit);
      return API.request(`/detections/events?${params}`);
    },

    getRecent(limit = 10) {
      return API.request(`/detections/recent?limit=${limit}`);
    },

    getGraphData(range = '1h') {
      return API.request(`/detections/graph?range=${range}`);
    },

    getStats() {
      return API.request('/detections/stats');
    },
  },

  // Settings endpoints
  settings: {
    get() {
      return API.request('/settings');
    },

    update(settings) {
      return API.request('/settings', {
        method: 'PUT',
        body: JSON.stringify(settings),
      });
    },

    testTelegram() {
      return API.request('/settings/test-telegram', { method: 'POST' });
    },

    testGif() {
      return API.request('/settings/test-gif', { method: 'POST' });
    },
  },

  // Storage endpoints
  storage: {
    getStats() {
      return API.request('/storage');
    },
  },

  // Health check
  health() {
    return API.request('/health');
  },
};
