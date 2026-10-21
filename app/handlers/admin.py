import json

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.menus import history_line
from app.handlers.states import Flow
from app.handlers.ui import navigation, render
from app.locales import tr
from app.services.errors import BusinessError

router = Router()


async def authorize(market, user):
    if not await market.is_admin(user.id):
        raise BusinessError("unauthorized")


@router.message(Command("admin"))
@router.callback_query(F.data == "admin")
async def panel(event, state: FSMContext, market, user):
    await authorize(market, user)
    await state.clear()
    lang = user.language or "en"
    actions = [
        ("dashboard", "ad:stats:30"),
        ("products_manage", "ad:products"),
        ("content_manage", "ad:config"),
        ("images_manage", "ad:image"),
        ("crypto_manage", "ad:crypto"),
        ("admins_manage", "ad:admins"),
        ("withdrawals", "ad:withdrawals:0"),
        ("users_manage", "ad:user"),
    ]
    await render(
        event,
        tr(lang, "admin"),
        [[(tr(lang, label), target)] for label, target in actions] + navigation(lang),
    )


@router.callback_query(F.data.startswith("ad:stats:"))
async def dashboard(event: CallbackQuery, market, user):
    days = int(event.data.rsplit(":", 1)[1])
    data = await market.dashboard(user.id, days)
    lang = user.language
    lines = [f"{tr(lang, 'days')}: {days}"]
    for key, value in data.items():
        if key == "recent":
            value = "\n" + "\n".join(
                f"{r['at'][:16]} · {r['actor']} · {r['event']} · {r['entity']}" for r in value
            )
        elif isinstance(value, list):
            value = "\n" + "\n".join(" / ".join(row) for row in value)
        lines.append(f"{tr(lang, 'stat_' + key)}: {value}")
    rows = [[(str(n), f"ad:stats:{n}") for n in (1, 7, 30, 365)]]
    await render(event, "\n".join(lines)[:4000], rows + navigation(lang, "admin"))


@router.callback_query(
    F.data.in_({"ad:products", "ad:config", "ad:image", "ad:crypto", "ad:admins", "ad:user"})
)
async def edit(event: CallbackQuery, state: FSMContext, market, user):
    await authorize(market, user)
    action = event.data.split(":")[1]
    mapping = {
        "products": (Flow.admin_product, "json_product"),
        "config": (Flow.admin_config, "json_config"),
        "image": (Flow.admin_image, "image_prompt"),
        "crypto": (Flow.admin_crypto, "json_crypto"),
        "admins": (Flow.admin_admins, "json_admin"),
        "user": (Flow.admin_user, "user_prompt"),
    }
    next_state, prompt = mapping[action]
    await state.set_state(next_state)
    text = tr(user.language, prompt)
    if action == "products":
        text += '\n{"id":"provider_a","name_ru":"Пример AI","name_en":"Example AI","rate":"0.30"}\n'
        text += "\n".join(
            f"{p.id} · {p.rate} · {tr(user.language, 'yes' if p.active else 'no')} · {p.display_order}"
            for p in await market.products(admin=user.id)
        )
    elif action == "admins":
        text += "\n" + ", ".join(str(a.id) for a in await market.admins(user.id))
    elif action == "crypto":
        async with market.sessions() as s:
            from sqlalchemy import select
            from app.database.models import CryptoOption

            options = list(await s.scalars(select(CryptoOption).order_by(CryptoOption.id)))
        text += "\n" + "\n".join(
            f"{o.id}: {o.asset} / {o.network} · {tr(user.language, 'yes' if o.active else 'no')}"
            for o in options
        )
    await render(event, text[:4000], navigation(user.language, "admin"))


@router.message(Flow.admin_product, F.text)
@router.message(Flow.admin_config, F.text)
@router.message(Flow.admin_crypto, F.text)
@router.message(Flow.admin_admins, F.text)
async def save_json(message: Message, state: FSMContext, market, user):
    await authorize(market, user)
    try:
        data = json.loads(message.text, parse_float=str)
        if not isinstance(data, dict):
            raise ValueError
    except (ValueError, TypeError):
        raise BusinessError("invalid_input") from None
    current = await state.get_state()
    if current == Flow.admin_product.state:
        await market.save_product(user.id, data)
    elif current == Flow.admin_config.state:
        if set(data) != {"key", "value"} or not isinstance(data["key"], str):
            raise BusinessError("invalid_input")
        await market.set_config(user.id, data["key"], data["value"])
    elif current == Flow.admin_crypto.state:
        await market.save_crypto(user.id, data)
    else:
        if (
            set(data) != {"id", "active"}
            or type(data["id"]) is not int
            or type(data["active"]) is not bool
        ):
            raise BusinessError("invalid_input")
        await market.change_admin(user.id, data["id"], data["active"])
    await render(message, tr(user.language, "saved"), navigation(user.language, "admin"))


@router.message(Flow.admin_image, F.photo)
async def save_image(message: Message, market, user):
    await authorize(market, user)
    target, image = (message.caption or "").strip(), message.photo[-1].file_id
    if target.startswith("product:"):
        await market.save_product(user.id, {"id": target.split(":", 1)[1], "image": image})
    else:
        await market.set_config(user.id, f"image.{target}", image)
    await render(message, tr(user.language, "saved"), navigation(user.language, "admin"))


async def show_user(event, market, actor, user_id):
    row, keys = await market.inspect_user(actor.id, user_id)
    lang = actor.language
    text = (
        f"ID: {row.id}\n{tr(lang, 'balance')}: {row.available_usd} USD\n"
        f"{tr(lang, 'reserved')}: {row.reserved_usd} USD\n{tr(lang, 'earned')}: {row.earned_usd} USD\n"
        f"{tr(lang, 'withdrawn')}: {row.withdrawn_usd} USD\n{tr(lang, 'keys_count')}: {row.accepted_count}\n\n"
    )
    text += "\n\n".join(history_line(key, lang) for key in keys)
    await render(event, text, navigation(lang, "admin"))


@router.message(Flow.admin_user, F.text)
async def user_lookup(message: Message, market, user):
    await authorize(market, user)
    await show_user(message, market, user, int(message.text))


@router.callback_query(F.data.startswith("ad:view_user:"))
async def user_callback(event: CallbackQuery, market, user):
    await show_user(event, market, user, int(event.data.rsplit(":", 1)[1]))


def withdrawal_summary(row, lang):
    return (
        f"#{row.id} · ID {row.user_id}\n{row.amount} {row.currency}\n{row.destination_label}\n"
        f"{row.created_at:%Y-%m-%d %H:%M} UTC\n{tr(lang, row.status)}"
    )


def withdrawal_rows(row, lang):
    rows = []
    if row.status in {"pending", "processing"}:
        if row.status == "pending":
            rows.append([(tr(lang, "processing"), f"ad:action:{row.id}:processing")])
        rows += [
            [(tr(lang, "paid"), f"ad:action:{row.id}:paid")],
            [
                (tr(lang, "rejected"), f"ad:action:{row.id}:rejected"),
                (tr(lang, "cancelled"), f"ad:action:{row.id}:cancelled"),
            ],
        ]
    rows += [
        [
            (tr(lang, "view_details"), f"ad:details:{row.id}"),
            (tr(lang, "view_user"), f"ad:view_user:{row.user_id}"),
        ]
    ]
    return rows


@router.callback_query(F.data.startswith("ad:withdrawals:"))
async def pending(event: CallbackQuery, market, user):
    page = int(event.data.rsplit(":", 1)[1])
    if not 0 <= page <= 100000:
        raise BusinessError("invalid_input")
    requests = await market.admin_withdrawals(user.id, page)
    rows = [[(f"#{w.id} · {w.amount} {w.currency}", f"ad:details:{w.id}")] for w in requests[:5]]
    pager = []
    if page:
        pager.append((tr(user.language, "prev"), f"ad:withdrawals:{page - 1}"))
    if len(requests) > 5:
        pager.append((tr(user.language, "next"), f"ad:withdrawals:{page + 1}"))
    await render(
        event,
        tr(user.language, "withdrawals") if requests else tr(user.language, "empty"),
        rows + ([pager] if pager else []) + navigation(user.language, "admin"),
    )


@router.callback_query(F.data.startswith("ad:details:"))
async def payment_details(event: CallbackQuery, market, user):
    row, details = await market.withdrawal_details(user.id, int(event.data.rsplit(":", 1)[1]))
    await render(
        event,
        withdrawal_summary(row, user.language)
        + "\n"
        + details
        + ("\n" + row.reason if row.reason else ""),
        withdrawal_rows(row, user.language) + navigation(user.language, "ad:withdrawals:0"),
    )


async def status_notification(bot, market, withdrawal):
    owner = await market.user(withdrawal.user_id)
    text = f"{tr(owner.language, 'withdraw_status')}: #{withdrawal.id} · {tr(owner.language, withdrawal.status)}"
    if withdrawal.reason:
        text += "\n" + withdrawal.reason
    try:
        await bot.send_message(owner.id, text)
    except TelegramAPIError:
        # Financial commit has already happened; status is always visible in history.
        import logging

        logging.getLogger(__name__).warning(
            "user_notification_failed", extra={"withdrawal_id": withdrawal.id}
        )


@router.callback_query(F.data.startswith("ad:action:"))
async def action(event: CallbackQuery, state: FSMContext, market, user, bot):
    await authorize(market, user)
    _, _, request_id, target = event.data.split(":")
    if target in {"rejected", "cancelled"}:
        await state.set_state(Flow.admin_reason)
        await state.update_data(request_id=int(request_id), target=target)
        return await render(
            event,
            tr(user.language, "reason_prompt"),
            navigation(user.language, f"ad:details:{request_id}"),
        )
    withdrawal = await market.transition(user.id, int(request_id), target)
    await status_notification(bot, market, withdrawal)
    await render(
        event,
        withdrawal_summary(withdrawal, user.language),
        withdrawal_rows(withdrawal, user.language) + navigation(user.language, "ad:withdrawals:0"),
    )


@router.message(Flow.admin_reason, F.text)
async def reason(message: Message, state: FSMContext, market, user, bot):
    await authorize(market, user)
    data = await state.get_data()
    withdrawal = await market.transition(user.id, data["request_id"], data["target"], message.text)
    await state.clear()
    await status_notification(bot, market, withdrawal)
    await render(
        message,
        withdrawal_summary(withdrawal, user.language),
        navigation(user.language, "ad:withdrawals:0"),
    )
