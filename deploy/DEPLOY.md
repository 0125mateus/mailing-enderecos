# Deploy na VPS (tudo online + Playwright)

Guia para rodar o **Enriquecimento NIO** numa VPS com automação Playwright, sem depender do seu PC.

## O que você precisa

| Item | Recomendação |
|------|----------------|
| VPS | Hetzner CX22 (2 GB RAM) ou DigitalOcean Droplet $12 (2 GB) |
| SO | Ubuntu 22.04 ou 24.04 |
| Domínio | Apontando o registro A para o IP da VPS |
| Sessão Google | Arquivo `google-auth.json` gerado no PC |

**Mínimo de RAM:** 2 GB (Playwright + Chromium + Django).

---

## Passo 1 — Criar a VPS

1. Crie uma VM Ubuntu na [Hetzner](https://www.hetzner.com/cloud) ou [DigitalOcean](https://www.digitalocean.com/).
2. Anote o **IP público**.
3. No seu provedor de domínio, crie um registro **A**:
   - `mailing.seudominio.com.br` → IP da VPS

---

## Passo 2 — Instalar na VPS

Conecte via SSH:

```bash
ssh root@SEU_IP
```

Clone e rode o script de setup:

```bash
git clone https://github.com/0125mateus/mailing-enderecos.git /opt/mailing-enderecos
cd /opt/mailing-enderecos
cp deploy/env.vps.example .env
nano .env
```

Edite o `.env`:

- `DOMAIN` — seu domínio (ex.: `mailing.seudominio.com.br`)
- `SECRET_KEY` — chave aleatória longa
- `POSTGRES_PASSWORD` — senha forte
- `DATABASE_URL` — use a **mesma senha** do Postgres
- `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` — seu domínio

Depois:

```bash
sudo bash deploy/setup-vps.sh
```

Ou manualmente:

```bash
docker compose up -d --build
```

O site ficará em **https://SEU_DOMINIO** (HTTPS automático via Caddy).

---

## Passo 3 — Sessão Google (obrigatório para automação)

No **seu PC**, com Chrome instalado:

```bash
pip install -r requirements-local.txt
python manage.py salvar_sessao_google --cdp http://127.0.0.1:9222
```

(Abra o Chrome antes com remote debugging — veja `python manage.py salvar_sessao_google --help`)

Isso gera `playwright/google-auth.json`.

### Enviar para a VPS

**Opção A — arquivo (recomendado):**

No PC (PowerShell ou terminal), na pasta do projeto:

```bash
scp playwright/google-auth.json root@SEU_IP:/opt/mailing-enderecos/playwright/google-auth.json
```

Na VPS:

```bash
cd /opt/mailing-enderecos
docker compose restart web
```

**Opção B — variável de ambiente:**

No `.env` da VPS, adicione o JSON em uma linha:

```env
PLAYWRIGHT_STORAGE_STATE_JSON={"cookies":[...],"origins":[...]}
```

Reinicie:

```bash
docker compose up -d --build
```

---

## Passo 4 — Testar

1. Acesse `https://SEU_DOMINIO`
2. Faça upload de uma planilha
3. Clique em **Abrir Google My Maps** — deve iniciar a automação Playwright no servidor

Logs:

```bash
cd /opt/mailing-enderecos
docker compose logs -f web
```

---

## Comandos úteis

```bash
# Atualizar após git pull
docker compose up -d --build

# Parar
docker compose down

# Ver status
docker compose ps
```

---

## Renovar sessão Google

A sessão expira periodicamente. Quando a automação falhar por login:

1. Rode `salvar_sessao_google` de novo no PC
2. Reenvie o `google-auth.json` para a VPS
3. `docker compose restart web`

---

## Render vs VPS

| | Render (free) | VPS (Docker) |
|---|---------------|--------------|
| Upload planilha | Sim | Sim |
| Playwright | Não | Sim |
| Depende do PC | Sim (automação) | Não |
| Custo | Grátis | ~€4–6/mês |

Você pode manter o Render como backup ou migrar o DNS para a VPS.
