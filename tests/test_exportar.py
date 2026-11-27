"""Exportação de planilhas (XLSX escrito à mão + CSV) e regras novas da cotação — sem dependências externas."""
import datetime as dt
import decimal
import io
import pathlib
import re
import sys
import unittest
import zipfile

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from app.services import exportar  # noqa: E402


class TestExportar(unittest.TestCase):
    CAB = ["Data", "Texto", "Valor (R$)", "Qtde"]
    LIN = [[dt.date(2026, 11, 27), "Pneu 295/80 R22.5 & <câmara>", decimal.Decimal("2100.50"), 10],
           [None, "x", 3.5, None]]

    def test_xlsx_e_um_zip_valido_com_o_conteudo(self):
        corpo, mime, ext = exportar.gerar("Pregões", self.CAB, self.LIN, "xlsx")
        self.assertEqual((ext, mime), ("xlsx", exportar.XLSX))
        z = zipfile.ZipFile(io.BytesIO(corpo))
        self.assertIn("xl/worksheets/sheet1.xml", z.namelist())
        xml = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("27/11/2026", xml)                 # data formatada
        self.assertIn("Pneu 295/80 R22.5 &amp; &lt;câmara&gt;", xml)  # escape de XML
        self.assertIn("<v>2100.5</v>", xml)              # Decimal -> número
        self.assertIn('<autoFilter ref="A1:D3"/>', xml)

    def test_xlsx_abre_no_openpyxl_se_instalado(self):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("openpyxl ausente (não é necessário em produção)")
        ws = load_workbook(io.BytesIO(exportar.gerar("t", self.CAB, self.LIN)[0])).active
        self.assertEqual([c.value for c in ws[1]], self.CAB)
        self.assertEqual(ws["C2"].value, 2100.5)

    def test_csv_pt_br(self):
        corpo, mime, ext = exportar.gerar("t", self.CAB, self.LIN, "csv")
        txt = corpo.decode("utf-8")
        self.assertTrue(txt.startswith("﻿"))        # BOM p/ Excel
        self.assertIn("27/11/2026;", txt)
        self.assertIn(";2100,5;", txt)                   # vírgula decimal, separador ';'

    def test_nome_arquivo_seguro(self):
        self.assertEqual(exportar.nome_arquivo("Ata ARP 01/2026", "xlsx"), "Ata_ARP_01_2026.xlsx")


class TestRegrasSql(unittest.TestCase):
    def setUp(self):
        self.m2 = (RAIZ / "db/migrations/002_pregoes_atas.sql").read_text(encoding="utf-8")
        self.m3 = (RAIZ / "db/migrations/003_views_pregoes_atas.sql").read_text(encoding="utf-8")

    def test_nao_existe_mais_nosso_valor_unit(self):
        for arq in list((RAIZ / "app").rglob("*.py")) + list((RAIZ / "db").rglob("*.sql")) + [RAIZ / "scripts/etl_planilhas.py", RAIZ / "ui/pregoes-atas.js"]:
            self.assertNotIn("nosso_valor_unit", arq.read_text(encoding="utf-8"), arq.name)

    def test_vitoria_da_cpx_exige_valor_vencedor(self):
        self.assertIn("chk_vencedor_cpx_valor", self.m2)

    def test_view_expoe_itens_ganhos_e_valor_ganho(self):
        self.assertRegex(self.m3, r"AS itens_ganhos")
        self.assertRegex(self.m3, r"AS valor_ganho")

    def test_sem_textos_nosso_nossa_na_interface(self):
        for arq in (RAIZ / "ui").glob("*.js"):
            self.assertIsNone(re.search(r"\bnoss[oa]s?\b", arq.read_text(encoding="utf-8"), re.I), arq.name)


if __name__ == "__main__":
    unittest.main()
