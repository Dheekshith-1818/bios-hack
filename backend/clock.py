import time

class SimulationClock:
    def __init__(self, speed: float = 1.0):
        self._real_start = time.time()
        self._virtual_start = self._real_start
        self._speed = speed
        self._paused = False
        self._pause_virtual_ts = None

    def now(self) -> float:
        if self._paused:
            return self._pause_virtual_ts
        elapsed_real = time.time() - self._real_start
        return self._virtual_start + (elapsed_real * self._speed)

    def set_speed(self, speed: float):
        if speed <= 0:
            raise ValueError("Speed must be positive")
        current_v = self.now()
        self._real_start = time.time()
        self._virtual_start = current_v
        self._speed = speed

    def pause(self):
        if not self._paused:
            self._pause_virtual_ts = self.now()
            self._paused = True

    def resume(self):
        if self._paused:
            self._real_start = time.time()
            self._virtual_start = self._pause_virtual_ts
            self._paused = False
            self._pause_virtual_ts = None

    def reset(self, virtual_start: float = None):
        self._real_start = time.time()
        self._virtual_start = virtual_start or self._real_start
        self._paused = False
        self._pause_virtual_ts = None

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def is_paused(self) -> bool:
        return self._paused

sim_clock = SimulationClock(speed=1.0)

