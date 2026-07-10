# Smart Litter Detection — Foydalanish qo'llanmasi

Ushbu hujjat tizimni **noldan** ishga tushirish va ishlatishni o'zbek tilida
tushuntiradi. Loyiha odam axlatni yerga tashlaganini kameradan (MP4 yoki RTSP)
aniqlaydi, 10 soniyalik video yozib oladi va veb-panelda ko'rsatadi.

---

## 1. Talablar

- **Python 3.12+** (3.14 ham ishlaydi)
- Internet (birinchi ishga tushishda YOLO modeli avtomatik yuklanadi)
- Diskda ~2 GB bo'sh joy (PyTorch + ultralytics uchun)

Tekshirish:

```bash
python --version
```

---

## 2. O'rnatish

```bash
# 1) Loyiha papkasiga kirish
cd smart_litter

# 2) Virtual muhit yaratish
python -m venv .venv

# 3) Virtual muhitni yoqish
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows (PowerShell)

# 4) Kutubxonalarni o'rnatish
pip install -r requirements.txt

# 5) Sozlama faylini nusxalash
cp .env.example .env
```

> **Eslatma:** `yolo11n.pt` modeli birinchi `process` buyrug'ida avtomatik
> yuklab olinadi — qo'lda hech narsa qilish shart emas.

---

## 3. Sozlash (`.env` fayli)

`.env` faylini oching va kamida `VIDEO_SOURCE` ni o'zgartiring:

```env
# MP4 fayl yo'li YOKI RTSP manzil
VIDEO_SOURCE=video.mp4
# RTSP misol:  rtsp://user:parol@192.168.1.10:554/stream

CAMERA_ID=cam-01
```

Muhim sozlamalar:

| O'zgaruvchi              | Ma'nosi                                                    |
|--------------------------|------------------------------------------------------------|
| `VIDEO_SOURCE`           | Video fayl yoki RTSP kamera manzili                        |
| `CONF_THRESHOLD`         | Aniqlash ishonchi (0–1). Kichraytirsangiz ko'proq aniqlaydi|
| `STATIONARY_SECONDS`     | Axlat yerda necha soniya turishi kerak (standart: 5)       |
| `PROXIMITY_PX`           | Odam va axlat "yaqin" hisoblanadigan piksel masofa         |
| `GROUND_Y_RATIO`         | Kadr balandligining qaysi qismidan "yer" boshlanadi (0–1)  |
| `PRE_EVENT_SECONDS`      | Hodisadan **oldingi** yozuv (soniya)                       |
| `POST_EVENT_SECONDS`     | Hodisadan **keyingi** yozuv (soniya)                       |
| `DATABASE_URL`           | Standart SQLite; keyin PostgreSQL ga o'tsa bo'ladi         |
| `DEVICE`                 | `cpu` yoki `0` (GPU)                                        |

---

## 4. Ishlatish

Tizim **ikki** qismdan iborat. Har birini alohida ishga tushirasiz.

### 4.1. Videoni tahlil qilish (aniqlash)

Bu buyruq videoni ko'radi, buzilishlarni aniqlaydi, `events/` papkasiga
kliplarni va bazaga yozuvlarni saqlaydi:

```bash
python main.py process --source video.mp4 --camera-id cam-01
```

RTSP kamera uchun:

```bash
python main.py process --source "rtsp://user:parol@host:554/stream"
```

`--source` bermasangiz, `.env` dagi `VIDEO_SOURCE` ishlatiladi:

```bash
python main.py process
```

Ishlash paytida terminalda log ko'rinadi. Buzilish topilsa:

```
VIOLATION: track 2 (bottle) littered, still 5.1s @ 6.2s
Wrote clip event_xxxx.mp4 (100 frames) + preview
Stored event id=1 (bottle)
```

### 4.2. Veb-panel va API ni ishga tushirish

```bash
python main.py serve
```

Keyin brauzerda oching:

- **Panel (dashboard):** <http://localhost:8000>
- **API hujjatlari:** <http://localhost:8000/docs>

Panelda har bir hodisa uchun: video, vaqt, ishonch foizi, kamera nomi va
**"Download clip"** tugmasi ko'rinadi.

---

## 5. REST API

| Metod  | Manzil                      | Vazifasi                          |
|--------|-----------------------------|-----------------------------------|
| GET    | `/health`                   | Tizim holati + hodisalar soni     |
| GET    | `/events`                   | Barcha hodisalar (yangi birinchi) |
| GET    | `/events/{id}`              | Bitta hodisa                      |
| DELETE | `/events/{id}`              | Hodisa + fayllarini o'chirish     |
| GET    | `/events/{id}/download`     | 10s MP4 klipni yuklab olish       |
| GET    | `/`                         | HTML panel                        |

Misollar:

```bash
# Holat
curl http://localhost:8000/health

# Hodisalar ro'yxati
curl http://localhost:8000/events

# Bitta hodisa
curl http://localhost:8000/events/1

# Hodisani o'chirish
curl -X DELETE http://localhost:8000/events/1
```

---

## 6. Qanday ishlaydi (qisqacha)

```
Video/RTSP → Kadrlar → YOLO11 → ByteTrack → Qoidalar → Klip yozish → Baza → Panel
```

**6 ta qoida** (hammasi bajarilsa — buzilish):

1. Odam va axlat yaqin (qo'lda).
2. Axlat odamdan ajraladi.
3. Axlat yerga tomon tushadi.
4. Axlat yerda kamida 5 soniya qimirlamay turadi.
5. Odam ketadi (qaytib olmaydi).
6. Axlat axlat qutisi ichida emas.

---

## 7. Tez-tez uchraydigan muammolar

**"Cannot open video source"** — fayl yo'li noto'g'ri yoki RTSP manzil ishlamayapti.
`.env` dagi `VIDEO_SOURCE` ni tekshiring.

**Hech narsa aniqlanmayapti** — `CONF_THRESHOLD` ni kamaytiring (masalan `0.20`)
yoki `PROXIMITY_PX` / `GROUND_Y_RATIO` ni videoingizga moslang.

**Panel bo'sh** — avval `process` buyrug'ini ishlatib hodisa yarating, keyin
`serve` ni oching. Ikkalasi ham bitta bazadan foydalanadi.

**"Disk quota exceeded" (o'rnatishda)** — diskda joy yetarli emas. PyTorch katta
(~2 GB), bo'sh joy oching yoki boshqa mashinada o'rnating.

---

## 8. Muhim eslatma (MVP cheklovi)

Standart YOLO11 modelida `paper` (qog'oz) va `trash_bin` (axlat quti) klasslari
yo'q. Hozircha qog'oz COCO `book` klassiga taqqoslanadi. Keyinchalik o'zingiz
o'rgatgan modelni qo'ysangiz — faqat `detector/detector.py` dagi `_COCO_TO_CLASS`
jadvalini tahrirlaysiz, boshqa hech narsa o'zgarmaydi.
