# AutoChain

**Recuperación de vehículos robados con IA y recompensas en stablecoin, sobre HSK Chain.**

Bolivia registra ~3,500 denuncias de robo vehicular al año, y el 64% de esos vehículos nunca se localiza. AutoChain convierte la búsqueda colaborativa de vehículos robados en un mercado de incentivos transparente: cualquier persona puede aportar una pista o foto, un modelo de IA valida qué tan útil es esa evidencia, y el propietario paga una recompensa en stablecoin directamente al colaborador a través de un contrato en HSK Chain — sin intermediarios y sin depender de que el colaborador tenga cuenta bancaria.

> Proyecto construido para el **Buildathon Ethereum Bolivia 2026 — HSK Chain Track** (Payments / RWA / AI × Web3).

## Cómo funciona

1. **Reporta** — el propietario registra su vehículo (verificación KYC simplificada + foto de referencia).
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

Copia la dirección del contrato desplegado en `.env` como `AUTOCHAIN_CONTRACT_ADDRESS`, y registra la wallet validadora con `setValidator(address, true)`.

### 2. Servicio de IA

```bash
cd backend
pip install -r requirements.txt
uvicorn ai_matching_service:app --reload --port 8001
```

### 3. API principal

```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Frontend

Abre `frontend/index.html` en el navegador (o sírvelo con cualquier servidor estático). Si tu API no corre en `localhost:8000`, define `window.AUTOCHAIN_API_BASE` antes de cargar el script.

## Enfoque de integración técnica

- **HSK Chain**: el contrato `AutoChainReward.sol` se despliega en HSK Chain (testnet para el hackathon; mainnet-ready) y custodia el stablecoin de cada caso hasta su liberación por tiers.
- **IA**: `open_clip` (ViT-B-32, pesos preentrenados) para embeddings de imagen — sin entrenamiento propio, priorizando velocidad de desarrollo y resultados verificables en vivo.
- **Stablecoin**: cualquier ERC-20 compatible desplegado en HSK Chain (mock USDT/USDC en testnet).

## Roadmap

- Reemplazar el relayer manual por un oráculo descentralizado que dispare `rewardTip` automáticamente al superar el umbral de similitud.
- KYC real vía proveedor externo (ej. verificación de cédula + selfie) en vez del hash de demo.
- Mecanismo de stake para colaboradores (reduce spam/pistas falsas).
- Integración con aseguradoras y la Policía Boliviana para verificación oficial de recuperación.
- Expansión a otros países de la región con altos índices de robo vehicular.

## Licencia

MIT
