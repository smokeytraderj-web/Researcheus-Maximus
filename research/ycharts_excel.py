"""Best-effort YCharts Excel Add-In bridge for authenticated Windows users.

The bridge asks the installed YCharts add-in to calculate formulas inside a
temporary workbook. It never handles YCharts credentials. Metric-level errors
are returned as limitations rather than silently substituted values.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class YChartsEvidence:
    values: tuple[tuple[str, object], ...]
    errors: tuple[str, ...]


METRICS = (
    ("YCharts consensus rating", "YCI", "consensus_rating"),
    ("YCharts price target", "YCP", "price_target"),
    ("YCharts price target low", "YCP", "price_target_low"),
    ("YCharts price target high", "YCP", "price_target_high"),
    ("YCharts price target upside", "YCP", "price_target_upside"),
    ("YCharts market capitalization", "YCP", "market_cap"),
    ("YCharts P/E ratio", "YCP", "pe_ratio"),
    ("YCharts price/sales ratio", "YCP", "ps_ratio"),
)


def retrieve_ycharts_metrics(ticker: str, workspace: Path, timeout: int = 60) -> YChartsEvidence:
    if not hasattr(__import__("sys"), "getwindowsversion"):
        return YChartsEvidence((), ("YCharts Excel automation is available only on Windows.",))
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return YChartsEvidence((), ("pywin32 is not installed, so the YCharts Excel add-in could not be queried.",))
    pythoncom.CoInitialize()
    excel = None
    workbook = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Add()
        sheet = workbook.Worksheets(1)
        sheet.Cells(1, 1).Value = "Metric"
        sheet.Cells(1, 2).Value = "Value"
        for row, (label, function, code) in enumerate(METRICS, start=2):
            sheet.Cells(row, 1).Value = label
            sheet.Cells(row, 2).Formula = f'={function}("{ticker}","{code}")'
        excel.CalculateFullRebuild()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if int(excel.CalculationState) == 0:
                break
            time.sleep(0.5)
        output = workspace / "ycharts-evidence.xlsx"
        workbook.SaveAs(str(output), FileFormat=51)
        values = []
        errors = []
        for row, (label, _function, _code) in enumerate(METRICS, start=2):
            value = sheet.Cells(row, 2).Value
            text = "" if value is None else str(value).strip()
            if not text or text.startswith("#") or text.lower() in {"loading", "n/a", "none"}:
                errors.append(f"{label} was unavailable from the YCharts Excel add-in.")
            else:
                values.append((label, value))
        if not values:
            errors.insert(0, "The YCharts Excel add-in returned no usable metrics. Confirm Excel is signed in to YCharts and the add-in is enabled.")
        return YChartsEvidence(tuple(values), tuple(errors))
    except Exception as exc:
        return YChartsEvidence((), (f"YCharts Excel automation did not complete: {exc}",))
    finally:
        if workbook is not None:
            try:
                workbook.Close(SaveChanges=False)
            except Exception:
                pass
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()

