# Русская локаль. Многострочные значения — с отступом, пустая строка завершает сообщение.

# ─── Общее ───────────────────────────────────────────────────────────────────
btn-back = ⬅️ Назад
btn-cancel = ✖️ Отмена
btn-main-menu = 🏠 Главное меню
btn-skip = Пропустить

# ─── Старт и главное меню ────────────────────────────────────────────────────
choose-language = Выберите язык / اختر اللغة
language-set = Язык переключён на русский.

welcome =
    Добро пожаловать! 🥙
    Соберите заказ в меню — привезём горячим.

main-menu = Чем займёмся?
menu-catalog = 🥙 Меню
menu-cart = 🛒 Корзина
menu-orders = 📋 Мои заказы
menu-contacts = ☎️ Контакты
menu-language = 🌐 Язык

# ─── Каталог ─────────────────────────────────────────────────────────────────
menu-dish = 🥙 <b>{ $name }</b> — { $desc }
menu-pick = Выберите блюда:
catalog-title = Выберите категорию:
catalog-empty = Меню пока пустое. Загляните чуть позже.
category-empty = В этой категории пока нет блюд.

product-card =
    <b>{ $name }</b>
    { $desc }

product-price-line = Цена: <b>{ $price }</b>
product-unavailable = «{ $name }» сейчас закончилась.
btn-add-to-cart = 🛒 В корзину · { $price }
cart-added = «{ $name }» × { $qty } в корзине 🛒
cart-added-title = ✅ Добавлено: <b>{ $name }</b> × { $qty }
btn-go-to-cart = 🛒 Корзина · { $total }
btn-continue-shopping = 🥙 Выбрать ещё
option-group-required = Выберите: { $group }
page-of = { $page } из { $pages }

# ─── Корзина ─────────────────────────────────────────────────────────────────
cart-title = 🛒 <b>Ваш заказ</b>
cart-empty = Корзина пуста. Загляните в меню 🥙
cart-line = { $index }. { $name }{ $options } — { $qty } × { $price } = <b>{ $total }</b>
cart-subtotal = Сумма: <b>{ $subtotal }</b>
btn-checkout = ✅ Оформить
btn-clear-cart = 🗑 Очистить
cart-cleared = Корзина очищена.
cart-unavailable-removed = Убрали из корзины то, что закончилось: { $names }
cart-min-order = Минимальная сумма заказа — { $min }. Не хватает { $left }.

# ─── Оформление ──────────────────────────────────────────────────────────────
checkout-closed = Сейчас закрыто. Принимаем заказы { $hours }.
checkout-fulfillment = Как удобнее получить заказ?
btn-delivery = 🛵 Доставка
btn-pickup = 🏃 Самовывоз

checkout-location = Отправьте геолокацию — посчитаем доставку.
btn-send-location = 📍 Отправить локацию
checkout-location-invalid = Нужна именно геолокация: нажмите кнопку ниже.
checkout-out-of-zone =
    К сожалению, туда мы не доезжаем: { $distance } км от кухни, возим до { $max } км.
    Напишите { $support } — попробуем что-нибудь придумать.
checkout-in-zone = Доставка: { $fee } ({ $distance } км).

checkout-branch = Выберите точку самовывоза:
checkout-branch-picked = 🏃 { $name }, { $address }

checkout-contact = Курьер свяжется с вами в Telegram — подтвердите аккаунт.
btn-send-username = 📨 Отправить @{ $username }
btn-contact-telegram = 📨 Писать мне в Telegram

checkout-payment = Как будете платить?
btn-pay-cash = 💵 Наличными при получении
btn-pay-shamcash = 📱 ShamCash
payment-method-cash = Наличными при получении
payment-method-shamcash = ShamCash

checkout-comment = Комментарий к заказу? Например: ориентир рядом с домом, без лука.

checkout-confirm-title = Проверьте заказ:
checkout-confirm-delivery = 🛵 Доставка по вашей геолокации, { $distance } км
checkout-confirm-pickup = 🏃 Самовывоз: { $branch }
checkout-confirm-contact = 💬 Связь в Telegram: @{ $username }
checkout-confirm-no-username = 💬 Связь через Telegram
checkout-confirm-comment = 💬 { $comment }
checkout-confirm-payment = 💳 { $method }
checkout-confirm-delivery-fee = Доставка: { $fee }
checkout-confirm-delivery-free = Доставка: бесплатно 🎉
checkout-confirm-total = <b>К оплате: { $total }</b>
btn-confirm-order = ✅ Подтвердить заказ
checkout-cancelled = Оформление отменено, корзина сохранена.

order-created-cash =
    Заказ <b>№{ $no }</b> принят! 🎉
    Напишем, как только кухня возьмёт его в работу.

order-created-shamcash =
    Заказ <b>№{ $no }</b> создан.
    Осталось оплатить — инструкция ниже 👇

# ─── ShamCash ────────────────────────────────────────────────────────────────
shamcash-instructions =
    💳 <b>Оплата ShamCash</b>
    Переведите <b>{ $total }</b> на кошелёк:
    <code>{ $wallet }</code>
    Получатель: <b>{ $holder }</b>
    Затем пришлите <b>скриншот перевода</b>, а следом — <b>номер транзакции</b>.
    ⏳ Ждём оплату до конца дня, потом заказ отменится сам.

shamcash-need-photo = Пришлите, пожалуйста, скриншот перевода фотографией.
shamcash-need-ref = Скриншот получен 👍 Теперь пришлите номер транзакции из ShamCash.
shamcash-ref-invalid = В номере транзакции должны быть цифры. Проверьте и пришлите ещё раз.
shamcash-received = Спасибо! Проверяем оплату — обычно это пара минут.
shamcash-confirmed = Оплата подтверждена ✅ Заказ №{ $no } передан на кухню.

shamcash-rejected =
    Оплату по заказу №{ $no } подтвердить не удалось ❌
    Проверьте сумму и получателя и пришлите скриншот ещё раз, либо напишите { $support }.

shamcash-timeout = Заказ №{ $no } отменён: оплата не поступила до конца дня.

# ─── Уведомления о статусе ───────────────────────────────────────────────────
status-accepted = Заказ №{ $no } принят ✅
status-cooking = Готовим ваш заказ №{ $no } 👨‍🍳
status-ready-delivery = Заказ №{ $no } готов, курьер забирает его 🥙
status-ready-pickup = Заказ №{ $no } готов — ждём вас 🥙
status-on_the_way = Курьер выехал 🛵 Заказ №{ $no } скоро у вас.
status-delivered = Заказ №{ $no } доставлен. Приятного аппетита! 🎉
status-picked_up = Спасибо за заказ №{ $no }! Приятного аппетита 🎉
status-cancelled = Заказ №{ $no } отменён. Если это ошибка — напишите { $support }.

# ─── Названия статусов ───────────────────────────────────────────────────────
status-name-new = Новый
status-name-awaiting_payment = Ждёт оплату
status-name-payment_submitted = Чек прислан
status-name-payment_rejected = Оплата отклонена
status-name-accepted = Принят
status-name-cooking = Готовится
status-name-ready = Готов
status-name-on_the_way = В пути
status-name-delivered = Доставлен
status-name-picked_up = Выдан
status-name-cancelled = Отменён

# ─── Мои заказы и контакты ───────────────────────────────────────────────────
orders-title = 📋 <b>Последние заказы</b>
orders-empty = Заказов пока нет.
orders-line = №{ $no } · { $date } · { $status } · { $total }
btn-repeat-order = 🔁 Повторить №{ $no }
orders-repeat-done = Позиции добавлены в корзину 🛒
orders-repeat-partial = Часть позиций закончилась и не добавлена: { $names }
orders-repeat-empty = Ни одной позиции из того заказа сейчас нет в меню.

contacts =
    ☎️ { $support }
    🕒 Работаем { $hours }
    📍 { $address }

# ─── Ошибки ──────────────────────────────────────────────────────────────────
error-generic = Что-то пошло не так. Попробуйте ещё раз или напишите { $support }.
error-too-fast = Слишком быстро 🙂 Секунду.
error-stale-button = Эта кнопка уже неактуальна.

# ─── Карточка для кухни ──────────────────────────────────────────────────────
kitchen-new-order = 🔔 Новый заказ №{ $no }

kitchen-card =
    { $emoji } <b>Заказ №{ $no }</b> · { $time }
    Статус: <b>{ $status }</b>
    ━━━━━━━━━━━━━━
    { $items }
    ━━━━━━━━━━━━━━
    { $money }
    { $fulfillment }
    { $contact }
    👤 { $client }
    { $payment }{ $comment }
    { $log }

kitchen-phone = ☎️ <code>{ $phone }</code>
kitchen-contact-username = 💬 <a href="https://t.me/{ $username }">@{ $username }</a>
kitchen-no-phone = 💬 Писать клиенту в Telegram
kitchen-item-line = • { $name }{ $options } × { $qty } — { $total }
kitchen-money = Блюда: { $subtotal } · Доставка: { $delivery } · <b>Итого: { $total }</b>
kitchen-delivery = 🛵 Доставка, { $distance } км — точка на карте ниже 👇
kitchen-address = 📍 { $address }
kitchen-pickup = 🏃 Самовывоз: { $branch }
kitchen-comment = 💬 { $comment }
kitchen-payment-cash = 💵 Наличные при получении
kitchen-payment-shamcash = 📱 ShamCash — { $state }
kitchen-payment-state-awaiting = ждём чек
kitchen-payment-state-submitted = чек прислан, проверьте
kitchen-payment-state-confirmed = оплачено
kitchen-payment-state-rejected = отклонено
kitchen-payment-ref = 🧾 Транзакция: <code>{ $ref }</code>
kitchen-log-line = { $emoji } { $status } · { $time } · { $actor }
kitchen-proof-caption = 🧾 Чек к заказу №{ $no }
kitchen-stale = Заказ уже в статусе «{ $status }».
kitchen-not-allowed = Кнопки заказа работают только в группе кухни.
kitchen-chat-id = ID этого чата: <code>{ $chat_id }</code>

kitchen-btn-accepted = ✅ Принять
kitchen-btn-cooking = 👨‍🍳 Готовится
kitchen-btn-ready = 🥙 Готов
kitchen-btn-on_the_way = 🛵 В пути
kitchen-btn-delivered = 🎉 Доставлен
kitchen-btn-picked_up = 🎉 Выдан
kitchen-btn-cancelled = ❌ Отменить
kitchen-btn-awaiting_payment = ⏳ Ждать оплату
kitchen-btn-payment_rejected = ⚠️ Оплата не пришла
