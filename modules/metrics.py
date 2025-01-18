import asyncio
from collections import defaultdict
from typing import Dict, List, Any

class Metrics:
    def __init__(self):
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        self._lock = asyncio.Lock()

    async def increment(self, metric: str, value: int = 1):
        async with self._lock:
            self.counters[metric] += value

    async def record_time(self, metric: str, duration: float):
        async with self._lock:
            self.timers[metric].append(duration)
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics state"""
        return {
            "counters": dict(self.counters),
            "timers": {k: {"avg": sum(v)/len(v), "count": len(v)} 
                      for k, v in self.timers.items() if v}
        }

    async def get_aggregated_metrics(self):
        return {
            "error_rate": self.calculate_error_rate(),
            "response_times": self.calculate_percentiles()
        }