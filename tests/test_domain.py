import unittest
from datetime import date

from app.domain import emailing, status, validators as v, vigencia


class TestCnpj(unittest.TestCase):
    def test_numerico_valido(self):
        self.assertTrue(v.cnpj_valido("11.222.333/0001-81"))      # CNPJ do Guia (pág. 11)

    def test_alfanumerico_valido(self):
        self.assertTrue(v.cnpj_valido("12.ABC.345/01DE-35"))      # CNPJ alfanumérico do Guia (pág. 10/18)
        self.assertEqual(v.limpar_cnpj("12.abc.345/01de-35"), "12ABC34501DE35")

    def test_invalidos(self):
        self.assertFalse(v.cnpj_valido("11.222.333/0001-82"))
        self.assertFalse(v.cnpj_valido("00000000000000"))
        self.assertFalse(v.cnpj_valido("123"))
        self.assertIsNone(v.limpar_cnpj("1234"))

    def test_formatar(self):
        self.assertEqual(v.formatar_cnpj("11222333000181"), "11.222.333/0001-81")


class TestEmails(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(v.parse_emails("A@x.gov.br; b@x.gov.br ;a@x.gov.br"), ["a@x.gov.br", "b@x.gov.br"])
        self.assertEqual(v.parse_emails(None), [])
        with self.assertRaises(ValueError):
            v.parse_emails("nao-e-email")


class TestArquivos(unittest.TestCase):
    PDF = b"%PDF-1.7\n..."

    def test_pdf_ok(self):
        self.assertEqual(v.validar_arquivo("c.pdf", self.PDF, v.CONFIRMACAO_TIPOS), "application/pdf")

    def test_nome_pdf_mas_conteudo_falso(self):
        with self.assertRaises(v.ArquivoInvalido):
            v.validar_arquivo("falso.pdf", b"MZ\x90\x00 executavel", v.CONFIRMACAO_TIPOS)

    def test_extensao_incoerente(self):
        with self.assertRaises(v.ArquivoInvalido):
            v.validar_arquivo("a.png", self.PDF, v.CONFIRMACAO_TIPOS)

    def test_limite_8mb(self):
        with self.assertRaises(v.ArquivoInvalido):
            v.validar_arquivo("g.pdf", b"%PDF-" + b"0" * (8 * v.MB), v.CONFIRMACAO_TIPOS)

    def test_xml_nf(self):
        self.assertEqual(v.validar_arquivo("n.xml", b'<?xml version="1.0"?><nfeProc/>', v.NOTA_FISCAL_TIPOS), "application/xml")

    def test_xml_nao_aceito_na_confirmacao(self):
        with self.assertRaises(v.ArquivoInvalido):
            v.validar_arquivo("n.xml", b"<?xml version='1.0'?><a/>", v.CONFIRMACAO_TIPOS)

    def test_docx_zip(self):
        self.assertIn("wordprocessing", v.validar_arquivo("e.docx", b"PK\x03\x04abc", v.DOC_PREGAO_TIPOS))
        with self.assertRaises(v.ArquivoInvalido):
            v.validar_arquivo("e.docx", b"PK\x03\x04abc", v.CONFIRMACAO_TIPOS)

    def test_nome_seguro(self):
        self.assertEqual(v.nome_seguro("../../etc/passwd"), "passwd")


S = status.ItemStatus


class TestTransicoes(unittest.TestCase):
    def test_caminho_principal(self):
        self.assertEqual(status.validar_transicao("lancar", S.EMP_RECEBIDO), S.LANCADO_SISTEMA)
        self.assertEqual(status.validar_transicao("faturar", S.LANCADO_SISTEMA), S.FATURADO)
        self.assertEqual(status.validar_transicao("entregar", S.FATURADO), S.ENTREGUE)

    def test_so_lancado_fatura(self):
        for s in (S.EMP_RECEBIDO, S.AG_ESTOQUE, S.TROCA_MARCA, S.ENTREGUE):
            with self.assertRaises(status.RegraNegocioErro):
                status.validar_transicao("faturar", s)

    def test_carta_so_depois_de_faturado(self):
        with self.assertRaises(status.RegraNegocioErro):
            status.validar_transicao("carta_correcao", S.LANCADO_SISTEMA)
        self.assertEqual(status.validar_transicao("carta_correcao", S.FATURADO), S.CARTA_CORRECAO)

    def test_carta_pode_ir_direto_a_entregue(self):
        self.assertEqual(status.validar_transicao("entregar", S.CARTA_CORRECAO), S.ENTREGUE)

    def test_op_perdida(self):
        self.assertEqual(status.validar_transicao("aguardar_estoque", S.LANCADO_SISTEMA), S.AG_ESTOQUE)
        with self.assertRaises(status.RegraNegocioErro):
            status.exigir_campos("aguardar_estoque", S.LANCADO_SISTEMA, motivo="  ")
        status.exigir_campos("aguardar_estoque", S.EMP_RECEBIDO)  # sem lançar OP não precisa de motivo

    def test_cancelar_em_qualquer_etapa_exceto_terminais(self):
        for s in (S.EMP_RECEBIDO, S.AG_ESTOQUE, S.TROCA_MARCA, S.LANCADO_SISTEMA, S.FATURADO, S.CARTA_CORRECAO):
            self.assertEqual(status.validar_transicao("cancelar", s), S.EMP_CANCELADO)
        for s in (S.ENTREGUE, S.EMP_CANCELADO):
            with self.assertRaises(status.RegraNegocioErro):
                status.validar_transicao("cancelar", s)

    def test_cancelar_outro_exige_descricao(self):
        with self.assertRaises(status.RegraNegocioErro):
            status.exigir_campos("cancelar", S.EMP_RECEBIDO, motivo="Outro")
        status.exigir_campos("cancelar", S.EMP_RECEBIDO, motivo="Outro", motivo_detalhe="Duplicado")
        status.exigir_campos("cancelar", S.EMP_RECEBIDO, motivo="Órgão desistiu")

    def test_lancar_exige_op_e_codigo_na_troca_de_marca(self):
        with self.assertRaises(status.RegraNegocioErro):
            status.exigir_campos("lancar", S.EMP_RECEBIDO, op_numero="")
        status.exigir_campos("lancar", S.EMP_RECEBIDO, op_numero="823962981303")
        with self.assertRaises(status.RegraNegocioErro):
            status.exigir_campos("lancar", S.TROCA_MARCA, op_numero="1")
        status.exigir_campos("lancar", S.TROCA_MARCA, op_numero="1", codigo_produto_enviado="X9")

    def test_reabrir(self):
        self.assertEqual(status.destino_reabertura("FATURADO", "ENTREGUE"), S.FATURADO)
        self.assertEqual(status.destino_reabertura(None, "EMP_CANCELADO"), S.EMP_RECEBIDO)
        with self.assertRaises(status.RegraNegocioErro):
            status.destino_reabertura(None, "FATURADO")

    def test_datas(self):
        hoje = date(2026, 11, 26)
        with self.assertRaises(status.RegraNegocioErro):
            status.validar_data_entrega(date(2026, 11, 27), hoje)
        status.validar_data_entrega(hoje, hoje)
        with self.assertRaises(status.RegraNegocioErro):
            status.validar_prazo(date(2026, 11, 12), date(2026, 11, 1))
        status.validar_prazo(date(2026, 11, 12), None)


class TestSituacao(unittest.TestCase):
    hoje = date(2026, 11, 26)

    def test_situacoes(self):
        f = lambda sts, prazo=None: status.situacao_licitacao(sts, prazo, self.hoje)  # noqa: E731
        self.assertEqual(f([S.EMP_RECEBIDO, S.ENTREGUE])[0], "ANDAMENTO")
        self.assertEqual(f([S.FATURADO, S.FATURADO])[0], "FATURADA")
        self.assertEqual(f([S.ENTREGUE, S.ENTREGUE])[0], "CONCLUIDA")
        self.assertEqual(f([S.ENTREGUE, S.EMP_CANCELADO])[0], "CONCLUIDA")
        self.assertEqual(f([S.EMP_CANCELADO, S.EMP_CANCELADO])[0], "CANCELADA")
        self.assertEqual(f([S.CARTA_CORRECAO, S.FATURADO])[0], "ANDAMENTO")

    def test_prazo_vencido_so_em_andamento(self):
        self.assertEqual(status.situacao_licitacao([S.EMP_RECEBIDO], date(2026, 11, 7), self.hoje), ("ANDAMENTO", True))
        self.assertEqual(status.situacao_licitacao([S.EMP_RECEBIDO], date(2026, 11, 26), self.hoje), ("ANDAMENTO", False))
        self.assertEqual(status.situacao_licitacao([S.FATURADO], date(2026, 11, 7), self.hoje), ("FATURADA", False))


class TestEtapasEProximoPasso(unittest.TestCase):
    def test_tela_do_guia_pag13(self):
        """Licitação LIC-2026-000003: sem confirmação, 1 item em Emp. recebido."""
        e = status.etapas(date(2026, 11, 3), False, [S.EMP_RECEBIDO], [])
        self.assertEqual([x["estado"] for x in e], ["concluida", "atual", "pendente", "pendente", "pendente", "pendente"])
        self.assertEqual(e[1]["detalhe"], "Falta anexar")
        self.assertEqual(e[2]["detalhe"], "0 de 1 item(ns)")
        self.assertEqual(e[4]["detalhe"], "Sai junto com a NF")
        self.assertEqual(status.proximo_passo(False, [S.EMP_RECEBIDO], [])["codigo"], "ANEXAR_CONFIRMACAO")

    def test_fluxo_completo(self):
        self.assertEqual(status.proximo_passo(True, [S.EMP_RECEBIDO], [])["codigo"], "VERIFICAR_ESTOQUE")
        self.assertEqual(status.proximo_passo(True, [S.LANCADO_SISTEMA], [])["codigo"], "REGISTRAR_NF")
        self.assertEqual(status.proximo_passo(True, [S.FATURADO], ["ENVIADO"])["codigo"], "REGISTRAR_ENTREGA")
        self.assertEqual(status.proximo_passo(True, [S.FATURADO], ["NAO_ENVIADO"])["codigo"], "REENVIAR_EMAIL")
        self.assertEqual(status.proximo_passo(True, [S.ENTREGUE], ["ENVIADO"])["codigo"], "NENHUM")

    def test_etapas_concluidas(self):
        e = status.etapas(date(2026, 11, 3), True, [S.ENTREGUE, S.EMP_CANCELADO], ["ENVIADO"])
        self.assertTrue(all(x["estado"] == "concluida" for x in e))


class TestVigencia(unittest.TestCase):
    def test_meses(self):
        self.assertEqual(vigencia.calcular_fim(date(2026, 3, 10), "6_MESES"), date(2026, 9, 10))
        self.assertEqual(vigencia.calcular_fim(date(2026, 3, 10), "12_MESES"), date(2027, 3, 10))

    def test_fim_de_mes_igual_postgres(self):
        self.assertEqual(vigencia.somar_meses(date(2026, 8, 31), 6), date(2027, 2, 28))
        self.assertEqual(vigencia.somar_meses(date(2027, 8, 31), 6), date(2028, 2, 29))

    def test_imediato_e_personalizado(self):
        self.assertIsNone(vigencia.calcular_fim(date(2026, 1, 1), "IMEDIATO"))
        with self.assertRaises(ValueError):
            vigencia.calcular_fim(date(2026, 1, 1), "PERSONALIZADO")
        with self.assertRaises(ValueError):
            vigencia.calcular_fim(date(2026, 1, 10), "PERSONALIZADO", date(2026, 1, 1))
        self.assertEqual(vigencia.calcular_fim(date(2026, 1, 1), "PERSONALIZADO", date(2027, 6, 1)), date(2027, 6, 1))

    def test_status(self):
        h = date(2026, 11, 26)
        self.assertEqual(vigencia.status_vigencia("IMEDIATO", None, h), "IMEDIATO")
        self.assertEqual(vigencia.status_vigencia("6_MESES", date(2026, 11, 25), h), "ENCERRADO")
        self.assertEqual(vigencia.status_vigencia("6_MESES", date(2026, 12, 26), h), "VENCE_30_DIAS")
        self.assertEqual(vigencia.status_vigencia("6_MESES", date(2026, 12, 27), h), "ATIVO")


class TestEmail(unittest.TestCase):
    def test_textos(self):
        self.assertEqual(emailing.assunto_padrao("2310826", "121196/2026", "Consórcio X/SC"),
                         "Nota fiscal 2310826 — Empenho 121196/2026 — Consórcio X/SC")
        self.assertIn("nota fiscal 2310826, referente ao empenho 121196/2026", emailing.mensagem_padrao("2310826", "121196/2026"))
        self.assertEqual(emailing.brl(2288), "R$ 2.288,00")

    def test_html_escapa(self):
        h = emailing.montar_html("<script>x</script>", {"Nota fiscal": "1"},
                                 [{"codigo_pedido": "1", "descricao": "Pneu <b>", "quantidade": 2, "valor_unitario": 10}])
        self.assertNotIn("<script>", h)
        self.assertIn("R$ 20,00", h)


if __name__ == "__main__":
    unittest.main()
