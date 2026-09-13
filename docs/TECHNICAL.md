# Documentación Técnica — AutoChain

## Track seleccionado

**HSK Chain Track**, con enfoque cruzado en:
- **Payments / Stablecoins** — el núcleo del producto es un desembolso de recompensa en stablecoin.
- **RWA (Real-World Assets)** — el vehículo físico y su documentación son el activo del mundo real que se registra y referencia on-chain.
- **AI × Web3** — un modelo de IA determina, de forma verificable, cuánto vale una pista, y ese resultado se traduce directamente en un pago on-chain.

## Arquitectura central

```
┌───────────┐   1. registra/reporta   ┌──────────────┐
│ Propietario│ ───────────────────────▶│  Backend API  │
└───────────┘                          │  (main.py)    │
                                        └──────┬────────┘
┌───────────┐   3. sube pista/foto           │
│Colaborador │ ───────────────────────────────▶
└───────────┘                                 │
                                        ┌──────▼────────┐
                                        │ AI Matching   │  4. score de similitud (CLIP)
                                        │ Service       │
                                        └──────┬────────┘
                                               │ tier confirmado
                                        ┌──────▼────────┐
                                        │ AutoChainReward│  5. libera % de recompensa
                                        │ (HSK Chain)    │     en stablecoin
                                        └────────────────┘
```

## Componentes clave

### Contrato `AutoChainReward.sol`
- Custodia el stablecoin de cada caso (`reportarVehiculoRobado`).
- Libera pagos incrementales por tier (`pagarRecompensaColaborador`), evitando doble pago del mismo nivel.
- Permite reembolso al propietario si el caso se cancela (`cancelarCaso`).
- Rol de `validator` (whitelisteado por el owner) es quien confirma tiers on-chain — puesto que la validación de IA hoy corre off-chain.

### Servicio de IA (`ai_matching_service.py`)
- Usa `open_clip` (ViT-B-32, pesos `openai`) para generar embeddings de imagen.
- Similitud coseno entre la foto de referencia del vehículo y la foto de la pista.
- Umbrales: `>=0.90` evidencia clave, `>=0.75` información útil, `<0.75` sin coincidencia.
- La "recuperación efectiva" (tier máximo) se confirma manualmente por un operador — no es una decisión de IA, ya que implica verificación física del vehículo.

### Backend (`main.py`)
- Orquesta el flujo completo: registro → caso → pistas → validación IA → payout on-chain.
- Persistencia en Supabase (Postgres + Storage, plan gratuito): las tablas `vehicles`/`cases`/`tips` viven en Postgres (ver `backend/supabase_schema.sql`); las fotos del vehículo y el documento de compra-venta se guardan en dos buckets de Storage (`vehicle-photos` público, `ownership-documents` privado). Todo el acceso pasa por `backend/db.py`.

## Seguridad y privacidad (KYC)

- KYC es un paso independiente y único por wallet (`POST /users/register`): nombre + foto de la cédula, guardada en un bucket privado de Storage (`owner-id-photos`), nunca expuesta en el tablero público. Hoy queda disponible para revisión manual del validador; no hay verificación automática del documento todavía.
- Las fotos de referencia, de pistas y del documento de compra-venta se almacenan off-chain; on-chain solo vive el estado del caso y los montos.
- La versión de producción integraría un proveedor KYC certificado (verificación automática de la cédula + prueba de vida) en vez de la revisión manual actual.

## Mitigación de fraude / pistas falsas

- Umbral mínimo de similitud (`0.75`) antes de cualquier pago.
- Tiers incrementales: una pista de baja calidad nunca cobra el monto completo.
- Roadmap: mecanismo de stake para colaboradores, penalizando pistas maliciosas repetidas.

## Roadmap / plan de iteración

1. Oráculo descentralizado para reemplazar al validator manual.
2. KYC real con proveedor externo.
3. Sistema de reputación y stake para colaboradores.
4. Integración con aseguradoras y autoridades para verificación oficial de recuperación.
5. Expansión regional (mismo problema existe en otros países de Latinoamérica).

## Despliegue

- **Red**: HSK Chain Testnet para el hackathon (mainnet-ready; el contrato no tiene dependencias específicas de testnet).
- **Faucet testnet**: https://hskchain.net/faucet
- Dirección del contrato desplegado: `0x0C8dA3431EDF2Fe388577F90655D77b0feC49b0e` (verificado en Blockscout).
- Frontend: https://autochain-hsk.vercel.app — API: https://autochain-hsk-api.vercel.app
- **Estado del servicio de IA (CLIP)**: probado y funcional en local (`ai_matching_service.py`); aún no desplegado en producción por el límite de tamaño de las funciones serverless de Vercel (ver README). En producción, las pistas se registran igual pero quedan marcadas `ai_unavailable: true` hasta que ese servicio esté en línea.
