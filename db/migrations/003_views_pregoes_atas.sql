-- =============================================================================
-- 003 - VIEWS ANALÍTICAS DAS NOVAS ABAS (schema pregao_atas)
-- =============================================================================
-- Correções em relação ao script original do Gemini:
--  * vw_pregoes_metricas: o JOIN direto itens x atas multiplicava linhas e inflava
--    COUNT/SUM quando o pregão tinha mais de uma ata. Agora cada agregado é pré-calculado.
--  * saldo de valor usa o valor VIGENTE (considera reequilíbrio deferido).
--  * consumo vem de vw_consumo_unificado (planilha legada + Portal Licitações - migração 004).
-- =============================================================================
SET search_path = pregao_atas, public, extensions;

-- -----------------------------------------------------------------------------
-- VIEW 1 (ABA 1): MÉTRICAS POR PREGÃO (% DE DISPUTA E % DE VITÓRIA)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_pregoes_metricas AS
WITH ci AS (
    SELECT pregao_id,
           COUNT(*)                                          AS qtd_itens_cotados,
           COUNT(*) FILTER (WHERE status_item = 'REGISTRADO') AS itens_registrados,
           COUNT(*) FILTER (WHERE status_item IN ('PERDIDO','DESCLASSIFICADO','FRACASSADO')) AS itens_perdidos,
           COALESCE(SUM(valor_total_minimo), 0)              AS valor_total_cotado_minimo,
           COALESCE(SUM(valor_total_vencedor) FILTER (WHERE status_item = 'REGISTRADO'), 0) AS valor_ganho
      FROM cotacao_itens GROUP BY pregao_id
), ca AS (
    SELECT pregao_id, COUNT(*) AS qtd_atas_contratos FROM contratos_atas GROUP BY pregao_id
), pd AS (
    SELECT pregao_id, COUNT(*) AS qtd_anexos_pregao FROM pregao_documentos GROUP BY pregao_id
)
SELECT
    p.id AS pregao_id, p.data_licitacao, p.hora_licitacao, p.numero_pregao, p.modalidade, p.empresa,
    p.portal, p.orgao_nome, p.orgao_cnpj, p.uf, p.porte, p.situacao, p.vendedor, p.total_itens_edital,
    GREATEST(p.itens_disputados, COALESCE(ci.qtd_itens_cotados, 0)) AS itens_disputados_efetivos,
    ROUND(GREATEST(p.itens_disputados, COALESCE(ci.qtd_itens_cotados, 0))::NUMERIC
          / NULLIF(p.total_itens_edital, 0) * 100, 2)               AS pct_disputa_edital,
    COALESCE(ci.itens_registrados, 0)                               AS itens_registrados,
    COALESCE(ci.itens_perdidos, 0)                                  AS itens_perdidos,
    ROUND(COALESCE(ci.itens_registrados, 0)::NUMERIC
          / NULLIF(GREATEST(p.itens_disputados, COALESCE(ci.qtd_itens_cotados, 0)), 0) * 100, 2)
                                                                    AS pct_vitoria_sobre_disputados,
    COALESCE(ci.valor_total_cotado_minimo, 0)                       AS valor_total_cotado_minimo,
    COALESCE(ca.qtd_atas_contratos, 0)                              AS qtd_atas_contratos,
    COALESCE(pd.qtd_anexos_pregao, 0)                               AS qtd_anexos_pregao,
    -- novos (fim da lista para não quebrar quem já consome a view): itens GANHOS = REGISTRADOS pela Empresa
    COALESCE(ci.itens_registrados, 0)                               AS itens_ganhos,
    COALESCE(ci.valor_ganho, 0)                                     AS valor_ganho
FROM pregoes p
LEFT JOIN ci ON ci.pregao_id = p.id
LEFT JOIN ca ON ca.pregao_id = p.id
LEFT JOIN pd ON pd.pregao_id = p.id;

-- -----------------------------------------------------------------------------
-- CONSUMO UNIFICADO (planilha legada). A migração 004 recria esta view com o UNION do Portal.
-- Os CASTs são explícitos para que o CREATE OR REPLACE da 004 mantenha os mesmos tipos.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_consumo_unificado AS
SELECT ce.id::TEXT                       AS ref,
       'PLANILHA'::TEXT                  AS origem,
       ce.ata_item_id                    AS ata_item_id,
       ce.status_entrega::TEXT           AS status_entrega,
       ce.quantidade::INTEGER            AS quantidade,
       ce.valor_total::NUMERIC(16,2)     AS valor_total
  FROM consumo_entregas ce
 WHERE ce.ata_item_id IS NOT NULL;

-- -----------------------------------------------------------------------------
-- VIEW 2 (ABA 2): DETALHAMENTO DE ATAS, VIGÊNCIA E CONSUMO POR ITEM
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_ata_itens_consumo AS
WITH consumo_agregado AS (
    SELECT ata_item_id,
           SUM(quantidade)   FILTER (WHERE status_entrega IN ('FATURADO','ENTREGUE','CARTA_DE_CORRECAO')) AS qtde_faturada,
           SUM(valor_total)  FILTER (WHERE status_entrega IN ('FATURADO','ENTREGUE','CARTA_DE_CORRECAO')) AS valor_faturado,
           SUM(quantidade)   FILTER (WHERE status_entrega IN ('AG_ESTOQUE','TROCA_DE_MARCA','LANCADO_NO_SISTEMA','CHEGADA')) AS qtde_em_processo,
           SUM(valor_total)  FILTER (WHERE status_entrega IN ('AG_ESTOQUE','TROCA_DE_MARCA','LANCADO_NO_SISTEMA','CHEGADA')) AS valor_em_processo
      FROM vw_consumo_unificado
     WHERE status_entrega NOT IN ('EMP_CANCELADO', 'FATURADO_DUPLICADO')
     GROUP BY ata_item_id
), base AS (
    SELECT ca.id AS contrato_ata_id, ca.nome_contrato, ca.tipo_instrumento, ca.data_contrato,
           ca.tipo_vigencia, ca.data_fim_vigencia,
           CASE WHEN ca.tipo_vigencia = 'IMEDIATO' THEN NULL
                ELSE (ca.data_fim_vigencia - CURRENT_DATE) END AS dias_para_fim,
           CASE WHEN ca.tipo_vigencia = 'IMEDIATO' THEN 'IMEDIATO'
                WHEN ca.data_fim_vigencia < CURRENT_DATE THEN 'ENCERRADO'
                WHEN (ca.data_fim_vigencia - CURRENT_DATE) <= 30 THEN 'VENCE_30_DIAS'
                ELSE 'ATIVO' END AS status_vigencia,
           p.id AS pregao_id, p.numero_pregao, p.orgao_nome, p.uf, p.vendedor, p.empresa,
           ai.id AS ata_item_id, ai.numero_item, ai.sku, ai.descricao, ai.categoria, ai.qtde_registrada,
           ai.status_reequilibrio,
           CASE WHEN ai.status_reequilibrio = 'DEFERIDO' AND ai.valor_reequilibrio IS NOT NULL
                THEN ai.valor_reequilibrio ELSE ai.valor_unit_registrado END AS valor_unit_vigente
      FROM contratos_atas ca
      JOIN pregoes p    ON p.id = ca.pregao_id
      JOIN ata_itens ai ON ai.contrato_ata_id = ca.id
)
SELECT b.contrato_ata_id, b.nome_contrato, b.tipo_instrumento, b.data_contrato, b.tipo_vigencia,
       b.data_fim_vigencia, b.dias_para_fim, b.status_vigencia,
       b.pregao_id, b.numero_pregao, b.orgao_nome, b.uf, b.vendedor, b.empresa,
       b.ata_item_id, b.numero_item, b.sku, b.descricao, b.categoria, b.qtde_registrada,
       b.valor_unit_vigente,
       (b.qtde_registrada * b.valor_unit_vigente)                          AS valor_total_contratado,
       COALESCE(c.qtde_faturada, 0)                                        AS qtde_consumida,
       COALESCE(c.valor_faturado, 0)                                       AS valor_consumido,
       COALESCE(c.qtde_em_processo, 0)                                     AS qtde_em_processo,
       GREATEST(b.qtde_registrada - COALESCE(c.qtde_faturada, 0), 0)       AS saldo_qtde_remanescente,
       -- saldo calculado sobre o valor VIGENTE (o original usava o valor registrado, ignorando reequilíbrio)
       GREATEST((b.qtde_registrada * b.valor_unit_vigente) - COALESCE(c.valor_faturado, 0), 0) AS saldo_valor_remanescente,
       ROUND(COALESCE(c.qtde_faturada, 0)::NUMERIC / NULLIF(b.qtde_registrada, 0) * 100, 2)    AS pct_consumo
  FROM base b
  LEFT JOIN consumo_agregado c ON c.ata_item_id = b.ata_item_id;

-- -----------------------------------------------------------------------------
-- VIEW 3 (ABA 2): CARDS DE KPIs EXECUTIVOS
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_dashboard_atas_kpis AS
SELECT
    COUNT(DISTINCT contrato_ata_id) FILTER (WHERE status_vigencia IN ('ATIVO','VENCE_30_DIAS')) AS contratos_ativos,
    COUNT(ata_item_id)              FILTER (WHERE status_vigencia IN ('ATIVO','VENCE_30_DIAS')) AS total_itens_registrados_ativos,
    COALESCE(SUM(valor_total_contratado)   FILTER (WHERE status_vigencia IN ('ATIVO','VENCE_30_DIAS')), 0) AS valor_total_itens_ativos,
    COALESCE(SUM(qtde_registrada)          FILTER (WHERE status_vigencia IN ('ATIVO','VENCE_30_DIAS')), 0) AS quantidade_total_itens_ativos,
    COALESCE(SUM(valor_consumido)          FILTER (WHERE status_vigencia IN ('ATIVO','VENCE_30_DIAS')), 0) AS valor_consumido_ativos,
    COALESCE(SUM(saldo_valor_remanescente) FILTER (WHERE status_vigencia IN ('ATIVO','VENCE_30_DIAS')), 0) AS saldo_valor_remanescente_ativos,
    COALESCE(SUM(qtde_registrada)          FILTER (WHERE status_vigencia = 'VENCE_30_DIAS'), 0) AS itens_proximos_30_dias,
    COALESCE(SUM(valor_total_contratado)   FILTER (WHERE status_vigencia = 'VENCE_30_DIAS'), 0) AS valores_proximos_30_dias,
    COALESCE(SUM(saldo_valor_remanescente) FILTER (WHERE status_vigencia = 'VENCE_30_DIAS'), 0) AS saldo_a_vencer_30_dias,
    COUNT(DISTINCT contrato_ata_id) FILTER (WHERE status_vigencia = 'IMEDIATO')                 AS contratos_imediatos,
    COALESCE(SUM(valor_total_contratado)   FILTER (WHERE status_vigencia = 'IMEDIATO'), 0)      AS valor_contratos_imediatos
FROM vw_ata_itens_consumo;
