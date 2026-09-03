"""Native PyQt UI — import submodules directly (e.g. ui.native.medium_panel)."""

__all__ = ["MediumPanel", "CompactBar"]


def __getattr__(name):
    if name == "MediumPanel":
        from ui.native.medium_panel import MediumPanel
        return MediumPanel
    if name == "CompactBar":
        from ui.native.compact_bar import CompactBar
        return CompactBar
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
