#!/usr/bin/env python3
from pathlib import Path

root = Path.cwd()
time_loop = root / "ProcessLib/TimeLoop.cpp"
text = time_loop.read_text(encoding="utf-8")

include = '#include "StagedConstruction/ConstructionTimeLoopDriver.h"\n'
if include not in text:
    anchor = '#include "ProcessData.h"\n'
    if anchor not in text:
        raise RuntimeError("Could not locate ProcessData.h include anchor in ProcessLib/TimeLoop.cpp")
    text = text.replace(anchor, anchor + include, 1)
    time_loop.write_text(text, encoding="utf-8")

print("Applied OGS Staged Construction R3G behavior-neutral TimeLoop compile bridge")
