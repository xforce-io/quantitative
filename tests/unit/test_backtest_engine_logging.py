"""Guard against the print->logging migration defect in BacktestEngine.

The migration left many ``logger.info("...{x}...")`` calls without an ``f``
prefix, so placeholders were emitted literally instead of interpolated.
"""

import pathlib
import re

ENGINE = pathlib.Path("quant/engines/backtest_engine.py")
LOGGER_CALL = re.compile(r'logger\.(?:info|warning|error|debug)\((f?)"((?:[^"\\]|\\.)*)"')


def test_engine_logger_calls_interpolate_placeholders():
    """Every logger call containing ``{`` placeholders must be an f-string."""
    src = ENGINE.read_text(encoding="utf-8")
    offenders = [
        body[:60]
        for is_f, body in LOGGER_CALL.findall(src)
        if "{" in body and not is_f
    ]
    assert not offenders, f"non-f-string logger calls with placeholders: {offenders}"
