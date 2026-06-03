# Panel de atención WhatsApp (Twilio)

Aplicación de escritorio en Python que funciona como panel de atención de WhatsApp vía Twilio: lista de conversaciones, recepción por webhook, envío de mensajes y almacenamiento local en SQLite.

## Requisitos

- Python 3.10 o superior
- Cuenta de Twilio con WhatsApp habilitado (sandbox o producción)

## Instalación

```bash
cd dashboard-python
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Edita `.env` con tus credenciales de Twilio.

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `TWILIO_ACCOUNT_SID` | SID de la cuenta Twilio |
| `TWILIO_AUTH_TOKEN` | Token de autenticación |
| `TWILIO_WHATSAPP_FROM` | Número WhatsApp de Twilio (`whatsapp:+14155238886`) |
| `WEBHOOK_PORT` | Puerto local (debe ser el mismo que `ngrok http`, ej. `5000`) |
| `WEBHOOK_PUBLIC_URL` | URL base de ngrok sin barra final (ej. `https://xxx.ngrok-free.dev`) |
| `LOG_LEVEL` | Nivel de logs (`INFO`, `DEBUG`, etc.) |

## Ejecutar la aplicación

```bash
python run.py
```

## Chatbot + panel a la vez (recomendado)

El **chatbot** puede seguir con Twilio en `https://tu-ngrok/bot` (puerto 5000).

El **panel** recibe mensajes consultando la API de Twilio cada pocos segundos (no necesita el webhook):

```env
WEBHOOK_ENABLED=false
MESSAGE_SYNC_ENABLED=true
MESSAGE_SYNC_INTERVAL=1
```

Ajusta en `.env` para más velocidad:
```env
MESSAGE_SYNC_INTERVAL=0.5
```
(Mínimo 0.5 s. Menos de eso puede saturar la API de Twilio.)

1. Deja el chatbot corriendo como siempre (`/bot` en ngrok).
2. Abre el panel: `python run.py`
3. Envía y recibe desde el panel; los mensajes aparecen en ~1 s (o menos con `MESSAGE_SYNC_INTERVAL=0.5`).

No hace falta cerrar el bot ni cambiar la URL de Twilio.

## Configurar webhook en Twilio (opcional)

1. En `.env` define tu túnel ngrok:
   ```env
   WEBHOOK_PORT=5000
   WEBHOOK_PUBLIC_URL=https://snowman-shower-pellet.ngrok-free.dev
   ```

2. Dos terminales:
   ```bash
   python run.py
   ngrok http 5000
   ```

3. El pie de la app muestra la URL para Twilio. También está en `TWILIO_WEBHOOK.txt`.

4. En [Twilio Console](https://console.twilio.com/) → **Messaging** → **WhatsApp Sandbox** (o tu sender):

   | Campo | URL (POST) |
   |-------|------------|
   | When a message comes in | `https://snowman-shower-pellet.ngrok-free.dev/webhook/whatsapp` |
   | (o si ya usas `/bot`) | `https://snowman-shower-pellet.ngrok-free.dev/bot` |
   | Status callback (opcional) | `https://snowman-shower-pellet.ngrok-free.dev/webhook/status` |

   **Conflicto con chatbot:** si ngrok muestra `POST /bot 200` pero el panel no recibe mensajes,
   el chatbot está ocupando el puerto 5000. Cierra el chatbot y ejecuta solo `python run.py`.

5. Guarda. Si reinicias ngrok y cambia la URL, actualiza `.env` y Twilio.

6. Prueba local antes de Twilio:
   ```powershell
   curl http://localhost:5000/health
   curl -X POST https://snowman-shower-pellet.ngrok-free.dev/webhook/whatsapp -d "From=whatsapp:+573001112233" -d "Body=Hola" -d "MessageSid=SMtest1"
   ```

## Funcionalidades

- Barra lateral con conversaciones ordenadas por actividad reciente
- Buscador de chats
- Indicador de mensajes no leídos
- Vista de chat con burbujas (entrante / saliente)
- Envío con botón o **Enter** (Shift+Enter para nueva línea)
- Nueva conversación con prefijo internacional y validación E.164
- Muestra SID y errores amigables al enviar
- Webhook local para mensajes entrantes en tiempo real
- Persistencia SQLite (`data/whatsapp_panel.db`)
- Logs en `logs/app.log`

## Estructura del proyecto

```
dashboard-python/
├── app/
│   ├── gui/              # CustomTkinter (sidebar, chat, diálogos)
│   ├── services/         # Twilio, webhook, lógica de conversaciones
│   ├── persistence/      # SQLite
│   └── utils/            # Config, logs, validación de teléfonos
├── data/                 # Base de datos (generada al ejecutar)
├── logs/                 # Logs (generados al ejecutar)
├── run.py
├── requirements.txt
├── .env.example
└── INTEGRACION_CHATBOT.md
```

## Solución de problemas

| Problema | Posible causa |
|----------|----------------|
| Error de autenticación | Revisa `TWILIO_ACCOUNT_SID` y `TWILIO_AUTH_TOKEN` |
| Número no verificado | En cuenta trial solo números verificados en Twilio |
| No llegan mensajes entrantes | Webhook no configurado o ngrok no activo |
| Ventana 24h cerrada | El usuario debe escribir primero o usar plantilla aprobada |

## Integración con chatbot

No está implementada en este proyecto. Consulta `INTEGRACION_CHATBOT.md` para pasos manuales futuros con `chatbot-cursor`.

## Licencia

Uso interno / educativo según tu organización.
