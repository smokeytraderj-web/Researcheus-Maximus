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
    audit: tuple[tuple[str, str, str], ...] = ()


METRICS = (
    ("YCharts consensus rating", "YCI", "consensus_recommendation_label"),
    ("YCharts price target", "YCP", "price_target"),
    ("YCharts price target low", "YCP", "price_target_low"),
    ("YCharts price target high", "YCP", "price_target_high"),
    ("YCharts price target upside", "YCP", "price_target_upside"),
    ("YCharts market capitalization", "YCP", "market_cap"),
    ("YCharts P/E ratio", "YCP", "pe_ratio"),
    ("YCharts price/sales ratio", "YCP", "ps_ratio"),
)


def _formula(ticker: str, function: str, code: str) -> str:
    return f'={function}("{ticker}","{code}")'


def _audit_rows(ticker: str, status: str) -> tuple[tuple[str, str, str], ...]:
    return tuple((f"F{row}", _formula(ticker, function, code), status) for row, (_label, function, code) in enumerate(METRICS, start=2))


def _is_excel_error(value: object, displayed_text: str) -> bool:
    if displayed_text.startswith("#"):
        return True
    return isinstance(value, int) and (value & 0xFFFF0000) == 0x800A0000


def _enable_ycharts_addin(excel) -> bool:
    """Connect an installed YCharts COM/Excel add-in in this Excel instance."""
    found = False
    for collection_name, enabled_property in (("COMAddIns", "Connect"), ("AddIns", "Installed")):
        try:
            collection = getattr(excel, collection_name)
            for index in range(1, int(collection.Count) + 1):
                addin = collection.Item(index)
                name = " ".join(
                    str(getattr(addin, field, "") or "")
                    for field in ("Description", "ProgId", "Name", "Title")
                )
                if "ycharts" not in name.lower():
                    continue
                found = True
                if not bool(getattr(addin, enabled_property)):
                    setattr(addin, enabled_property, True)
        except Exception:
            continue
    return found


def retrieve_ycharts_metrics(ticker: str, workspace: Path, timeout: int = 60) -> YChartsEvidence:
    if not hasattr(__import__("sys"), "getwindowsversion"):
        message = "YCharts Excel automation is available only on Windows."
        return YChartsEvidence((), (message,), _audit_rows(ticker, "Not run - Windows required"))
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        message = "pywin32 is not installed, so the YCharts Excel add-in could not be queried."
        return YChartsEvidence((), (message,), _audit_rows(ticker, "Not run - pywin32 missing"))
    pythoncom.CoInitialize()
    excel = None
    workbook = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        addin_found = _enable_ycharts_addin(excel)
        workbook = excel.Workbooks.Add()
        sheet = workbook.Worksheets(1)
        headers = ("Metric", "Ticker", "Function", "Metric code", "Exact formula", "Live result", "Status")
        for column, header in enumerate(headers, start=1):
            sheet.Cells(1, column).Value = header
        for row, (label, function, code) in enumerate(METRICS, start=2):
            formula = _formula(ticker, function, code)
            sheet.Cells(row, 1).Value = label
            sheet.Cells(row, 2).Value = ticker
            sheet.Cells(row, 3).Value = function
            sheet.Cells(row, 4).Value = code
            sheet.Cells(row, 5).NumberFormat = "@"
            sheet.Cells(row, 5).Value = formula
            sheet.Cells(row, 6).Formula = formula
        excel.CalculateFullRebuild()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if int(excel.CalculationState) == 0:
                break
            time.sleep(0.5)
        values = []
        errors = []
        audit = []
        for row, (label, _function, _code) in enumerate(METRICS, start=2):
            cell = sheet.Cells(row, 6)
            value = cell.Value
            displayed = "" if cell.Text is None else str(cell.Text).strip()
            formula = _formula(ticker, _function, _code)
            if _is_excel_error(value, displayed):
                status = f"Unavailable - Excel returned {displayed or 'a formula error'}"
                errors.append(f"{label} was unavailable: {status}. Cell F{row}: {formula}")
            elif not displayed or displayed.lower() in {"loading", "n/a", "none", "-"}:
                status = "Unavailable - no value returned"
                errors.append(f"{label} was unavailable from the YCharts Excel add-in. Cell F{row}: {formula}")
            else:
                values.append((label, value))
                status = f"Loaded - {displayed}"
            sheet.Cells(row, 7).Value = status
            audit.append((f"F{row}", formula, status))
        sheet.Columns("A:G").AutoFit()
        output = workspace / f"ycharts-evidence-{ticker}.xlsx"
        workbook.SaveAs(str(output), FileFormat=51)
        if not values:
            addin_note = "The installed YCharts add-in was detected but returned no usable metrics." if addin_found else "No YCharts add-in was detected in the isolated Excel session."
            errors.insert(0, f"{addin_note} Confirm Excel is signed in to YCharts and the add-in is enabled.")
        return YChartsEvidence(tuple(values), tuple(errors), tuple(audit))
    except Exception as exc:
        message = f"YCharts Excel automation did not complete: {exc}"
        return YChartsEvidence((), (message,), _audit_rows(ticker, "Not completed - Excel automation error"))
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
