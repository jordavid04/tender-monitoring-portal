/* MODO DEMONSTRAÇÃO — sem backend. Reproduz as rotas /api/v1 das abas Pregões e Atas e Contratos, com as MESMAS regras
 * de negócio, guardando tudo no localStorage do navegador. Começa VAZIO (nenhum dado fictício).
 * Usado automaticamente quando a API não responde (ex.: só `python -m http.server`). Não é código de produção. */
import { salvarBlob } from './api-client.js';

const CHAVE = 'demo_pregoes_atas_v1';
const VAZIO = () => ({ pregoes: [], itens: [], concorrentes: [], atas: [], ata_itens: [], docs: [] });
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : 'id-' + Math.random().toString(16).slice(2) + Date.now().toString(16));
const agora = () => new Date().toISOString();
const hojeISO = () => new Date().toISOString().slice(0, 10);
const E = m => { const e = new Error(m); throw e; };

const SIT = ['EM ANÁLISE', 'CADASTRADO', 'EM ANDAMENTO', 'SUSPENSO', 'VITÓRIA TOTAL', 'VITÓRIA PARCIAL', 'DERROTA', 'FRACASSADO/DESERTO', 'REVOGADO/ANULADO', 'EM RECURSO'];
const PORTES = ['AMPLA PARTICIPAÇÃO', 'EXCLUSIVO ME/EPP', 'COTA ME/EPP', 'MISTO'];
const ST = ['EM_COTACAO', 'EM_DISPUTA', 'AGUARDANDO_HOMOLOGACAO', 'REGISTRADO', 'PERDIDO', 'DESCLASSIFICADO', 'FRACASSADO', 'EM_RECURSO'];
const PERD = ['PERDIDO', 'DESCLASSIFICADO', 'FRACASSADO'];

/* CNPJ alfanumérico — mesmo algoritmo de app/domain/validators.py (módulo 11 sobre ord(c)-48) */
const PESOS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
const limparCnpj = v => { const s = String(v || '').toUpperCase().replace(/[^0-9A-Z]/g, ''); return /^[0-9A-Z]{12}[0-9]{2}$/.test(s) ? s : null; };
const dv = base => { const p = PESOS.slice(-base.length); const r = [...base].reduce((a, c, i) => a + (c.charCodeAt(0) - 48) * p[i], 0) % 11; return r < 2 ? 0 : 11 - r; };
export const cnpjValido = c => { const s = limparCnpj(c); if (!s) return false; const d1 = dv(s.slice(0, 12)); return d1 === +s[12] && dv(s.slice(0, 12) + d1) === +s[13]; };

const somarMeses = (iso, n) => { const [y, m, d] = iso.split('-').map(Number); const t = m - 1 + n; const ano = y + Math.floor(t / 12), mes = ((t % 12) + 12) % 12; const ult = new Date(Date.UTC(ano, mes + 1, 0)).getUTCDate(); return new Date(Date.UTC(ano, mes, Math.min(d, ult))).toISOString().slice(0, 10); };
const fimVigencia = (dc, tipo, fim) => { if (tipo === '6_MESES') return somarMeses(dc, 6); if (tipo === '12_MESES') return somarMeses(dc, 12); if (tipo === 'IMEDIATO') return null;
  if (tipo === 'PERSONALIZADO') { if (!fim) E('Para vigência PERSONALIZADA informe a data de fim.'); if (fim < dc) E('O fim da vigência não pode ser anterior à data do contrato.'); return fim; } E('Tipo de vigência inválido.'); };
const dias = (a, b) => Math.round((Date.parse(a) - Date.parse(b)) / 864e5);
const statusVig = (a) => a.tipo_vigencia === 'IMEDIATO' ? 'IMEDIATO' : a.data_fim_vigencia < hojeISO() ? 'ENCERRADO' : dias(a.data_fim_vigencia, hojeISO()) <= 30 ? 'VENCE_30_DIAS' : 'ATIVO';
const pc = (a, b) => b ? Math.round(a / b * 10000) / 100 : null;
const r2 = n => Math.round(n * 100) / 100;

export function criarMock() {
  let S; try { S = JSON.parse(localStorage.getItem(CHAVE)) || VAZIO(); } catch { S = VAZIO(); }
  const salvar = () => { try { localStorage.setItem(CHAVE, JSON.stringify(S)); } catch { /* sem persistência: segue em memória */ } };
  const ok = v => JSON.parse(JSON.stringify(v));

  const metr = p => {
    const it = S.itens.filter(i => i.pregao_id === p.id), gan = it.filter(i => i.status_item === 'REGISTRADO'), disp = Math.max(p.itens_disputados, it.length);
    return { ...p, pregao_id: p.id, itens_disputados_efetivos: disp, pct_disputa_edital: pc(disp, p.total_itens_edital), itens_registrados: gan.length, itens_ganhos: gan.length,
      itens_perdidos: it.filter(i => PERD.includes(i.status_item)).length, pct_vitoria_sobre_disputados: pc(gan.length, disp),
      valor_total_cotado_minimo: r2(it.reduce((s, i) => s + i.quantidade * i.valor_unit_minimo, 0)), valor_ganho: r2(gan.reduce((s, i) => s + i.quantidade * (i.valor_unit_vencedor || 0), 0)),
      qtd_atas_contratos: S.atas.filter(a => a.pregao_id === p.id).length, qtd_anexos_pregao: S.docs.filter(d => d.dono === p.id).length };
  };
  const pagina = (arr, q) => { const pg = Math.max(+q.pagina || 1, 1), t = Math.min(Math.max(+q.tamanho || 25, 1), 200); return { itens: arr.slice((pg - 1) * t, pg * t), total: arr.length, pagina: pg, tamanho: t }; };
  const linhasAta = a => { const p = S.pregoes.find(x => x.id === a.pregao_id) || {}; return S.ata_itens.filter(x => x.contrato_ata_id === a.id).map(ai => {
    const unit = ai.status_reequilibrio === 'DEFERIDO' && ai.valor_reequilibrio ? ai.valor_reequilibrio : ai.valor_unit_registrado, tot = r2(ai.qtde_registrada * unit);
    return { contrato_ata_id: a.id, nome_contrato: a.nome_contrato, tipo_instrumento: a.tipo_instrumento, data_contrato: a.data_contrato, tipo_vigencia: a.tipo_vigencia, data_fim_vigencia: a.data_fim_vigencia,
      dias_para_fim: a.tipo_vigencia === 'IMEDIATO' ? null : dias(a.data_fim_vigencia, hojeISO()), status_vigencia: statusVig(a), pregao_id: p.id, numero_pregao: p.numero_pregao, orgao_nome: p.orgao_nome, uf: p.uf, vendedor: p.vendedor,
      ata_item_id: ai.id, numero_item: ai.numero_item, sku: ai.sku, descricao: ai.descricao, qtde_registrada: ai.qtde_registrada, valor_unit_vigente: unit, status_reequilibrio: ai.status_reequilibrio || null,
      valor_total_contratado: tot, qtde_consumida: 0, valor_consumido: 0, qtde_em_processo: 0, saldo_qtde_remanescente: ai.qtde_registrada, saldo_valor_remanescente: tot, pct_consumo: 0 }; }); };
  const resumoAtas = () => S.atas.map(a => { const ls = linhasAta(a); if (!ls.length) return null; const s = k => r2(ls.reduce((x, l) => x + l[k], 0)); const l0 = ls[0];
    return { ...l0, itens: ls.length, qtde_registrada: s('qtde_registrada'), valor_total_contratado: s('valor_total_contratado'), valor_consumido: s('valor_consumido'), saldo_valor_remanescente: s('saldo_valor_remanescente'), pct_consumo: pc(s('qtde_consumida'), s('qtde_registrada')) }; }).filter(Boolean);
  const filtroAtas = (rows, q) => { const t = (q.q || '').toLowerCase(); return rows.filter(r => (!t || [r.nome_contrato, r.numero_pregao, r.orgao_nome].some(x => String(x || '').toLowerCase().includes(t))) && (!q.uf || r.uf === q.uf.toUpperCase()) && (!q.vendedor || String(r.vendedor).toLowerCase().includes(q.vendedor.toLowerCase())) && (!q.status_vigencia || r.status_vigencia === q.status_vigencia)).sort((a, b) => (a.dias_para_fim ?? 1e9) - (b.dias_para_fim ?? 1e9)); };
  const listaPregoes = q => { const t = (q.q || '').toLowerCase(); return S.pregoes.filter(p => (!t || [p.numero_pregao, p.orgao_nome, p.portal].some(x => String(x).toLowerCase().includes(t))) && (!q.uf || p.uf === q.uf.toUpperCase()) && (!q.situacao || p.situacao === q.situacao) && (!q.vendedor || p.vendedor === q.vendedor) && (!q.porte || p.porte === q.porte) && (!q.de || p.data_licitacao >= q.de) && (!q.ate || p.data_licitacao <= q.ate))
    .sort((a, b) => (b.data_licitacao + b.hora_licitacao).localeCompare(a.data_licitacao + a.hora_licitacao)).map(metr); };

  function validarPregao(d, base) {
    const b = base || {}, n = { ...b };
    const txt = (k, rot) => { if (k in d || !base) { const v = String(d[k] ?? '').trim(); if (!v) E(`Informe: ${rot}.`); n[k] = v; } };
    txt('numero_pregao', 'nº do pregão'); txt('portal', 'portal'); txt('orgao_nome', 'órgão'); txt('vendedor', 'vendedor'); if (n.vendedor) n.vendedor = n.vendedor.toUpperCase();   // a API grava o vendedor em maiúsculas
    for (const k of ['data_licitacao', 'hora_licitacao']) if (k in d || !base) { if (!d[k]) E(`Informe: ${k === 'data_licitacao' ? 'data' : 'hora'} da licitação.`); n[k] = d[k]; }
    if ('uf' in d || !base) { const u = String(d.uf || '').trim().toUpperCase(); if (u.length !== 2) E('UF inválida (2 letras).'); n.uf = u; }
    if ('porte' in d || !base) { if (!PORTES.includes(d.porte)) E('Porte inválido.'); n.porte = d.porte; }
    if ('situacao' in d || !base) { n.situacao = d.situacao || 'EM ANDAMENTO'; if (!SIT.includes(n.situacao)) E('Situação inválida.'); }
    if ('total_itens_edital' in d || !base) { n.total_itens_edital = +d.total_itens_edital; if (!(n.total_itens_edital > 0)) E('Itens no edital: mínimo 1.'); }
    if ('itens_disputados' in d || !base) n.itens_disputados = +d.itens_disputados || 0;
    if ('orgao_cnpj' in d) { if (d.orgao_cnpj) { if (!cnpjValido(d.orgao_cnpj)) E('CNPJ do órgão inválido.'); n.orgao_cnpj = limparCnpj(d.orgao_cnpj); } else n.orgao_cnpj = null; }
    if ('observacoes' in d) n.observacoes = d.observacoes || null;
    if (n.itens_disputados > n.total_itens_edital) E('Itens disputados não pode ser maior que o total de itens do edital.');
    n.modalidade = n.modalidade || 'ELETRÔNICO'; n.empresa = 'Empresa/SC'; return n;
  }

  function resultado(i, d) {
    const t = d.vencedor_tipo; if (!['PROPRIA', 'CONCORRENTE', 'SEM_VENCEDOR'].includes(t)) E('Vencedor inválido.');
    if (S.ata_itens.some(x => x.cotacao_item_id === i.id)) E('Este item compõe uma Ata/Contrato. Remova-o da ata antes de alterar o resultado.');
    let conc = null, val = d.valor_unit_vencedor == null || d.valor_unit_vencedor === '' ? null : +d.valor_unit_vencedor;
    if (t === 'CONCORRENTE') { if (!d.vencedor_concorrente_id) E('Selecione ou cadastre o concorrente vencedor.'); if (!S.concorrentes.some(c => c.id === d.vencedor_concorrente_id)) E('Concorrente não encontrado.');
      if (i.status_item === 'REGISTRADO') E('Item REGISTRADO é da empresa; altere o status do item antes de apontar um concorrente.'); conc = d.vencedor_concorrente_id; }
    else if (t === 'SEM_VENCEDOR') val = null; else if (!val) E('Informe o valor unitário vencedor da empresa.');
    Object.assign(i, { vencedor_tipo: t, vencedor_concorrente_id: conc, valor_unit_vencedor: val });
  }

  const itemOut = i => { const c = S.concorrentes.find(x => x.id === i.vencedor_concorrente_id); return { ...i, valor_total_minimo: r2(i.quantidade * i.valor_unit_minimo), valor_total_vencedor: r2(i.quantidade * (i.valor_unit_vencedor || 0)),
    vencedor_nome: c?.nome_abreviado || null, vencedor_cnpj: c?.cnpj_clean || null, em_ata: S.ata_itens.some(x => x.cotacao_item_id === i.id) }; };
  const ordemItem = (a, b) => String(a.numero_item).localeCompare(String(b.numero_item), 'pt', { numeric: true });

  const csv = (cab, linhas) => '﻿' + [cab, ...linhas].map(l => l.map(v => { const s = v == null ? '' : typeof v === 'number' && !Number.isInteger(v) ? String(v).replace('.', ',') : String(v); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(';')).join('\r\n');
  const exporta = (nome, cab, linhas) => salvarBlob(new Blob([csv(cab, linhas)], { type: 'text/csv;charset=utf-8' }), nome + '.csv');
  const d_ = v => v ? String(v).slice(0, 10).split('-').reverse().join('/') : '';

  /* ------------------------------------------------------------------ roteador */
  function rota(m, path, q = {}, b = {}) {
    let r;
    if (m === 'GET' && path === '/pregoes') return pagina(listaPregoes(q), q);
    if (m === 'GET' && path === '/pregoes/insights') { const rows = listaPregoes({ de: q.de, ate: q.ate });
      const agg = rs => { const ed = rs.reduce((s, x) => s + x.total_itens_edital, 0), dp = rs.reduce((s, x) => s + x.itens_disputados_efetivos, 0), g = rs.reduce((s, x) => s + x.itens_ganhos, 0);
        return { pregoes: rs.length, itens_edital: ed, itens_disputados: dp, itens_registrados: g, itens_ganhos: g, itens_perdidos: rs.reduce((s, x) => s + x.itens_perdidos, 0), valor_ganho: r2(rs.reduce((s, x) => s + x.valor_ganho, 0)), pct_disputa: pc(dp, ed), pct_vitoria: pc(g, dp) }; };
      const por = k => Object.entries(rows.reduce((o, x) => ((o[x[k]] = o[x[k]] || []).push(x), o), {})).map(([chave, rs]) => ({ chave, ...agg(rs) })).sort((a, c) => c.pregoes - a.pregoes);
      return { geral: agg(rows), por_vendedor: por('vendedor'), por_uf: por('uf'), por_situacao: por('situacao'), por_porte: por('porte') }; }
    if (m === 'GET' && path === '/pregoes/exportar') { const cab = ['Data', 'Hora', 'Nº do pregão', 'Portal', 'Órgão', 'UF', 'Porte', 'Situação', 'Vendedor', 'Itens no edital', 'Itens disputados', '% disputa', 'Itens ganhos', 'Itens perdidos', '% vitória', 'Valor ganho (R$)', 'Atas'];
      exporta('Pregoes', cab, listaPregoes(q).map(p => [d_(p.data_licitacao), p.hora_licitacao, p.numero_pregao, p.portal, p.orgao_nome, p.uf, p.porte, p.situacao, p.vendedor, p.total_itens_edital, p.itens_disputados_efetivos, p.pct_disputa_edital, p.itens_ganhos, p.itens_perdidos, p.pct_vitoria_sobre_disputados, p.valor_ganho, p.qtd_atas_contratos])); return null; }
    if (m === 'POST' && path === '/pregoes') { const n = validarPregao(b); if (S.pregoes.some(p => p.numero_pregao === n.numero_pregao && p.orgao_nome.toLowerCase() === n.orgao_nome.toLowerCase())) E('Já existe um pregão com este número para este órgão.');
      n.id = uuid(); n.created_at = agora(); S.pregoes.push(n); salvar(); return { id: n.id }; }
    if ((r = path.match(/^\/pregoes\/([^/]+)(\/.*)?$/)) && !['insights', 'exportar', 'itens', 'documentos'].includes(r[1])) {
      const p = S.pregoes.find(x => x.id === r[1]); if (!p) E('Pregão não encontrado.'); const sub = r[2] || '';
      if (sub === '' && m === 'GET') { return { pregao: metr(p), dados: { observacoes: p.observacoes, criado_por: 'Demo' }, documentos: S.docs.filter(d => d.dono === p.id).map(({ dono, ...d }) => d),
        cotacao: S.itens.filter(i => i.pregao_id === p.id).sort(ordemItem).map(itemOut), atas: S.atas.filter(a => a.pregao_id === p.id).map(a => ({ id: a.id, nome_contrato: a.nome_contrato, tipo_instrumento: a.tipo_instrumento, data_contrato: a.data_contrato, tipo_vigencia: a.tipo_vigencia, data_fim_vigencia: a.data_fim_vigencia })) }; }
      if (sub === '' && m === 'PATCH') { const n = validarPregao(b, p); const cot = S.itens.filter(i => i.pregao_id === p.id).length; if (n.total_itens_edital < cot) E(`O pregão já tem ${cot} itens cotados; o edital não pode ter menos que isso.`); Object.assign(p, n); salvar(); return { ok: true }; }
      if (sub === '' && m === 'DELETE') { if (S.atas.some(a => a.pregao_id === p.id)) E('Este pregão possui Ata/Contrato. Remova-a antes de excluir o pregão.'); S.pregoes = S.pregoes.filter(x => x !== p); S.itens = S.itens.filter(i => i.pregao_id !== p.id); S.docs = S.docs.filter(d => d.dono !== p.id); salvar(); return null; }
      if (sub === '/exportar') { const cab = ['Item', 'SKU', 'Medida', 'Marca', 'Modelo', 'Categoria', 'Descrição', 'Quantidade', 'Valor mínimo da empresa (unit.)', 'Total mínimo da empresa', 'Status', 'Vencedor', 'Valor unit. vencedor', 'Total vencedor', 'Em ata'];
        exporta('Cotacao_' + p.numero_pregao.replace(/[^\w-]+/g, '_'), cab, S.itens.filter(i => i.pregao_id === p.id).sort(ordemItem).map(itemOut).map(i => [i.numero_item, i.sku, i.medida, i.marca, i.modelo, i.categoria, i.descricao, i.quantidade, i.valor_unit_minimo, i.valor_total_minimo, i.status_item, i.vencedor_tipo === 'PROPRIA' ? 'Empresa' : i.vencedor_nome, i.valor_unit_vencedor, i.valor_total_vencedor, i.em_ata ? 'Sim' : 'Não'])); return null; }
      if (sub === '/itens' && m === 'POST') { const novos = b.itens || []; const cot = S.itens.filter(i => i.pregao_id === p.id);
        if (cot.length + novos.length > p.total_itens_edital) E(`O pregão tem ${p.total_itens_edital} itens no edital; a cotação teria ${cot.length + novos.length}.`);
        const ids = []; for (const it of novos) { const n = String(it.numero_item || '').trim(); if (!n) E('Informe o nº do item.'); if (S.itens.some(i => i.pregao_id === p.id && i.numero_item === n)) E(`O item ${n} já existe neste pregão.`);
          if (!it.descricao && !it.sku) E(`Item ${n}: informe a descrição ou um SKU do catálogo.`); if (!(it.quantidade > 0)) E(`Item ${n}: quantidade mínima 1.`); if (it.status_item === 'REGISTRADO') E('Para marcar o item como ganho, use "Resultado" (vencedor a empresa + valor).');
          const novo = { id: uuid(), pregao_id: p.id, numero_item: n, sku: it.sku || null, marca: it.marca || null, modelo: it.modelo || null, medida: it.medida || null, descricao: it.descricao, categoria: it.categoria || null, quantidade: +it.quantidade,
            valor_unit_minimo: +it.valor_unit_minimo || 0, valor_unit_vencedor: null, vencedor_tipo: null, vencedor_concorrente_id: null, status_item: it.status_item || 'EM_COTACAO', observacoes: it.observacoes || null };
          S.itens.push(novo); ids.push(novo.id); }
        p.itens_disputados = Math.min(p.total_itens_edital, Math.max(p.itens_disputados, cot.length + novos.length)); salvar(); return { ids }; }
      if (sub === '/contratos-atas' && m === 'POST') { const dc = b.data_contrato; if (!b.nome_contrato || !dc) E('Informe o nome e a data do contrato.'); const fim = fimVigencia(dc, b.tipo_vigencia, b.data_fim_vigencia);
        const ids = [...new Set(b.cotacao_item_ids || [])]; const its = S.itens.filter(i => ids.includes(i.id) && i.pregao_id === p.id); if (!ids.length || its.length !== ids.length) E('Há itens que não pertencem a este pregão.');
        const nr = its.filter(i => i.status_item !== 'REGISTRADO').map(i => i.numero_item); if (nr.length) E('Apenas itens com status REGISTRADO podem compor a Ata/Contrato. Itens bloqueados: ' + nr.join(', ') + '.');
        const sv = its.filter(i => !i.valor_unit_vencedor).map(i => i.numero_item); if (sv.length) E('Itens sem valor unitário vencedor (defina o vencedor a empresa e o valor): ' + sv.join(', ') + '.');
        const ja = its.filter(i => S.ata_itens.some(x => x.cotacao_item_id === i.id)).map(i => i.numero_item); if (ja.length) E('Itens já vinculados a outra Ata/Contrato: ' + ja.join(', '));
        const a = { id: uuid(), pregao_id: p.id, nome_contrato: b.nome_contrato.trim(), tipo_instrumento: b.tipo_instrumento || 'ATA_REGISTRO_PRECO', data_contrato: dc, tipo_vigencia: b.tipo_vigencia, data_fim_vigencia: fim }; S.atas.push(a);
        its.sort(ordemItem).forEach(i => S.ata_itens.push({ id: uuid(), contrato_ata_id: a.id, cotacao_item_id: i.id, numero_item: i.numero_item, sku: i.sku, descricao: i.descricao, qtde_registrada: i.quantidade, valor_unit_registrado: i.valor_unit_vencedor }));
        salvar(); return { contrato_ata_id: a.id, data_fim_vigencia: fim, itens_vinculados: its.length }; }
      if (sub === '/documentos' && m === 'POST') { const arqs = b.__arquivos || []; if (!arqs.length) E('Envie ao menos um arquivo.'); arqs.forEach(f => S.docs.push({ id: uuid(), dono: p.id, categoria: b.categoria, nome_arquivo: f.name, mime_type: f.type, tamanho_bytes: f.size, uploaded_by: 'Demo', uploaded_at: agora() })); salvar(); return { ids: [] }; }
    }
    if ((r = path.match(/^\/pregoes\/itens\/([^/]+)(\/vencedor)?$/))) {
      const i = S.itens.find(x => x.id === r[1]); if (!i) E('Item não encontrado.'); const em = S.ata_itens.some(x => x.cotacao_item_id === i.id);
      if (m === 'DELETE') { if (em) E('Este item compõe uma Ata/Contrato. Remova-o da ata primeiro.'); S.itens = S.itens.filter(x => x !== i); salvar(); return null; }
      if (m === 'PUT' && r[2]) { resultado(i, b); salvar(); return { ok: true }; }
      if (m === 'PATCH') { if (b.status_item) { if (!ST.includes(b.status_item)) E('Status inválido.'); if (b.status_item === 'REGISTRADO' && i.vencedor_tipo === 'CONCORRENTE') E('Item REGISTRADO não pode ter concorrente como vencedor. Ajuste o vencedor primeiro.');
          if (b.status_item === 'REGISTRADO' && !(i.vencedor_tipo === 'PROPRIA' && i.valor_unit_vencedor)) E('Para registrar o item como ganho, defina o resultado: vencedor a empresa e valor unitário vencedor.');
          if (em && b.status_item !== 'REGISTRADO') E(`O item ${i.numero_item} já compõe uma Ata/Contrato; remova-o da ata antes de alterar o status.`); }
        for (const k of ['sku', 'marca', 'modelo', 'medida', 'descricao', 'categoria', 'observacoes', 'status_item']) if (b[k] != null) i[k] = b[k];
        if (b.quantidade != null) { if (em) E('Item em ata: a quantidade não pode ser alterada.'); i.quantidade = +b.quantidade; } if (b.valor_unit_minimo != null) i.valor_unit_minimo = +b.valor_unit_minimo; salvar(); return { ok: true }; }
    }
    if (m === 'GET' && path === '/concorrentes') return { itens: ok(S.concorrentes).sort((a, c) => a.nome_abreviado.localeCompare(c.nome_abreviado)).map(c => ({ id: c.id, nome_abreviado: c.nome_abreviado, razao_social: c.razao_social, cnpj: c.cnpj_clean, municipio: c.municipio, uf: c.uf })) };
    if (m === 'POST' && path === '/concorrentes/cadastro-rapido') { if (!cnpjValido(b.cnpj)) E('CNPJ inválido (formato ou dígitos verificadores).'); const cj = limparCnpj(b.cnpj);
      if (!b.nome_abreviado || !b.razao_social || String(b.uf || '').length !== 2) E('Informe nome abreviado, razão social e UF.'); let c = S.concorrentes.find(x => x.cnpj_clean === cj);
      if (c) { if (b.municipio) c.municipio = b.municipio; } else { c = { id: uuid(), nome_abreviado: b.nome_abreviado, razao_social: b.razao_social, cnpj_clean: cj, municipio: b.municipio || '', uf: b.uf.toUpperCase(), data_chegada: agora() }; S.concorrentes.push(c); }
      salvar(); return { concorrente: ok(c) }; }
    if (m === 'GET' && path === '/catalogo/produtos') return { resultados: [] };
    if (m === 'GET' && path === '/atas') return pagina(filtroAtas(resumoAtas(), q), q);
    if (m === 'GET' && path === '/atas/insights') { const ls = filtroAtas(resumoAtas(), q).flatMap(r => linhasAta(S.atas.find(a => a.id === r.contrato_ata_id))); const at = ls.filter(l => ['ATIVO', 'VENCE_30_DIAS'].includes(l.status_vigencia)), v30 = ls.filter(l => l.status_vigencia === 'VENCE_30_DIAS'), im = ls.filter(l => l.status_vigencia === 'IMEDIATO');
      const s = (a, k) => r2(a.reduce((x, l) => x + l[k], 0)); return { kpis: { contratos_ativos: new Set(at.map(l => l.contrato_ata_id)).size, total_itens_registrados_ativos: at.length, valor_total_itens_ativos: s(at, 'valor_total_contratado'), quantidade_total_itens_ativos: s(at, 'qtde_registrada'),
        valor_consumido_ativos: s(at, 'valor_consumido'), saldo_valor_remanescente_ativos: s(at, 'saldo_valor_remanescente'), itens_proximos_30_dias: s(v30, 'qtde_registrada'), valores_proximos_30_dias: s(v30, 'valor_total_contratado'), saldo_a_vencer_30_dias: s(v30, 'saldo_valor_remanescente'),
        contratos_imediatos: new Set(im.map(l => l.contrato_ata_id)).size, valor_contratos_imediatos: s(im, 'valor_total_contratado') } }; }
    if (m === 'GET' && path === '/atas/exportar') { const cab = ['Instrumento', 'Tipo', 'Pregão', 'Órgão', 'UF', 'Vendedor', 'Data do contrato', 'Vigência', 'Fim da vigência', 'Dias p/ fim', 'Situação', 'Itens', 'Contratado (R$)', 'Consumido (R$)', 'Saldo (R$)', '% consumo'];
      exporta('Atas_e_Contratos', cab, filtroAtas(resumoAtas(), q).map(r => [r.nome_contrato, r.tipo_instrumento, r.numero_pregao, r.orgao_nome, r.uf, r.vendedor, d_(r.data_contrato), r.tipo_vigencia, d_(r.data_fim_vigencia), r.dias_para_fim, r.status_vigencia, r.itens, r.valor_total_contratado, r.valor_consumido, r.saldo_valor_remanescente, r.pct_consumo])); return null; }
    if ((r = path.match(/^\/atas\/([^/]+)(\/exportar)?$/))) { const a = S.atas.find(x => x.id === r[1]); if (!a) E('Ata/Contrato não encontrado.');
      if (r[2]) { exporta('Ata_' + a.nome_contrato.replace(/[^\w-]+/g, '_'), ['Item', 'SKU', 'Descrição', 'Qtde registrada', 'Qtde consumida', 'Qtde em processo', 'Saldo (un.)', 'Valor unit. vigente', 'Contratado (R$)', 'Consumido (R$)', 'Saldo (R$)', '% consumo', 'Reequilíbrio'],
          linhasAta(a).map(l => [l.numero_item, l.sku, l.descricao, l.qtde_registrada, l.qtde_consumida, l.qtde_em_processo, l.saldo_qtde_remanescente, l.valor_unit_vigente, l.valor_total_contratado, l.valor_consumido, l.saldo_valor_remanescente, l.pct_consumo, l.status_reequilibrio || ''])); return null; }
      if (m === 'GET') return { ata: ok(a), itens: linhasAta(a), consumo: [], documentos: S.docs.filter(d => d.dono === a.id).map(({ dono, ...d }) => d) };
      if (m === 'PATCH') { const dc = b.data_contrato || a.data_contrato, tv = b.tipo_vigencia || a.tipo_vigencia; if (b.nome_contrato) a.nome_contrato = b.nome_contrato; if (b.data_contrato || b.tipo_vigencia || b.data_fim_vigencia) { a.data_fim_vigencia = fimVigencia(dc, tv, b.data_fim_vigencia || (tv === 'PERSONALIZADO' ? a.data_fim_vigencia : null)); a.data_contrato = dc; a.tipo_vigencia = tv; } salvar(); return { ok: true }; }
      if (m === 'DELETE') { S.atas = S.atas.filter(x => x !== a); S.ata_itens = S.ata_itens.filter(x => x.contrato_ata_id !== a.id); salvar(); return null; } }
    if (m === 'POST' && /^\/atas\/[^/]+\/documentos$/.test(path)) { const a = S.atas.find(x => x.id === path.split('/')[2]); if (!a) E('Ata/Contrato não encontrado.'); (b.__arquivos || []).forEach(f => S.docs.push({ id: uuid(), dono: a.id, categoria: b.categoria, nome_arquivo: f.name, mime_type: f.type, tamanho_bytes: f.size, uploaded_by: 'Demo', uploaded_at: agora() })); salvar(); return { ids: [] }; }
    if (m === 'GET' && /\/documentos\//.test(path)) E('No modo demonstração os arquivos anexados não são guardados — ligue a API para baixar anexos.');
    E('Rota não disponível no modo demonstração: ' + m + ' ' + path);
  }

  const espera = v => new Promise(res => setTimeout(() => res(v === undefined ? v : ok(v)), 60));
  const chamar = async (m, p, q, b) => { try { return await espera(rota(m, p, q, b)); } catch (e) { throw new Error(e.message); } };
  return { base: '(demo)', modo: 'demo',
    get: (p, q) => chamar('GET', p, q || {}), send: (m, p, b) => chamar(m, p, {}, b || {}),
    upload: (p, form) => chamar('POST', p, {}, { categoria: form.get('categoria'), __arquivos: form.getAll('arquivos').filter(f => f && f.name) }),
    baixar: (p, q) => chamar('GET', p, q || {}),
    zerar: () => { S = VAZIO(); salvar(); } };
}
