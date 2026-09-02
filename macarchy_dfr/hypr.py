"""Window/workspace context as read from Hyprland (Task 13 fills in the reader)."""
import dataclasses


@dataclasses.dataclass(frozen=True)
class Context:
    cls: str = ""
    title: str = ""
    workspace: int = 0
    occupied: tuple = ()
    fn: bool = False
    awake: bool = True

    def replace(self, **kw):
        return dataclasses.replace(self, **kw)
