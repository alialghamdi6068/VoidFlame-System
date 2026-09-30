import threading
import time

from database import get_guild_data


class SettingsCache:
    def __init__(self, ttl=15, max_entries=1000):
        self.ttl = ttl
        self.max_entries = max_entries
        self._data = {}
        self._lock = threading.RLock()

    def get(self, guild_id):
        guild_id = int(guild_id)
        now = time.monotonic()

        with self._lock:
            item = self._data.get(guild_id)
            if item and now - item[0] < self.ttl:
                return dict(item[1])

        data = get_guild_data(guild_id)

        with self._lock:
            if len(self._data) >= self.max_entries and guild_id not in self._data:
                oldest_id = min(self._data, key=lambda key: self._data[key][0], default=None)
                if oldest_id is not None:
                    self._data.pop(oldest_id, None)
            self._data[guild_id] = (time.monotonic(), dict(data))

        return dict(data)

    def invalidate(self, guild_id):
        with self._lock:
            self._data.pop(int(guild_id), None)

    def clear(self):
        with self._lock:
            self._data.clear()


settings_cache = SettingsCache()
