# tests/try_payments.py
# اختبار منطق الدفع بدون تيليجرام: python -m tests.try_payments

import asyncio
import uuid
from types import SimpleNamespace

from bot.database import crud
from bot.database.init_db import init_db
from bot.keyboards.main_menu import main_menu_keyboard
from bot.keyboards.platform_menu import platform_menu_keyboard
from bot.keyboards.subscription_menu import donate_menu_keyboard, subscription_menu_keyboard
from bot.services.payments import apply_successful_payment, validate_precheckout

USER_ID = 999999


async def main() -> None:
    await init_db()
    await crud.get_or_create_user(USER_ID, "tester", "Tester")

    print("keyboards:", [
        len(k.inline_keyboard)
        for k in (main_menu_keyboard(), platform_menu_keyboard(),
                  subscription_menu_keyboard(), donate_menu_keyboard())
    ])

    print("precheckout good :", validate_precheckout("plan:p100", 100, "XTR"))
    print("precheckout wrong:", validate_precheckout("plan:p100", 1, "XTR"))

    payment = SimpleNamespace(
        invoice_payload="plan:p100",
        total_amount=100,
        telegram_payment_charge_id="TEST-" + uuid.uuid4().hex,
    )
    print("first  :", (await apply_successful_payment(USER_ID, payment))[0])
    print("second :", (await apply_successful_payment(USER_ID, payment))[0])

    stats = await crud.get_user_stats(USER_ID)
    print("balance:", stats["balance"])


asyncio.run(main())