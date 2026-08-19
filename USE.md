# Smart Litter Detection — Foydalanish qo'llanmasi

Ushbu hujjat tizimni **noldan** ishga tushirish va ishlatishni o'zbek tilida
tushuntiradi. Loyiha odam axlatni yerga tashlaganini kameradan (MP4 yoki RTSP)
aniqlaydi, kimligini (agar ro'yxatdan o'tgan bo'lsa) yuzidan taniydi, 10
soniyalik video yozib oladi va JWT bilan himoyalangan veb-panelda ko'rsatadi.

---

## 1. Talablar

- **Python 3.12+** (3.14 ham ishlaydi)
- Internet (birinchi ishga tushishda YOLO va yuz aniqlash modellari avtomatik yuklanadi)
- Diskda ~2 GB bo'sh joy (PyTorch + ultralytics uchun)

Tekshirish:

```bash
python --version
```

---

## 2. O'rnatish

```bash
# 1) Loyiha papkasiga kirish
cd smart-linter

# 2) Virtual muhit yaratish
python -m venv .venv

# 3) Virtual muhitni yoqish
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows (PowerShell)

# 4) Kutubxonalarni o'rnatish
pip install -r requirements.txt

# 5) Sozlama faylini nusxalash
cp .env.example .env

# 6) Admin parolini hash qilish (login uchun kerak)
python main.py hash-password 'parolingiz'
# chiqqan qiymatni .env faylidagi ADMIN_PASSWORD_HASH ga qo'ying
```

> **Eslatma:** `yolo11n.pt` va yuz aniqlash modellari birinchi ishlatishda
> avtomatik yuklab olinadi — qo'lda hech narsa qilish shart emas.

---

## 3. Sozlash (`.env` fayli)

`.env` faylini oching va kamida quyidagilarni to'ldiring:

```env
# MP4 fayl yo'li YOKI RTSP manzil
VIDEO_SOURCE=video.mp4
CAMERA_ID=cam-01

# Login
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=...          # 2-bosqichda hash-password chiqargan qiymat
JWT_SECRET=uzun-tasodifiy-qiymat  # productionda albatta o'zgartiring
```

Muhim sozlamalar:

| O'zgaruvchi              | Ma'nosi                                                    |
|--------------------------|--------------------------------------------------------------|
| `VIDEO_SOURCE`           | Video fayl yoki RTSP kamera manzili                        |
| `CONF_THRESHOLD`         | Aniqlash ishonchi (0–1). Kichraytirsangiz ko'proq aniqlaydi|
| `STATIONARY_SECONDS`     | Axlat yerda necha soniya turishi kerak (standart: 5)       |
| `PROXIMITY_PX`           | Odam va axlat "yaqin" hisoblanadigan piksel masofa         |
| `GROUND_Y_RATIO`         | Kadr balandligining qaysi qismidan "yer" boshlanadi (0–1) — panelda sudrab ham o'zgartirsa bo'ladi |
| `TRACK_TTL_SECONDS`      | Kuzatilmagan obyekt holati necha soniyadan keyin unutiladi |
| `PRE_EVENT_SECONDS`      | Hodisadan **oldingi** yozuv (soniya)                       |
| `POST_EVENT_SECONDS`     | Hodisadan **keyingi** yozuv (soniya)                       |
| `WS_DETECT_EVERY_N_FRAMES` | Jonli oqimda har N-kadrda aniqlash (sekin CPU'da oshiring) |
| `FACE_MATCH_THRESHOLD`   | Yuz mosligi uchun bo'sag'a (yuqori = qattiqroq talab)      |
| `DATABASE_URL`           | Standart SQLite; keyin PostgreSQL ga o'tsa bo'ladi         |
| `DEVICE`                 | `cpu` yoki `0` (GPU)                                        |

---

## 4. Ishlatish

Tizim **ikki** qismdan iborat. Har birini alohida ishga tushirasiz.

### 4.1. Videoni tahlil qilish (aniqlash)

Bu buyruq videoni ko'radi, buzilishlarni aniqlaydi, `events/` papkasiga
kliplarni va bazaga yozuvlarni saqlaydi (agar odam ro'yxatdan o'tgan bo'lsa,
yuzidan tanib, ismini ham yozadi):

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
# ko'p mijoz uchun: python main.py serve --workers 4
```

Keyin brauzerda oching:

- **Kirish:** <http://localhost:8000/login> — `.env` dagi admin login/parol bilan
- **Panel (dashboard):** <http://localhost:8000> — hodisalar ro'yxati
- **Jonli aniqlash:** <http://localhost:8000/process> — video/RTSP/webcam tanlab jonli kuzatish
- **Odamlar:** <http://localhost:8000/roster> — yuz-tanish ro'yxatiga odam qo'shish
- **API hujjatlari:** <http://localhost:8000/docs>

Panelda har bir hodisa uchun: video, vaqt, ishonch foizi, kamera nomi,
(agar mos kelsa) **taniqli odam ismi**, va **"Download clip"** hamda
**o'chirish** tugmalari ko'rinadi.

#### Jonli aniqlash sahifasida sozlash

- **Yer chizig'i** — qizil chiziqni sichqon bilan sudrab, R3 qoidasining
  "yer" chegarasini video ustida ko'rgan holda to'g'rilang. O'zgarish darhol
  amal qiladi.
- **Axlat qutisi zonasi** — **"+ Bin Zone"** tugmasini bosing, so'ng haqiqiy
  axlat qutisi ustida to'rtburchak chizing. Bu zona saqlanadi va keyingi
  barcha seanslarda avtomatik qo'llaniladi (R6 qoidasi uchun) — hatto YOLO
  qutini o'zi tanimasa ham. Zonani ikki marta bosib o'chirish mumkin.

#### Odamlarni ro'yxatga olish

`/roster` sahifasida ism va bitta aniq (old tomondan tushirilgan) rasm bilan
odamni qo'shing. Shundan keyin shu odam chiqindi tashlasa, hodisa ro'yxatida
ismi va o'xshashlik foizi ko'rinadi.

---

## 5. REST API

| Metod  | Manzil                      | Vazifasi                          |
|--------|-----------------------------|-------------------------------------|
| POST   | `/auth/login`                | Login/parol → access + refresh token |
| POST   | `/auth/refresh`               | Refresh token → yangi juftlik      |
| GET    | `/health`                   | Tizim holati + hodisalar soni     |
| GET    | `/events`                   | Hodisalar ro'yxati (sahifalangan) |
| GET    | `/events/{id}`              | Bitta hodisa                      |
| DELETE | `/events/{id}`              | Hodisa + fayllarini o'chirish     |
| GET    | `/events/{id}/download`     | 10s MP4 klipni yuklab olish       |
| POST/GET | `/people`                  | Odam qo'shish / ro'yxat           |
| DELETE | `/people/{id}`              | Odamni ro'yxatdan o'chirish       |
| POST/GET | `/bin-zones`               | Axlat quti zonasi qo'shish / ro'yxat |
| DELETE | `/bin-zones/{id}`           | Zonani unutish                    |
| GET    | `/`                         | HTML panel                        |

Misollar (avval token oling):

```bash
# Login qilib token olish
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -d "username=admin&password=parolingiz" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Holat (token shart emas)
curl http://localhost:8000/health

# Hodisalar ro'yxati (token kerak)
curl http://localhost:8000/events -H "Authorization: Bearer $TOKEN"

# Hodisani o'chirish
curl -X DELETE http://localhost:8000/events/1 -H "Authorization: Bearer $TOKEN"
```

---

## 6. Qanday ishlaydi (qisqacha)

```
Video/RTSP → Kadrlar → YOLO11 → ByteTrack → Qoidalar → Yuz moslash → Klip yozish → Baza → Panel
```

**6 ta qoida** (hammasi bajarilsa — buzilish):

1. Odam va axlat yaqin (qo'lda).
2. Axlat odamdan ajraladi.
3. Axlat yerga tomon tushadi.
4. Axlat yerda kamida 5 soniya qimirlamay turadi.
5. Odam ketadi (qaytib olmaydi).
6. Axlat axlat qutisi ichida emas — YOLO aniqlagan quti **yoki** qo'lda chizilgan zona.

---

## 7. Tez-tez uchraydigan muammolar

**"Cannot open video source"** — fayl yo'li noto'g'ri yoki RTSP manzil ishlamayapti.
`.env` dagi `VIDEO_SOURCE` ni tekshiring.

**Hech narsa aniqlanmayapti** — `CONF_THRESHOLD` ni kamaytiring (masalan `0.20`)
yoki `PROXIMITY_PX` / `GROUND_Y_RATIO` ni videoingizga moslang (yoki jonli
sahifada yer chizig'ini sudrab to'g'rilang).

**Panel bo'sh** — avval `process` buyrug'ini ishlatib hodisa yarating, keyin
`serve` ni oching. Ikkalasi ham bitta bazadan foydalanadi.

**Login qilolmayapman** — `.env` dagi `ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`
to'g'ri ekanini tekshiring; hash ni `python main.py hash-password '<parol>'`
bilan qayta yarating.

**Yuz tanib bo'lmayapti** — enroll qilingan rasmda yuz aniq va old tomondan
ko'rinishi kerak; `FACE_MATCH_THRESHOLD` ni pasaytirib ko'ring (masalan `0.3`).

**"Disk quota exceeded" (o'rnatishda)** — diskda joy yetarli emas. PyTorch katta
(~2 GB), bo'sh joy oching yoki boshqa mashinada o'rnating.

---

## 8. Muhim eslatma (MVP cheklovi)

Standart YOLO11 modelida `paper` (qog'oz) va `trash_bin` (axlat quti) klasslari
yo'q. Hozircha qog'oz COCO `book`/`tie`/`box`, axlat quti esa `toilet`
klassiga taqqoslanadi — shuning uchun jonli sahifada **"+ Bin Zone"** bilan
qo'lda zona chizish tavsiya etiladi. Keyinchalik o'zingiz o'rgatgan modelni
qo'ysangiz — faqat `detector/detector.py` dagi `_COCO_TO_CLASS` jadvalini
tahrirlaysiz, boshqa hech narsa o'zgarmaydi.
