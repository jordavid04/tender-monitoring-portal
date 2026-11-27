-- =============================================================================
-- 004 - INTEGRAÇÃO ABA ATAS <-> PORTAL LICITAÇÕES (consumo automático)
-- =============================================================================
-- Cria uma tabela de VÍNCULO entre o item de ata e o item do Portal Licitações.
-- NÃO altera nenhuma tabela existente do portal em produção.
--
-- >>> AJUSTE ANTES DE RODAR EM PRODUÇÃO <<<
--   public.licitacao_itens(id)      -> confirme o NOME da tabela e o TIPO do id (BIGINT aqui)
--   colunas usadas na view abaixo   -> quantidade, valor_total, status
--   valores de status               -> EMP_RECEBIDO, AG_ESTOQUE, TROCA_MARCA, LANCADO_SISTEMA,
--                                      FATURADO, CARTA_CORRECAO, ENTREGUE, EMP_CANCELADO
-- Se os nomes/valores diferirem, edite SOMENTE este arquivo.
-- =============================================================================
SET search_path = pregao_atas, public, extensions;

CREATE TABLE IF NOT EXISTS vinculo_ata_licitacao_item (
    licitacao_item_id BIGINT PRIMARY KEY REFERENCES public.licitacao_itens(id) ON DELETE CASCADE,
    ata_item_id       UUID   NOT NULL REFERENCES ata_itens(id) ON DELETE RESTRICT,
    vinculado_por     VARCHAR(100) NOT NULL,
    vinculado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vinculo_ata_item ON vinculo_ata_licitacao_item (ata_item_id);

-- Mesma lista de colunas/tipos da view criada na 003 (exigência do CREATE OR REPLACE VIEW).
CREATE OR REPLACE VIEW vw_consumo_unificado AS
SELECT ce.id::TEXT                       AS ref,
       'PLANILHA'::TEXT                  AS origem,
       ce.ata_item_id                    AS ata_item_id,
       ce.status_entrega::TEXT           AS status_entrega,
       ce.quantidade::INTEGER            AS quantidade,
       ce.valor_total::NUMERIC(16,2)     AS valor_total
  FROM consumo_entregas ce
 WHERE ce.ata_item_id IS NOT NULL
UNION ALL
SELECT ('li:' || li.id::TEXT)::TEXT      AS ref,
       'PORTAL'::TEXT                    AS origem,
       v.ata_item_id                     AS ata_item_id,
       (CASE li.status
            WHEN 'EMP_RECEBIDO'    THEN 'CHEGADA'
            WHEN 'TROCA_MARCA'     THEN 'TROCA_DE_MARCA'
            WHEN 'LANCADO_SISTEMA' THEN 'LANCADO_NO_SISTEMA'
            WHEN 'CARTA_CORRECAO'  THEN 'CARTA_DE_CORRECAO'
            ELSE li.status
        END)::TEXT                       AS status_entrega,
       li.quantidade::INTEGER            AS quantidade,
       li.valor_total::NUMERIC(16,2)     AS valor_total
  FROM vinculo_ata_licitacao_item v
  JOIN public.licitacao_itens li ON li.id = v.licitacao_item_id;
