# Persistência, histórico em banco e handoff para agentes

## O que já existia no MiroFish

- **Projetos:** `backend/uploads/projects/<project_id>/project.json` e ficheiros associados.
- **Simulações:** `backend/uploads/simulations/<simulation_id>/` (`state.json`, perfis, configs, SQLite OASIS por simulação, etc.).
- **Relatórios:** `backend/uploads/reports/<report_id>/`.
- **Grafo Zep:** na nuvem (conta Zep), não no teu disco.

A pasta `backend/uploads/` está no `.gitignore`: **um `git commit` normal não leva os dados da simulação**, só o código.

## Índice em SQLite (novo)

Cada vez que a UI (ou qualquer cliente) chama **`GET /api/simulation/history`**, o backend:

1. Monta a lista enriquecida a partir do disco (como antes).
2. **Grava um snapshot** na base SQLite:

**Ficheiro por defeito:** `backend/instance/mirofish_history.sqlite`

3. **Copia sempre** (por defeito) para a pasta do projeto: **`backups/history_index/`** na raiz do repositório — `mirofish_history.sqlite` + `mirofish_history_manifest.json` (ficheiros gerados localmente; ignorados pelo Git por conterem caminhos absolutos).

Para desativar esta cópia: `MIROFISH_DISABLE_PROJECT_BACKUP=true`. Para mudar a pasta: `MIROFISH_PROJECT_BACKUP_DIR=/outro/caminho`. Snapshots com data na pasta do projeto: `MIROFISH_PROJECT_BACKUP_VERSIONED=true`.

Cada linha guarda o JSON completo do cartão de histórico (`payload_json`), incluindo `simulation_id`, `project_id`, `report_id`, requisito da simulação, ficheiros, etc.

### Ler só a partir do banco

- **`GET /api/simulation/history/persisted?limit=50`** — devolve os registos do último snapshot, mais `db_path` com o caminho absoluto do ficheiro.

Útil para **agentes** ou scripts que só precisam dos IDs e metadados sem revarrer pastas.

### Variável de ambiente

- **`HISTORY_INDEX_DB_PATH`** — caminho absoluto alternativo para o ficheiro `.sqlite`.

## O que “continuar depois” realmente precisa

| Objetivo | O que guardar |
|----------|----------------|
| Voltar às mesmas URLs (`/report/...`, `/interaction/...`) | Snapshot SQLite **e** cópia de `backend/uploads/` (ou o mesmo volume em Docker). |
| Só lembrar IDs para conversar com um agente | Basta o ficheiro **`mirofish_history.sqlite`** depois de abrires a home (ou chamares `/api/simulation/history` uma vez). |
| Grafo e memória de longo prazo | Conta **Zep** (chave no `.env`). |

## Versionar o SQLite no Git (opcional)

Por defeito, **`backend/instance/mirofish_history.sqlite`** pode ser ignorado pelo Git (evita binários e dados pessoais no remoto). Se quiseres **commitar um snapshot só para ti**:

```bash
git add -f backend/instance/mirofish_history.sqlite
```

Alternativa: copiar o `.sqlite` para um sítio fora do repo ou usar backup em nuvem.

## Rota de exemplo (interação)

Com `report_id` no índice, a rota de UI é:

`/interaction/<reportId>` — por exemplo `http://localhost:3000/interaction/report_e951c8f2625a`.

Os mesmos IDs aparecem no JSON de `/api/simulation/history` e no SQLite.

## Cópia externa automática (índice SQLite)

Define no `.env`:

```env
MIROFISH_EXTERNAL_BACKUP_DIR=/caminho/absoluto/para/pasta
# opcional: guardar também cópias com data em .../snapshots/
MIROFISH_EXTERNAL_BACKUP_VERSIONED=true
```

Sempre que o backend grava o índice (após **`GET /api/simulation/history`**), copia:

- `mirofish_history.sqlite` — ficheiro atual (substitui o anterior)
- `mirofish_history_manifest.json` — `synced_at`, número de linhas, caminhos

Se `MIROFISH_EXTERNAL_BACKUP_VERSIONED=true`, grava ainda `snapshots/mirofish_history_<timestamp>.sqlite`.

A pasta pode ser um **disco externo** ou uma **pasta sincronizada** (Dropbox, iCloud Drive, etc.). Isto copia só o **índice**, não a pasta `uploads/` completa.

## Segurança

- **Nunca** commits com chaves em `.env` ou em `.env.example`. Usa sempre placeholders no exemplo.
