"""Telegram commands for user-scoped FVG preferences and event statistics."""

import asyncio
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from alerts.fvg_store import FvgAlertSettings, FvgEventStore
from exchanges.bitunix import BitunixClient
from handlers.auth import authorized


WAITING_PRICE_TEMPLATE_KEY = "waiting_fvg_price_template"
PRICE_FILTER_TEMPLATE = (
    "💰 Настройка фильтра цены FVG\n\n"
    "Скопируй шаблон ниже, замени значения и отправь его одним сообщением:\n\n"
    "Инструмент: BTCUSDT\n"
    "Минимальная цена: 60000\n"
    "Максимальная цена: 90000\n"
    "Применять к: оба\n\n"
    "Можно написать «нет» вместо минимальной или максимальной цены.\n"
    "В последней строке доступны: оба, пред-FVG, подтверждённые.\n\n"
    "Чтобы отключить фильтр:\n"
    "Инструмент: BTCUSDT\n"
    "Фильтр: выключить\n\n"
    "Отмена: /cancel"
)


def parse_price_filter_template(text: str) -> dict:
    fields = {}
    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        fields[key.strip().lower().replace("ё", "е")] = value.strip()

    symbol = fields.get("инструмент", "").upper().replace("/", "")
    if not re.fullmatch(r"[A-Z0-9]{5,20}", symbol):
        raise ValueError("Укажи инструмент, например BTCUSDT.")

    disabled = fields.get("фильтр", "").lower() in {"выключить", "выкл", "off"}
    if disabled:
        return {"symbol": symbol, "enabled": False}

    def boundary(name):
        value = fields.get(name)
        if value is None:
            raise ValueError(f"Не заполнено поле «{name.capitalize()}».")
        if value.lower() in {"нет", "без", "-", "не ограничивать"}:
            return None
        return value.replace(" ", "").replace(",", ".")

    minimum = boundary("минимальная цена")
    maximum = boundary("максимальная цена")
    scope_label = fields.get("применять к", "").lower().replace("ё", "е")
    aliases = {
        "оба": "both", "обоим": "both", "both": "both",
        "пред-fvg": "pre", "пред fvg": "pre", "пред": "pre", "pre": "pre",
        "подтвержденные": "confirmed", "подтвержденный": "confirmed",
        "confirmed": "confirmed",
    }
    scope = aliases.get(scope_label)
    if scope is None:
        raise ValueError("В поле «Применять к» напиши: оба, пред-FVG или подтверждённые.")
    return {
        "symbol": symbol,
        "enabled": True,
        "minimum": minimum,
        "maximum": maximum,
        "scope": scope,
    }


async def send_price_filter_template(message):
    await message.reply_text(PRICE_FILTER_TEMPLATE)


@authorized
async def fvg_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting = context.args[0].lower() if context.args else "status"
    settings = FvgAlertSettings()
    chat_id = update.effective_chat.id
    if setting in {"on", "off"}:
        settings.set_enabled(chat_id, setting == "on")
    user = settings.user(chat_id)
    await update.effective_message.reply_text(format_fvg_settings(user))


@authorized
async def fvg_pre_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    setting = context.args[0].lower() if context.args else "status"
    settings = FvgAlertSettings()
    chat_id = update.effective_chat.id
    if setting in {"on", "off"}:
        settings.set_pre_enabled(chat_id, setting == "on")
    await update.effective_message.reply_text(format_fvg_settings(settings.user(chat_id)))


@authorized
async def fvg_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = FvgAlertSettings()
    chat_id = update.effective_chat.id
    if len(context.args) == 2 and context.args[0].lower() in {"add", "remove"}:
        action, symbol = context.args[0].lower(), context.args[1].upper()
        if action == "add":
            try:
                valid = await asyncio.to_thread(BitunixClient().is_open_symbol, symbol)
            except Exception:
                await update.effective_message.reply_text("Не удалось проверить инструмент через Bitunix. Попробуй позже.")
                return
            if not valid:
                await update.effective_message.reply_text(f"Инструмент {symbol} не найден или недоступен на Bitunix.")
                return
            settings.add_symbol(chat_id, symbol)
        else:
            settings.remove_symbol(chat_id, symbol)
    symbols = ", ".join(settings.user(chat_id).get("symbols", {})) or "не выбраны"
    await update.effective_message.reply_text(
        f"Инструменты FVG: {symbols}\nИспользуй: /fvg_symbol add ETHUSDT или /fvg_symbol remove ETHUSDT"
    )


@authorized
async def fvg_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = FvgAlertSettings()
    chat_id = update.effective_chat.id
    if len(context.args) >= 2 and context.args[1].lower() == "off":
        symbol = context.args[0].upper()
        settings.set_price_filter(chat_id, symbol, None, None, enabled=False)
    elif len(context.args) >= 3:
        symbol = context.args[0].upper()
        minimum = None if context.args[1] == "-" else context.args[1]
        maximum = None if context.args[2] == "-" else context.args[2]
        scope = context.args[3].lower() if len(context.args) > 3 else "both"
        if scope not in {"pre", "confirmed", "both"}:
            await update.effective_message.reply_text("Режим должен быть pre, confirmed или both.")
            return
        try:
            settings.set_price_filter(
                chat_id, symbol, minimum, maximum, enabled=True,
                apply_to_pre=scope in {"pre", "both"},
                apply_to_confirmed=scope in {"confirmed", "both"},
            )
        except ValueError as error:
            await update.effective_message.reply_text(str(error))
            return
    else:
        await send_price_filter_template(update.effective_message)
        context.user_data[WAITING_PRICE_TEMPLATE_KEY] = True
        return
    await update.effective_message.reply_text(format_fvg_settings(settings.user(chat_id)))


@authorized
async def fvg_price_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await send_price_filter_template(update.callback_query.message)
    context.user_data[WAITING_PRICE_TEMPLATE_KEY] = True


@authorized
async def receive_price_filter_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get(WAITING_PRICE_TEMPLATE_KEY):
        return
    try:
        values = parse_price_filter_template(update.effective_message.text)
        settings = FvgAlertSettings()
        chat_id = update.effective_chat.id
        symbol = values["symbol"]
        if symbol not in settings.user(chat_id).get("symbols", {}):
            valid = await asyncio.to_thread(BitunixClient().is_open_symbol, symbol)
            if not valid:
                raise ValueError(f"Инструмент {symbol} не найден на Bitunix.")
            settings.add_symbol(chat_id, symbol)
        if not values["enabled"]:
            settings.set_price_filter(chat_id, symbol, None, None, enabled=False)
            result = f"✅ Фильтр цены для {symbol} отключён."
        else:
            scope = values["scope"]
            settings.set_price_filter(
                chat_id,
                symbol,
                values["minimum"],
                values["maximum"],
                enabled=True,
                apply_to_pre=scope in {"pre", "both"},
                apply_to_confirmed=scope in {"confirmed", "both"},
            )
            scope_text = {
                "both": "пред-FVG и подтверждённых FVG",
                "pre": "пред-FVG",
                "confirmed": "подтверждённых FVG",
            }[scope]
            result = (
                f"✅ Фильтр цены сохранён\n"
                f"Инструмент: {symbol}\n"
                f"Диапазон: {values['minimum'] or 'без минимума'} — "
                f"{values['maximum'] or 'без максимума'}\n"
                f"Применяется к: {scope_text}"
            )
    except (ValueError, TypeError) as error:
        await update.effective_message.reply_text(
            f"Не получилось сохранить: {error}\n\nПоправь шаблон и отправь ещё раз или нажми /cancel."
        )
        return
    context.user_data.pop(WAITING_PRICE_TEMPLATE_KEY, None)
    await update.effective_message.reply_text(result)


@authorized
async def cancel_price_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(WAITING_PRICE_TEMPLATE_KEY, None)
    await update.effective_message.reply_text("Настройка фильтра отменена.")


def build_fvg_price_handlers():
    return (
        CommandHandler("fvg_price", fvg_price),
        CallbackQueryHandler(fvg_price_button, pattern=r"^menu:fvg-price$"),
        CommandHandler("cancel", cancel_price_filter),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_price_filter_template,
        ),
    )


@authorized
async def fvg_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_fvg_stats(update.effective_message, days=7)


async def send_fvg_stats(message, days=7):
    await message.reply_text(format_fvg_stats(days), reply_markup=build_fvg_stats_period_menu(days))


def format_fvg_stats(days=7):
    stats = FvgEventStore().summary(days)
    period = "всё время" if days is None else f"{days} дней"
    bull, bear = stats["BULLISH"], stats["BEARISH"]
    return (
        f"📊 FVG-события · {period}\n\n"
        f"🟢🐂 Бычьи: {bull['total']} (подтверждено {bull['confirmed']}, предварительных {bull['pre']})\n"
        f"🔴🐻 Медвежьи: {bear['total']} (подтверждено {bear['confirmed']}, предварительных {bear['pre']})\n"
        f"Отправлено уведомлений пользователям: {stats['deliveries']}"
    )


def build_fvg_stats_period_menu(selected_days=7):
    periods = ((7, "7 дней"), (30, "30 дней"), (None, "Всё время"))
    buttons = []
    for days, label in periods:
        if days == selected_days:
            label = f"✓ {label}"
        key = "all" if days is None else str(days)
        buttons.append(InlineKeyboardButton(label, callback_data=f"menu:fvg-stats:{key}"))
    return InlineKeyboardMarkup([buttons])


def format_fvg_settings(user: dict) -> str:
    def on(value):
        return "вкл." if value else "выкл."
    symbols = []
    for symbol, config in user.get("symbols", {}).items():
        price = config.get("price_filter", {})
        if price.get("enabled"):
            limits = f"{price.get('min') or '−∞'}…{price.get('max') or '+∞'}"
            symbols.append(f"{symbol} ({limits})")
        else:
            symbols.append(symbol)
    return (
        "⚙️ Настройки FVG 15м\n"
        f"Модуль: {on(user.get('enabled'))}\n"
        f"Подтверждённые: {on(user.get('notify_confirmed_fvg', True))}\n"
        f"Пред-FVG за 3 минуты: {on(user.get('notify_pre_fvg', False))}\n"
        f"Бычьи: {on(user.get('bullish_enabled', True))}; медвежьи: {on(user.get('bearish_enabled', True))}\n"
        f"Инструменты: {', '.join(symbols) or 'не выбраны'}"
    )
