"""Geração de planilhas SEM dependências: XLSX escrito à mão (zip + XML) e CSV (UTF-8 com BOM, separador ';' — abre direto no Excel pt-BR)."""
from __future__ import annotations

import csv
import datetime as _dt
import decimal
import io
import re
import uuid
import zipfile
from urllib.parse import quote
from xml.sax.saxutils import escape

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV = "text/csv; charset=utf-8"
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def nome_arquivo(titulo: str, ext: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", titulo).strip("_") or "planilha"
    return f"{base}.{ext}"


def _letra(n: int) -> str:  # 1 -> A
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _celula(ref: str, v, estilo_texto: int = 0) -> str:
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        v = "Sim" if v else "Não"
    if isinstance(v, (int, float)):
        return f'<c r="{ref}" s="{2 if isinstance(v, float) else 0}"><v>{v!r}</v></c>'
    t = escape(_CTRL.sub("", str(v)))
    return f'<c r="{ref}" t="inlineStr" s="{estilo_texto}"><is><t xml:space="preserve">{t}</t></is></c>'


def _xlsx(titulo: str, cab: list, linhas: list) -> bytes:
    nome = re.sub(r"[\\/*?:\[\]]", " ", titulo)[:31].strip() or "Planilha"
    largura = [min(max([len(str(cab[i]))] + [len(str(l[i])) for l in linhas if i < len(l) and l[i] is not None]) + 3, 55) for i in range(len(cab))]
    cols = "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(largura, 1))
    rows = ['<row r="1" ht="22" customHeight="1">' + "".join(_celula(f"{_letra(i)}1", c, 1) for i, c in enumerate(cab, 1)) + "</row>"]
    for r, l in enumerate(linhas, 2):
        rows.append(f'<row r="{r}">' + "".join(_celula(f"{_letra(i)}{r}", v) for i, v in enumerate(l, 1)) + "</row>")
    fim = f"{_letra(len(cab))}{len(linhas) + 1}"
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
             f'<cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData><autoFilter ref="A1:{fim}"/></worksheet>')
    estilos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>'
               '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
               '<fill><patternFill patternType="solid"><fgColor rgb="FF4E008E"/><bgColor indexed="64"/></patternFill></fill></fills>'
               '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
               '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
               '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
               '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
               '<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
               '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    ns = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
    arquivos = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                               '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships {ns}><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                           f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape(nome)}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships {ns}>'
                                      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                                      '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": estilos, "xl/worksheets/sheet1.xml": sheet}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in arquivos.items():
            z.writestr(n, c)
    return buf.getvalue()


def _norm(v):
    """Tipos vindos do banco -> tipos simples (Decimal->float, datas dd/mm/aaaa, hora HH:MM, UUID->str)."""
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, _dt.datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, _dt.date):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, _dt.time):
        return v.strftime("%H:%M")
    if isinstance(v, uuid.UUID):
        return str(v)
    return v


def gerar(titulo: str, cabecalho: list, linhas: list, formato: str = "xlsx"):
    """Retorna (bytes, mime, extensão). Formatos: xlsx | csv."""
    linhas = [[_norm(v) for v in l] for l in linhas]
    if formato == "xlsx":
        return _xlsx(titulo, cabecalho, linhas), XLSX, "xlsx"
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(cabecalho)
    for l in linhas:
        w.writerow(["" if v is None else (str(v).replace(".", ",") if isinstance(v, float) else v) for v in l])
    return ("﻿" + buf.getvalue()).encode("utf-8"), CSV, "csv"


def resposta(titulo: str, cabecalho: list, linhas: list, formato: str = "xlsx"):
    """Resposta HTTP (download) para os endpoints /exportar."""
    from fastapi.responses import Response
    corpo, mime, ext = gerar(titulo, cabecalho, linhas, formato)
    return Response(corpo, media_type=mime, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome_arquivo(titulo, ext))}"})
