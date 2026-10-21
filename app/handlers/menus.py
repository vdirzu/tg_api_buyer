from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import func, select

from app.database.models import AcceptedKey, Transaction, Withdrawal
from app.handlers.ui import content, navigation, render
from app.locales import tr
from app.services.errors import BusinessError
from app.services.pricing import display_amount

router = Router()


@router.callback_query(F.data == "home")
async def home(event, state: FSMContext, market, user):
    await state.clear()
    if not user.language:
        from app.handlers.onboarding import language_screen

        return await language_screen(event)
    if not user.currency:
        from app.handlers.onboarding import currency_screen

        return await currency_screen(event, user.language)
    lang = user.language
    config = await market.settings()
    rows = [
        [(tr(lang, key), key)] for key in ("catalog", "profile", "withdraw", "support", "about")
    ]
    if await market.is_admin(user.id):
        rows.append([(tr(lang, "admin"), "admin")])
    await render(event, content(config, lang, "main"), rows, config.get("image.main"))


@router.callback_query(F.data == "catalog")
async def catalog(event: CallbackQuery, state: FSMContext, market, user):
    await state.clear()
    config = await market.settings()
    products = await market.products()
    rows = [[(getattr(p, f"name_{user.language}"), f"product:{p.id}")] for p in products]
    await render(
        event,
        content(config, user.language, "catalog")
        + ("" if products else "\n" + tr(user.language, "no_products")),
        rows + navigation(user.language),
        config.get("image.catalog"),
    )


@router.callback_query(F.data.startswith("product:"))
async def product(event: CallbackQuery, market, user):
    item = await market.product(event.data.split(":", 1)[1])
    lang = user.language
    text = f"{getattr(item, f'name_{lang}')}\n\n{getattr(item, f'description_{lang}')}\n\n{tr(lang, 'price')}: {item.rate}\n{tr(lang, 'conditions')}: {getattr(item, f'conditions_{lang}')}"
    await render(
        event,
        text,
        [[(tr(lang, "submit"), f"submit:{item.id}")]] + navigation(lang, "catalog"),
        item.image,
    )


@router.callback_query(F.data == "profile")
async def profile(event: CallbackQuery, state: FSMContext, market, user):
    await state.clear()
    lang = user.language
    config = await market.settings()
    lines = [
        content(config, lang, "profile"),
        f"ID: {user.id}",
        f"{tr(lang, 'registered')}: {user.registered_at:%Y-%m-%d}",
        f"{tr(lang, 'language')}: {lang}",
        f"{tr(lang, 'currency')}: {user.currency}",
    ]
    try:
        rate, _ = await market.shown_balance(user)
        for key, value in [
            ("balance", user.available_usd),
            ("reserved", user.reserved_usd),
            ("earned", user.earned_usd),
            ("withdrawn", user.withdrawn_usd),
        ]:
            lines.append(f"{tr(lang, key)}: {display_amount(value, rate.value)} {user.currency}")
    except BusinessError:
        lines += [
            tr(lang, "rate_unavailable"),
            f"{tr(lang, 'balance')}: {user.available_usd} USD",
            f"{tr(lang, 'reserved')}: {user.reserved_usd} USD",
        ]
    async with market.sessions() as s:
        pending = await s.scalar(
            select(func.count())
            .select_from(Withdrawal)
            .where(Withdrawal.user_id == user.id, Withdrawal.status.in_(["pending", "processing"]))
        )
    lines += [
        f"{tr(lang, 'keys_count')}: {user.accepted_count}",
        f"{tr(lang, 'pending_count')}: {pending}",
    ]
    rows = [[(tr(lang, "change_language"), "language"), (tr(lang, "change_currency"), "currency")]]
    rows += [
        [(tr(lang, key), f"history:{key}:0")] for key in ("transactions", "keys", "withdrawals")
    ]
    rows += [
        [(tr(lang, "retry_pending"), "retry_pending")],
        [(tr(lang, "withdraw"), "withdraw"), (tr(lang, "support"), "support")],
    ]
    await render(event, "\n".join(lines), rows + navigation(lang), config.get("image.profile"))


def history_line(row, lang):
    header = f"#{row.id} · {row.created_at:%Y-%m-%d %H:%M} UTC"
    if isinstance(row, AcceptedKey):
        return (
            f"{header}\n{row.product_id} · {tr(lang, row.status)}\n"
            f"{tr(lang, 'keys_balance')}: {row.balance_usd}\n{tr(lang, 'price')}: {row.purchase_rate}\n"
            f"{tr(lang, 'discount')}: {row.discount * 100:.0f}%\n"
            f"{tr(lang, 'keys_region')}: {tr(lang, 'yes' if row.csv_region_restricted else 'no')}\n"
            f"{tr(lang, 'keys_test_region')}: {tr(lang, 'yes' if row.test_region_restricted else 'no')}\n"
            f"{row.credited_amount} {row.currency} · FX {row.exchange_rate}"
        )
    if isinstance(row, Withdrawal):
        return (
            f"{header}\n{row.amount} {row.currency} · {row.destination_label}\n{tr(lang, row.status)}"
            + (f"\n{row.reason}" if row.reason else "")
        )
    if isinstance(row, Transaction):
        return (
            f"{header}\n{tr(lang, row.kind)} · {tr(lang, row.status)}\n{row.amount} {row.currency}"
        )
    return header


@router.callback_query(F.data.startswith("history:"))
async def history(event: CallbackQuery, market, user):
    _, kind, raw_page = event.data.split(":")
    page = int(raw_page)
    items = await market.history(user.id, kind, page)
    lang = user.language
    lines = [tr(lang, kind)]
    async with market.sessions() as session:
        for item in items[:5]:
            if isinstance(item, Transaction) and item.accepted_key_id:
                key = await session.get(AcceptedKey, item.accepted_key_id)
                lines.append(history_line(key, lang))
            else:
                lines.append(history_line(item, lang))
    if not items:
        lines.append(tr(lang, "empty"))
    pagination = []
    if page:
        pagination.append((tr(lang, "prev"), f"history:{kind}:{page - 1}"))
    if len(items) > 5:
        pagination.append((tr(lang, "next"), f"history:{kind}:{page + 1}"))
    await render(
        event,
        "\n\n".join(lines),
        ([pagination] if pagination else []) + navigation(lang, "profile"),
    )


@router.callback_query(F.data.in_({"support", "about", "terms", "privacy"}))
async def information(event: CallbackQuery, market, user):
    # Support and legal screens deliberately preserve the current FSM workflow.
    config, lang = await market.settings(), user.language
    key = event.data
    rows = []
    if key == "support":
        text = content(config, lang, key, tr(lang, "contact_fallback"))
        contact = config.get(f"support_contact.{lang}", "").lstrip("@")
        if contact:
            text += f"\n@{contact}"
            rows.append([(tr(lang, "open_contact"), f"url:https://t.me/{contact}")])
    elif key == "about":
        text = content(config, lang, key, tr(lang, "about_text"))
        for legal in ("terms", "privacy"):
            url = config.get(f"{legal}_url.{lang}")
            rows.append([(tr(lang, legal), f"url:{url}" if url else legal)])
        rows.append([(tr(lang, "support"), "support")])
    else:
        text = content(config, lang, "legal_fallback")
    await render(
        event,
        text,
        rows + navigation(lang, "about" if key in {"terms", "privacy"} else "home"),
        config.get(f"image.{key}"),
    )
