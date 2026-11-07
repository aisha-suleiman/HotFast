# اللغة العربية — الترجمة الافتراضية للبوت.
# القيم متعددة الأسطر تُكتب بمسافة بادئة، والسطر الفارغ ينهي الرسالة.

# ─── عام ─────────────────────────────────────────────────────────────────────
btn-back = ⬅️ رجوع
btn-cancel = ✖️ إلغاء
btn-main-menu = 🏠 القائمة الرئيسية
btn-skip = تخطّي

# ─── البداية والقائمة الرئيسية ───────────────────────────────────────────────
choose-language = اختر اللغة / Выберите язык
language-set = تم التبديل إلى العربية.

welcome =
    أهلاً وسهلاً! 🥙
    اختر طلبك من القائمة ونوصله لك ساخناً.

main-menu = كيف نبدأ؟
menu-catalog = 🥙 القائمة
menu-cart = 🛒 السلة
menu-orders = 📋 طلباتي
menu-contacts = ☎️ تواصل معنا
menu-language = 🌐 اللغة

# ─── القائمة والأصناف ────────────────────────────────────────────────────────
menu-dish = 🥙 <b>{ $name }</b> — { $desc }
menu-pick = اختر الأصناف:
catalog-title = اختر القسم:
catalog-empty = القائمة فارغة حالياً. عاود المحاولة بعد قليل.
category-empty = لا توجد أصناف في هذا القسم حالياً.

product-card =
    <b>{ $name }</b>
    { $desc }

product-price-line = السعر: <b>{ $price }</b>
product-unavailable = «{ $name }» غير متوفّر حالياً.
btn-add-to-cart = 🛒 أضف للسلة · { $price }
cart-added = «{ $name }» × { $qty } في السلة 🛒
cart-added-title = ✅ تمت الإضافة: <b>{ $name }</b> × { $qty }
btn-go-to-cart = 🛒 السلة · { $total }
btn-continue-shopping = 🥙 اختر المزيد
option-group-required = اختر: { $group }
page-of = { $page } من { $pages }

# ─── السلة ───────────────────────────────────────────────────────────────────
cart-title = 🛒 <b>طلبك</b>
cart-empty = السلة فارغة. تفضّل إلى القائمة 🥙
cart-line = { $index }. { $name }{ $options } — { $qty } × { $price } = <b>{ $total }</b>
cart-subtotal = المجموع: <b>{ $subtotal }</b>
btn-checkout = ✅ إتمام الطلب
btn-clear-cart = 🗑 إفراغ السلة
cart-cleared = تم إفراغ السلة.
cart-unavailable-removed = أزلنا من السلة ما نفد: { $names }
cart-min-order = الحد الأدنى للطلب { $min }. ينقصك { $left }.

# ─── إتمام الطلب ─────────────────────────────────────────────────────────────
checkout-closed = نحن مغلقون الآن. نستقبل الطلبات { $hours }.
checkout-fulfillment = كيف تفضّل استلام طلبك؟
btn-delivery = 🛵 توصيل
btn-pickup = 🏃 استلام من الفرع

checkout-location = أرسل موقعك لنحسب أجرة التوصيل.
btn-send-location = 📍 إرسال الموقع
checkout-location-invalid = نحتاج الموقع الجغرافي: اضغط الزر بالأسفل.
checkout-out-of-zone =
    للأسف لا نصل إلى هناك: المسافة { $distance } كم من المطبخ، ونوصّل حتى { $max } كم.
    راسلنا على { $support } وسنحاول إيجاد حل.
checkout-in-zone = التوصيل: { $fee } ({ $distance } كم).

checkout-branch = اختر فرع الاستلام:
checkout-branch-picked = 🏃 { $name }، { $address }

checkout-contact = سيتواصل معك السائق عبر تيليغرام — أكّد حسابك.
btn-send-username = 📨 إرسال @{ $username }
btn-contact-telegram = 📨 راسلوني على تيليغرام

checkout-payment = كيف ستدفع؟
btn-pay-cash = 💵 نقداً عند الاستلام
btn-pay-shamcash = 📱 شام كاش
payment-method-cash = نقداً عند الاستلام
payment-method-shamcash = شام كاش

checkout-comment = هل من ملاحظة على الطلب؟ مثلاً: أقرب معلم، بدون بصل.

checkout-confirm-title = راجع طلبك:
checkout-confirm-delivery = 🛵 توصيل إلى موقعك، { $distance } كم
checkout-confirm-pickup = 🏃 استلام من: { $branch }
checkout-confirm-contact = 💬 التواصل عبر تيليغرام: @{ $username }
checkout-confirm-no-username = 💬 التواصل عبر تيليغرام
checkout-confirm-comment = 💬 { $comment }
checkout-confirm-payment = 💳 { $method }
checkout-confirm-delivery-fee = التوصيل: { $fee }
checkout-confirm-delivery-free = التوصيل: مجاناً 🎉
checkout-confirm-total = <b>الإجمالي: { $total }</b>
btn-confirm-order = ✅ تأكيد الطلب
checkout-cancelled = تم إلغاء الإتمام، وسلتك محفوظة.

order-created-cash =
    تم استلام الطلب <b>رقم { $no }</b>! 🎉
    سنعلمك فور بدء المطبخ بتحضيره.

order-created-shamcash =
    تم إنشاء الطلب <b>رقم { $no }</b>.
    بقي الدفع — التعليمات بالأسفل 👇

# ─── شام كاش ─────────────────────────────────────────────────────────────────
shamcash-instructions =
    💳 <b>الدفع عبر شام كاش</b>
    حوّل مبلغ <b>{ $total }</b> إلى المحفظة:
    <code>{ $wallet }</code>
    اسم المستفيد: <b>{ $holder }</b>
    ثم أرسل <b>صورة إشعار التحويل</b> وبعدها <b>رقم العملية</b>.
    ⏳ ننتظر الدفع حتى نهاية اليوم، وبعدها يُلغى الطلب تلقائياً.

shamcash-need-photo = أرسل من فضلك صورة إشعار التحويل.
shamcash-need-ref = وصلتنا الصورة 👍 أرسل الآن رقم العملية من شام كاش.
shamcash-ref-invalid = رقم العملية يجب أن يحتوي أرقاماً. تحقّق وأعد الإرسال.
shamcash-received = شكراً لك! نتحقّق من الدفع، وعادةً لا يستغرق سوى دقائق.
shamcash-confirmed = تم تأكيد الدفع ✅ الطلب رقم { $no } في المطبخ الآن.

shamcash-rejected =
    تعذّر تأكيد الدفع للطلب رقم { $no } ❌
    تحقّق من المبلغ واسم المستفيد وأعد إرسال الصورة، أو راسلنا على { $support }.

shamcash-timeout = أُلغي الطلب رقم { $no }: لم يصلنا الدفع حتى نهاية اليوم.

# ─── إشعارات الحالة ──────────────────────────────────────────────────────────
status-accepted = تم قبول الطلب رقم { $no } ✅
status-cooking = نحضّر طلبك رقم { $no } الآن 👨‍🍳
status-ready-delivery = الطلب رقم { $no } جاهز والسائق في طريقه لاستلامه 🥙
status-ready-pickup = الطلب رقم { $no } جاهز — بانتظارك 🥙
status-on_the_way = السائق انطلق 🛵 الطلب رقم { $no } سيصلك قريباً.
status-delivered = تم توصيل الطلب رقم { $no }. بالهناء والشفاء! 🎉
status-picked_up = شكراً لطلبك رقم { $no }! بالهناء والشفاء 🎉
status-cancelled = أُلغي الطلب رقم { $no }. إن كان ذلك بالخطأ راسلنا على { $support }.

# ─── أسماء الحالات ───────────────────────────────────────────────────────────
status-name-new = جديد
status-name-awaiting_payment = بانتظار الدفع
status-name-payment_submitted = وصل الإشعار
status-name-payment_rejected = الدفع مرفوض
status-name-accepted = مقبول
status-name-cooking = قيد التحضير
status-name-ready = جاهز
status-name-on_the_way = في الطريق
status-name-delivered = تم التوصيل
status-name-picked_up = تم الاستلام
status-name-cancelled = ملغى

# ─── طلباتي والتواصل ─────────────────────────────────────────────────────────
orders-title = 📋 <b>آخر الطلبات</b>
orders-empty = لا توجد طلبات بعد.
orders-line = رقم { $no } · { $date } · { $status } · { $total }
btn-repeat-order = 🔁 كرّر الطلب { $no }
orders-repeat-done = أضفنا الأصناف إلى السلة 🛒
orders-repeat-partial = بعض الأصناف نفد ولم يُضف: { $names }
orders-repeat-empty = لا يتوفّر أي صنف من ذلك الطلب حالياً.

contacts =
    ☎️ { $support }
    🕒 أوقات العمل { $hours }
    📍 { $address }

# ─── الأخطاء ─────────────────────────────────────────────────────────────────
error-generic = حدث خطأ ما. أعد المحاولة أو راسلنا على { $support }.
error-too-fast = بهدوء 🙂 لحظة من فضلك.
error-stale-button = هذا الزر لم يعد صالحاً.

# ─── بطاقة المطبخ ────────────────────────────────────────────────────────────
kitchen-new-order = 🔔 طلب جديد رقم { $no }

kitchen-card =
    { $emoji } <b>الطلب رقم { $no }</b> · { $time }
    الحالة: <b>{ $status }</b>
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
kitchen-no-phone = 💬 راسل الزبون عبر تيليغرام
kitchen-item-line = • { $name }{ $options } × { $qty } — { $total }
kitchen-money = الأصناف: { $subtotal } · التوصيل: { $delivery } · <b>الإجمالي: { $total }</b>
kitchen-delivery = 🛵 توصيل، { $distance } كم — الموقع في الرسالة أدناه 👇
kitchen-address = 📍 { $address }
kitchen-pickup = 🏃 استلام من الفرع: { $branch }
kitchen-comment = 💬 { $comment }
kitchen-payment-cash = 💵 نقداً عند الاستلام
kitchen-payment-shamcash = 📱 شام كاش — { $state }
kitchen-payment-state-awaiting = بانتظار الإشعار
kitchen-payment-state-submitted = وصل الإشعار، يرجى التحقق
kitchen-payment-state-confirmed = مدفوع
kitchen-payment-state-rejected = مرفوض
kitchen-payment-ref = 🧾 رقم العملية: <code>{ $ref }</code>
kitchen-log-line = { $emoji } { $status } · { $time } · { $actor }
kitchen-proof-caption = 🧾 إشعار الدفع للطلب رقم { $no }
kitchen-stale = الطلب في الحالة «{ $status }» بالفعل.
kitchen-not-allowed = أزرار الطلب تعمل داخل مجموعة المطبخ فقط.
kitchen-chat-id = معرّف هذه المجموعة: <code>{ $chat_id }</code>

kitchen-btn-accepted = ✅ قبول
kitchen-btn-cooking = 👨‍🍳 قيد التحضير
kitchen-btn-ready = 🥙 جاهز
kitchen-btn-on_the_way = 🛵 في الطريق
kitchen-btn-delivered = 🎉 تم التوصيل
kitchen-btn-picked_up = 🎉 تم الاستلام
kitchen-btn-cancelled = ❌ إلغاء
kitchen-btn-awaiting_payment = ⏳ انتظار الدفع
kitchen-btn-payment_rejected = ⚠️ لم يصل الدفع
