-- =============================================================================
-- 001 - BASE DO PORTAL LICITAÇÕES (RECONSTRUÍDA A PARTIR DO "GUIA DE USO")
-- =============================================================================
-- ATENÇÃO: este arquivo reconstrói o módulo que JÁ EXISTE em produção.
-- Serve para ambientes de DEV/STAGING e como referência de regras.
-- NÃO EXECUTAR EM PRODUÇÃO. Em produção aplique apenas 002, 003 e 004.
-- PostgreSQL 15+
-- =============================================================================

-- Código sequencial por ano: LIC-2026-000001
CREATE TABLE IF NOT EXISTS licitacao_codigo_seq (
    ano     INTEGER PRIMARY KEY,
    ultimo  INTEGER NOT NULL DEFAULT 0
);

CREATE OR REPLACE FUNCTION fn_proximo_codigo_licitacao() RETURNS TEXT AS $$
DECLARE
    v_ano INTEGER := EXTRACT(YEAR FROM NOW())::INTEGER;
    v_n   INTEGER;
BEGIN
    INSERT INTO licitacao_codigo_seq (ano, ultimo) VALUES (v_ano, 1)
    ON CONFLICT (ano) DO UPDATE SET ultimo = licitacao_codigo_seq.ultimo + 1
    RETURNING ultimo INTO v_n;
    RETURN 'LIC-' || v_ano || '-' || LPAD(v_n::TEXT, 6, '0');
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS licitacoes (
    id                   BIGSERIAL PRIMARY KEY,
    codigo               VARCHAR(20) NOT NULL UNIQUE DEFAULT fn_proximo_codigo_licitacao(),
    -- CNPJ alfanumérico (vigente desde jul/2026): 12 posições [0-9A-Z] + 2 dígitos verificadores
    cnpj                 VARCHAR(14) NOT NULL CHECK (cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$'),
    orgao                VARCHAR(255) NOT NULL,
    uf                   CHAR(2) NOT NULL,
    situacao_financeira  VARCHAR(12) NOT NULL DEFAULT 'REGULAR'
                         CHECK (situacao_financeira IN ('REGULAR', 'BLOQUEADO')),  -- antiga coluna INADIMPLÊNCIA (só aviso)
    pregao               VARCHAR(80) NOT NULL,
    empenho              VARCHAR(80) NOT NULL,
    vendedor             VARCHAR(100) NOT NULL,
    recebimento          DATE NOT NULL,
    prazo_entrega        DATE,
    emails_responsaveis  TEXT[] NOT NULL DEFAULT '{}',
    dados_nota           TEXT,          -- antiga coluna OBS NOTA
    observacoes          TEXT,
    version              INTEGER NOT NULL DEFAULT 1,   -- controle otimista de concorrência
    criado_por           VARCHAR(100) NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_prazo_apos_recebimento CHECK (prazo_entrega IS NULL OR prazo_entrega >= recebimento)
);
CREATE INDEX IF NOT EXISTS idx_licitacoes_cnpj ON licitacoes (cnpj, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_licitacoes_prazo ON licitacoes (prazo_entrega);

CREATE TABLE IF NOT EXISTS licitacao_itens (
    id                      BIGSERIAL PRIMARY KEY,
    licitacao_id            BIGINT NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    codigo_pedido           VARCHAR(60) NOT NULL,          -- "ID PEDIDO"
    descricao               VARCHAR(255) NOT NULL,
    quantidade              INTEGER NOT NULL CHECK (quantidade > 0),
    valor_unitario          NUMERIC(14,2) NOT NULL CHECK (valor_unitario >= 0),
    valor_total             NUMERIC(16,2) GENERATED ALWAYS AS (quantidade * valor_unitario) STORED,
    status                  VARCHAR(20) NOT NULL DEFAULT 'EMP_RECEBIDO' CHECK (status IN (
                                'EMP_RECEBIDO','AG_ESTOQUE','TROCA_MARCA','LANCADO_SISTEMA',
                                'FATURADO','CARTA_CORRECAO','ENTREGUE','EMP_CANCELADO')),
    status_anterior         VARCHAR(20),                   -- usado na reabertura (admin)
    op_numero               VARCHAR(60),
    ordem_remessa           VARCHAR(80),
    codigo_produto_enviado  VARCHAR(60),                   -- só se diferente do empenhado
    proposta_troca          TEXT,
    motivo                  TEXT,                          -- OP perdida / cancelamento
    carta_correcao_texto    TEXT,
    data_entrega            DATE,
    anotacao                TEXT,                          -- anotação atual (as antigas ficam no histórico)
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_litens_licitacao ON licitacao_itens (licitacao_id);
CREATE INDEX IF NOT EXISTS idx_litens_status ON licitacao_itens (status);
CREATE INDEX IF NOT EXISTS idx_litens_op ON licitacao_itens (op_numero);

CREATE TABLE IF NOT EXISTS licitacao_documentos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    licitacao_id  BIGINT NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    tipo          VARCHAR(20) NOT NULL CHECK (tipo IN ('CONFIRMACAO', 'NF')),
    nome_arquivo  VARCHAR(255) NOT NULL,
    mime_type     VARCHAR(120) NOT NULL,
    tamanho_bytes BIGINT NOT NULL,
    storage_path  TEXT NOT NULL,
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,           -- "Substituir" desativa o anterior
    enviado_por   VARCHAR(100) NOT NULL,
    enviado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ldocs_licitacao ON licitacao_documentos (licitacao_id, tipo);

CREATE TABLE IF NOT EXISTS notas_fiscais (
    id                     BIGSERIAL PRIMARY KEY,
    licitacao_id           BIGINT NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    numero                 VARCHAR(60) NOT NULL,
    data_faturamento       DATE NOT NULL,
    previsao_entrega       DATE,
    valor                  NUMERIC(16,2) NOT NULL,
    documento_id           UUID REFERENCES licitacao_documentos(id),
    email_status           VARCHAR(15) NOT NULL DEFAULT 'PENDENTE'
                           CHECK (email_status IN ('ENVIADO', 'PENDENTE', 'NAO_ENVIADO')),
    email_para             TEXT[] NOT NULL DEFAULT '{}',
    email_assunto          TEXT,
    email_mensagem         TEXT,
    email_erro             TEXT,
    email_enviado_em       TIMESTAMPTZ,
    email_ultima_tentativa TIMESTAMPTZ,
    registrada_por         VARCHAR(100) NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_nf_numero_por_licitacao UNIQUE (licitacao_id, numero)   -- NF não repete na licitação
);

CREATE TABLE IF NOT EXISTS nota_itens (
    nota_id  BIGINT NOT NULL REFERENCES notas_fiscais(id) ON DELETE CASCADE,
    item_id  BIGINT NOT NULL REFERENCES licitacao_itens(id) ON DELETE CASCADE,
    PRIMARY KEY (nota_id, item_id)
);

-- Histórico imutável: "Ninguém consegue editar o histórico."
CREATE TABLE IF NOT EXISTS historico (
    id            BIGSERIAL PRIMARY KEY,
    licitacao_id  BIGINT NOT NULL REFERENCES licitacoes(id) ON DELETE CASCADE,
    item_id       BIGINT,
    acao          VARCHAR(40) NOT NULL,
    descricao     TEXT NOT NULL,
    usuario       VARCHAR(100) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_historico_licitacao ON historico (licitacao_id, created_at DESC);

CREATE OR REPLACE FUNCTION fn_historico_imutavel() RETURNS TRIGGER AS $$
BEGIN
    -- Permite a remoção em cascata quando a licitação inteira é apagada (uso administrativo/DEV).
    IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM licitacoes WHERE id = OLD.licitacao_id) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'O histórico é imutável (operação % bloqueada).', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_historico_imutavel ON historico;
CREATE TRIGGER trg_historico_imutavel BEFORE UPDATE OR DELETE ON historico
FOR EACH ROW EXECUTE FUNCTION fn_historico_imutavel();

-- updated_at automático
CREATE OR REPLACE FUNCTION fn_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at := NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_licitacoes_touch ON licitacoes;
CREATE TRIGGER trg_licitacoes_touch BEFORE UPDATE ON licitacoes
FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();
DROP TRIGGER IF EXISTS trg_litens_touch ON licitacao_itens;
CREATE TRIGGER trg_litens_touch BEFORE UPDATE ON licitacao_itens
FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

-- Resumo por licitação: situação calculada a partir dos itens (mesma regra de app/domain/status.py)
CREATE OR REPLACE VIEW vw_licitacoes_resumo AS
SELECT
    l.id, l.codigo, l.cnpj, l.orgao, l.uf, l.pregao, l.empenho, l.vendedor,
    l.recebimento, l.prazo_entrega, l.situacao_financeira, l.emails_responsaveis, l.version,
    COUNT(i.id)                                                        AS itens_total,
    COUNT(i.id) FILTER (WHERE i.status <> 'EMP_CANCELADO')             AS itens_ativos,
    COALESCE(SUM(i.valor_total) FILTER (WHERE i.status <> 'EMP_CANCELADO'), 0) AS valor,
    COALESCE(ARRAY_AGG(DISTINCT i.status) FILTER (WHERE i.id IS NOT NULL), '{}') AS status_itens,
    CASE
        WHEN COUNT(i.id) = 0 THEN 'ANDAMENTO'
        WHEN COUNT(i.id) FILTER (WHERE i.status = 'EMP_CANCELADO') = COUNT(i.id) THEN 'CANCELADA'
        WHEN COUNT(i.id) FILTER (WHERE i.status IN
             ('EMP_RECEBIDO','AG_ESTOQUE','TROCA_MARCA','LANCADO_SISTEMA','CARTA_CORRECAO')) > 0 THEN 'ANDAMENTO'
        WHEN COUNT(i.id) FILTER (WHERE i.status = 'FATURADO') > 0 THEN 'FATURADA'
        ELSE 'CONCLUIDA'
    END                                                                AS situacao,
    EXISTS (SELECT 1 FROM licitacao_documentos d
             WHERE d.licitacao_id = l.id AND d.tipo = 'CONFIRMACAO' AND d.ativo) AS tem_confirmacao,
    (SELECT COUNT(*) FROM notas_fiscais n WHERE n.licitacao_id = l.id) AS qtd_nf
FROM licitacoes l
LEFT JOIN licitacao_itens i ON i.licitacao_id = l.id
GROUP BY l.id;
