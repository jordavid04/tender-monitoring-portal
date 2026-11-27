from __future__ import annotations

from datetime import date, time
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- Portal Licitações (existente)
class ItemIn(BaseModel):
    codigo_pedido: str = Field(min_length=1, max_length=60)
    descricao: str = Field(min_length=1, max_length=255)
    quantidade: int = Field(gt=0)
    valor_unitario: float = Field(ge=0)


class LicitacaoCreate(BaseModel):
    cnpj: str
    orgao: str = Field(min_length=1, max_length=255)
    uf: str = Field(min_length=2, max_length=2)
    situacao_financeira: Literal["REGULAR", "BLOQUEADO"] = "REGULAR"
    pregao: str
    empenho: str
    vendedor: str
    recebimento: date
    prazo_entrega: Optional[date] = None
    emails_responsaveis: List[str] = []
    dados_nota: Optional[str] = None
    observacoes: Optional[str] = None
    itens: List[ItemIn] = Field(min_length=1)


class LicitacaoUpdate(BaseModel):
    version: int                       # controle de concorrência: "outra pessoa alterou a licitação"
    cnpj: Optional[str] = None
    orgao: Optional[str] = None
    uf: Optional[str] = None
    situacao_financeira: Optional[Literal["REGULAR", "BLOQUEADO"]] = None
    pregao: Optional[str] = None
    empenho: Optional[str] = None
    vendedor: Optional[str] = None
    recebimento: Optional[date] = None
    prazo_entrega: Optional[date] = None
    emails_responsaveis: Optional[List[str]] = None
    dados_nota: Optional[str] = None
    observacoes: Optional[str] = None


class ItemUpdate(BaseModel):
    codigo_pedido: Optional[str] = None
    descricao: Optional[str] = None
    quantidade: Optional[int] = Field(default=None, gt=0)
    valor_unitario: Optional[float] = Field(default=None, ge=0)


class LancarIn(BaseModel):
    item_ids: List[int] = Field(min_length=1)
    op_numero: str
    ordem_remessa: Optional[str] = None
    codigo_produto_enviado: Optional[str] = None
    observacao: Optional[str] = None


class EntregarIn(BaseModel):
    item_ids: List[int] = Field(min_length=1)
    data_entrega: date
    observacao: Optional[str] = None


class AguardarEstoqueIn(BaseModel):
    motivo: Optional[str] = None


class TrocaMarcaIn(BaseModel):
    proposta_troca: str


class CancelarIn(BaseModel):
    motivo: str
    motivo_detalhe: Optional[str] = None


class CartaCorrecaoIn(BaseModel):
    carta_correcao_texto: str


class AnotarIn(BaseModel):
    anotacao: str = Field(min_length=1)


class ReabrirIn(BaseModel):
    motivo: str


class NfPreviewIn(BaseModel):
    numero: str
    data_faturamento: date
    item_ids: List[int] = Field(min_length=1)


class ReenvioIn(BaseModel):
    para: Optional[List[str]] = None
    assunto: Optional[str] = None
    mensagem: Optional[str] = None


# ---------------------------------------------------------------- ABA 1 - Pregões
Porte = Literal["AMPLA PARTICIPAÇÃO", "EXCLUSIVO ME/EPP", "COTA ME/EPP", "MISTO"]
SituacaoPregao = Literal["EM ANÁLISE", "CADASTRADO", "EM ANDAMENTO", "SUSPENSO", "VITÓRIA TOTAL", "VITÓRIA PARCIAL",
                         "DERROTA", "FRACASSADO/DESERTO", "REVOGADO/ANULADO", "EM RECURSO"]
StatusItemCotacao = Literal["EM_COTACAO", "EM_DISPUTA", "AGUARDANDO_HOMOLOGACAO", "REGISTRADO", "PERDIDO",
                            "DESCLASSIFICADO", "FRACASSADO", "EM_RECURSO"]


class PregaoIn(BaseModel):
    data_licitacao: date
    hora_licitacao: time
    numero_pregao: str = Field(min_length=1, max_length=80)
    modalidade: str = "ELETRÔNICO"
    empresa: str = "Empresa/SC"
    portal: str
    orgao_nome: str
    orgao_cnpj: Optional[str] = None
    uf: str = Field(min_length=2, max_length=2)
    porte: Porte
    situacao: SituacaoPregao = "EM ANDAMENTO"
    total_itens_edital: int = Field(gt=0)
    itens_disputados: int = Field(default=0, ge=0)
    vendedor: str
    observacoes: Optional[str] = None


class PregaoUpdate(BaseModel):
    data_licitacao: Optional[date] = None
    hora_licitacao: Optional[time] = None
    numero_pregao: Optional[str] = None
    modalidade: Optional[str] = None
    empresa: Optional[str] = None
    portal: Optional[str] = None
    orgao_nome: Optional[str] = None
    orgao_cnpj: Optional[str] = None
    uf: Optional[str] = Field(default=None, min_length=2, max_length=2)
    porte: Optional[Porte] = None
    situacao: Optional[SituacaoPregao] = None
    total_itens_edital: Optional[int] = Field(default=None, gt=0)
    itens_disputados: Optional[int] = Field(default=None, ge=0)
    vendedor: Optional[str] = None
    observacoes: Optional[str] = None


class CotacaoItemIn(BaseModel):
    numero_item: str
    sku: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    medida: Optional[str] = None
    descricao: Optional[str] = None
    categoria: Optional[str] = None
    quantidade: int = Field(gt=0)
    valor_unit_minimo: float = Field(default=0, ge=0)          # valor mínimo da empresa (unit.)
    status_item: StatusItemCotacao = "EM_COTACAO"
    observacoes: Optional[str] = None


class CotacaoLoteIn(BaseModel):
    itens: List[CotacaoItemIn] = Field(min_length=1)


class CotacaoItemUpdate(BaseModel):
    sku: Optional[str] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    medida: Optional[str] = None
    descricao: Optional[str] = None
    categoria: Optional[str] = None
    quantidade: Optional[int] = Field(default=None, gt=0)
    valor_unit_minimo: Optional[float] = Field(default=None, ge=0)
    status_item: Optional[StatusItemCotacao] = None
    observacoes: Optional[str] = None


class VencedorIn(BaseModel):
    vencedor_tipo: Literal["PROPRIA", "CONCORRENTE", "SEM_VENCEDOR"]
    vencedor_concorrente_id: Optional[UUID] = None
    valor_unit_vencedor: Optional[float] = Field(default=None, ge=0)


class ConcorrenteRapidoIn(BaseModel):
    nome_abreviado: str = Field(min_length=1)
    razao_social: str = Field(min_length=1)
    cnpj: str
    municipio: str = ""
    uf: str = Field(min_length=2, max_length=2)


# ---------------------------------------------------------------- ABA 2 - Atas e Contratos
class ContratoAtaIn(BaseModel):
    nome_contrato: str = Field(min_length=1, max_length=150)
    tipo_instrumento: Literal["ATA_REGISTRO_PRECO", "CONTRATO", "EMPENHO_DIRETO"] = "ATA_REGISTRO_PRECO"
    data_contrato: date
    tipo_vigencia: Literal["6_MESES", "12_MESES", "IMEDIATO", "PERSONALIZADO"]
    data_fim_vigencia: Optional[date] = None
    observacoes: Optional[str] = None
    cotacao_item_ids: List[UUID] = Field(min_length=1)   # somente itens REGISTRADO


class ContratoAtaUpdate(BaseModel):
    nome_contrato: Optional[str] = None
    tipo_instrumento: Optional[Literal["ATA_REGISTRO_PRECO", "CONTRATO", "EMPENHO_DIRETO"]] = None
    data_contrato: Optional[date] = None
    tipo_vigencia: Optional[Literal["6_MESES", "12_MESES", "IMEDIATO", "PERSONALIZADO"]] = None
    data_fim_vigencia: Optional[date] = None
    observacoes: Optional[str] = None


class AtaItemUpdate(BaseModel):
    qtde_registrada: Optional[int] = Field(default=None, gt=0)
    valor_unit_registrado: Optional[float] = Field(default=None, ge=0)
    valor_reequilibrio: Optional[float] = Field(default=None, ge=0)
    data_pedido_reequilibrio: Optional[date] = None
    status_reequilibrio: Optional[Literal["ENVIADO", "DEFERIDO", "INDEFERIDO", "DESISTENCIA"]] = None
    observacoes: Optional[str] = None


class VinculoIn(BaseModel):
    licitacao_item_ids: List[int] = Field(min_length=1)
