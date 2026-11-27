import sys, unittest
from datetime import date
from pathlib import Path

try:
    import pandas as pd
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import etl_planilhas as etl
except Exception:  # pandas ausente no ambiente do time: pula
    pd = None


@unittest.skipIf(pd is None, "pandas não instalado")
class TestEtl(unittest.TestCase):
    def test_concorrentes_alfanumerico_duplicado_e_invalido(self):
        df = pd.DataFrame({"CNPJ": ["11.222.333/0001-81", "11222333000181", "12.ABC.345/01DE-35", "123", None, "11.222.333/0001-82"]})
        validos, invalidos, dv_ruim = etl.preparar_concorrentes(df)
        self.assertEqual(sorted(validos["cnpj_clean"]), ["11222333000181", "11222333000182", "12ABC34501DE35"])  # 1 duplicado removido
        self.assertEqual(len(invalidos), 2)       # "123" e vazio
        self.assertEqual(list(dv_ruim["cnpj_clean"]), ["11222333000182"])  # formato ok, DV não confere -> só sinaliza

    def test_status_desconhecido_nao_vira_faturado(self):
        self.assertEqual(etl.normalizar_status_entrega(" lançado no sistema "), "LANCADO_NO_SISTEMA")
        self.assertIsNone(etl.normalizar_status_entrega("EM TRANSITO"))

    def test_entregas_rejeicoes_e_corte(self):
        df = pd.DataFrame({
            "STATUS": ["FATURADO", "XYZ", "ENTREGUE", "FATURADO"],
            "QUANTIDADE": [2, 1, 0, 3], "EMPENHO/PEDIDO/AF": ["1", "2", "3", "4"],
            "VALOR UNITÁRIO": [10, 10, 10, 10],
            "RECEBIMENTO": ["2026-01-10", "2026-01-10", "2026-01-10", "2026-11-20"],
        })
        ok, rej = etl.preparar_entregas(df, date(2026, 11, 1))
        self.assertEqual(list(ok["EMPENHO/PEDIDO/AF"]), ["1"])
        self.assertEqual(set(rej["motivo_rejeicao"]), {"status desconhecido", "quantidade inválida", "após data de corte (vem do Portal)"})

    def test_normalizacoes(self):
        self.assertEqual(etl.normalizar_empresa("empresa demo sc"), "Empresa/SC")
        self.assertEqual(etl.normalizar_vendedor("*Ana*"), "ANA")
        self.assertEqual(etl._sku_base("12345.0"), "12345")


if __name__ == "__main__":
    unittest.main()
