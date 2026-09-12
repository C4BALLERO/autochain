# AutoChain — Contexto del proyecto para Claude Code

Este documento es el contexto completo del proyecto AutoChain. Pégalo (o apunta a él) al iniciar una sesión de Claude Code para que tenga toda la información sin que tengas que re-explicarla.

---

## 1. Qué es AutoChain

AutoChain es un sistema de recuperación de vehículos robados que combina:
- **Registro y reporte** de vehículos (KYC simplificado).
- **Colaboración ciudadana**: cualquier persona sube fotos/pistas de un vehículo robado.
- **Validación por IA**: comparación de imágenes (embeddings CLIP) entre la foto de referencia del vehículo y la evidencia recibida.
- **Recompensas en stablecoin sobre HSK Chain**: un contrato en escrow libera pagos por tiers (Información Útil / Evidencia Clave / Recuperación Efectiva) directamente al colaborador, sin intermediarios.

**Problema que resuelve**: en Bolivia se registran ~3,500 denuncias de robo vehicular al año, y el 64% de esos vehículos nunca se localiza.

## 2. Contexto de la competencia (por qué existen las restricciones de tiempo/alcance)

Este proyecto se construye para el **Buildathon Ethereum Bolivia 2026 — HSK Chain Track**.

- **Timeline**: Cierre de submission 13 sep 8:30am. Demo Day 13 sep 10:30–14:30 (5 min: 3 pitch + 2 QA). Ganador se anuncia a las 16:00.
- **Doble inscripción obligatoria**: Devfolio Ethereum Bolivia (track "Bolivia Hackathon" + track "HSK Chain") **y** el portal EAG Global Buildathon.
- **Requisitos HSK Chain Track**: construido sobre HSK Chain, desplegado en HSK Chain Mainnet (testnet aceptado si el tiempo es limitado — faucet: https://hskchain.net/faucet), repo público en GitHub, demo funcional, participación en Demo Day.
- **Criterios de juicio**: viabilidad/potencial real, si resuelve un problema significativo, innovación técnica/de producto.
- **Entregables obligatorios**: demo funcional, repo de GitHub con README (features, instalación, cómo correrlo, enfoque de integración técnica), documentación técnica (track elegido, arquitectura, features clave, roadmap).
- **Premios HSK Chain**: 1º 500 USDT, 2º 300 USDT, 3º 200 USDT.

**Implicación práctica para Claude Code**: quedan ~36–40 horas desde que se escribió este documento. Prioriza siempre "funciona de punta a punta" sobre "está pulido". Cuando una función no sea viable de construir con datos reales en ese tiempo (ver sección 5), constrúyela como una simulación honesta y documenta claramente en el README/roadmap que la versión de producción usaría la integración real.

## 3. Estructura actual del repositorio

```
autochain/
├── contracts/
│   └── AutoChainReward.sol      # escrow de recompensa por tiers, en stablecoin, sobre HSK Chain
├── scripts/
│   └── deploy.js                # despliegue con Hardhat
├── hardhat.config.js            # redes hskTestnet / hskMainnet (RPC y chainId son placeholders — completar)
├── backend/
│   ├── main.py                  # API principal: registro, casos, pistas, orquesta IA + pagos on-chain
│   ├── ai_matching_service.py   # microservicio de similitud de imagen (CLIP, ViT-B-32 preentrenado)
│   └── requirements.txt
├── frontend/
│   └── index.html               # demo de una sola página (registro → caso → pista → validación → recompensa)
├── docs/
│   └── TECHNICAL.md             # documentación técnica exigida por las bases
├── README.md
├── .env.example
└── package.json
```

### Decisiones de arquitectura ya tomadas (no las re-abras sin razón)

- **On-chain vs off-chain**: solo hashes/estado de caso van on-chain. Fotos, datos KYC y evidencia viven off-chain. Esto es una decisión deliberada de privacidad, no un descuido.
- **Validación de IA off-chain**: el resultado (tier) se relaya on-chain por una wallet `validator` whitelisteada en el contrato (`setValidator`). El roadmap contempla reemplazarla por un oráculo descentralizado — no lo construyas ahora, no hay tiempo y no es crítico para el demo.
- **Tiers de recompensa**: Información Útil (10%), Evidencia Clave (30%), Recuperación Efectiva (60% restante, confirmación manual — nunca decidida por IA, porque implica verificación física).
- **Stablecoin**: cualquier ERC-20 en HSK Chain (mock USDT/USDC en testnet está bien para el demo).
- **IA de matching**: `open_clip` preentrenado (ViT-B-32), sin entrenamiento propio. Umbrales: ≥0.90 evidencia clave, ≥0.75 información útil, <0.75 sin coincidencia.

## 4. Cómo correr el proyecto localmente

```bash
# Contrato
npm install
cp .env.example .env   # completar PRIVATE_KEY, HSK_*_RPC_URL, STABLECOIN_ADDRESS
npm run compile
npm run deploy:hsk-testnet

# IA
cd backend && pip install -r requirements.txt
uvicorn ai_matching_service:app --reload --port 8001

# API principal (otra terminal)
uvicorn main:app --reload --port 8000

# Frontend
abrir frontend/index.html en el navegador
```

---

## 5. NUEVO MÓDULO A CONSTRUIR: Reconocimiento de vehículos con cámaras de la ciudad

### 5.1 Objetivo

Además de depender de que un ciudadano suba una foto manualmente, AutoChain debe poder **detectar automáticamente** un vehículo reportado como robado cuando pasa frente a una cámara de tránsito/seguridad de la ciudad — generando una "pista" automática con ubicación y hora, sin esperar a que alguien lo reporte manualmente.

Esto refuerza el pitch: pasa de "economía de recompensas por pistas humanas" a "red de detección híbrida humano + infraestructura urbana", que es un argumento fuerte de innovación técnica para el jurado.

### 5.2 Restricción de realidad para el hackathon

**No vamos a tener acceso real a las cámaras municipales de Cochabamba en 36 horas** (requiere convenio con la alcaldía/policía, permisos, integración con su VMS). Sé honesto con esto en el demo. La estrategia correcta es:

- Construir el **pipeline completo y funcional** usando un feed simulado (un video de muestra o imágenes de vehículos en la vía pública, de stock/libres de derechos, o grabadas por el propio equipo).
- Dejar el punto de integración (`camera_ingestion_service.py`) diseñado para conectarse a un stream RTSP/HTTP real sin cambios de arquitectura — solo cambia la fuente del frame.
- En el pitch: "Hoy lo demostramos con un feed simulado; la arquitectura ya está lista para conectarse a las cámaras de la Guardia Municipal / AASANA / cámaras de seguridad ciudadana vía RTSP en cuanto exista el convenio."

### 5.3 Pipeline técnico

```
Cámara (RTSP / video de prueba / carpeta de imágenes)
   │
   ▼
camera_ingestion_service.py   → muestrea 1 frame cada N segundos
   │
   ▼
Detección de vehículo + placa  → YOLOv8n (detección) + recorte de la región de la placa
   │
   ▼
OCR de placa                   → EasyOCR o PaddleOCR sobre el recorte
   │
   ▼
Match contra registro de placas reportadas como robadas (backend/main.py)
   │
   ├── si hay match → crea automáticamente un "tip" de tipo camera_detection
   │                   con: caseId, cámara, timestamp, ubicación, frame como evidencia
   │                   → se envía también a ai_matching_service para score de imagen (doble verificación)
   │                   → tier sugerido: "evidencia_clave" (alta confianza), NUNCA "recompensa_total"
   │                     automáticamente (la recuperación física siempre la confirma un humano)
   │
   └── si no hay match → se descarta el frame (no se almacena para minimizar datos de personas
                          que no están involucradas — ver privacidad abajo)
```

### 5.4 Nuevos archivos a crear

- `backend/camera_ingestion_service.py` — nuevo microservicio FastAPI:
  - `POST /cameras/register` — registra una cámara (id, nombre/ubicación, url del feed o modo "mock").
  - Loop en background (`asyncio`) por cámara registrada: lee frame → detecta placa → compara contra `GET /plates/watchlist` del backend principal → si hay match, `POST /cases/{case_id}/tips` en `main.py` con `source=camera`, adjuntando el frame como `tip_photo` y el texto de la placa reconocida.
  - Modo `mock`: en vez de RTSP, lee frames de una carpeta local `sample_footage/` o un archivo de video de prueba con OpenCV (`cv2.VideoCapture`), para que el demo funcione sin cámaras reales.

- `backend/plate_recognition.py` — funciones puras, reusables y testeables:
  - `detect_vehicle_and_plate(frame) -> Optional[PlateCrop]` (YOLOv8n, pesos pre-entrenados de detección de vehículos/placas — buscar un modelo público ya afinado, no entrenar desde cero).
  - `read_plate_text(plate_crop) -> str` (EasyOCR o PaddleOCR).

### 5.5 Cambios en archivos existentes

- **`backend/main.py`**:
  - Nuevo endpoint `GET /plates/watchlist` → devuelve `{plate: case_id}` de todos los casos abiertos (para que `camera_ingestion_service` pueda hacer el match sin acoplarse a la base de datos interna).
  - `submit_tip` debe aceptar un campo opcional `source: Literal["community", "camera"]` para diferenciar en la UI y en las métricas de qué tan efectiva es cada vía.
  - Cuando `source == "camera"` y hay match de placa exacto, el tier mínimo sugerido es `evidencia_clave` incluso si el score de imagen CLIP es más bajo (la placa es una señal fuerte por sí sola) — pero **nunca** disparar `recompensa_total` automáticamente.

- **`frontend/index.html`**:
  - Agregar una tarjeta/etapa nueva "Detección automática por cámaras" que muestre, si existen, los eventos de detección (cámara, hora, placa, thumbnail del frame) recibidos vía `GET /cases/{case_id}/camera-events` (nuevo endpoint de solo lectura en `main.py`).

- **`docs/TECHNICAL.md`**: agregar una sección "Reconocimiento por cámaras urbanas" que documente el pipeline de la sección 5.3, la limitación de acceso real a cámaras municipales, y el roadmap de integración formal (convenio con la alcaldía, cumplimiento de protección de datos).

- **`README.md`**: agregar el nuevo microservicio a "Instalación y ejecución" (`uvicorn camera_ingestion_service:app --reload --port 8002`) y a la lista de features.

### 5.6 Privacidad — importante, no te lo saltes

Las cámaras de vía pública capturan a personas y vehículos no involucrados. Reglas a implementar/documentar:

- Solo se conserva un frame si hay match positivo de placa contra la watchlist de vehículos robados; todo lo demás se descarta inmediatamente, sin almacenamiento.
- El frame guardado como evidencia se recorta idealmente a la región del vehículo/placa, no a la escena completa, para minimizar la exposición de terceros (peatones, otros conductores).
- Documentar esto explícitamente en `docs/TECHNICAL.md` — es un punto que un jurado técnico va a preguntar, y tener la respuesta lista suma puntos de "viabilidad real".

### 5.7 Dependencias nuevas a añadir a `backend/requirements.txt`

```
opencv-python-headless==4.10.0.84
ultralytics==8.2.103      # YOLOv8
easyocr==1.7.2
```

### 5.8 Qué NO hacer (para no perder tiempo)

- No entrenar un modelo propio de detección de placas bolivianas — usa un modelo YOLO pre-entrenado de detección de vehículos/placas ya disponible públicamente y afínalo únicamente si sobra tiempo.
- No intentes conseguir acceso real a cámaras municipales durante el hackathon — no es alcanzable en el tiempo disponible y no es lo que se está evaluando.
- No conectes este módulo a pagos automáticos de "recompensa total" — mantenlo limitado a generar evidencia (`evidencia_clave` como máximo), tal como se especifica arriba.

---

## 6. Checklist general vigente (para que Claude Code sepa en qué fase estamos)

1. Setup + contrato desplegado en HSK Chain testnet.
2. Backend + servicio de IA de matching por imagen (CLIP) — **ya en el scaffold**.
3. Frontend mínimo del loop principal — **ya en el scaffold**.
4. Conectar todo de punta a punta.
5. **Nuevo**: módulo de reconocimiento por cámaras (sección 5), con feed simulado.
6. Pulido, README/docs finales, grabación de video de respaldo, submission en ambos portales antes de las 8:30am del 13 de septiembre.
7. Demo Day 13 sep 10:30–14:30.
