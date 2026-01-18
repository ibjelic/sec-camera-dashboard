/**
 * WebSocket client for real-time updates
 */
class WebSocketClient {
  constructor() {
    this.ws = null;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    this.listeners = {
      detection: [],
      status: [],
      storage: [],
      open: [],
      close: [],
    };
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectDelay = 1000;
        this._emit('open');
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this._emit('close');
        this._scheduleReconnect();
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      this.ws.onmessage = (event) => {
        this._handleMessage(event.data);
      };
    } catch (error) {
      console.error('WebSocket connection failed:', error);
      this._scheduleReconnect();
    }
  }

  _scheduleReconnect() {
    setTimeout(() => {
      console.log(`Reconnecting WebSocket in ${this.reconnectDelay}ms...`);
      this.connect();
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
    }, this.reconnectDelay);
  }

  _handleMessage(data) {
    try {
      const message = JSON.parse(data);
      const { type, data: payload } = message;

      if (type && this.listeners[type]) {
        this._emit(type, payload);
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }

  _emit(event, data = null) {
    if (this.listeners[event]) {
      this.listeners[event].forEach((callback) => callback(data));
    }
  }

  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
  }

  off(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter((cb) => cb !== callback);
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data));
    }
  }

  ping() {
    this.send('ping');
  }

  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}

// Global WebSocket instance
const wsClient = new WebSocketClient();
