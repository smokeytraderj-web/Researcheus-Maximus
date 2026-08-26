import unittest

from research.ycharts_excel import METRICS, _audit_rows, _is_excel_error


class YChartsExcelTests(unittest.TestCase):
    def test_excel_name_error_hresult_is_rejected(self):
        self.assertTrue(_is_excel_error(-2146826259, "#NAME?"))
        self.assertTrue(_is_excel_error(-2146826259, ""))
        self.assertFalse(_is_excel_error(128.43, "$128.43"))

    def test_audit_exposes_exact_result_cells_and_formulas(self):
        audit = _audit_rows("WMT", "Not run")
        self.assertEqual(len(audit), len(METRICS))
        self.assertEqual(audit[0][0], "F2")
        self.assertEqual(audit[0][1], '=YCI("WMT","consensus_recommendation_label")')


if __name__ == "__main__":
    unittest.main()
