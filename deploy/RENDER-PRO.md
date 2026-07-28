# Deploy no Render Pro (Playwright online)

Guia para rodar **upload + automação Playwright** no Render, sem depender do PC.

## 1. Assinar Render Pro

1. Acesse [render.com](https://render.com) → seu serviço **enriquecimento-nio**
2. **Settings → Instance Type** → escolha **Pro** com **pelo menos 2 GB RAM** (Chromium precisa disso)
3. Confirme o upgrade (cobrança mensal)

> O `render.yaml` do repo já está com `plan: pro` e `PLAYWRIGHT_ENABLED=True`.

---

## 2. Variável secreta — sessão Google

A automação precisa estar logada no Google My Maps. Gere no **PC**:

```bash
pip install -r requirements-local.txt
python manage.py salvar_sessao_google --cdp http://127.0.0.1:9222
```

Isso cria `playwright/google-auth.json`.

No **Render Dashboard** → serviço web → **Environment**:

| Variável | Valor |
|----------|--------|
| `PLAYWRIGHT_STORAGE_STATE_JSON` | Cole o **conteúdo inteiro** do `google-auth.json` (uma linha JSON) |

Marque como **Secret** e salve.

O app grava esse JSON em disco na inicialização (`mailing/apps.py`).

---

## 3. Deploy

Faça push do código ou **Manual Deploy** no Render. O `build.sh` vai:

- Instalar Playwright + Chromium (`playwright install --with-deps`)
- Rodar `collectstatic` e `migrate`

Build pode demorar alguns minutos na primeira vez (download do Chromium).

---

## 4. Testar

1. Abra `https://mailing-enderecos.onrender.com` (ou seu domínio)
2. Upload de planilha
3. **Abrir Google My Maps** → deve iniciar automação no servidor

Logs: Render → **Logs** → filtre por erros Playwright.

---

## 5. Renovar sessão Google

Quando a sessão expirar:

1. Rode `salvar_sessao_google` de novo no PC
2. Atualize `PLAYWRIGHT_STORAGE_STATE_JSON` no Render
3. **Redeploy** ou restart do serviço

---

## Checklist rápido

- [ ] Plano Pro com **≥ 2 GB RAM**
- [ ] `PLAYWRIGHT_ENABLED=True` (já no render.yaml)
- [ ] `PLAYWRIGHT_STORAGE_STATE_JSON` configurado no painel
- [ ] Deploy concluído sem erro no build
- [ ] Upload + botão do mapa funcionando

---

## Render free vs Pro

| | Free | Pro |
|---|------|-----|
| Upload planilha | Sim | Sim |
| Playwright | Não | Sim |
| RAM mínima | 512 MB | Escolha ≥ 2 GB |
| Sempre online | Não (dorme) | Sim |

## VPS Docker

Se no futuro quiser migrar, o deploy Docker está em `deploy/DEPLOY.md`.
