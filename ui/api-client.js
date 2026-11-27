/* Cliente HTTP da API /api/v1. No site real, o colega troca SÓ este arquivo pelo cliente que o hub já usa
 * (mesma sessão/cookie/token). Contrato esperado por pregoes-atas.js: { base, get, send, upload, baixar }.
 *   get(path, params)            -> JSON
 *   send(método, path, corpo)    -> JSON | null (204)
 *   upload(path, FormData)       -> JSON
 *   baixar(path, params)         -> dispara o download de planilha/anexo
 * Erros: lança Error(mensagem em português) — a mensagem vem de {"detail": "..."} (FastAPI). */
export function criarApi({ base = '/api/v1', headers = () => ({}) } = {}) {
  const qs = p => { const u = new URLSearchParams(); Object.entries(p || {}).forEach(([k, v]) => v !== '' && v != null && u.set(k, v)); const s = u.toString(); return s ? '?' + s : ''; };
  const msg = (d, status) => {
    const x = d && (d.detail ?? d.erro);
    if (typeof x === 'string') return x;
    if (Array.isArray(x)) return x.map(e => `${(e.loc || []).slice(1).join('.')}: ${e.msg}`).join(' · ');   // validação do FastAPI
    return `Erro ${status}`;
  };
  async function req(method, path, { params, body, form } = {}) {
    const h = { ...headers() };
    let corpo;
    if (form) corpo = form; else if (body !== undefined) { h['Content-Type'] = 'application/json'; corpo = JSON.stringify(body); }
    let r;
    try { r = await fetch(base + path + qs(params), { method, headers: h, body: corpo, credentials: 'same-origin' }); }
    catch { throw new Error('Sem conexão com o servidor. Verifique se a API está no ar.'); }
    if (r.status === 204) return null;
    const json = (r.headers.get('content-type') || '').includes('json');
    const dados = json ? await r.json() : null;
    if (!r.ok) throw new Error(msg(dados, r.status));
    return dados;
  }
  return {
    base, modo: 'api',
    get: (path, params) => req('GET', path, { params }),
    send: (method, path, body) => req(method, path, { body }),
    upload: (path, form) => req('POST', path, { form }),
    async baixar(path, params) {
      let r;
      try { r = await fetch(base + path + qs(params), { headers: { ...headers() }, credentials: 'same-origin' }); }
      catch { throw new Error('Sem conexão com o servidor.'); }
      if (!r.ok) { let d = null; try { d = await r.json(); } catch { /* corpo não-JSON */ } throw new Error(msg(d, r.status)); }
      const cd = r.headers.get('content-disposition') || '';
      const nome = decodeURIComponent((cd.match(/filename\*=UTF-8''([^;]+)/) || [])[1] || 'arquivo');
      salvarBlob(await r.blob(), nome);
    }
  };
}

export function salvarBlob(blob, nome) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: nome });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
}
