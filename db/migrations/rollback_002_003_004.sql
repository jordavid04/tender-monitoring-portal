-- ROLLBACK das novas abas. Remove SOMENTE o schema pregao_atas (nada do portal existente é tocado).
-- ATENÇÃO: apaga todos os dados das abas Pregões/Atas. Faça backup antes.
DROP SCHEMA IF EXISTS pregao_atas CASCADE;
