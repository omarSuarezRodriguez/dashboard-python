"""Servidor HTTP local para webhooks entrantes de Twilio."""

import threading
from queue import Queue
from typing import Any, Callable, Dict, Optional

from flask import Flask, request

from app.utils.logger import get_logger

logger = get_logger("webhook")

# Eventos para la GUI: ("incoming", payload) | ("status", payload)
EventPayload = Dict[str, Any]
EventCallback = Callable[[str, EventPayload], None]


class WebhookServer:
    """Servidor Flask en hilo daemon que recibe POST de Twilio."""

    def __init__(
        self,
        host: str,
        port: int,
        event_queue: Queue,
        public_base_url: str = "",
    ):
        self.host = host
        self.port = port
        self.public_base_url = public_base_url.rstrip("/")
        self.event_queue = event_queue
        self._thread: Optional[threading.Thread] = None
        self._app = self._create_app()

    def _create_app(self) -> Flask:
        app = Flask(__name__)
        app.logger.disabled = True

        @app.route("/webhook/whatsapp", methods=["POST"])
        @app.route("/bot", methods=["POST"])  # alias: Twilio suele apuntar aquí (chatbot)
        def whatsapp_incoming():
            return self._handle_incoming()

        @app.route("/webhook/status", methods=["POST"])
        def whatsapp_status():
            return self._handle_status()

        @app.route("/health", methods=["GET"])
        def health():
            return {"status": "ok"}, 200

        @app.route("/", methods=["GET", "HEAD"])
        def root():
            return {
                "app": "whatsapp_panel",
                "webhook": f"{self.public_base_url or ''}/webhook/whatsapp",
                "alias": f"{self.public_base_url or ''}/bot",
            }, 200

        return app

    def _handle_incoming(self):
        data = request.form.to_dict()
        message_sid = data.get("MessageSid", "")
        from_number = data.get("From", "")
        body = data.get("Body", "")
        profile_name = data.get("ProfileName", "")

        if not from_number:
            logger.warning("Webhook sin remitente")
            return "", 400

        payload = {
            "message_sid": message_sid,
            "from_number": from_number,
            "body": body,
            "profile_name": profile_name,
        }
        logger.info("Mensaje entrante de %s", from_number)
        self.event_queue.put(("incoming", payload))
        return "", 200

    def _handle_status(self):
        data = request.form.to_dict()
        payload = {
            "message_sid": data.get("MessageSid", ""),
            "status": data.get("MessageStatus", ""),
        }
        if payload["message_sid"]:
            self.event_queue.put(("status", payload))
        return "", 200

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def run():
            logger.info(
                "Webhook local: http://127.0.0.1:%s/webhook/whatsapp", self.port
            )
            if self.public_base_url:
                logger.info(
                    "Webhook público (Twilio): %s/webhook/whatsapp",
                    self.public_base_url,
                )
            self._app.run(
                host=self.host,
                port=self.port,
                threaded=True,
                use_reloader=False,
            )

        self._thread = threading.Thread(target=run, daemon=True, name="WebhookServer")
        self._thread.start()

    @property
    def incoming_url(self) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/webhook/whatsapp"
        return f"http://localhost:{self.port}/webhook/whatsapp"

    @property
    def status_url(self) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/webhook/status"
        return f"http://localhost:{self.port}/webhook/status"
