import unittest

from research.ycharts_excel import METRICS, _audit_rows, _enable_ycharts_addin, _is_excel_error


class _Addin:
    Description = "YCharts Excel Add-In"
    ProgId = "YCharts.Excel"
    Name = "YChartsExcel.xll"
    Title = "YCharts"
    FullName = r"C:\Program Files\YChartsExcel\YChartsExcel.xll"
    Connect = False
    Installed = False


class _SparseComAddin:
    Description = "YCharts COM Add-In"
    ProgId = "YCharts.Excel"
    Connect = False

    def __getattribute__(self, name):
        if name in {"Name", "Title", "FullName", "Installed"}:
            raise AttributeError(name)
        return super().__getattribute__(name)


class _Collection:
    def __init__(self, addin):
        self.addin = addin
        self.Count = 1

    def Item(self, _index):
        return self.addin


class _Excel:
    def __init__(self):
        self.addin = _Addin()
        self.COMAddIns = _Collection(self.addin)
        self.AddIns = _Collection(self.addin)
        self.registered = []

    def RegisterXLL(self, path):
        self.registered.append(path)


class YChartsExcelTests(unittest.TestCase):
    def test_excel_name_error_hresult_is_rejected(self):
        self.assertTrue(_is_excel_error(-2146826259, "#NAME?"))
        self.assertTrue(_is_excel_error(-2146826259, ""))
        self.assertTrue(_is_excel_error("ERR: INVALID CALC", "ERR: INVALID CALC"))
        self.assertFalse(_is_excel_error(128.43, "$128.43"))

    def test_audit_exposes_exact_result_cells_and_formulas(self):
        audit = _audit_rows("WMT", "Not run")
        self.assertEqual(len(audit), len(METRICS))
        self.assertEqual(audit[0][0], "F2")
        self.assertEqual(audit[0][1], '=YCI("WMT","consensus_recommendation_label")')

    def test_bridge_activates_excel_and_com_addins_and_registers_xll(self):
        excel = _Excel()
        self.assertTrue(_enable_ycharts_addin(excel))
        self.assertTrue(excel.addin.Connect)
        self.assertTrue(excel.addin.Installed)
        self.assertEqual(excel.registered, [excel.addin.FullName])

    def test_bridge_does_not_skip_sparse_com_addin_properties(self):
        addin = _SparseComAddin()

        class SparseExcel:
            COMAddIns = _Collection(addin)

            @property
            def AddIns(self):
                raise AttributeError("AddIns")

        self.assertTrue(_enable_ycharts_addin(SparseExcel()))
        self.assertTrue(addin.Connect)


if __name__ == "__main__":
    unittest.main()
