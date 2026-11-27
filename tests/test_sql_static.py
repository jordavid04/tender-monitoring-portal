"""Checagem estática (sem banco): parênteses balanceados, $$ pareados e coerência de enums SQL x Python."""
import re, unittest
from pathlib import Path

from app.domain.status import ItemStatus
from app.domain.vigencia import TIPOS_VIGENCIA

MIG = Path(__file__).resolve().parents[1] / "db" / "migrations"


def sem_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


class TestSqlStatic(unittest.TestCase):
    def test_balanceamento(self):
        for f in sorted(MIG.glob("*.sql")):
            s = sem_comentarios(f.read_text(encoding="utf-8"))
            self.assertEqual(s.count("$$") % 2, 0, f"$$ ímpar em {f.name}")
            corpo = re.sub(r"\$\$.*?\$\$", "", s, flags=re.S)           # ignora corpo das funções
            corpo = re.sub(r"'(?:[^']|'')*'", "''", corpo)                # ignora literais
            self.assertEqual(corpo.count("("), corpo.count(")"), f"parênteses em {f.name}")

    def test_status_item_sql_igual_ao_enum_python(self):
        s = (MIG / "001_base_licitacoes.sql").read_text(encoding="utf-8")
        bloco = re.search(r"status\s+VARCHAR\(20\).*?CHECK \(status IN \((.*?)\)\)", s, re.S).group(1)
        self.assertEqual(set(re.findall(r"'([A-Z_]+)'", bloco)), {e.value for e in ItemStatus})

    def test_vigencia_sql_igual_ao_python(self):
        s = (MIG / "002_pregoes_atas.sql").read_text(encoding="utf-8")
        bloco = re.search(r"tipo_vigencia\s+VARCHAR\(20\) NOT NULL CHECK \(\s*tipo_vigencia IN \((.*?)\)", s, re.S).group(1)
        self.assertEqual(set(re.findall(r"'([A-Z0-9_]+)'", bloco)), set(TIPOS_VIGENCIA))

    def test_view_resumo_usa_mesmos_pendentes(self):
        s = (MIG / "001_base_licitacoes.sql").read_text(encoding="utf-8")
        from app.domain.status import PENDENTES
        s = s[s.index("CREATE OR REPLACE VIEW vw_licitacoes_resumo"):]
        m = re.search(r"IN\s*\(\s*'EMP_RECEBIDO'(.*?)\)\) > 0 THEN 'ANDAMENTO'", s, re.S)
        sql_set = set(re.findall(r"'([A-Z_]+)'", "'EMP_RECEBIDO'" + m.group(1)))
        self.assertEqual(sql_set, {p.value for p in PENDENTES})

    def test_migracoes_de_producao_nao_alteram_tabelas_existentes(self):
        for nome in ("002_pregoes_atas.sql", "003_views_pregoes_atas.sql", "004_vinculo_portal_licitacoes.sql"):
            s = sem_comentarios((MIG / nome).read_text(encoding="utf-8"))
            self.assertNotRegex(s, r"(?i)ALTER\s+TABLE\s+(?!pregao_atas)", nome)
            self.assertNotRegex(s, r"(?i)DROP\s+TABLE", nome)


if __name__ == "__main__":
    unittest.main()
