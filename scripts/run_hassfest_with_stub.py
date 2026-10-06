"""Register Easywave feature enums, then run hassfest from a Core checkout."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _register_stub(stub_init: Path) -> None:
    """Overlay HACS feature enums onto ``homeassistant.components.easywave``.

    Core may already ship Easywave without the HACS state-trigger flags
    (SWITCH_*, COVER_*). Hassfest must resolve the enums from this repo's
    ``const.py``, not from an older Core copy.
    """
    import homeassistant.components as components

    name = "homeassistant.components.easywave"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, stub_init)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load hassfest Easywave stub from {stub_init}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    setattr(components, "easywave", module)
    spec = importlib.util.spec_from_file_location(name, stub_init)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load hassfest Easywave stub from {stub_init}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    import homeassistant.components as components

    setattr(components, "easywave", module)


def main() -> int:
    """Run ``script.hassfest`` after registering the HACS feature-enum stub."""
    if len(sys.argv) < 3:
        print(
            "Usage: run_hassfest_with_stub.py <core_path> <integration_path>",
            file=sys.stderr,
        )
        return 2
    core_path = Path(sys.argv[1]).resolve()
    integration_path = str(Path(sys.argv[2]).resolve())
    stub_init = Path(__file__).resolve().parent / "hassfest_easywave_stub" / "__init__.py"
    sys.path.insert(0, str(core_path))
    _register_stub(stub_init)
    sys.argv = [
        "hassfest",
        "--action",
        "validate",
        "--integration-path",
        integration_path,
        "--core-path",
        str(core_path),
    ]
    from script.hassfest.__main__ import main as hassfest_main

    return hassfest_main()


if __name__ == "__main__":
    raise SystemExit(main())
