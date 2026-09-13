# AutoChain

**Recuperación de vehículos robados con IA y recompensas en stablecoin, sobre HSK Chain.**

Bolivia registra ~3,500 denuncias de robo vehicular al año, y el 64% de esos vehículos nunca se localiza. AutoChain convierte la búsqueda colaborativa de vehículos robados en un mercado de incentivos transparente: cualquier persona puede aportar una pista o foto, un modelo de IA valida qué tan útil es esa evidencia, y el propietario paga una recompensa en stablecoin directamente al colaborador a través de un contrato en HSK Chain — sin intermediarios y sin depender de que el colaborador tenga cuenta bancaria.

> Proyecto construido para el **Buildathon Ethereum Bolivia 2026 — HSK Chain Track** (Payments / RWA / AI × Web3).

**Demo en vivo:**
- Frontend: https://autochain-hsk.vercel.app
- API (Supabase en producción): https://autochain-hsk-api.vercel.app

La validación de IA (CLIP) **no está activa en producción todavía**: torch/CLIP (~350MB) no cabe en el límite de una función serverless de Vercel, así que necesita un servicio aparte. El código ya soporta apuntar a uno vía `AI_SERVICE_URL` o `HF_API_TOKEN` (ver `backend/main.py`), pero ese servicio externo aún no quedó desplegado — se probó localmente (`ai_matching_service.py`, con métricas y umbrales reales) y ese es el video/demo de respaldo. En producción, cada pista se registra igual, pero queda marcada como `ai_unavailable: true` hasta que el servicio de IA esté en línea.

## Cómo funciona

0. **Verifica tu identidad (KYC)** — paso independiente y único por wallet: nombre + foto de la cédula. Se hace una sola vez y habilita registrar/reportar cualquier cantidad de vehículos después.
1. **Reporta** — el propietario registra su vehículo (foto de referencia + datos del auto).
2. **Publica** — al reportar el robo, se abre un caso y se bloquea la recompensa en stablecoin dentro del contrato.
3. **Colabora** — cualquier persona sube fotos/pistas del vehículo en tiempo real.
4. **Valida** — un servicio de IA (embeddings CLIP) compara la foto de la pista contra la foto de referencia y asigna un nivel de evidencia.
5. **Colabora (recompensa)** — según el nivel de evidencia, el contrato libera el porcentaje correspondiente de la recompensa al colaborador.

| Acción del colaborador | Evidencia | Validación IA | Recompensa |
|---|---|---|---|
| Información útil | Pista o dato clave | Filtrado de coherencia | Parcial (10%) |
| Evidencia clave | Foto/video nítido | Coincidencia de imagen | Mayor porcentaje (30%) |
| Recuperación efectiva | Ayuda decisiva | Confirmación manual de recuperación | Total (60% restante) |

## Arquitectura

```
frontend/            → UI de una sola página (registro, reporte, pistas, estado de recompensa)
backend/main.py       → API que orquesta casos, pistas y pagos on-chain
backend/ai_matching_service.py → microservicio de similitud de imagen (CLIP)
contracts/AutoChainReward.sol  → escrow de recompensa por niveles, en stablecoin, sobre HSK Chain
scripts/deploy.js     → despliegue del contrato con Hardhat
```

**Por qué esta arquitectura:**
- El **hash** de los documentos KYC y de la evidencia va on-chain (trazabilidad, sin exponer datos sensibles); las imágenes y datos personales viven off-chain.
- La **validación de IA es off-chain** (rápida, iterable) y solo el **resultado** (tier) se relaya on-chain por una wallet validadora — la hoja de ruta reemplaza esto por un oráculo/multi-sig descentralizado.
- El **pago es en stablecoin** para que la recompensa tenga valor estable y pueda cobrarla cualquier persona con una wallet, sin necesidad de cuenta bancaria — clave en un contexto de economía informal.

## Instalación y ejecución

### 1. Contrato (Hardhat)

```bash
npm install
cp .env.example .env   # completa PRIVATE_KEY, HSK_*_RPC_URL, STABLECOIN_ADDRESS
npm run compile
npm run deploy:hsk-testnet
```

Copia la dirección del contrato desplegado en `.env` como `AUTOCHAIN_CONTRACT_ADDRESS`, y registra la wallet validadora con `asignarValidador(address, true)`.

### 2. Base de datos (Supabase, gratis)

1. Crea un proyecto en [supabase.com](https://supabase.com).
2. En **SQL Editor**, corre `backend/supabase_schema.sql` (crea las tablas `users`, `vehicles`, `cases`, `tips`).
3. En **Project Settings → API**, copia el **Project URL** y la **secret key** a `.env` como `SUPABASE_URL` y `SUPABASE_SECRET_KEY`.
4. Los buckets de almacenamiento (`vehicle-photos` público, `ownership-documents` y `owner-id-photos` privados) se crean automáticamente la primera vez que corre el backend.

### 3. Validación de IA (matching de imágenes)

Por defecto, `backend/main.py` llama al Inference API de Hugging Face (gratis) para comparar la foto de la pista contra la foto de referencia — no hace falta correr nada aparte. Solo crea un token en https://huggingface.co/settings/tokens (con el permiso **"Make calls to Inference Providers"** activado) y ponlo en `.env` como `HF_API_TOKEN`.

Si prefieres correr el modelo tú mismo en local (por ejemplo, sin depender de un servicio externo):

```bash
cd backend
pip install -r requirements.txt -r requirements-ai.txt
uvicorn ai_matching_service:app --reload --port 8001
```

y define `AI_SERVICE_URL=http://localhost:8001/match` en `.env` para que `main.py` lo use en vez de Hugging Face. (`requirements-ai.txt` trae torch/CLIP, separado del resto porque la API principal —y su despliegue en Vercel— no los necesita.)

### 4. API principal

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 5. Frontend

Abre `frontend/index.html` en el navegador (o sírvelo con cualquier servidor estático). Si tu API no corre en `localhost:8000`, define `window.AUTOCHAIN_API_BASE` antes de cargar el script.

## Despliegue (Vercel)

Frontend y API se despliegan como dos proyectos de Vercel separados (cada uno desde su propia carpeta):

```bash
cd frontend && vercel deploy --prod   # sitio estático + cabeceras de seguridad (vercel.json)
cd backend  && vercel deploy --prod   # API FastAPI como función serverless (backend/api/index.py)
```

En el proyecto del backend, configura como variables de entorno de producción: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `AUTOCHAIN_CONTRACT_ADDRESS`, `VALIDATOR_PRIVATE_KEY`, `STABLECOIN_ADDRESS`, `HSK_RPC_URL` (con `vercel env add <NOMBRE> production`). Agrega `AI_SERVICE_URL` o `HF_API_TOKEN` una vez que el servicio de IA esté desplegado (ver nota arriba) — sin eso, el backend sigue funcionando pero no puntúa pistas automáticamente.

## Enfoque de integración técnica

- **HSK Chain**: el contrato `AutoChainReward.sol` se despliega en HSK Chain (testnet para el hackathon; mainnet-ready) y custodia el stablecoin de cada caso hasta su liberación por tiers.
- **IA**: `open_clip` (ViT-B-32, pesos preentrenados) para embeddings de imagen — sin entrenamiento propio, priorizando velocidad de desarrollo y resultados verificables en vivo.
- **Stablecoin**: cualquier ERC-20 compatible desplegado en HSK Chain (mock USDT/USDC en testnet).

## Roadmap

- Reemplazar el relayer manual por un oráculo descentralizado que dispare `pagarRecompensaColaborador` automáticamente al superar el umbral de similitud.
- Verificación automática de la cédula subida en el KYC (hoy solo se guarda para revisión manual del validador) vía un proveedor externo de identidad.
- Mecanismo de stake para colaboradores (reduce spam/pistas falsas).
- Integración con aseguradoras y la Policía Boliviana para verificación oficial de recuperación.
- Expansión a otros países de la región con altos índices de robo vehicular.

## Licencia

MIT
