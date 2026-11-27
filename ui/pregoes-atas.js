/* Abas "Pregões" e "Atas e Contratos" — Portal Licitações (Empresa).
 * Módulo ES sem dependências. Usa as MESMAS classes/tokens do remote em produção (demo-theme.css é apenas o tema do protótipo).
 *
 *   import { montarAbas } from './pregoes-atas.js'
 *   const abas = montarAbas({ main, api, sessao })      // main = <main class="conteudo"> do remote
 *   abas.abrir('pregoes' | 'atas')
 *
 * api    : { base, get, send, upload, baixar }  (ver api-client.js)  -> /api/v1/*
 * sessao : { podeEditar, podeAdministrar }      (vem de GET /api/v1/sessao)
 */
const ICO = {
  gavel: '<path d="m14 13-8.4 8.4a2 2 0 0 1-2.8-2.8L11 10.2M16 16l6-6M8 8l6-6M9 7l8 8M21 11l-8-8"/>',
  scroll: '<path d="M15 12h-5M15 8h-5M19 17V5a2 2 0 0 0-2-2H4"/><path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"/>',
  plus: '<path d="M5 12h14M12 5v14"/>', back: '<path d="m12 19-7-7 7-7M19 12H5"/>', trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  clip: '<path d="m21.4 11.1-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  down: '<path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14"/>', trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>'
};
export const ico = (n, c = '') => `<svg class="ico ${c}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICO[n] || ''}</svg>`;

/** Itens que o remote acrescenta ao <nav> (grupo novo, mesmo padrão .menu-grupo). */
export const ITENS_MENU = [{ grupo: 'Pregões e Atas' }, { id: 'pregoes', rotulo: 'Pregões', icone: 'gavel' }, { id: 'atas', rotulo: 'Atas e Contratos', icone: 'scroll' }];

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const brl = v => v == null || v === '' ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const num = v => v == null ? '—' : Number(v).toLocaleString('pt-BR');
const pct = v => v == null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';
const dt = v => v ? String(v).slice(0, 10).split('-').reverse().join('/') : '—';
const hr = v => v ? String(v).slice(0, 5) : '';
const cnpjFmt = c => { const s = String(c || ''); return s.length === 14 ? `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(8, 12)}-${s.slice(12)}` : s; };

const SIT = { 'VITÓRIA TOTAL': 'ok', 'VITÓRIA PARCIAL': 'ok', 'EM ANDAMENTO': 'marca', 'EM ANÁLISE': 'neutro', 'CADASTRADO': 'neutro', 'SUSPENSO': 'atencao',
  'EM RECURSO': 'atencao', 'DERROTA': 'critico', 'FRACASSADO/DESERTO': 'cancelado', 'REVOGADO/ANULADO': 'cancelado' };
const ST_ITEM = { EM_COTACAO: ['Em cotação', 'neutro'], EM_DISPUTA: ['Em disputa', 'marca'], AGUARDANDO_HOMOLOGACAO: ['Ag. homologação', 'atencao'],
  REGISTRADO: ['Ganho (registrado)', 'ok'], PERDIDO: ['Perdido', 'critico'], DESCLASSIFICADO: ['Desclassificado', 'critico'], FRACASSADO: ['Fracassado/deserto', 'cancelado'], EM_RECURSO: ['Em recurso', 'atencao'] };
const lst = ks => ks.map(k => [k, ST_ITEM[k][0]]);
const VIG = { ATIVO: ['Ativo', 'ok'], VENCE_30_DIAS: ['Vence em 30 dias', 'atencao'], ENCERRADO: ['Encerrado', 'cancelado'], IMEDIATO: ['Imediato', 'marca'] };
const TIPO = { ATA_REGISTRO_PRECO: 'Ata de Registro de Preços', CONTRATO: 'Contrato', EMPENHO_DIRETO: 'Empenho direto' };
const PORTE = ['AMPLA PARTICIPAÇÃO', 'EXCLUSIVO ME/EPP', 'COTA ME/EPP', 'MISTO'];
const DOC_PREGAO = [['EDITAL', 'Edital'], ['TERMO_REFERENCIA', 'Termo de referência'], ['PROPOSTA_INICIAL', 'Proposta inicial'], ['PROPOSTA_AJUSTADA', 'Proposta ajustada'],
  ['HABILITACAO', 'Habilitação'], ['ATA_SESSAO', 'Ata da sessão'], ['RECURSO_IMPUGNACAO', 'Recurso / impugnação'], ['OUTROS', 'Outros']];
const DOC_ATA = [['CONTRATO_ATA', 'Contrato / Ata'], ['ADITIVO_PRAZO', 'Aditivo de prazo'], ['ADITIVO_QUANTIDADE', 'Aditivo de quantidade'], ['REEQUILIBRIO', 'Reequilíbrio'], ['EMPENHO', 'Empenho'], ['OUTROS', 'Outros']];
const selo = (t, c) => `<span class="selo ${c}">${esc(t)}</span>`;
const opts = (arr, sel, todos) => (todos ? `<option value="">${todos}</option>` : '') + arr.map(o => { const [v, l] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(v)}"${v === sel ? ' selected' : ''}>${esc(l)}</option>`; }).join('');

export function montarAbas({ main, api, sessao = {} }) {
  const root = main.getRootNode();
  const pode = !!sessao.podeEditar, admin = !!sessao.podeAdministrar;
  const E = { pregoes: { f: { pagina: 1, tamanho: 25 } }, atas: { f: { pagina: 1, tamanho: 25 } } };
  const $ = (s, el = main) => el.querySelector(s);
  const set = h => { main.innerHTML = h; };
  const host = () => root.querySelector('.licitacoes-raiz') || root.body || document.body;
  const carregando = () => set('<div class="state"><span class="spinner lg"></span>Carregando…</div>');
  const erro = (e, retry) => { set(`<div class="panel err"><h2>Não foi possível concluir</h2><p class="msg">${esc(e.message || e)}</p></div><button class="ghost tentar-de-novo" id="re">Tentar de novo</button>`); $('#re').onclick = retry; };
  const aviso = (msg, tipo = 'ok') => { const d = document.createElement('div'); d.className = `panel ${tipo} aviso-de-sessao`; d.setAttribute('role', 'status'); d.innerHTML = `<p class="msg">${esc(msg)}</p>`; host().appendChild(d); setTimeout(() => d.remove(), 4200); };
  const baixar = async (path, params) => { try { await api.baixar(path, params); } catch (e) { aviso(e.message, 'err'); } };
  const q = o => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v != null));

  function modal(titulo, corpo, { largo = '', onOk, ok = 'Salvar', perigo, aoAbrir } = {}) {
    const f = document.createElement('div'); f.className = 'fundo-modal';
    f.innerHTML = `<div class="modal ${largo}" role="dialog" aria-modal="true" aria-label="${esc(titulo)}"><div class="modal-topo"><h2>${esc(titulo)}</h2><button type="button" class="modal-fechar" aria-label="Fechar">×</button></div>
      <form class="modal-corpo" novalidate>${corpo}<div class="erro-campo" data-erro role="alert"></div><div class="modal-rodape"><button type="button" class="ghost" data-x>${onOk ? 'Cancelar' : 'Fechar'}</button>${onOk ? `<button class="primary ${perigo ? 'perigo' : ''}">${ok}</button>` : ''}</div></form></div>`;
    host().appendChild(f);
    const fechar = () => f.remove();
    f.querySelector('.modal-fechar').onclick = f.querySelector('[data-x]').onclick = fechar;
    const form = f.querySelector('form');
    form.onsubmit = async ev => {
      ev.preventDefault(); if (!onOk) return;
      if (!form.reportValidity()) return;
      const b = f.querySelector('button.primary'), er = f.querySelector('[data-erro]'); b.disabled = true; er.textContent = '';
      try { await onOk(Object.fromEntries(new FormData(form)), form); fechar(); } catch (e) { er.textContent = e.message || String(e); b.disabled = false; }
    };
    if (aoAbrir) aoAbrir(f, form);
    const primeiro = form.querySelector('input:not([type=hidden]),select,textarea'); if (primeiro) primeiro.focus();
    return f;
  }
  const campo = (rot, nome, v = '', tipo = 'text', extra = '', hint = '') => `<div><label>${rot}${hint ? `<span class="hint">${hint}</span>` : ''}</label><input name="${nome}" type="${tipo}" value="${esc(v)}" ${extra}></div>`;
  const sel = (rot, nome, o, v, extra = '') => `<div><label>${rot}</label><select name="${nome}" ${extra}>${opts(o, v)}</select></div>`;
  const paginacao = (pg, total) => { const n = Math.max(1, Math.ceil(total / pg.tamanho));
    return `<div class="paginacao"><span class="apagado">${num(total)} registro(s)</span><div class="passos"><button class="ghost pequeno" data-pg="-1" ${pg.pagina <= 1 ? 'disabled' : ''}>Anterior</button><span class="pagina-atual">Página ${pg.pagina} de ${n}</span><button class="ghost pequeno" data-pg="1" ${pg.pagina >= n ? 'disabled' : ''}>Próxima</button></div></div>`; };
  const kpi = (r, v, d = '', c = '') => `<div class="kpi ${c}"><div class="rotulo">${r}</div><div class="valor">${v}</div><div class="detalhe">${d}</div></div>`;
  const exportar = () => `<span class="botoes-em-linha"><button class="ghost pequeno" data-exp="xlsx">${ico('down')} Planilha (.xlsx)</button><button class="ghost pequeno" data-exp="csv">CSV</button></span>`;  // sem id: evita colisão com #ex/#exc (excluir)

  /* ============================== ABA 1 — PREGÕES ============================== */
  async function pregoes() {
    const f = E.pregoes.f; carregando();
    try {
      const [lista, ins] = await Promise.all([api.get('/pregoes', q(f)), api.get('/pregoes/insights', q({ de: f.de, ate: f.ate }))]);
      const g = ins.geral || {}, vend = (ins.por_vendedor || []).map(v => v.chave).filter(Boolean);
      set(`<div class="topo"><div><h1>Pregões</h1><p class="sub">Controle diário: edital, disputa, cotação de itens e atas geradas.</p></div>
        <div class="acoes">${exportar()}${pode ? `<button class="primary" id="novo">${ico('plus')} Novo pregão</button>` : ''}</div></div>
        <div class="kpis">${kpi('Pregões', num(g.pregoes), `${num(g.itens_edital)} itens nos editais`, 'marca')}
          ${kpi('Itens disputados', num(g.itens_disputados), `${pct(g.pct_disputa)} do edital`, 'normal')}
          ${kpi('Itens ganhos', num(g.itens_ganhos), `${pct(g.pct_vitoria)} dos disputados · ${brl(g.valor_ganho)}`, 'normal')}
          ${kpi('Itens perdidos', num(g.itens_perdidos), 'perdidos, desclassificados ou fracassados', g.itens_perdidos ? 'critico' : '')}</div>
        ${(ins.por_vendedor || []).length ? `<section class="secao"><div class="card"><div class="card-topo"><h2>Resumo por vendedor</h2></div><div class="grid-wrap"><table><thead><tr><th>Vendedor</th><th class="num">Pregões</th><th class="num">Itens no edital</th><th class="num">Disputados</th><th class="num">% disputa</th><th class="num">Ganhos</th><th class="num">% vitória</th><th class="num">Valor ganho</th></tr></thead><tbody>
          ${ins.por_vendedor.map(v => `<tr><td><b>${esc(v.chave || '—')}</b></td><td class="num">${num(v.pregoes)}</td><td class="num">${num(v.itens_edital)}</td><td class="num">${num(v.itens_disputados)}</td><td class="num">${pct(v.pct_disputa)}</td><td class="num">${num(v.itens_ganhos)}</td><td class="num">${pct(v.pct_vitoria)}</td><td class="num">${brl(v.valor_ganho)}</td></tr>`).join('')}</tbody></table></div></div></section>` : ''}
        <div class="cabeca-do-bloco"><div><h2>Pregões</h2></div></div>
        <form class="filtros" id="flt"><div class="busca"><label>Buscar</label><input name="q" placeholder="Nº do pregão, órgão ou portal" value="${esc(f.q || '')}"></div>
          <div><label>Situação</label><select name="situacao">${opts(Object.keys(SIT), f.situacao, 'Todas')}</select></div>
          <div><label>UF</label><input name="uf" maxlength="2" value="${esc(f.uf || '')}"></div>
          <div><label>Vendedor</label><select name="vendedor">${opts(vend, f.vendedor, 'Todos')}</select></div>
          <div><label>Porte</label><select name="porte">${opts(PORTE, f.porte, 'Todos')}</select></div>
          <div><label>Licitação de</label><input type="date" name="de" value="${f.de || ''}"></div><div><label>Licitação até</label><input type="date" name="ate" value="${f.ate || ''}"></div>
          <button class="visually-hidden">Buscar</button></form>
        <div class="resultado">${lista.itens.length ? `<div class="grid-wrap"><table><thead><tr><th>Data</th><th>Pregão</th><th>Órgão</th><th>UF</th><th>Situação</th><th class="num">Edital</th><th class="num">Disputados</th><th class="num">Ganhos</th><th class="num">Perdidos</th><th class="num">% vitória</th><th class="num">Atas</th><th>Vendedor</th></tr></thead><tbody>
          ${lista.itens.map(p => `<tr class="clicavel" data-id="${p.pregao_id}"><td class="nowrap">${dt(p.data_licitacao)}<br><span class="apagado">${hr(p.hora_licitacao)}</span></td><td><b>${esc(p.numero_pregao)}</b><br><span class="apagado">${esc(p.portal)}</span></td><td>${esc(p.orgao_nome)}<br><span class="apagado">${esc(p.porte)}</span></td><td>${esc(p.uf)}</td><td>${selo(p.situacao, SIT[p.situacao] || 'neutro')}</td>
            <td class="num">${num(p.total_itens_edital)}</td><td class="num">${num(p.itens_disputados_efetivos)}<br><span class="apagado">${pct(p.pct_disputa_edital)}</span></td><td class="num"><b>${num(p.itens_ganhos)}</b></td><td class="num">${num(p.itens_perdidos)}</td><td class="num">${pct(p.pct_vitoria_sobre_disputados)}</td><td class="num">${num(p.qtd_atas_contratos)}</td><td>${esc(p.vendedor)}</td></tr>`).join('')}</tbody></table></div>${paginacao(f, lista.total)}`
          : '<div class="state"><strong>Nenhum pregão encontrado</strong>Ajuste os filtros ou cadastre um novo pregão.</div>'}</div>`);
      $('#flt').onsubmit = e => { e.preventDefault(); Object.assign(f, Object.fromEntries(new FormData(e.target)), { pagina: 1 }); pregoes(); };
      main.querySelectorAll('#flt select,#flt input[type=date]').forEach(el => el.onchange = () => $('#flt').requestSubmit());
      main.querySelectorAll('tr.clicavel').forEach(tr => tr.onclick = () => pregao(tr.dataset.id));
      main.querySelectorAll('[data-pg]').forEach(b => b.onclick = () => { f.pagina += +b.dataset.pg; pregoes(); });
      main.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => baixar('/pregoes/exportar', { ...q(f), pagina: '', tamanho: '', formato: b.dataset.exp }));
      const n = $('#novo'); if (n) n.onclick = () => formPregao();
    } catch (e) { erro(e, pregoes); }
  }

  function formPregao(p) {
    const v = p || {};
    modal(p ? 'Editar pregão' : 'Novo pregão', `<div class="grade-form">${campo('Data da licitação', 'data_licitacao', String(v.data_licitacao || '').slice(0, 10), 'date', 'required')}${campo('Hora', 'hora_licitacao', hr(v.hora_licitacao) || '09:00', 'time', 'required')}
      ${campo('Nº do pregão', 'numero_pregao', v.numero_pregao, 'text', 'required')}${campo('Portal', 'portal', v.portal, 'text', 'required placeholder="ComprasGov, BLL, Licitanet…"')}
      <div class="largo">${campo('Órgão', 'orgao_nome', v.orgao_nome, 'text', 'required')}</div>${campo('CNPJ do órgão', 'orgao_cnpj', cnpjFmt(v.orgao_cnpj), 'text', 'placeholder="opcional"')}${campo('UF', 'uf', v.uf, 'text', 'maxlength=2 required')}
      ${sel('Porte', 'porte', PORTE, v.porte)}${sel('Situação', 'situacao', Object.keys(SIT), v.situacao || 'EM ANDAMENTO')}
      ${campo('Itens no edital', 'total_itens_edital', v.total_itens_edital, 'number', 'min=1 required')}${campo('Itens disputados', 'itens_disputados', v.itens_disputados ?? 0, 'number', 'min=0', 'atualiza sozinho ao cotar itens')}
      ${campo('Vendedor', 'vendedor', v.vendedor, 'text', 'required')}
      <div class="largo"><label>Observações</label><textarea name="observacoes">${esc(v.observacoes || '')}</textarea></div></div>`,
      { largo: 'largo', onOk: async d => {
        d.total_itens_edital = +d.total_itens_edital; d.itens_disputados = +d.itens_disputados || 0; d.uf = d.uf.toUpperCase();
        d.orgao_cnpj = (d.orgao_cnpj || '').replace(/[^0-9A-Za-z]/g, '').toUpperCase() || null; if (!d.observacoes) d.observacoes = null;
        if (p) { await api.send('PATCH', `/pregoes/${p.pregao_id}`, d); aviso('Pregão atualizado.'); pregao(p.pregao_id); }
        else { const r = await api.send('POST', '/pregoes', d); aviso('Pregão cadastrado.'); pregao(r.id); }
      } });
  }

  async function pregao(id) {
    carregando();
    try {
      const r = await api.get(`/pregoes/${id}`); const p = r.pregao;
      const prontos = r.cotacao.filter(i => i.status_item === 'REGISTRADO' && !i.em_ata);
      set(`<button class="voltar" id="vl">${ico('back')} Pregões</button>
        <div class="topo"><div><h1>Pregão ${esc(p.numero_pregao)}</h1><p class="sub">${esc(p.orgao_nome)} · ${esc(p.uf)} · ${dt(p.data_licitacao)} ${hr(p.hora_licitacao)} · ${esc(p.portal)}</p><div class="selos selos-do-topo">${selo(p.situacao, SIT[p.situacao] || 'neutro')}${selo(p.porte, 'neutro')}</div></div>
          <div class="acoes">${pode ? `<button class="ghost" id="ed">Editar dados</button><button class="primary" id="ata" ${prontos.length ? '' : 'disabled title="Nenhum item ganho (registrado) sem ata"'}>${ico('scroll')} Gerar ata / contrato</button>` : ''}${admin ? '<button class="ghost perigo" id="ex">Excluir</button>' : ''}</div></div>
        <div class="kpis">${kpi('Itens no edital', num(p.total_itens_edital), `${num(p.itens_disputados_efetivos)} disputados · ${pct(p.pct_disputa_edital)}`, 'marca')}
          ${kpi('Itens ganhos', num(p.itens_ganhos), `${pct(p.pct_vitoria_sobre_disputados)} dos disputados`, 'normal')}${kpi('Itens perdidos', num(p.itens_perdidos), '', p.itens_perdidos ? 'critico' : '')}${kpi('Valor ganho', brl(p.valor_ganho), `mínimo da empresa cotado: ${brl(p.valor_total_cotado_minimo)}`)}</div>
        <section class="secao"><div class="card"><div class="card-topo"><h2>Dados do pregão</h2></div><dl class="dados">
          <div><dt>Portal</dt><dd>${esc(p.portal)}</dd></div><div><dt>CNPJ do órgão</dt><dd>${esc(cnpjFmt(p.orgao_cnpj)) || '—'}</dd></div><div><dt>Vendedor</dt><dd>${esc(p.vendedor)}</dd></div><div><dt>Empresa</dt><dd>${esc(p.empresa)}</dd></div><div><dt>Modalidade</dt><dd>${esc(p.modalidade)}</dd></div>
          <div class="largo"><dt>Observações</dt><dd>${esc(r.dados?.observacoes) || '—'}</dd></div></dl></div></section>
        <section class="secao"><div class="card"><div class="card-topo"><h2>Cotação de itens</h2><span class="botoes-em-linha">${exportar()}${pode ? `<button class="ghost pequeno" id="ni">${ico('plus')} Adicionar item</button>` : ''}</span></div>
          ${r.cotacao.length ? `<div class="grid-wrap"><table><thead><tr><th>Item</th><th>Descrição</th><th class="num">Qtde</th><th class="num">Valor mín. da empresa (unit.)</th><th>Quem venceu</th><th class="num">Valor unit. vencedor</th><th>Status</th><th></th></tr></thead><tbody>
          ${r.cotacao.map(i => `<tr><td class="nowrap"><b>${esc(i.numero_item)}</b><br><span class="apagado">${esc(i.sku || '')}</span></td><td>${esc(i.descricao)}<br><span class="apagado">${esc([i.marca, i.modelo, i.medida].filter(Boolean).join(' · '))}</span></td><td class="num">${num(i.quantidade)}</td><td class="num">${brl(i.valor_unit_minimo)}</td>
            <td>${i.vencedor_tipo === 'PROPRIA' ? '<b>Empresa</b>' : i.vencedor_tipo === 'CONCORRENTE' ? esc(i.vencedor_nome) : i.vencedor_tipo === 'SEM_VENCEDOR' ? '<span class="apagado">Sem vencedor</span>' : '<span class="apagado">—</span>'}</td><td class="num">${brl(i.valor_unit_vencedor)}</td>
            <td>${selo(...(ST_ITEM[i.status_item] || [i.status_item, 'neutro']))}${i.em_ata ? ' ' + selo('Em ata', 'marca') : ''}</td>
            <td class="num">${pode ? `<span class="botoes-em-linha"><button class="ghost pequeno" data-res="${i.id}" ${i.em_ata ? 'disabled title="Item em ata: remova da ata para alterar"' : ''}>${ico('trophy')} Resultado</button><button class="ghost pequeno" data-edi="${i.id}">Editar</button>${!i.em_ata ? `<button class="icone" data-rm="${i.id}" aria-label="Remover item ${esc(i.numero_item)}">${ico('trash')}</button>` : ''}</span>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<div class="state"><strong>Sem itens cotados</strong>Use “Adicionar item” para lançar os itens do edital que a empresa vai disputar.</div>'}</div></section>
        <div class="duas secao"><div class="card"><div class="card-topo"><h2>Atas e contratos</h2></div>${r.atas.length ? r.atas.map(a => `<div class="anexo"><span class="ico-arquivo">${ico('scroll')}</span><div class="info"><b>${esc(a.nome_contrato)}</b><span>${esc(TIPO[a.tipo_instrumento] || '')} · fim ${a.tipo_vigencia === 'IMEDIATO' ? 'imediato' : dt(a.data_fim_vigencia)}</span></div><button class="ghost pequeno" data-ata="${a.id}">Abrir</button></div>`).join('') : '<p class="apagado">Nenhuma ata gerada.</p>'}</div>
          <div class="card"><div class="card-topo"><h2>Documentos</h2>${pode ? `<button class="ghost pequeno" id="up">${ico('clip')} Anexar</button>` : ''}</div>${listaDocs(r.documentos, '/pregoes/documentos', pode)}</div></div>`);
      $('#vl').onclick = pregoes;
      main.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => baixar(`/pregoes/${id}/exportar`, { formato: b.dataset.exp }));
      main.querySelectorAll('[data-ata]').forEach(b => b.onclick = () => ata(b.dataset.ata));
      main.querySelectorAll('[data-doc]').forEach(b => b.onclick = () => baixar(`/pregoes/documentos/${b.dataset.doc}`));
      if (pode) {
        $('#ed').onclick = () => formPregao({ ...p, ...r.dados });
        $('#ni').onclick = () => formItem(id, r.pregao);
        $('#up').onclick = () => formAnexo(`/pregoes/${id}/documentos`, DOC_PREGAO, () => pregao(id));
        const ba = $('#ata'); if (ba) ba.onclick = () => formAta(id, prontos);
        main.querySelectorAll('[data-res]').forEach(b => b.onclick = () => formResultado(r.cotacao.find(i => i.id === b.dataset.res), () => pregao(id)));
        main.querySelectorAll('[data-edi]').forEach(b => b.onclick = () => formEditarItem(r.cotacao.find(i => i.id === b.dataset.edi), () => pregao(id)));
        main.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => modal('Remover item', '<p>Remover este item da cotação? A ação fica registrada na auditoria.</p>', { ok: 'Remover', perigo: true, onOk: async () => { await api.send('DELETE', `/pregoes/itens/${b.dataset.rm}`); aviso('Item removido.'); pregao(id); } }));
        main.querySelectorAll('[data-rmdoc]').forEach(b => b.onclick = () => modal('Remover documento', '<p>Remover este anexo da lista? O arquivo físico é mantido (retenção).</p>', { ok: 'Remover', perigo: true, onOk: async () => { await api.send('DELETE', `/pregoes/documentos/${b.dataset.rmdoc}`); pregao(id); } }));
      }
      const ex = $('#ex'); if (ex) ex.onclick = () => modal('Excluir pregão', `<p>Excluir o pregão <b>${esc(p.numero_pregao)}</b>? Só é possível sem atas vinculadas.</p>`, { ok: 'Excluir', perigo: true, onOk: async () => { await api.send('DELETE', `/pregoes/${id}`); aviso('Pregão excluído.'); pregoes(); } });
    } catch (e) { erro(e, () => pregao(id)); }
  }

  const listaDocs = (docs, base, podeRm) => docs.length ? docs.map(d => `<div class="anexo"><span class="ico-arquivo">${ico('file')}</span><div class="info"><b>${esc(d.nome_arquivo)}</b><span>${esc(d.categoria)} · ${Math.max(1, Math.round(d.tamanho_bytes / 1024))} KB · ${esc(d.uploaded_by)}</span></div><button class="ghost pequeno" data-doc="${d.id}">Baixar</button>${podeRm && base.startsWith('/pregoes') ? `<button class="icone" data-rmdoc="${d.id}" aria-label="Remover documento">${ico('trash')}</button>` : ''}</div>`).join('') : '<p class="apagado">Sem documentos.</p>';

  const formAnexo = (path, cats, depois) => modal('Anexar documento', `${sel('Categoria', 'categoria', cats, cats[0][0])}<div><label>Arquivo(s) <span class="hint">PDF, imagem ou planilha</span></label><input type="file" name="arquivos" multiple required></div>`,
    { ok: 'Enviar', onOk: async (_, form) => { await api.upload(path, new FormData(form)); aviso('Documento anexado.'); depois(); } });

  /* ---- cotação: adicionar item (com sugestão de SKU do catálogo) ---- */
  function formItem(pid, p) {
    modal('Adicionar item à cotação', `<p class="nota-campo">O edital tem <b>${num(p.total_itens_edital)}</b> itens; já foram cotados <b>${num(p.itens_disputados_efetivos)}</b>.</p>
      <div class="grade-form">${campo('Nº do item', 'numero_item', '', 'text', 'required')}${campo('SKU (catálogo)', 'sku', '', 'text', 'list="skus" autocomplete="off"', 'opcional — preenche medida/marca/modelo')}<datalist id="skus"></datalist>
      ${campo('Medida', 'medida', '', 'text', 'placeholder="295/80 R22.5"')}${campo('Marca', 'marca')}${campo('Modelo', 'modelo')}${campo('Categoria', 'categoria')}
      <div class="largo">${campo('Descrição', 'descricao', '', 'text', '', 'obrigatória se não informar SKU')}</div>${campo('Quantidade', 'quantidade', '', 'number', 'min=1 required')}
      ${campo('Valor mínimo da empresa (unit., R$)', 'valor_unit_minimo', '', 'number', 'step=0.01 min=0 required', 'menor preço que a empresa aceita')}${sel('Status', 'status_item', lst(['EM_COTACAO', 'EM_DISPUTA', 'AGUARDANDO_HOMOLOGACAO']), 'EM_COTACAO')}
      <div class="largo"><label>Observações</label><textarea name="observacoes"></textarea></div></div>`,
      { largo: 'largo', aoAbrir: (_, form) => { let t; form.sku.oninput = () => { clearTimeout(t); t = setTimeout(async () => { const s = form.sku.value.trim(); if (s.length < 2) return;
          try { const r = await api.get('/catalogo/produtos', { q: s, limit: 8 }); $('#skus', form).innerHTML = r.resultados.map(c => `<option value="${esc(c.sku)}">${esc([c.medida, c.marca, c.modelo].filter(Boolean).join(' '))}</option>`).join(''); } catch { /* sugestão é opcional */ } }, 250); }; },
        onOk: async d => {
          const it = { numero_item: d.numero_item.trim(), sku: d.sku.trim() || null, medida: d.medida || null, marca: d.marca || null, modelo: d.modelo || null, categoria: d.categoria || null,
            descricao: d.descricao.trim() || null, quantidade: +d.quantidade, valor_unit_minimo: +d.valor_unit_minimo || 0, status_item: d.status_item, observacoes: d.observacoes || null };
          if (!it.sku && !it.descricao) throw new Error('Informe a descrição ou um SKU do catálogo.');
          await api.send('POST', `/pregoes/${pid}/itens`, { itens: [it] }); aviso(`Item ${it.numero_item} adicionado.`); pregao(pid);
        } });
  }

  const formEditarItem = (i, depois) => modal(`Editar item ${i.numero_item}`, `<div class="grade-form">${campo('Medida', 'medida', i.medida)}${campo('Marca', 'marca', i.marca)}${campo('Modelo', 'modelo', i.modelo)}${campo('Categoria', 'categoria', i.categoria)}
    <div class="largo">${campo('Descrição', 'descricao', i.descricao, 'text', 'required')}</div>${campo('Quantidade', 'quantidade', i.quantidade, 'number', `min=1 required ${i.em_ata ? 'readonly title="Item em ata"' : ''}`)}
    ${campo('Valor mínimo da empresa (unit., R$)', 'valor_unit_minimo', i.valor_unit_minimo, 'number', 'step=0.01 min=0 required')}<div class="largo"><label>Observações</label><textarea name="observacoes">${esc(i.observacoes || '')}</textarea></div></div>`,
    { largo: 'largo', onOk: async d => { await api.send('PATCH', `/pregoes/itens/${i.id}`, { medida: d.medida || null, marca: d.marca || null, modelo: d.modelo || null, categoria: d.categoria || null, descricao: d.descricao,
        quantidade: +d.quantidade, valor_unit_minimo: +d.valor_unit_minimo, observacoes: d.observacoes || null }); aviso('Item atualizado.'); depois(); } });

  /* ---- cotação: RESULTADO do item = quem venceu (a empresa / concorrente da lista / ninguém) ---- */
  async function formResultado(i, depois) {
    let conc;
    try { conc = (await api.get('/concorrentes')).itens; } catch (e) { return aviso(e.message, 'err'); }
    const rotulo = c => `${c.nome_abreviado} — ${cnpjFmt(c.cnpj)} (${c.municipio ? c.municipio + '/' : ''}${c.uf})`;
    const opcConc = (sel_) => `<option value="">— escolha o concorrente —</option>` + conc.map(c => `<option value="${c.id}"${c.id === sel_ ? ' selected' : ''}>${esc(rotulo(c))}</option>`).join('');
    const tem = !!i.vencedor_tipo;
    modal(`Resultado do item ${i.numero_item}`, `<p class="nota-campo">${esc(i.descricao)} · ${num(i.quantidade)} un. · valor mínimo da empresa ${brl(i.valor_unit_minimo)}</p>
      ${sel('Quem venceu o item?', 'vencedor_tipo', [...(tem ? [] : [['', '— Ainda sem resultado (só mudar o status)']]), ['PROPRIA', 'Empresa (ganhamos o item)'], ['CONCORRENTE', 'Um concorrente'], ['SEM_VENCEDOR', 'Ninguém (fracassado / deserto)']], i.vencedor_tipo || '')}
      <div data-b="sem">${sel('Status do item', 'st_sem', lst(['EM_COTACAO', 'EM_DISPUTA', 'AGUARDANDO_HOMOLOGACAO']), i.status_item)}</div>
      <div data-b="conc"><label>Concorrente vencedor</label><div class="botoes-em-linha" style="display:flex;gap:8px;align-items:flex-start"><select name="concorrente_id" style="flex:1">${opcConc(i.vencedor_concorrente_id)}</select><button type="button" class="ghost" data-novo-conc>${ico('plus')} Cadastrar concorrente</button></div>
        <p class="nota-campo" data-vazio-conc style="${conc.length ? 'display:none' : ''}">Nenhum concorrente cadastrado ainda. Se ele não está na lista, use <b>Cadastrar concorrente</b> (nome, CNPJ, município e UF).</p>${sel('Status do item', 'st_conc', lst(['PERDIDO', 'DESCLASSIFICADO', 'EM_RECURSO']), ['PERDIDO', 'DESCLASSIFICADO', 'EM_RECURSO'].includes(i.status_item) ? i.status_item : 'PERDIDO')}</div>
      <div data-b="cpx">${sel('Status do item', 'st_cpx', lst(['REGISTRADO', 'AGUARDANDO_HOMOLOGACAO', 'EM_RECURSO']), ['REGISTRADO', 'AGUARDANDO_HOMOLOGACAO', 'EM_RECURSO'].includes(i.status_item) ? i.status_item : 'REGISTRADO')}
        <p class="nota-campo">“Ganho (registrado)” é o que libera o item para virar Ata/Contrato.</p></div>
      <div data-b="valor">${campo('Valor unit. vencedor (R$)', 'valor_unit_vencedor', i.valor_unit_vencedor ?? '', 'number', 'step=0.01 min=0', '')}</div>`,
      { ok: 'Salvar resultado',
        aoAbrir: (f, form) => {
          const mostrar = () => { const t = form.vencedor_tipo.value; const on = (b, v) => { const el = $(`[data-b=${b}]`, form); el.style.display = v ? '' : 'none'; };
            on('sem', t === ''); on('conc', t === 'CONCORRENTE'); on('cpx', t === 'PROPRIA'); on('valor', t === 'PROPRIA' || t === 'CONCORRENTE');
            form.valor_unit_vencedor.required = t === 'PROPRIA'; };
          form.vencedor_tipo.onchange = mostrar; mostrar();
          $('[data-novo-conc]', form).onclick = () => formConcorrente(c => { conc.push(c); form.concorrente_id.innerHTML = opcConc(c.id); $('[data-vazio-conc]', form).style.display = 'none'; });
        },
        onOk: async (d) => {
          const t = d.vencedor_tipo, val_ = d.valor_unit_vencedor === '' ? null : +d.valor_unit_vencedor;
          const st = t === '' ? d.st_sem : t === 'PROPRIA' ? d.st_cpx : t === 'CONCORRENTE' ? d.st_conc : 'FRACASSADO';
          if (t === 'CONCORRENTE' && !d.concorrente_id) throw new Error('Escolha o concorrente na lista ou cadastre um novo.');
          if (t === 'PROPRIA' && !val_) throw new Error('Informe o valor unitário vencedor da empresa.');
          const patch = () => api.send('PATCH', `/pregoes/itens/${i.id}`, { status_item: st });
          const put = () => t && api.send('PUT', `/pregoes/itens/${i.id}/vencedor`, { vencedor_tipo: t, vencedor_concorrente_id: t === 'CONCORRENTE' ? d.concorrente_id : null, valor_unit_vencedor: t === 'SEM_VENCEDOR' ? null : val_ });
          // a ordem importa: o banco proíbe REGISTRADO com concorrente vencedor
          if (st === 'REGISTRADO') { await put(); await patch(); } else { if (st !== i.status_item) await patch(); await put(); }
          aviso('Resultado salvo.'); depois();
        } });
  }

  /* ---- cadastro de concorrente (nome, CNPJ, município, UF) ---- */
  const formConcorrente = (aoCriar) => modal('Cadastrar concorrente', `<div class="grade-form">${campo('Nome abreviado', 'nome_abreviado', '', 'text', 'required maxlength=80', 'como aparece nas listas')}${campo('Razão social', 'razao_social', '', 'text', 'required')}
    ${campo('CNPJ', 'cnpj', '', 'text', 'required placeholder="00.000.000/0000-00 ou alfanumérico"')}${campo('Município', 'municipio')}${campo('UF', 'uf', '', 'text', 'maxlength=2 required')}</div>
    <p class="nota-campo">A data/hora de cadastro é registrada automaticamente. Se o CNPJ já existir, o cadastro existente é reaproveitado.</p>`,
    { ok: 'Cadastrar', onOk: async d => { const r = await api.send('POST', '/concorrentes/cadastro-rapido', { nome_abreviado: d.nome_abreviado.trim(), razao_social: d.razao_social.trim(), cnpj: d.cnpj.trim(), municipio: d.municipio.trim(), uf: d.uf.trim().toUpperCase() });
      const c = r.concorrente; aoCriar({ id: c.id, nome_abreviado: c.nome_abreviado, razao_social: c.razao_social, cnpj: c.cnpj_clean || c.cnpj, municipio: c.municipio, uf: c.uf }); aviso('Concorrente cadastrado e selecionado.'); } });

  const formAta = (pid, prontos) => modal('Gerar ata / contrato', `<div class="grade-form"><div class="largo">${campo('Nome do instrumento', 'nome_contrato', '', 'text', 'required')}</div>${sel('Tipo', 'tipo_instrumento', Object.entries(TIPO), 'ATA_REGISTRO_PRECO')}${campo('Data do contrato', 'data_contrato', '', 'date', 'required')}
    ${sel('Vigência', 'tipo_vigencia', [['12_MESES', '12 meses'], ['6_MESES', '6 meses'], ['IMEDIATO', 'Imediato (sem prazo)'], ['PERSONALIZADO', 'Personalizada']], '12_MESES')}${campo('Fim (se personalizada)', 'data_fim_vigencia', '', 'date')}</div>
    <fieldset class="escolha"><legend>Itens ganhos disponíveis</legend>${prontos.map(i => `<label><input type="checkbox" name="it" value="${i.id}" checked> <span><b>${esc(i.numero_item)}</b> — ${esc(i.descricao)} <span class="apagado">(${num(i.quantidade)} un. × ${brl(i.valor_unit_vencedor)})</span></span></label>`).join('')}</fieldset>`,
    { largo: 'largo', ok: 'Gerar', onOk: async (d, form) => {
      const ids = [...form.querySelectorAll('input[name=it]:checked')].map(x => x.value); if (!ids.length) throw new Error('Selecione ao menos um item.');
      const r = await api.send('POST', `/pregoes/${pid}/contratos-atas`, { nome_contrato: d.nome_contrato, tipo_instrumento: d.tipo_instrumento, data_contrato: d.data_contrato, tipo_vigencia: d.tipo_vigencia, data_fim_vigencia: d.data_fim_vigencia || null, cotacao_item_ids: ids });
      aviso('Ata gerada.'); ata(r.contrato_ata_id); } });

  /* ============================ ABA 2 — ATAS E CONTRATOS ============================ */
  async function atas() {
    const f = E.atas.f; carregando();
    try {
      const [lista, ins] = await Promise.all([api.get('/atas', q(f)), api.get('/atas/insights', q({ uf: f.uf, vendedor: f.vendedor, status_vigencia: f.status_vigencia }))]);
      const k = ins.kpis || {};
      set(`<div class="topo"><div><h1>Atas e Contratos</h1><p class="sub">Vigência, saldo e consumo de cada item registrado (consumo do Portal Licitações e da planilha legada).</p></div><div class="acoes">${exportar()}</div></div>
        <div class="kpis">${kpi('Contratos ativos', num(k.contratos_ativos), `${num(k.total_itens_registrados_ativos)} itens registrados`, 'marca')}${kpi('Valor contratado (ativos)', brl(k.valor_total_itens_ativos), `${num(k.quantidade_total_itens_ativos)} unidades`, 'normal')}
          ${kpi('Consumido', brl(k.valor_consumido_ativos), 'faturado e entregue', 'normal')}${kpi('Saldo remanescente', brl(k.saldo_valor_remanescente_ativos), 'sobre o valor vigente (c/ reequilíbrio)', 'marca')}
          ${kpi('Vencem em 30 dias', num(k.itens_proximos_30_dias) + ' un.', `${brl(k.valores_proximos_30_dias)} · saldo ${brl(k.saldo_a_vencer_30_dias)}`, Number(k.itens_proximos_30_dias) ? 'atencao' : '')}${kpi('Imediatos', num(k.contratos_imediatos), brl(k.valor_contratos_imediatos))}</div>
        <div class="cabeca-do-bloco"><div><h2>Instrumentos</h2></div></div>
        <form class="filtros" id="flt"><div class="busca"><label>Buscar</label><input name="q" placeholder="Contrato, pregão ou órgão" value="${esc(f.q || '')}"></div>
          <div><label>Vigência</label><select name="status_vigencia">${opts(Object.entries(VIG).map(([a, b]) => [a, b[0]]), f.status_vigencia, 'Todas')}</select></div>
          <div><label>UF</label><input name="uf" maxlength="2" value="${esc(f.uf || '')}"></div><div><label>Vendedor</label><input name="vendedor" value="${esc(f.vendedor || '')}"></div><button class="visually-hidden">Buscar</button></form>
        ${lista.itens.length ? `<div class="grid-wrap"><table><thead><tr><th>Instrumento</th><th>Órgão</th><th>Vigência</th><th class="num">Itens</th><th class="num">Contratado</th><th class="num">Consumido</th><th class="num">Saldo</th><th>Consumo</th></tr></thead><tbody>
          ${lista.itens.map(a => `<tr class="clicavel" data-id="${a.contrato_ata_id}"><td><b>${esc(a.nome_contrato)}</b><br><span class="apagado">${esc(TIPO[a.tipo_instrumento])} · pregão ${esc(a.numero_pregao)}</span></td><td>${esc(a.orgao_nome)}<br><span class="apagado">${esc(a.uf)} · ${esc(a.vendedor)}</span></td>
            <td>${selo(...(VIG[a.status_vigencia] || [a.status_vigencia, 'neutro']))}<br><span class="apagado">${a.tipo_vigencia === 'IMEDIATO' ? 'sem prazo' : 'até ' + dt(a.data_fim_vigencia) + (a.dias_para_fim != null ? ` (${a.dias_para_fim} d)` : '')}</span></td>
            <td class="num">${num(a.itens)}</td><td class="num">${brl(a.valor_total_contratado)}</td><td class="num">${brl(a.valor_consumido)}</td><td class="num">${brl(a.saldo_valor_remanescente)}</td><td style="min-width:110px"><div class="barra"><i style="width:${Math.min(100, a.pct_consumo || 0)}%"></i></div><span class="apagado">${pct(a.pct_consumo)}</span></td></tr>`).join('')}</tbody></table></div>${paginacao(f, lista.total)}`
          : '<div class="state"><strong>Nenhuma ata ou contrato</strong>Gere uma ata a partir dos itens ganhos de um pregão (aba Pregões).</div>'}`);
      $('#flt').onsubmit = e => { e.preventDefault(); Object.assign(f, Object.fromEntries(new FormData(e.target)), { pagina: 1 }); atas(); };
      $('#flt select').onchange = () => $('#flt').requestSubmit();
      main.querySelectorAll('tr.clicavel').forEach(tr => tr.onclick = () => ata(tr.dataset.id));
      main.querySelectorAll('[data-pg]').forEach(b => b.onclick = () => { f.pagina += +b.dataset.pg; atas(); });
      main.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => baixar('/atas/exportar', { ...q(f), pagina: '', tamanho: '', formato: b.dataset.exp }));
    } catch (e) { erro(e, atas); }
  }

  async function ata(id) {
    carregando();
    try {
      const r = await api.get(`/atas/${id}`); const a = r.ata, it = r.itens;
      const tot = it.reduce((s, i) => s + Number(i.valor_total_contratado || 0), 0), cons = it.reduce((s, i) => s + Number(i.valor_consumido || 0), 0);
      const vg = VIG[it[0]?.status_vigencia] || ['—', 'neutro'];
      const nItem = Object.fromEntries(it.map(i => [i.ata_item_id, i.numero_item]));
      set(`<button class="voltar" id="vl">${ico('back')} Atas e Contratos</button>
        <div class="topo"><div><h1>${esc(a.nome_contrato)}</h1><p class="sub">${esc(TIPO[a.tipo_instrumento] || '')} · ${esc(it[0]?.orgao_nome || '')} · pregão ${esc(it[0]?.numero_pregao || '')}</p><div class="selos selos-do-topo">${selo(...vg)}</div></div>
          <div class="acoes">${exportar()}${pode ? `<button class="ghost" id="ed">Editar</button><button class="ghost" id="up">${ico('clip')} Anexar</button>` : ''}${admin ? '<button class="ghost perigo" id="exc">Excluir</button>' : ''}</div></div>
        <div class="kpis">${kpi('Contratado', brl(tot), `${it.length} itens`, 'marca')}${kpi('Consumido', brl(cons), pct(tot ? cons / tot * 100 : 0), 'normal')}${kpi('Saldo', brl(Math.max(tot - cons, 0)), '', 'normal')}${kpi('Fim da vigência', a.tipo_vigencia === 'IMEDIATO' ? 'Imediato' : dt(a.data_fim_vigencia), String(a.tipo_vigencia || '').replace('_', ' ').toLowerCase())}</div>
        <section class="secao"><div class="card"><div class="card-topo"><h2>Itens da ata</h2></div><div class="grid-wrap"><table><thead><tr><th>Item</th><th>Descrição</th><th class="num">Registrada</th><th class="num">Consumida</th><th class="num">Em processo</th><th class="num">Saldo (un.)</th><th class="num">Unit. vigente</th><th class="num">Saldo (R$)</th><th>Consumo</th></tr></thead><tbody>
          ${it.map(i => `<tr><td class="nowrap"><b>${esc(i.numero_item)}</b><br><span class="apagado">${esc(i.sku || '')}</span></td><td>${esc(i.descricao)}</td><td class="num">${num(i.qtde_registrada)}</td><td class="num">${num(i.qtde_consumida)}</td><td class="num">${num(i.qtde_em_processo)}</td><td class="num">${num(i.saldo_qtde_remanescente)}</td><td class="num">${brl(i.valor_unit_vigente)}</td><td class="num">${brl(i.saldo_valor_remanescente)}</td><td style="min-width:100px"><div class="barra"><i style="width:${Math.min(100, i.pct_consumo || 0)}%"></i></div><span class="apagado">${pct(i.pct_consumo)}</span></td></tr>`).join('')}</tbody></table></div></div></section>
        <div class="duas secao"><div class="card"><div class="card-topo"><h2>Consumo (histórico)</h2></div>${r.consumo.length ? `<ol class="fluxo">${r.consumo.map(c => `<li class="passo sucesso"><div class="quando">${esc(c.origem)} · ${esc(c.ref)} · item ${esc(nItem[c.ata_item_id] || '')}</div><div class="titulo">${num(c.quantidade)} un. · ${brl(c.valor_total)}</div><div class="quem">${esc(c.status_entrega)}</div></li>`).join('')}</ol>` : '<p class="apagado">Sem consumo registrado. O consumo chega do Portal Licitações (pedidos vinculados) ou da carga das planilhas.</p>'}</div>
          <div class="card"><div class="card-topo"><h2>Documentos</h2></div>${listaDocs(r.documentos, '/atas/documentos', false)}</div></div>`);
      $('#vl').onclick = atas;
      main.querySelectorAll('[data-exp]').forEach(b => b.onclick = () => baixar(`/atas/${id}/exportar`, { formato: b.dataset.exp }));
      main.querySelectorAll('[data-doc]').forEach(b => b.onclick = () => baixar(`/atas/documentos/${b.dataset.doc}`));
      if (pode) {
        $('#ed').onclick = () => modal('Editar instrumento', `<div class="grade-form"><div class="largo">${campo('Nome', 'nome_contrato', a.nome_contrato, 'text', 'required')}</div>${campo('Data do contrato', 'data_contrato', String(a.data_contrato || '').slice(0, 10), 'date')}${sel('Vigência', 'tipo_vigencia', [['12_MESES', '12 meses'], ['6_MESES', '6 meses'], ['IMEDIATO', 'Imediato'], ['PERSONALIZADO', 'Personalizada']], a.tipo_vigencia)}${campo('Fim (personalizada)', 'data_fim_vigencia', String(a.data_fim_vigencia || '').slice(0, 10), 'date')}</div>`,
          { onOk: async d => { if (!d.data_fim_vigencia) delete d.data_fim_vigencia; await api.send('PATCH', `/atas/${id}`, d); aviso('Instrumento atualizado.'); ata(id); } });
        $('#up').onclick = () => formAnexo(`/atas/${id}/documentos`, DOC_ATA, () => ata(id));
      }
      const ex = $('#exc'); if (ex) ex.onclick = () => modal('Excluir instrumento', `<p>Excluir <b>${esc(a.nome_contrato)}</b>? Os itens voltam a ficar disponíveis no pregão.</p>`, { ok: 'Excluir', perigo: true, onOk: async () => { await api.send('DELETE', `/atas/${id}`); aviso('Instrumento excluído.'); atas(); } });
    } catch (e) { erro(e, () => ata(id)); }
  }

  return { abrir: aba => (aba === 'atas' ? atas() : pregoes()), pregoes, atas };
}
