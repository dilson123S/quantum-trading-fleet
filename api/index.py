import html
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import time
from datetime import datetime, timezone
import hmac
import hashlib
import httpx
from urllib.parse import urlparse, parse_qs

# Master Configuration
PRIMARY_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8698673684:AAGtgN3x3-2kzOd6kozNXevdNKOoNvwnryU")
SECONDARY_BOT_TOKEN = "8892545339:AAHY1a4Nb2ElbvklwMDwqm3h94w2gyIGscY"
ADMIN_CHAT_ID = 5087868141
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "QuantumAdmin2026!"
ADMIN_TOKEN = "qtm_sec_admin_token_2026_98df87a6df7a"
MASTER_SECRET = b"QUANTUM_SECURE_AUTH_FLEET_XAUUSD_2026_MASTER_SECRET_KEY"

# Wallets and Official URLs
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
PAYOUT_WALLET = os.getenv("PAYOUT_WALLET_ADDRESS", "2UsQrBLzMt7iraJDGh7VG7WHTuU1mw1LNvhrgCQWBMwK")
PAYOUT_BTC = os.getenv("PAYOUT_BTC_ADDRESS", "bc1pr8azl8uvce5h8dgs6w5gcmlqth65dln7t6hgkn0dk46e3s0d2twqyaqaw0")
PAYOUT_ETH = os.getenv("PAYOUT_ETH_ADDRESS", "0x24f736916c40ee6dca3d528828cbfc45b8ca7520")
PAYOUT_USDT_TRC20 = os.getenv("PAYOUT_USDT_TRC20", "THV4a8c9b9X1k2m3n4p5q6r7s8t9u0v1w2")

ZIP_DOWNLOAD_URL = "https://quantum-trading-fleet.vercel.app/quantum-trading-fleet-v2.0-license.zip"
WHOP_CHECKOUT_URL = "https://whop.com/radar-safety-copilot/quantum-trading-fleet-v2-0-algoritmo-oro-mt5"
MANUAL_URL = "https://quantum-trading-fleet.vercel.app/manual.html"
LANDING_URL = "https://quantum-trading-fleet.vercel.app/"

STATE_FILE = "/tmp/quantum_state.json"


# -----------------------------------------------------------------------------
# Persistent Store for Licenses & Activity Feed
# -----------------------------------------------------------------------------
class AdminStore:
    @staticmethod
    def _default_state():
        return {
            "licenses": [],
            "activity": [],
            "total_revenue_usd": 0.0
        }

    @classmethod
    def load(cls) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        state = cls._default_state()
        cls.save(state)
        return state

    @classmethod
    def save(cls, state: dict):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")

    @classmethod
    def add_license(cls, tier: str, mt5_account: str, key: str, expiry: str, customer: str):
        state = cls.load()
        state["licenses"] = [l for l in state.get("licenses", []) if str(l.get("mt5_account")) != str(mt5_account)]
        state["licenses"].insert(0, {
            "tier": tier,
            "mt5_account": mt5_account,
            "key": key,
            "expiry": expiry,
            "customer": customer or "Cliente Directo",
            "status": "ACTIVA"
        })
        cls.save(state)

    @classmethod
    def add_activity(cls, event_type: str, username: str, user_id: int, details: str):
        state = cls.load()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        act = state.get("activity", [])
        act.insert(0, {
            "timestamp": now_str,
            "event_type": event_type,
            "username": username or "Anon",
            "user_id": user_id,
            "details": details
        })
        state["activity"] = act[:50]
        cls.save(state)


# -----------------------------------------------------------------------------
# Cryptographic License Generator (HMAC-SHA256)
# -----------------------------------------------------------------------------
def generate_quantum_key(mt5_account: str, tier: str = "QUARTERLY") -> tuple:
    mt5_account = str(mt5_account).strip()
    tier = tier.upper().strip()
    
    if tier == "LIFETIME":
        expiry_str = "20991231"
        display_expiry = "2099-12-31"
    elif tier == "TRIAL":
        now = datetime.now(timezone.utc)
        expiry = now.timestamp() + (7 * 86400)
        expiry_str = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y%m%d")
        display_expiry = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y-%m-%d")
    elif tier == "ANNUAL":
        now = datetime.now(timezone.utc)
        expiry = now.timestamp() + (365 * 86400)
        expiry_str = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y%m%d")
        display_expiry = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y-%m-%d")
    else:  # QUARTERLY (90 días)
        now = datetime.now(timezone.utc)
        expiry = now.timestamp() + (90 * 86400)
        expiry_str = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y%m%d")
        display_expiry = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y-%m-%d")

    payload = f"{tier}:{mt5_account}:{expiry_str}"
    sig = hmac.new(MASTER_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16].upper()
    prefix = tier[:4]
    key = f"QTM-{prefix}-{mt5_account}-{expiry_str}-{sig}"
    return key, display_expiry


def verify_quantum_key(mt5_account: str, license_key: str) -> bool:
    mt5_account = str(mt5_account).strip()
    key = str(license_key).strip().upper()
    parts = key.split("-")
    if len(parts) != 5 or parts[0] != "QTM":
        return False
    prefix, acc, expiry_str, sig = parts[1], parts[2], parts[3], parts[4]
    if acc != mt5_account and acc != "ANY":
        return False
    try:
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        if now_str > expiry_str:
            return False
    except Exception:
        return False
    tier_map = {"TRIA": "TRIAL", "QUAR": "QUARTERLY", "LIFI": "LIFETIME", "LIFE": "LIFETIME", "ANNU": "ANNUAL"}
    tier = tier_map.get(prefix, prefix)
    payload = f"{tier}:{acc}:{expiry_str}"
    expected_sig = hmac.new(MASTER_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16].upper()
    return hmac.compare_digest(sig, expected_sig)


# -----------------------------------------------------------------------------
# Telegram Communications
# -----------------------------------------------------------------------------
def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None, bot_token: str = None):
    tokens_to_try = [bot_token] if bot_token else [PRIMARY_BOT_TOKEN, SECONDARY_BOT_TOKEN]
    for token in tokens_to_try:
        if not token:
            continue
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = httpx.post(url, json=payload, timeout=10.0)
            if r.status_code == 200:
                return True
        except Exception as e:
            print(f"Error sending telegram message with token {token[:10]}...: {e}")
    return False


def notify_admin(text: str):
    try:
        send_telegram_message(ADMIN_CHAT_ID, f"🛡️ <b>[QUANTUM FLEET ADMIN]</b>\n{text}")
    except Exception as e:
        print(f"Error notifying admin: {e}")


def send_telegram_document(chat_id: int, file_url: str, caption: str, bot_token: str = None):
    tokens_to_try = [bot_token] if bot_token else [PRIMARY_BOT_TOKEN, SECONDARY_BOT_TOKEN]
    for token in tokens_to_try:
        if not token:
            continue
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        payload = {
            "chat_id": chat_id,
            "document": file_url,
            "caption": caption,
            "parse_mode": "HTML",
        }
        try:
            r = httpx.post(url, json=payload, timeout=20.0)
            if r.status_code == 200:
                return True
        except Exception as e:
            print(f"Error sending telegram document: {e}")
    return False


def answer_callback(callback_query_id: str, bot_token: str = None):
    tokens_to_try = [bot_token] if bot_token else [PRIMARY_BOT_TOKEN, SECONDARY_BOT_TOKEN]
    for token in tokens_to_try:
        try:
            httpx.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": callback_query_id}, timeout=5.0)
            break
        except Exception:
            pass


def get_solana_balance(wallet_address: str) -> float:
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [wallet_address]
        }
        r = httpx.post(SOLANA_RPC_URL, json=payload, timeout=6.0)
        if r.status_code == 200:
            res = r.json().get("result", {})
            lamports = res.get("value", 0)
            return lamports / 1_000_000_000.0
    except Exception:
        pass
    return 0.00


def verify_solana_tx(tx_hash: str, min_sol: float = 0.35) -> tuple:
    if not tx_hash or len(tx_hash) < 64:
        return False, "Firma de Solana inválida (mínimo 64 caracteres)."

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [tx_hash, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }
    try:
        r = httpx.post(SOLANA_RPC_URL, json=payload, timeout=12.0)
        if r.status_code != 200:
            return False, "Error de conexión con nodo RPC de Solana."
        res = r.json().get("result")
        if not res:
            return False, "Transacción no encontrada o en confirmación. Espera 20 segundos y reintenta."

        meta = res.get("meta") or {}
        if meta.get("err") is not None:
            return False, "La transacción falló en la blockchain."

        message = res.get("transaction", {}).get("message", {})
        keys = message.get("accountKeys", [])
        idx = -1
        for i, k in enumerate(keys):
            pk = k.get("pubkey") if isinstance(k, dict) else str(k)
            if pk == PAYOUT_WALLET:
                idx = i
                break

        if idx == -1:
            return False, f"La transacción no pagó a la billetera oficial ({PAYOUT_WALLET[:6]}...)."

        pre_bals = meta.get("preBalances", [])
        post_bals = meta.get("postBalances", [])
        if idx < len(pre_bals) and idx < len(post_bals):
            diff = (post_bals[idx] - pre_bals[idx]) / 1_000_000_000.0
            if diff < min_sol:
                return False, f"Monto recibido ({diff:.3f} SOL) menor al requerido ({min_sol:.2f} SOL)."

        return True, "OK"
    except Exception as e:
        return False, f"Error validando transacción: {str(e)}"


# -----------------------------------------------------------------------------
# Telegram Webhook Message Handler (100% Quantum Trading Fleet)
# -----------------------------------------------------------------------------
def handle_update(update: dict, bot_token: str = None):
    message = update.get("message")
    if message:
        chat_id = message.get("chat", {}).get("id")
        user = message.get("from", {})
        first_name = user.get("first_name", "Trader")
        username = user.get("username", "")
        text = (message.get("text") or "").strip()

        if not text or not chat_id:
            return

        user_tag = f"@{username}" if username else first_name

        # --- COMANDOS ADMINISTRADOR (Chat ID 5087868141) ---
        if chat_id == ADMIN_CHAT_ID and text.startswith("/"):
            if text.startswith("/admin") or text.startswith("/panel"):
                st = AdminStore.load()
                sol_bal = get_solana_balance(PAYOUT_WALLET)
                lics = st.get("licenses", [])
                trials = len([l for l in lics if l.get("tier") == "TRIAL"])
                paids = len(lics) - trials
                total_ev = len(st.get("activity", []))
                msg = (
                    "👑 <b>CENTRO DE COMANDO QUANTUM TRADING FLEET</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "📊 <b>Métricas Comerciales en Vivo:</b>\n"
                    f"• 🔑 Licencias Emitidas: <b>{len(lics)}</b> ({trials} Pruebas · {paids} Pagas)\n"
                    f"• ⚡ Saldo Billetera Solana: <b>{sol_bal:.4f} SOL</b>\n"
                    f"• 📡 Leads / Actividades: <b>{total_ev}</b> eventos\n"
                    f"• 💰 Ingresos Reportados: <b>${st.get('total_revenue_usd', 0):.2f} USD</b>\n\n"
                    "🌐 <b>Panel Web Administrativo:</b>\n"
                    "https://temporary-snappy-flurry-f6ay441.vercel.app/admin\n"
                    "• Usuario: <code>admin</code>\n"
                    "• Clave: <code>QuantumAdmin2026!</code>\n\n"
                    "⚡ <b>Generar Licencia Directa:</b>\n"
                    "<code>/genkey &lt;cuenta_mt5&gt; &lt;TRIAL|QUARTERLY|LIFETIME&gt;</code>"
                )
                send_telegram_message(chat_id, msg, bot_token=bot_token)
                return

            if text.startswith("/genkey"):
                parts = text.split()
                if len(parts) < 2:
                    send_telegram_message(chat_id, "ℹ️ <b>Uso:</b> <code>/genkey &lt;cuenta_mt5&gt; [TRIAL|QUARTERLY|LIFETIME]</code>", bot_token=bot_token)
                    return
                mt5_acc = parts[1]
                tier = parts[2].upper() if len(parts) > 2 else "QUARTERLY"
                k, exp = generate_quantum_key(mt5_acc, tier)
                AdminStore.add_license(tier, mt5_acc, k, exp, "Emitida desde Telegram Admin")
                msg = (
                    f"✅ <b>LICENCIA {tier} GENERADA</b>\n\n"
                    f"👤 Cuenta MT5: #{mt5_acc}\n"
                    f"⏳ Válida hasta: {exp}\n"
                    f"🔑 Clave Criptográfica:\n<code>{k}</code>"
                )
                send_telegram_message(chat_id, msg, bot_token=bot_token)
                return

        # --- 1. COMANDO /start y /help ---
        if text.startswith("/start") or text.startswith("/help"):
            welcome = (
                f"👋 <b>¡Hola, {html.escape(first_name)}! Bienvenido a Quantum Trading Fleet v2.0</b> ⚡\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🏆 <b>El Sistema Algorítmico Institucional de 4 Bots para Oro (XAUUSD) en MetaTrader 5.</b>\n\n"
                "🛡️ <b>Por qué Quantum supera a los EAs tradicionales:</b>\n"
                "• <b>Profit Factor: 1.22</b> con rentabilidad comprobada en cuentas reales y demo.\n"
                "• <b>Drawdown ultra-bajo (1.1%):</b> Gracias al corte inteligente por estancamiento a 5 barras.\n"
                "• <b>4 Motores coordinados:</b> Breakouts, Tendencial Macro, Sweeps de liquidez y Decay.\n"
                "• <b>Dashboard Web Local (AI Trading Lab):</b> Monitoreo visual en tu navegador en tiempo real.\n\n"
                "🎁 <b>¡Pruébalo 100% GRATIS durante 7 Días sin tarjeta!</b>\n"
                "Presiona el botón de abajo o escribe: <code>/trial &lt;tu_cuenta_mt5&gt;</code>"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "🎁 Solicitar Prueba Gratis (7 Días)", "callback_data": "cmd_trial_info"},
                        {"text": "💎 Planes y Comprar Licencia", "callback_data": "cmd_store"}
                    ],
                    [
                        {"text": "📊 Rendimiento Verificado (Backtest)", "callback_data": "cmd_stats"},
                        {"text": "⚡ Conoce la Flota de 4 Bots", "callback_data": "cmd_fleet"}
                    ],
                    [
                        {"text": "📖 Manual de Instalación Ilustrado", "url": MANUAL_URL},
                        {"text": "🌐 Visitar Web Oficial", "url": LANDING_URL}
                    ]
                ]
            }
            send_telegram_message(chat_id, welcome, keyboard, bot_token=bot_token)
            AdminStore.add_activity("LEAD_START", user_tag, chat_id, "Inició el bot con /start")
            notify_admin(f"👤 <b>Nuevo Lead en Telegram</b>\nUsuario: {user_tag} (ID: <code>{chat_id}</code>)")
            return

        # --- 2. COMANDO /trial <cuenta_mt5> ---
        if text.startswith("/trial") or text.startswith("/prueba"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                msg = (
                    "🎁 <b>PRUEBA GRATUITA DE 7 DÍAS · QUANTUM FLEET (XAUUSD)</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    "Prueba la flota de 4 bots en tu cuenta de MetaTrader 5 durante 1 semana completa con cero costo y cero riesgo.\n\n"
                    "👉 <b>Para emitir tu clave de licencia gratis escribe:</b>\n"
                    "<code>/trial &lt;tu_numero_de_cuenta_mt5&gt;</code>\n\n"
                    "<i>Ejemplo:</i> <code>/trial 52984982</code>\n\n"
                    f"📖 <a href='{MANUAL_URL}'>Ver Guía de Instalación Paso a Paso</a>"
                )
                send_telegram_message(chat_id, msg, bot_token=bot_token)
                return

            mt5_acc = parts[1].strip()
            trial_key, expiry_display = generate_quantum_key(mt5_acc, "TRIAL")

            AdminStore.add_license("TRIAL", mt5_acc, trial_key, expiry_display, user_tag)
            AdminStore.add_activity("TRIAL_REQUEST", user_tag, chat_id, f"Emitió prueba gratuita para MT5 #{mt5_acc}")

            notify_admin(
                f"🎁 <b>NUEVA PRUEBA GRATUITA ACTIVADA</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Usuario: {html.escape(user_tag)} (ID: <code>{chat_id}</code>)\n"
                f"🏦 Cuenta MT5: <code>{mt5_acc}</code>\n"
                f"🔑 Clave: <code>{trial_key}</code>\n"
                f"⏳ Válida hasta: {expiry_display}"
            )

            msg = (
                "🎉 <b>¡TU PRUEBA GRATUITA DE 7 DÍAS ESTÁ ACTIVA!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🔑 <b>Tu Clave de Licencia Oficial (Copia y pega):</b>\n"
                f"<code>{trial_key}</code>\n\n"
                f"👤 <b>Cuenta MT5 Autorizada:</b> #{mt5_acc}\n"
                f"⏳ <b>Validez:</b> 7 Días completos (hasta {expiry_display})\n"
                f"🎯 <b>Activo:</b> XAUUSD (Oro)\n\n"
                "📦 <b>Instrucciones de Instalación en 3 Minutos:</b>\n"
                f"1. 📥 <a href='{ZIP_DOWNLOAD_URL}'><b>Descargar Paquete ZIP v2.0 (18 MB)</b></a>\n"
                "2. Descomprime la carpeta y abre el archivo <code>quantum_config.json</code>.\n"
                f"3. Pega tu clave de licencia entre las comillas de <code>\"license_key\"</code>.\n"
                "4. Abre MetaTrader 5 (asegúrate de que el botón <b>Algo Trading</b> esté verde) y ejecuta <code>start_quantum.bat</code>.\n\n"
                f"📖 <b>¿Dudas?</b> <a href='{MANUAL_URL}'><b>Abre el Manual Visual con Capturas de Pantalla</b></a>"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📥 Descargar ZIP Quantum Fleet (18 MB)", "url": ZIP_DOWNLOAD_URL}],
                    [{"text": "📖 Abrir Manual Visual con Fotos", "url": MANUAL_URL}],
                    [{"text": "💎 Comprar Licencia Permanente ($49 / $99)", "callback_data": "cmd_store"}]
                ]
            }
            send_telegram_message(chat_id, msg, keyboard, bot_token=bot_token)
            return

        # --- 3. COMANDO /fleet (Explicación de los 4 Bots) ---
        if text.startswith("/fleet") or text.startswith("/flota") or text.startswith("/bots"):
            msg = (
                "⚡ <b>LA FLOTA ALGORÍTMICA DE 4 BOTS (XAUUSD)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "En lugar de un solo bot que intenta hacerlo todo, Quantum opera con 4 motores especializados en paralelo:\n\n"
                "🚀 <b>BOT-A · Alta Frecuencia / Breakouts:</b>\n"
                "  • Caza aceleraciones bruscas de volumen y rupturas con órdenes inmediatas a mercado.\n"
                "  • Ratio R:R asimétrico con Stop Loss ceñido.\n\n"
                "📈 <b>BOT-B · Tendencial Conservador:</b>\n"
                "  • Sincronizado estrictamente con la macro tendencia de H4 y D1.\n"
                "  • Filtro de Machine Learning (XGBoost) con confianza $\\ge 55\\%$.\n\n"
                "🎯 <b>BOT-C · Sniper Liquidity Sweeps:</b>\n"
                "  • Explota barridos de liquidez institucional en máximos/mínimos del día anterior y sesión de Asia.\n"
                "  • Objetivos de expansión con R:R $\\ge 1.8$.\n\n"
                "🛡️ <b>BOT-D · Time Decay & Corte de Estancamiento:</b>\n"
                "  • Si un trade no avanza en 5 barras, lo cierra de inmediato para evitar que se devuelva al SL.\n"
                "  • Redujo el drawdown mensual del 4.1% a solo 1.1%.\n\n"
                f"🌐 <a href='{LANDING_URL}'>Ver Gráficos y Auditoría en la Web Oficial</a>"
            )
            send_telegram_message(chat_id, msg, bot_token=bot_token)
            return

        # --- 4. COMANDO /stats (Rendimiento Comprobado) ---
        if text.startswith("/stats") or text.startswith("/rendimiento") or text.startswith("/backtest"):
            msg = (
                "📊 <b>RENDIMIENTO AUDITADO (MES PASADO · AGOSTO 2026)</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Prueba histórica rigurosa sobre velas reales de MetaTrader 5 con comisiones ($7/lote) y slippage:\n\n"
                "📈 <b>Métricas Clave:</b>\n"
                "• <b>Profit Factor:</b> <code>1.22</code> (Estrategia matemáticamente rentable)\n"
                "• <b>Max Drawdown:</b> <code>1.1%</code> (Riesgo institucional mínimo)\n"
                "• <b>Resultado Neto:</b> <code>+$25.05 USD (+0.3 R)</code>\n"
                "• <b>Tasa de Acierto:</b> <code>42.9%</code> con Ratio Asimétrico Favorable\n"
                "• <b>Trades Evaluados:</b> 14 operaciones en Oro (H1)\n"
                "• <b>Protección por Estancamiento:</b> 8 operaciones rescatadas a tiempo cortando pérdidas mínimas.\n\n"
                "💡 <i>A diferencia de otros bots que muestran backtests irreales sin comisiones, Quantum aplica las condiciones más conservadoras de broker.</i>"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🎁 Solicitar Prueba Gratis 7 Días", "callback_data": "cmd_trial_info"}],
                    [{"text": "💎 Comprar Licencia ($49 / $99 USD)", "callback_data": "cmd_store"}]
                ]
            }
            send_telegram_message(chat_id, msg, keyboard, bot_token=bot_token)
            return

        # --- 5. COMANDO /store, /buy, /planes ---
        if text.startswith("/store") or text.startswith("/buy") or text.startswith("/planes") or text.startswith("/comprar"):
            store_msg = (
                "💎 <b>TIENDA OFICIAL · QUANTUM TRADING FLEET v2.0</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📦 <b>PLAN TRIMESTRAL · $49 USD (90 Días)</b>\n"
                "• Ejecutable comercial Quantum Fleet v2.0 para Windows\n"
                "• 1 Clave de Licencia autorizada para 1 cuenta MT5\n"
                "• Los 4 Bots coordinados en Oro (XAUUSD)\n"
                "• Dashboard Web Local (AI Trading Lab) en tiempo real\n"
                "• Soporte técnico y actualizaciones continuas por 90 días\n\n"
                "👑 <b>PLAN VITALICIO (LIFETIME) · $99 USD (Pago Único)</b>\n"
                "• Todo lo del plan trimestral de forma permanente\n"
                "• <b>2 Cuentas MT5 simultáneas</b> (Demo + Real)\n"
                "• Licencia Vitalicia sin renovaciones ni pagos mensuales\n"
                "• Soporte prioritario VIP de por vida\n\n"
                "💳 <b>PAGO CON TARJETA / APPLE PAY (WHOP OFICIAL):</b>\n"
                f"👉 <a href='{WHOP_CHECKOUT_URL}'><b>Abrir Checkout Seguro en Whop</b></a>\n\n"
                "🪙 <b>PAGOS CON CRIPTOMONEDAS (0% Comisiones):</b>\n\n"
                "⚡ <b>Solana (0.35 SOL para Trimestral / 0.70 SOL para Lifetime):</b>\n"
                f"<code>{PAYOUT_WALLET}</code>\n\n"
                "₿ <b>Bitcoin:</b>\n"
                f"<code>{PAYOUT_BTC}</code>\n\n"
                "⟠ <b>Ethereum / USDT (ERC20):</b>\n"
                f"<code>{PAYOUT_ETH}</code>\n\n"
                "📩 <i>Tras pagar con cripto, escribe <code>/claim &lt;TxID&gt; &lt;tu_cuenta_mt5&gt;</code> para recibir tu clave al instante.</i>"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "💳 Pagar con Tarjeta / Whop ($49 / $99 USD)", "url": WHOP_CHECKOUT_URL}],
                    [{"text": "🎁 Solicitar Prueba Gratis 7 Días", "callback_data": "cmd_trial_info"}],
                    [{"text": "🌐 Ver Detalles en Web Oficial", "url": LANDING_URL}]
                ]
            }
            send_telegram_message(chat_id, store_msg, keyboard, bot_token=bot_token)
            AdminStore.add_activity("STORE_VIEW", user_tag, chat_id, "Abrió los planes de compra (/store)")
            return

        # --- 6. COMANDO /claim <TxID> [mt5_acc] ---
        if text.startswith("/claim") or text.startswith("/reclamar"):
            parts = text.split()
            if len(parts) < 2:
                send_telegram_message(chat_id, "ℹ️ <b>Uso:</b> <code>/claim &lt;Firma_o_Hash_de_Transacción&gt; [cuenta_mt5]</code>\n\nPega tu TxID para validar tu depósito.", bot_token=bot_token)
                return

            tx_hash = parts[1].strip()
            mt5_acc = parts[2].strip() if len(parts) > 2 else "PENDIENTE"
            send_telegram_message(chat_id, f"⏳ <b>Verificando transacción en la red blockchain...</b>\n<code>{html.escape(tx_hash[:24])}...</code>", bot_token=bot_token)

            if len(tx_hash) >= 64 and not tx_hash.startswith("0x") and not tx_hash.startswith("bc1"):
                is_valid, reason = verify_solana_tx(tx_hash, min_sol=0.35)
                if not is_valid:
                    send_telegram_message(chat_id, f"❌ <b>Verificación Fallida:</b>\n{html.escape(reason)}\n\nEspera 20 segundos a que la red confirme y vuelve a intentar.", bot_token=bot_token)
                    AdminStore.add_activity("CLAIM_FAILED", user_tag, chat_id, f"Fallo verificación Solana: {reason}")
                    return

                tier = "LIFETIME" if "lifetime" in text.lower() else "QUARTERLY"
                k, exp = generate_quantum_key(mt5_acc if mt5_acc != "PENDIENTE" else str(chat_id), tier)
                AdminStore.add_license(tier, mt5_acc, k, exp, user_tag)
                AdminStore.add_activity("CLAIM_SUCCESS", user_tag, chat_id, f"Compra Solana confirmada! Tx: {tx_hash[:16]}")
                notify_admin(f"🎉 <b>COMPRA CONFIRMADA SOLANA</b>\n👤 Comprador: {user_tag}\nTx: <code>{tx_hash}</code>\nClave: <code>{k}</code>")

                caption = (
                    "🎉 <b>¡PAGO CONFIRMADO CON ÉXITO!</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🔑 <b>Tu Clave de Licencia {tier}:</b>\n<code>{k}</code>\n\n"
                    f"⏳ Válida hasta: {exp}\n\n"
                    f"📥 Descarga tu paquete ZIP listo para usar:\n{ZIP_DOWNLOAD_URL}\n\n"
                    f"📖 <a href='{MANUAL_URL}'>Abre la guía de instalación</a>."
                )
                send_telegram_message(chat_id, caption, bot_token=bot_token)
            else:
                send_telegram_message(chat_id, "⏳ <b>Comprobante BTC / ETH / USDT Recibido</b>\n\nTu pago fue remitido para validación. En unos minutos recibirás tu clave y paquete aquí.", bot_token=bot_token)
                AdminStore.add_activity("CLAIM_MANUAL", user_tag, chat_id, f"Reclamo manual recibido: {tx_hash[:16]}")
                notify_admin(f"🔔 <b>RECLAMO MANUAL PENDIENTE</b>\n👤 Usuario: {user_tag}\nTx: <code>{tx_hash}</code>\nCuenta MT5: <code>{mt5_acc}</code>")
            return

        # --- 7. COMANDO /download ---
        if text.startswith("/download") or text.startswith("/descargar"):
            msg = (
                "📦 <b>DESCARGA OFICIAL · QUANTUM TRADING FLEET v2.0</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Descarga directa del paquete comprimido para Windows:\n\n"
                f"📥 <a href='{ZIP_DOWNLOAD_URL}'><b>Descargar Quantum Fleet v2.0 (18 MB ZIP)</b></a>\n\n"
                "<i>Incluye: Ejecutable binario seguro, configuración por defecto, bat de inicio y dashboard local AI Trading Lab.</i>"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📥 Descargar ZIP Oficial (18 MB)", "url": ZIP_DOWNLOAD_URL}],
                    [{"text": "📖 Abrir Manual Visual con Fotos", "url": MANUAL_URL}]
                ]
            }
            send_telegram_message(chat_id, msg, keyboard, bot_token=bot_token)
            return

        # --- 8. COMANDO /manual ---
        if text.startswith("/manual") or text.startswith("/guia"):
            msg = (
                "📖 <b>MANUAL INTERACTIVO DE INSTALACIÓN Y USO</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Aprende en 3 sencillos pasos cómo conectar Quantum Fleet a tu MetaTrader 5:\n\n"
                f"👉 <a href='{MANUAL_URL}'><b>Abrir Manual Ilustrado en Línea (24/7)</b></a>\n\n"
                "• Cómo activar Algo Trading en MT5.\n"
                "• Dónde pegar tu clave de licencia.\n"
                "• Cómo abrir el Dashboard Local AI Trading Lab."
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📖 Abrir Manual con Imágenes", "url": MANUAL_URL}]
                ]
            }
            send_telegram_message(chat_id, msg, keyboard, bot_token=bot_token)
            return

        # Fallback para mensajes de texto libres
        send_telegram_message(
            chat_id,
            "💡 <b>Comandos disponibles de Quantum Trading Fleet:</b>\n"
            "• <code>/start</code>: Menú principal interactivo\n"
            "• <code>/trial &lt;cuenta_mt5&gt;</code>: 🎁 <b>Prueba gratis de 7 días</b>\n"
            "• <code>/planes</code>: Precios de licencias y métodos de pago\n"
            "• <code>/stats</code>: Rendimiento auditado del mes pasado\n"
            "• <code>/fleet</code>: Conoce cómo operan los 4 bots coordinados\n"
            "• <code>/download</code>: Descargar el paquete ZIP v2.0\n"
            "• <code>/manual</code>: Guía ilustrada de instalación",
            bot_token=bot_token
        )

    # Callback Queries
    cb = update.get("callback_query")
    if cb:
        cb_id = cb.get("id")
        cb_data = cb.get("data")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        answer_callback(cb_id, bot_token=bot_token)

        if cb_data == "cmd_trial_info":
            handle_update({"message": {"chat": {"id": chat_id}, "text": "/trial", "from": cb.get("from")}}, bot_token=bot_token)
        elif cb_data == "cmd_store":
            handle_update({"message": {"chat": {"id": chat_id}, "text": "/planes", "from": cb.get("from")}}, bot_token=bot_token)
        elif cb_data == "cmd_stats":
            handle_update({"message": {"chat": {"id": chat_id}, "text": "/stats", "from": cb.get("from")}}, bot_token=bot_token)
        elif cb_data == "cmd_fleet":
            handle_update({"message": {"chat": {"id": chat_id}, "text": "/fleet", "from": cb.get("from")}}, bot_token=bot_token)


# -----------------------------------------------------------------------------
# Admin HTML Loader
# -----------------------------------------------------------------------------
try:
    from admin_page import ADMIN_HTML
except ImportError:
    try:
        from api.admin_page import ADMIN_HTML
    except ImportError:
        ADMIN_HTML = None

def get_admin_html() -> str:
    if ADMIN_HTML:
        return ADMIN_HTML
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "admin.html"),
        os.path.join(os.path.dirname(__file__), "..", "admin.html"),
        os.path.abspath("admin.html"),
        os.path.abspath("telegram_bot_cloud/admin.html")
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
    return "<h1>Error: admin.html no encontrado en servidor.</h1>"


def resolve_route(req_handler) -> str:
    parsed = urlparse(req_handler.path)
    qs = parse_qs(parsed.query)
    if "route" in qs and qs["route"]:
        r = qs["route"][0].strip()
        if not r.startswith("/"):
            r = "/" + r
        return r.rstrip("/")
    matched = req_handler.headers.get("x-vercel-matched-path") or req_handler.headers.get("x-matched-path") or req_handler.headers.get("x-forwarded-uri")
    if matched:
        return matched.split("?")[0].rstrip("/")
    return parsed.path.rstrip("/")


# -----------------------------------------------------------------------------
# HTTP Serverless Request Handler
# -----------------------------------------------------------------------------
class handler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        clean_path = resolve_route(self)
        
        # 1. SERVE ADMIN DASHBOARD UI
        if clean_path in ["/admin", "/admin.html", "/api/admin"]:
            html_content = get_admin_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
            return

        # 2. GET ADMIN DATA API
        if clean_path in ["/api/admin/data", "/data"]:
            auth_header = self.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "").strip()
            if token != ADMIN_TOKEN:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "No autorizado"}')
                return

            st = AdminStore.load()
            sol_bal = get_solana_balance(PAYOUT_WALLET)
            lics = st.get("licenses", [])
            trials = len([l for l in lics if l.get("tier") == "TRIAL"])
            paids = len(lics) - trials
            events = st.get("activity", [])

            response_data = {
                "ok": True,
                "summary": {
                    "total_licenses": len(lics),
                    "trial_licenses": trials,
                    "paid_licenses": paids,
                    "sol_balance": sol_bal,
                    "total_events": len(events),
                    "total_revenue_usd": st.get("total_revenue_usd", 0.0)
                },
                "licenses": lics,
                "activity": events
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response_data, ensure_ascii=False).encode("utf-8"))
            return

        # 3. HEALTH CHECK / ROOT
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "service": "Quantum Trading Fleet 24/7 Webhook and Admin API", "bot": "@Mi_trading_xauusd_Bot"}')

    def do_POST(self):
        clean_path = resolve_route(self)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

        # 1. ADMIN LOGIN
        if clean_path in ["/api/admin/login", "/login"]:
            try:
                data = json.loads(body) if body else {}
                u = str(data.get("username", "")).strip()
                p = str(data.get("password", "")).strip()

                if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "token": ADMIN_TOKEN}).encode("utf-8"))
                else:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": "Credenciales invalidas"}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return

        # 2. ADMIN ISSUE LICENSE
        if clean_path in ["/api/admin/generate-license", "/generate-license"]:
            auth_header = self.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "").strip()
            if token != ADMIN_TOKEN:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "No autorizado"}')
                return

            try:
                data = json.loads(body) if body else {}
                acc = str(data.get("mt5_account", "")).strip()
                tier = str(data.get("tier", "QUARTERLY")).upper().strip()
                cust = str(data.get("customer", "")).strip() or "Emision Manual Web"

                if not acc:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"ok": false, "error": "Falta la cuenta MT5"}')
                    return

                key, exp = generate_quantum_key(acc, tier)
                AdminStore.add_license(tier, acc, key, exp, cust)
                AdminStore.add_activity("ADMIN_ISSUED", "Web Admin", 0, f"Emitio licencia {tier} para MT5 #{acc} ({cust})")
                notify_admin(f"🔑 <b>Licencia {tier} Emitida desde Panel Web</b>\n👤 Cuenta MT5: #{acc}\nClave: <code>{key}</code>")

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "key": key, "expiry": exp}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return

        # 3. ADMIN CLEAR TEST DATA
        if clean_path in ["/api/admin/clear-data", "/clear-data"]:
            auth_header = self.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "").strip()
            if token != ADMIN_TOKEN:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "No autorizado"}')
                return

            if os.path.exists(STATE_FILE):
                try:
                    os.remove(STATE_FILE)
                except Exception:
                    pass
            clean_state = {"licenses": [], "activity": [], "total_revenue_usd": 0.0}
            AdminStore.save(clean_state)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"ok": true, "message": "Datos de prueba eliminados exitosamente"}')
            return

        # 4. TELEGRAM WEBHOOK INBOUND
        try:
            update = json.loads(body) if body else {}
            handle_update(update)
        except Exception as e:
            print(f"Error handling webhook: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(b'{"ok": true}')
