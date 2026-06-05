# 📄 Chatea con tus PDFs (RAG)

Aplicación full‑stack que te deja **subir PDFs y hacerles preguntas en lenguaje natural**. Las respuestas las genera **Claude** usando *solo* el contenido de tus documentos, y siempre cita las fuentes (documento + página). Es un proyecto de portafolio diseñado para **desplegarse gratis** en un único servicio.

> **Stack:** FastAPI · Voyage AI (embeddings) · Qdrant Cloud (vector DB) · Anthropic Claude (generación) · HTML/CSS/JS vanilla con streaming por SSE.

---

## ¿Qué es RAG y cómo funciona aquí?

**RAG** (*Retrieval‑Augmented Generation*) le da al LLM información que no tiene en sus pesos: recupera los fragmentos relevantes de tus documentos y se los pasa como contexto para que responda con base en ellos en vez de "alucinar".

```
                          INGESTA (POST /documents)
  ┌────────┐   pypdf    ┌──────────┐  chunking   ┌──────────┐  Voyage AI   ┌──────────┐
  │  PDF   │ ─────────▶ │  texto   │ ──────────▶ │  chunks  │ ───────────▶ │ vectores │
  └────────┘  por pág.  │ + páginas│  ~800 tok   │ +metadata│  embeddings  └────┬─────┘
                        └──────────┘  100 overlap └──────────┘                   │ upsert
                                                                                 ▼
                                                                         ┌───────────────┐
                                                                         │  Qdrant Cloud │
                                                                         │  (vector DB)  │
                                                                         └───────┬───────┘
                          CONSULTA (POST /chat)                                  │
  ┌──────────┐  Voyage   ┌──────────┐   búsqueda top‑k (similitud coseno)        │
  │ pregunta │ ────────▶ │ embedding│ ◀──────────────────────────────────────────┘
  └──────────┘  (query)  └────┬─────┘
                              │  chunks recuperados + metadata
                              ▼
                        ┌──────────────┐  prompt con contexto   ┌──────────┐
                        │ construir    │ ─────────────────────▶ │  Claude  │
                        │ prompt RAG   │   "responde solo con   │ (stream) │
                        └──────────────┘    el contexto, cita"  └────┬─────┘
                                                                     ▼
                                          respuesta + citas (documento, página) ──▶ frontend
```

**Flujo en 4 pasos:** `ingesta → embedding → retrieval → generación`.

---

## Características

- **Ingesta de varios PDFs** a la vez (drag & drop) con feedback de progreso.
- **Chunking con overlap** (~800 tokens / 100 de solapamiento) y metadata por chunk: documento, página, índice.
- **Embeddings en batch** con Voyage AI (`input_type` distinto para documentos y consultas).
- **Retrieval top‑k** con filtro opcional por documento y umbral de similitud para descartar ruido.
- **Respuestas citadas**: el modelo cita `[n]` y el frontend muestra la fuente (documento + página + snippet).
- **Anti‑alucinación**: si no hay contexto relevante, Claude lo dice en vez de inventar.
- **Streaming** de la respuesta token a token vía Server‑Sent Events.
- **Manejo de errores** consistente: PDF corrupto/escaneado/protegido, archivo muy grande, fallo de API externa, sin resultados.
- **Un solo servicio**: FastAPI sirve la API *y* el frontend estático → deploy gratis simple.
- **Docs automáticas** en `/docs` (Swagger) y `/redoc`.

---

## Estructura del proyecto

```
CHATBOT/
├── app/
│   ├── main.py              # FastAPI: routers + sirve el frontend estático
│   ├── config.py            # Configuración tipada desde variables de entorno
│   ├── schemas.py           # Modelos Pydantic (validación + docs)
│   ├── routers/
│   │   ├── documents.py     # POST / GET / DELETE de documentos
│   │   └── chat.py          # POST /chat (RAG, con streaming SSE)
│   └── services/
│       ├── pdf.py           # Extracción de texto + chunking con páginas
│       ├── embeddings.py    # Cliente de Voyage AI
│       ├── vectorstore.py   # Cliente de Qdrant (index/search/list/delete)
│       └── llm.py           # Cliente de Anthropic + construcción del prompt
├── static/                  # Frontend (HTML + CSS + JS vanilla)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── requirements.txt
├── Dockerfile
├── render.yaml              # Deploy en Render (un servicio)
├── .env.example
└── README.md
```

---

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/documents` | Sube uno o varios PDFs e indexa sus chunks. |
| `GET` | `/documents` | Lista los documentos ingeridos (páginas, chunks). |
| `DELETE` | `/documents/{id}` | Borra un documento y todos sus vectores en Qdrant. |
| `POST` | `/chat` | Pregunta al RAG. `stream=true` → SSE; `stream=false` → JSON. |
| `GET` | `/health` | Healthcheck. |
| `GET` | `/docs` | Documentación interactiva (Swagger UI). |

**Ejemplo de `/chat` (no streaming):**

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Cuál es la conclusión del informe?", "stream": false}'
```

```jsonc
{
  "answer": "Según el documento, la conclusión es… [1][2]",
  "citations": [
    { "filename": "informe.pdf", "page": 12, "score": 0.78, "snippet": "…" }
  ]
}
```

---

## Cómo conseguir las API keys (todas tienen tier gratis)

1. **Anthropic (Claude)** → <https://console.anthropic.com> → *Settings → API Keys → Create Key*. Variable: `ANTHROPIC_API_KEY`.
2. **Voyage AI (embeddings)** → <https://dashboard.voyageai.com> → crea una cuenta y una API key (incluye tokens gratis). Variable: `VOYAGE_API_KEY`.
3. **Qdrant Cloud (vector DB)** → <https://cloud.qdrant.io> → crea un **cluster gratis (1 GB)** → copia la **URL** del cluster (termina en `:6333`) y genera una **API key**. Variables: `QDRANT_URL`, `QDRANT_API_KEY`.

> La colección en Qdrant se crea automáticamente la primera vez que subes un PDF.

---

## Correr en local

Requisitos: **Python 3.11+**.

```bash
# 1. Clonar y entrar al proyecto
cd CHATBOT

# 2. Entorno virtual
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Dependencias
pip install -r requirements.txt

# 4. Configurar claves
cp .env.example .env               # y rellena tus keys

# 5. Levantar el servidor (con autoreload)
uvicorn app.main:app --reload
```

Abre **<http://localhost:8000>** para la interfaz y **<http://localhost:8000/docs>** para la API.

---

## Desplegar gratis

La app es **un solo servicio** (FastAPI sirve también el frontend), así que el hosting gratuito es directo.

### Opción A — Render (recomendada, incluye `render.yaml`)

1. Sube el repo a GitHub.
2. En <https://render.com> → *New → Blueprint* y selecciona el repo (detecta `render.yaml`).
3. En el dashboard, añade los *secrets* marcados como `sync: false`: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`.
4. Deploy. Render asigna el puerto vía `$PORT` (ya contemplado en el `startCommand`).

> Sin blueprint: *New → Web Service* · Build `pip install -r requirements.txt` · Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

### Opción B — Railway

1. *New Project → Deploy from GitHub repo*.
2. Railway detecta el `Dockerfile` (o usa Nixpacks). Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Añade las variables de entorno en *Variables*.

### Frontend separado (opcional)

No es necesario, pero si quieres servir el frontend aparte (Vercel/Netlify), publica la carpeta `static/` y apunta las llamadas `fetch` de `app.js` a la URL del backend (cambia la constante `API`). Recuerda habilitar **CORS** en FastAPI en ese caso.

---

## Notas de diseño

- **Citas precisas por página:** durante el chunking se mantiene un mapa de offsets→página, así cada chunk conserva su número de página real aunque el texto cruce fronteras de página.
- **Sin base de datos extra:** la lista de documentos se deriva agregando los payloads de Qdrant, manteniendo el deploy en un único servicio.
- **Tokenización aproximada:** se estima ~4 caracteres por token para evitar dependencias pesadas (tiktoken); suficiente para un proyecto de portafolio. Los tamaños de chunk son configurables por entorno.
- **Modelos configurables:** `ANTHROPIC_MODEL` y `VOYAGE_MODEL` se cambian por variable de entorno sin tocar el código. Si cambias el modelo de embeddings, ajusta `EMBEDDING_DIM`.

---

## Posibles mejoras

- Reranking de los chunks recuperados.
- Memoria conversacional (historial multi‑turno en el prompt).
- Soporte de OCR para PDFs escaneados.
- Autenticación y multi‑usuario (colecciones/namespaces por usuario en Qdrant).
