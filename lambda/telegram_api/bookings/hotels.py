from dataclasses import dataclass, field


@dataclass
class Location:
    lon: float
    lat: float
    address: str | None = None


@dataclass
class Hotel:
    name: str
    location: Location
    stars: int
    url: str | None = field(default=None)
    poster: bytes | None = field(default=None, hash=False, repr=False)
