-- =============================================================================
-- 002 - NOVAS ABAS: CONTROLE DE PREGÕES DIÁRIOS (ABA 1) + ATAS E CONTRATOS (ABA 2)
-- =============================================================================
-- Seguro para produção: tudo é criado no schema ISOLADO "pregao_atas".
-- Nenhuma tabela existente é alterada. PostgreSQL 15+ / Supabase.
-- Origem: scripts do Gemini ("Fluxo e Scripts Pregões", Script 1), com as correções
-- listadas em docs/02_ABAS_ADICIONADAS_INTEGRACAO_RPA.md (seção "Correções").
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
-- (gen_random_uuid() é nativo no PostgreSQL 13+, não precisa de pgcrypto)

CREATE SCHEMA IF NOT EXISTS pregao_atas;
SET search_path = pregao_atas, public, extensions;

-- -----------------------------------------------------------------------------
-- 1. TABELAS MESTRAS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS produtos_catalogo (
    sku             VARCHAR(30) PRIMARY KEY,
    marca           VARCHAR(80)  NOT NULL,
    modelo          VARCHAR(120) NOT NULL,
    medida          VARCHAR(150),
    descricao_origem VARCHAR(255) NOT NULL,
    categoria       VARCHAR(50)  NOT NULL,   -- CARRO, CARGA, OTR, AGRICOLA, ATV/UTV, MOTO, CÂMARA, PROTETOR, RODA
    ativo           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orgaos_publicos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome        VARCHAR(255) NOT NULL,
    -- CNPJ alfanumérico: 12 posições [0-9A-Z] + 2 dígitos verificadores
    cnpj_clean  VARCHAR(14) UNIQUE CHECK (cnpj_clean ~ '^[0-9A-Z]{12}[0-9]{2}$'),
    municipio   VARCHAR(120),
    uf          CHAR(2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_orgaos_nome ON orgaos_publicos (UPPER(nome)) WHERE cnpj_clean IS NULL;

CREATE TABLE IF NOT EXISTS concorrentes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome_abreviado VARCHAR(150) NOT NULL,
    razao_social   VARCHAR(255) NOT NULL,
    cnpj_clean     VARCHAR(14)  NOT NULL UNIQUE CHECK (cnpj_clean ~ '^[0-9A-Z]{12}[0-9]{2}$'),
    municipio      VARCHAR(120),
    uf             CHAR(2) NOT NULL,
    data_chegada   TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- data/hora salvas automaticamente (substitui a coluna CHEGADA)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_concorrentes_busca ON concorrentes
    USING GIN ((nome_abreviado || ' ' || razao_social || ' ' || cnpj_clean) gin_trgm_ops);

-- -----------------------------------------------------------------------------
-- 2. ABA 1 - PREGÕES E DOCUMENTOS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pregoes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data_licitacao      DATE NOT NULL,
    hora_licitacao      TIME NOT NULL,
    numero_pregao       VARCHAR(80) NOT NULL,
    modalidade          VARCHAR(50) NOT NULL DEFAULT 'ELETRÔNICO',
    empresa             VARCHAR(50) NOT NULL DEFAULT 'Empresa/SC',
    portal              VARCHAR(100) NOT NULL,
    orgao_id            UUID REFERENCES orgaos_publicos(id),
    orgao_nome          VARCHAR(255) NOT NULL,
    orgao_cnpj          VARCHAR(14) CHECK (orgao_cnpj IS NULL OR orgao_cnpj ~ '^[0-9A-Z]{12}[0-9]{2}$'),
    uf                  CHAR(2) NOT NULL,
    porte               VARCHAR(40) NOT NULL CHECK (
                            porte IN ('AMPLA PARTICIPAÇÃO', 'EXCLUSIVO ME/EPP', 'COTA ME/EPP', 'MISTO')),
    situacao            VARCHAR(40) NOT NULL DEFAULT 'EM ANDAMENTO' CHECK (situacao IN (
                            'EM ANÁLISE', 'CADASTRADO', 'EM ANDAMENTO', 'SUSPENSO',
                            'VITÓRIA TOTAL', 'VITÓRIA PARCIAL', 'DERROTA',
                            'FRACASSADO/DESERTO', 'REVOGADO/ANULADO', 'EM RECURSO')),
    total_itens_edital  INTEGER NOT NULL CHECK (total_itens_edital > 0),
    itens_disputados    INTEGER NOT NULL DEFAULT 0 CHECK (itens_disputados >= 0),
    vendedor            VARCHAR(100) NOT NULL,
    observacoes         TEXT,
    criado_por          VARCHAR(100),
    atualizado_por      VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_disputados_menor_igual_edital CHECK (itens_disputados <= total_itens_edital),
    -- evita cadastro duplicado do mesmo pregão (e torna o ETL idempotente)
    CONSTRAINT uq_pregao_data_numero_orgao UNIQUE (data_licitacao, numero_pregao, orgao_nome)
);
CREATE INDEX IF NOT EXISTS idx_pregoes_data ON pregoes (data_licitacao DESC);
CREATE INDEX IF NOT EXISTS idx_pregoes_numero ON pregoes (numero_pregao);
CREATE INDEX IF NOT EXISTS idx_pregoes_vendedor ON pregoes (vendedor);

CREATE TABLE IF NOT EXISTS pregao_documentos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pregao_id     UUID NOT NULL REFERENCES pregoes(id) ON DELETE CASCADE,
    categoria     VARCHAR(60) NOT NULL CHECK (categoria IN (
                      'EDITAL', 'TERMO_REFERENCIA', 'PROPOSTA_INICIAL', 'PROPOSTA_AJUSTADA',
                      'HABILITACAO', 'ATA_SESSAO', 'RECURSO_IMPUGNACAO', 'OUTROS')),
    nome_arquivo  VARCHAR(255) NOT NULL,
    storage_path  TEXT NOT NULL,   -- ex.: pregoes/2026/SC/{pregao_id}/EDITAL/arquivo.pdf
    mime_type     VARCHAR(120),
    tamanho_bytes BIGINT,
    uploaded_by   VARCHAR(100),
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pregao_docs_pregao ON pregao_documentos (pregao_id);

-- -----------------------------------------------------------------------------
-- 3. SEÇÃO 1.1 - COTAÇÃO (ITENS EM DISPUTA)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cotacao_itens (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pregao_id                UUID NOT NULL REFERENCES pregoes(id) ON DELETE CASCADE,
    numero_item              VARCHAR(30) NOT NULL,
    sku                      VARCHAR(30) REFERENCES produtos_catalogo(sku),
    marca                    VARCHAR(80),
    modelo                   VARCHAR(120),
    medida                   VARCHAR(150),
    descricao                VARCHAR(255) NOT NULL,
    categoria                VARCHAR(50),
    quantidade               INTEGER NOT NULL CHECK (quantidade > 0),
    -- valor_unit_minimo = MENOR preço unitário que a empresa aceita praticar neste item ("valor mínimo da empresa")
    valor_unit_minimo        NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (valor_unit_minimo >= 0),
    valor_total_minimo       NUMERIC(16,2) GENERATED ALWAYS AS (quantidade * valor_unit_minimo) STORED,
    -- valor_unit_vencedor = preço unitário que VENCEU o item (da empresa, quando ganhou; do concorrente, quando perdeu)
    valor_unit_vencedor      NUMERIC(14,2) CHECK (valor_unit_vencedor IS NULL OR valor_unit_vencedor >= 0),
    valor_total_vencedor     NUMERIC(16,2) GENERATED ALWAYS AS (quantidade * COALESCE(valor_unit_vencedor, 0)) STORED,
    vencedor_tipo            VARCHAR(20) CHECK (vencedor_tipo IN ('PROPRIA', 'CONCORRENTE', 'SEM_VENCEDOR')),
    vencedor_concorrente_id  UUID REFERENCES concorrentes(id),
    status_item              VARCHAR(30) NOT NULL DEFAULT 'EM_COTACAO' CHECK (status_item IN (
                                 'EM_COTACAO', 'EM_DISPUTA', 'AGUARDANDO_HOMOLOGACAO',
                                 'REGISTRADO', 'PERDIDO', 'DESCLASSIFICADO',
                                 'FRACASSADO', 'EM_RECURSO')),
    observacoes              TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pregao_id, numero_item),
    -- vencedor concorrente exige o concorrente selecionado/cadastrado
    CONSTRAINT chk_vencedor_concorrente CHECK (
        vencedor_tipo IS DISTINCT FROM 'CONCORRENTE' OR vencedor_concorrente_id IS NOT NULL),
    -- vitória da empresa exige o valor unitário vencedor (é ele que vira o preço da Ata/Contrato)
    CONSTRAINT chk_vencedor_cpx_valor CHECK (
        vencedor_tipo IS DISTINCT FROM 'PROPRIA' OR valor_unit_vencedor IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_cotacao_pregao ON cotacao_itens (pregao_id);
CREATE INDEX IF NOT EXISTS idx_cotacao_sku ON cotacao_itens (sku);

-- -----------------------------------------------------------------------------
-- 4. SEÇÃO 1.2 - ATAS E CONTRATOS (1:N POR PREGÃO + MÚLTIPLOS ANEXOS)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contratos_atas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pregao_id        UUID NOT NULL REFERENCES pregoes(id) ON DELETE CASCADE,
    nome_contrato    VARCHAR(150) NOT NULL,
    tipo_instrumento VARCHAR(40) NOT NULL DEFAULT 'ATA_REGISTRO_PRECO' CHECK (
                         tipo_instrumento IN ('ATA_REGISTRO_PRECO', 'CONTRATO', 'EMPENHO_DIRETO')),
    data_contrato    DATE NOT NULL,
    tipo_vigencia    VARCHAR(20) NOT NULL CHECK (
                         tipo_vigencia IN ('6_MESES', '12_MESES', 'IMEDIATO', 'PERSONALIZADO')),
    data_fim_vigencia DATE,   -- calculada por trigger para 6/12 meses; NULL para IMEDIATO
    observacoes      TEXT,
    criado_por       VARCHAR(100),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_fim_apos_inicio CHECK (data_fim_vigencia IS NULL OR data_fim_vigencia >= data_contrato)
);
CREATE INDEX IF NOT EXISTS idx_contratos_pregao ON contratos_atas (pregao_id);
CREATE INDEX IF NOT EXISTS idx_contratos_fim ON contratos_atas (data_fim_vigencia);

CREATE TABLE IF NOT EXISTS contrato_documentos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_ata_id UUID NOT NULL REFERENCES contratos_atas(id) ON DELETE CASCADE,
    -- A lista do script original veio truncada no PDF; completada aqui (ver doc, seção "Pontos a validar").
    categoria       VARCHAR(60) NOT NULL DEFAULT 'CONTRATO_ATA' CHECK (categoria IN (
                        'CONTRATO_ATA', 'ADITIVO_PRAZO', 'ADITIVO_QUANTIDADE',
                        'REEQUILIBRIO', 'EMPENHO', 'OUTROS')),
    nome_arquivo    VARCHAR(255) NOT NULL,
    storage_path    TEXT NOT NULL,
    mime_type       VARCHAR(120),
    tamanho_bytes   BIGINT,
    uploaded_by     VARCHAR(100),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contrato_docs ON contrato_documentos (contrato_ata_id);

CREATE TABLE IF NOT EXISTS ata_itens (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contrato_ata_id         UUID NOT NULL REFERENCES contratos_atas(id) ON DELETE CASCADE,
    cotacao_item_id         UUID NOT NULL UNIQUE REFERENCES cotacao_itens(id) ON DELETE RESTRICT,
    numero_item             VARCHAR(30) NOT NULL,
    sku                     VARCHAR(30) REFERENCES produtos_catalogo(sku),
    descricao               VARCHAR(255) NOT NULL,
    categoria               VARCHAR(50),
    qtde_registrada         INTEGER NOT NULL CHECK (qtde_registrada > 0),
    valor_unit_registrado   NUMERIC(14,2) NOT NULL CHECK (valor_unit_registrado >= 0),
    valor_total_registrado  NUMERIC(16,2) GENERATED ALWAYS AS (qtde_registrada * valor_unit_registrado) STORED,
    valor_reequilibrio      NUMERIC(14,2) CHECK (valor_reequilibrio IS NULL OR valor_reequilibrio >= 0),
    data_pedido_reequilibrio DATE,
    status_reequilibrio     VARCHAR(30) CHECK (
                                status_reequilibrio IN ('ENVIADO', 'DEFERIDO', 'INDEFERIDO', 'DESISTENCIA')),
    observacoes             TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ata_itens_contrato ON ata_itens (contrato_ata_id);
CREATE INDEX IF NOT EXISTS idx_ata_itens_sku ON ata_itens (sku);

-- -----------------------------------------------------------------------------
-- 5. CONSUMO / ENTREGAS DA PLANILHA LEGADA (histórico importado via ETL)
--    Os pedidos NOVOS vêm do Portal Licitações via vínculo (migração 004).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consumo_entregas (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ata_item_id      UUID REFERENCES ata_itens(id) ON DELETE SET NULL,
    pregao_ref       VARCHAR(80),
    empenho_pedido_af VARCHAR(100) NOT NULL,
    status_entrega   VARCHAR(40) NOT NULL CHECK (status_entrega IN (
                         'CHEGADA', 'AG_ESTOQUE', 'TROCA_DE_MARCA', 'LANCADO_NO_SISTEMA',
                         'FATURADO', 'ENTREGUE', 'CARTA_DE_CORRECAO',
                         'EMP_CANCELADO', 'FATURADO_DUPLICADO')),
    data_recebimento DATE,
    prazo_entrega    DATE,
    sku_pedido       VARCHAR(30),
    sku_enviado      VARCHAR(30),   -- preenchido em caso de troca de marca aprovada
    quantidade       INTEGER NOT NULL CHECK (quantidade > 0),
    valor_unitario   NUMERIC(14,2) NOT NULL,
    valor_total      NUMERIC(16,2) GENERATED ALWAYS AS (quantidade * valor_unitario) STORED,
    op_numero        VARCHAR(60),
    ordem_remessa    VARCHAR(80),
    nf_numero        VARCHAR(60),
    data_faturamento DATE,
    data_entrega     DATE,
    observacoes      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_consumo_ata_item ON consumo_entregas (ata_item_id);

-- -----------------------------------------------------------------------------
-- 6. AUDITORIA DAS NOVAS ABAS (append-only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pregao_auditoria (
    id          BIGSERIAL PRIMARY KEY,
    entidade    VARCHAR(40) NOT NULL,   -- PREGAO, COTACAO_ITEM, ATA, ATA_ITEM, DOCUMENTO, CONCORRENTE, VINCULO
    entidade_id TEXT NOT NULL,
    acao        VARCHAR(40) NOT NULL,
    usuario     VARCHAR(100) NOT NULL,
    detalhe     JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pregao_aud ON pregao_auditoria (entidade, entidade_id, created_at DESC);

-- -----------------------------------------------------------------------------
-- 7. TRIGGERS DE INTEGRIDADE E REGRAS DE NEGÓCIO
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_touch_updated_at() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = pregao_atas, public AS $$
BEGIN NEW.updated_at := NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_pregoes_touch ON pregoes;
CREATE TRIGGER trg_pregoes_touch BEFORE UPDATE ON pregoes
FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();
DROP TRIGGER IF EXISTS trg_cotacao_touch ON cotacao_itens;
CREATE TRIGGER trg_cotacao_touch BEFORE UPDATE ON cotacao_itens
FOR EACH ROW EXECUTE FUNCTION fn_touch_updated_at();

-- Regra 1: somente itens com status REGISTRADO podem ser vinculados a uma Ata/Contrato
CREATE OR REPLACE FUNCTION fn_validar_item_registrado() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = pregao_atas, public AS $$
DECLARE
    v_status VARCHAR(30);
    v_pregao_item UUID;
    v_pregao_ata  UUID;
BEGIN
    SELECT status_item, pregao_id INTO v_status, v_pregao_item
      FROM cotacao_itens WHERE id = NEW.cotacao_item_id;

    IF v_status IS DISTINCT FROM 'REGISTRADO' THEN
        RAISE EXCEPTION 'Operação bloqueada: o item de cotação % possui status "%" e precisa estar como "REGISTRADO".',
            NEW.cotacao_item_id, COALESCE(v_status, 'INEXISTENTE');
    END IF;

    -- o item precisa pertencer ao MESMO pregão da ata/contrato
    SELECT pregao_id INTO v_pregao_ata FROM contratos_atas WHERE id = NEW.contrato_ata_id;
    IF v_pregao_ata IS DISTINCT FROM v_pregao_item THEN
        RAISE EXCEPTION 'Operação bloqueada: o item de cotação % pertence a outro pregão.', NEW.cotacao_item_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validar_item_registrado ON ata_itens;
CREATE TRIGGER trg_validar_item_registrado
BEFORE INSERT OR UPDATE OF cotacao_item_id, contrato_ata_id ON ata_itens
FOR EACH ROW EXECUTE FUNCTION fn_validar_item_registrado();

-- Regra 1b (novo): um item já vinculado a uma ata não pode "desregistrar"
CREATE OR REPLACE FUNCTION fn_bloquear_desregistro() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = pregao_atas, public AS $$
BEGIN
    IF OLD.status_item = 'REGISTRADO' AND NEW.status_item <> 'REGISTRADO'
       AND EXISTS (SELECT 1 FROM ata_itens WHERE cotacao_item_id = OLD.id) THEN
        RAISE EXCEPTION 'O item % já compõe uma Ata/Contrato; remova-o da ata antes de alterar o status.', OLD.numero_item;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_bloquear_desregistro ON cotacao_itens;
CREATE TRIGGER trg_bloquear_desregistro BEFORE UPDATE OF status_item ON cotacao_itens
FOR EACH ROW EXECUTE FUNCTION fn_bloquear_desregistro();

-- Regra 2: cálculo automático do fim da vigência (6 meses, 12 meses ou imediato)
CREATE OR REPLACE FUNCTION fn_calcular_vigencia_ata() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = pregao_atas, public AS $$
BEGIN
    IF NEW.tipo_vigencia = '6_MESES' THEN
        NEW.data_fim_vigencia := (NEW.data_contrato + INTERVAL '6 months')::DATE;
    ELSIF NEW.tipo_vigencia = '12_MESES' THEN
        NEW.data_fim_vigencia := (NEW.data_contrato + INTERVAL '12 months')::DATE;
    ELSIF NEW.tipo_vigencia = 'IMEDIATO' THEN
        NEW.data_fim_vigencia := NULL;
    ELSIF NEW.tipo_vigencia = 'PERSONALIZADO' AND NEW.data_fim_vigencia IS NULL THEN
        RAISE EXCEPTION 'Para vigência PERSONALIZADO/ADITIVO é obrigatório informar data_fim_vigencia.';
    END IF;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_calcular_vigencia_ata ON contratos_atas;
CREATE TRIGGER trg_calcular_vigencia_ata BEFORE INSERT OR UPDATE ON contratos_atas
FOR EACH ROW EXECUTE FUNCTION fn_calcular_vigencia_ata();

-- -----------------------------------------------------------------------------
-- 8. FUNÇÕES RPC: BUSCA INTELIGENTE E CADASTRO RÁPIDO DE CONCORRENTES
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION buscar_concorrentes(p_termo TEXT)
RETURNS TABLE (id UUID, nome_abreviado VARCHAR, razao_social VARCHAR,
               cnpj_clean VARCHAR, municipio VARCHAR, uf CHAR(2))
LANGUAGE plpgsql STABLE SET search_path = pregao_atas, public, extensions AS $$
DECLARE
    -- CNPJ alfanumérico: mantém letras e números
    v_alnum TEXT := UPPER(regexp_replace(COALESCE(p_termo, ''), '[^0-9A-Za-z]', '', 'g'));
BEGIN
    RETURN QUERY
    SELECT c.id, c.nome_abreviado, c.razao_social, c.cnpj_clean, c.municipio, c.uf
      FROM concorrentes c
     WHERE unaccent(c.nome_abreviado) ILIKE '%' || unaccent(p_termo) || '%'
        OR unaccent(c.razao_social)   ILIKE '%' || unaccent(p_termo) || '%'
        -- só busca por CNPJ se o termo parecer um CNPJ (>=4 caracteres e ao menos 1 dígito)
        OR (length(v_alnum) >= 4 AND v_alnum ~ '[0-9]' AND c.cnpj_clean LIKE '%' || v_alnum || '%')
     ORDER BY CASE WHEN c.cnpj_clean = v_alnum THEN 0 ELSE 1 END,
              similarity(unaccent(c.nome_abreviado), unaccent(p_termo)) DESC
     LIMIT 20;
END;
$$;

CREATE OR REPLACE FUNCTION cadastrar_concorrente_rapido(
    p_nome_abreviado TEXT, p_razao_social TEXT, p_cnpj TEXT, p_municipio TEXT, p_uf TEXT)
RETURNS concorrentes
LANGUAGE plpgsql SET search_path = pregao_atas, public AS $$
DECLARE
    v_cnpj_clean TEXT := UPPER(regexp_replace(COALESCE(p_cnpj, ''), '[^0-9A-Za-z]', '', 'g'));
    v_registro   concorrentes;
BEGIN
    IF v_cnpj_clean !~ '^[0-9A-Z]{12}[0-9]{2}$' THEN
        RAISE EXCEPTION 'CNPJ inválido: informe 14 caracteres (12 letras/números + 2 dígitos verificadores).';
    END IF;

    INSERT INTO concorrentes (nome_abreviado, razao_social, cnpj_clean, municipio, uf, data_chegada)
    VALUES (UPPER(TRIM(p_nome_abreviado)), UPPER(TRIM(p_razao_social)), v_cnpj_clean,
            NULLIF(TRIM(p_municipio), ''), UPPER(TRIM(p_uf)), NOW())
    ON CONFLICT (cnpj_clean) DO UPDATE
        SET municipio = COALESCE(NULLIF(TRIM(EXCLUDED.municipio), ''), concorrentes.municipio)
    RETURNING * INTO v_registro;

    RETURN v_registro;
END;
$$;
