from dataclasses import dataclass, field


@dataclass(unsafe_hash=True)
class Contact:
    whatsapp_id: str
    name: str | None = field(default=None, hash=False, compare=False)

    def __repr__(self) -> str:
        if self.name is None or len(self.name.strip()) == 0:
            return self.whatsapp_id

        return f'{self.name}'
