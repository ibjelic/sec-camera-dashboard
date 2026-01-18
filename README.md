# Security Camera Dashboard

A modern security camera dashboard with RTSP stream ingestion, person detection (YOLO), rolling recordings, Telegram notifications, and a web interface.

## Features

- **Live HLS Streaming**: Low-latency live preview from RTSP cameras
- **Person Detection**: YOLO-based person detection with configurable confidence threshold
- **Rolling Recordings**: 10-minute MP4 segments with configurable retention
- **Telegram Alerts**: Screenshots and 10-second GIF clips on detection
- **Detection Timeline**: Interactive chart showing detection history
- **File Browser**: Browse and playback recorded segments by date
- **Storage Monitoring**: Disk usage tracking with automatic cleanup
- **Light/Dark Theme**: Modern glass-card UI following design system

## Requirements

- Python 3.11+
- FFmpeg 5.0+
- 4GB+ RAM (for YOLO model)

## Installation

1. Clone the repository and navigate to the project directory

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or: venv\Scripts\activate  # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables in `.env`:
   ```env
   RTSP_URL_HIGH=rtsp://192.168.1.137/streamtype=0
   RTSP_URL_LOW=rtsp://192.168.1.137/streamtype=1
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   DATA_DIR=./data
   HOST=0.0.0.0
   PORT=8000
   ```

5. Start the server:
   ```bash
   python run.py
   ```

6. Open `http://localhost:8000` in your browser

## Configuration

Runtime settings can be adjusted via the web interface or in `config/settings.json`:

| Setting | Default | Description |
|---------|---------|-------------|
| `telegram_enabled` | true | Enable/disable Telegram notifications |
| `telegram_screenshot` | true | Send screenshot on detection |
| `telegram_gif` | true | Send 10s GIF clip on detection |
| `detection_threshold` | 50 | Person detection confidence (0-100%) |
| `retention_hours` | 48 | Keep recordings for N hours |
| `notification_cooldown_seconds` | 60 | Minimum seconds between alerts |
| `theme` | dark | UI theme (light/dark) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stream/hls/stream.m3u8` | GET | Live HLS playlist |
| `/api/stream/status` | GET | Stream status |
| `/api/stream/restart` | POST | Restart streams |
| `/api/recordings` | GET | List recordings |
| `/api/recordings/file/{date}/{name}` | GET | Stream recording |
| `/api/detections/graph?range=1h` | GET | Detection timeline data |
| `/api/detections/recent` | GET | Recent detection events |
| `/api/settings` | GET/PUT | Get/update settings |
| `/api/storage` | GET | Storage statistics |
| `/ws` | WebSocket | Real-time events |

## Project Structure

```
sec-camera-dashboard/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── routers/             # API routes
│   ├── services/            # Core services
│   └── websocket/           # Real-time updates
├── frontend/
│   ├── index.html           # Dashboard page
│   ├── css/styles.css       # Design system
│   └── js/                  # Components & services
├── data/
│   ├── recordings/          # MP4 segments
│   ├── hls/                 # Live stream segments
│   ├── detections/          # SQLite database
│   └── thumbnails/          # Detection images
├── config/
│   └── settings.json        # Runtime settings
├── .env                     # Environment variables
├── requirements.txt         # Python dependencies
└── run.py                   # Entry point
```

## Telegram Setup

1. Create a bot with [@BotFather](https://t.me/botfather)
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Add bot token and chat ID to `.env`

## License

MIT
