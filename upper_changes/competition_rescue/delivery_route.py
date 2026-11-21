"""Upper-owned staging legs. Each D=0 handoff belongs to one navigation action."""
from dataclasses import dataclass


@dataclass
class DeliveryRoute:
    points: tuple[tuple[float, float], ...]
    destination: str
    precise: bool = False
    index: int = 0
    zero_sent: bool = False

    @property
    def target(self):
        return self.points[self.index]

    @property
    def last(self):
        return self.index == len(self.points) - 1

    def arrived(self, x, y):
        return (abs(x - self.target[0]) <= (0.010 if self.precise else 0.050) + 1e-9
                and abs(y - self.target[1]) <= 0.050 + 1e-9)

    def advance(self):
        assert not self.last
        self.index += 1
        self.zero_sent = False
