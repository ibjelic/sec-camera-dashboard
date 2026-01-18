/**
 * Settings Panel Component
 */
class SettingsPanel {
  constructor() {
    this.settings = {};
  }

  init() {
    this.loadSettings();
  }

  async loadSettings() {
    try {
      this.settings = await API.settings.get();
      this.updateUI();
    } catch (error) {
      console.error('Failed to load settings:', error);
    }
  }

  updateUI() {
    // Toggle switches
    document.getElementById('setting-telegram-enabled').checked =
      this.settings.telegram_enabled;
    document.getElementById('setting-telegram-screenshot').checked =
      this.settings.telegram_screenshot;
    document.getElementById('setting-telegram-gif').checked =
      this.settings.telegram_gif;

    // Threshold slider
    document.getElementById('setting-threshold').value =
      this.settings.detection_threshold;
    document.getElementById('threshold-value').textContent =
      this.settings.detection_threshold;

    // Retention dropdown
    document.getElementById('setting-retention').value =
      this.settings.retention_hours;

    // Cooldown dropdown
    document.getElementById('setting-cooldown').value =
      this.settings.notification_cooldown_seconds;

    // Apply theme
    document.documentElement.setAttribute('data-theme', this.settings.theme);
    this.updateThemeIcon();
  }

  async updateSetting(key, value) {
    try {
      this.settings[key] = value;
      await API.settings.update({ [key]: value });
      showToast('Setting updated', 'success');

      // Handle theme change
      if (key === 'theme') {
        document.documentElement.setAttribute('data-theme', value);
        this.updateThemeIcon();
      }
    } catch (error) {
      console.error('Failed to update setting:', error);
      showToast('Failed to update setting', 'error');
      // Reload settings to reset UI
      this.loadSettings();
    }
  }

  updateThemeIcon() {
    const icon = document.getElementById('theme-icon');
    const theme = document.documentElement.getAttribute('data-theme');
    icon.innerHTML = theme === 'dark' ? '&#9790;' : '&#9728;'; // Moon or Sun
  }

  toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    this.updateSetting('theme', newTheme);
  }

  async testTelegram() {
    try {
      showToast('Sending test message...', 'success');
      await API.settings.testTelegram();
      showToast('Test message sent!', 'success');
    } catch (error) {
      console.error('Telegram test failed:', error);
      showToast('Telegram test failed: ' + error.message, 'error');
    }
  }
}

// Global instance
let settingsPanel = null;

// Global function for updating settings from HTML
function updateSetting(key, value) {
  if (settingsPanel) {
    settingsPanel.updateSetting(key, value);
  }
}

// Global function for testing Telegram
function testTelegram() {
  if (settingsPanel) {
    settingsPanel.testTelegram();
  }
}
