from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    key = State()
    withdraw_amount = State()
    withdraw_destination = State()
    admin_product = State()
    admin_config = State()
    admin_crypto = State()
    admin_admins = State()
    admin_image = State()
    admin_user = State()
    admin_reason = State()
