# TEXNIK TOPSHIRIQ (TZ) — Test Video Uchun
## Smart Litter Detection System — Kamera Operatorlari Uchun

---

## 1. MAQSAD

Tizimni test qilish uchun **haqiqiy video material** kerak. Quyidagi senariyolar bo'yicha video olish kerak.

---

## 2. KAMERA TALABLARI

### 2.1. Texnik parametrlar
- **Format:** MP4 (H.264 yoki H.265)
- **Minimal aniqlik:** 720p (1280x720), afzal 1080p (1920x1080)
- **FPS:** 25-30 (kamida 15 FPS)
- **Davomiylik:** Har bir senariy 15-30 soniya
- **Rasm sifati:** MJPEG yoki MP4, JPEG quality 70%

### 2.2. Kamera pozitsiyasi
- **Balandlik:** 2-4 metr (odam ko'kragi darajasida yoki yuqoriroq)
- **Burchak:** 30-60 gradus pastga qaragan (yerdagi ob'ektlarni ko'rish uchun)
- **Masofa:** 3-8 metr (odam to'liq ko'rinishi kerak)

### 2.3. Yoritish
- **Kunduzi:** Tabiiy yorug'lik, soyada yoki quyoshda
- **Tungi:** Sun'iy yorug'lik (300+ lux)
- **Qarama-qarshilik:** Odatiy sharoitda, ekstremal emas

---

## 3. SENARIYOLAR (HAR BIRI ALOHIDA VIDEO)

### SENARIY 1: "Shishani tashlash" (BOTTLE)
**Davomiylik:** 20 soniya
**Kamera:** O'rta masofa (5-6 metr), yuqoridan pastga burchak

**Ssenariy:**
1. **0-5 soniya:** Odan kadrga kiradi, qo'lidagi PET shishani ushlab turadi
2. **5-10 soniya:** Odan yuradi, shishani qo'lidagi ko'rinadi (yaqin)
3. **10-13 soniya:** Odan shishani qo'yib yuboradi (yerga tashlaydi)
4. **13-18 soniya:** Shisha yerdadi (pastda turadi), odan uzoqlashadi
5. **18-20 soniya:** Shisha yerdadi, odan kadrdan chiqadi

**Muhim:** Shisha yerdada **kamida 5 soniya** turishi kerak.

---

### SENARIY 2: "Qog'oz tashlash" (PAPER)
**Davomiylik:** 20 soniya
**Kamera:** O'rta masofa (4-5 metr)

**Ssenariy:**
1. **0-5 soniya:** Odan kadrga kiradi, qo'lidagi qog'oz (kitob, varaqa) ko'rinadi
2. **5-10 soniya:** Odan yuradi, qog'ozni ushlab turadi
3. **10-13 soniya:** Odan qog'ozni tashlaydi
4. **13-18 soniya:** Qog'oz yerdadi, odan uzoqlashadi
5. **18-20 soniya:** Qog'oz yerdadi

**Muhihim:** Qog'oz yerdada **kamida 5 soniya** turishi kerak.

---

### SENARIY 3: "Sumka tashlash" (HANDBAG/BACKPACK)
**Davomiylik:** 25 soniya
**Kamera:** Kengroq kadrd (6-8 metr)

**Ssenariy:**
1. **0-5 soniya:** Odan kadrga kiradi, yelkasida sumka
2. **5-12 soniya:** Odan yuradi, sumka ko'rinishi kerak
3. **12-15 soniya:** Odan sumkani yerga qo'yadi
4. **15-22 soniya:** Sumka yerdadi, odan uzoqlashadi
5. **22-25 soniya:** Sumka yerdadi

---

### SENARIY 4: "Musiqa qutisi tashlash" (BOX)
**Davomiylik:** 20 soniya
**Kamera:** O'rta masofa

**Ssenariy:**
1. **0-5 soniya:** Odan qo'lidagi qutini ko'rsatadi
2. **5-10 soniya:** Odan yuradi
3. **10-13 soniya:** Odan qutini tashlaydi
4. **13-20 soniya:** Quti yerdadi, odan uzoqlashadi

---

### SENARIY 5: "YO'QOTISH" (FALSE POSITIVE — Chiqarilmasin)
**Davomiylik:** 20 soniya
**Kamera:** O'rta masofa

**Ssenariy:**
1. **0-5 soniya:** Odan kadrga kiradi, qo'lidagi shishani ushlab turadi
2. **5-12 soniya:** Odan yuradi
3. **12-15 soniya:** Odan shishani **qo'liga qaytaradi** (tashlamaydi!)
4. **15-20 soniya:** Odan shishani ushlab yuradi

**Maqsad:** Tizim NOTOG'RIsiz aniqlamasligi kerak (false positive test).

---

### SENARIY 6: "CHIQINDI QUTISIGA TASHLASH" (CORRECT DISPOSAL)
**Davomiylik:** 25 soniya
**Kamera:** Kengroq kadrd, chiqindi qutisi ko'rinishi kerak

**Ssenariy:**
1. **0-5 soniya:** Odan kadrga kiradi, qo'lidagi shishani ushlab turadi
2. **5-10 soniya:** Odan yuradi, chiqindi qutisi yaqinlashadi
3. **10-15 soniya:** Odan shishani **chiqindi qutisiga tashlaydi**
4. **15-20 soniya:** Odan chiqindi qutisidan uzoqlashadi
5. **20-25 soniya:** Shisha chiqindi qutisida turadi

**Maqsad:** Tizim NOTOG'RIsiz aniqlamasligi kerak (chiqindi qutisiga tashlagan).

---

### SENARIY 7: "ODAM YERGA O'TIRISHI" (SIT DOWN — False Positive)
**Davomiylik:** 15 soniya
**Kamera:** O'rta masofa

**Ssenariy:**
1. **0-5 soniya:** Odan kadrga kiradi
2. **5-10 soniya:** Odan **yerga o'tiradi** (tashlamaydi!)
3. **10-15 soniya:** Odan turadi, yurib ketadi

**Maqsad:** Odan o'tirganda tizim false positive bermasligi kerak.

---

## 4. MUHIM TO'MONLAR

### 4.1. Odam ko'rinishi
- Odan **to'liq ko'rinishi** kerak (oyoqdan boshgacha)
- Yuz aniq ko'rinishi shart emas, lekin **tana ko'rinishi** kerak
- Qo'l va harakatlar **aniq ko'rinishi** kerak

### 4.2. Trash ob'ektlar
- **Shisha:** PET, 0.5-1.5L, rangi aniq (ko'k, yashil, sariq)
- **Qog'oz:** Kitob, varaqa, qog'oz qutisi
- **Sumka:** Xalta, sumka, ryukzak
- **Quti:** Karton quti, mahsulot qutisi

### 4.3. Yer surface
- **Aniq ko'rinishi** kerak (asfalt, beton, g'isht, marmar)
- Soyada yoki quyoshda bo'lishi mumkin
- **Tekis** bo'lishi kerak (egri emas)

### 4.4. Fon
- **Oddiy fon** — devor, piyodalar yo'li, park
- **Band fon** — odamlar, mashinalar bo'lishi mumkin (lekin asosiy ob'ektlar ko'rinishi kerak)

---

## 5. NAMUNA FAYLLAR

Quyidagi namunalar `video/` papkasida mavjud:

| Fayl | Senariy | Davomiylik |
|------|---------|------------|
| `video_2026-08-19_12-03-45.mp4` | Namuna 1 | ~5 soniya |
| `video_2026-08-19_12-04-01.mp4` | Namuna 2 | ~3 soniya |
| `video_2026-08-19_12-04-04.mp4` | Namuna 3 | ~3 soniya |
| `video_2026-08-19_12-04-07.mp4` | Namuna 4 | ~3 soniya |

---

## 6. FAYLLARNI YUBORISH

Video fayllarni quyidagi manzilga yuboring:
- **Telegram:** @Manager_Dilyorbek
- **Yoki:** `video/` papkasiga joylashtiring

**Fayl nomi formati:** `video_YYYY-MM-DD_HH-MM-SS.mp4`

---

## 7. TEXNIK XUSUSIYATLAR (TIZIM UCHUN)

Tizim quyidagi parametrlarni ishlatadi:

```
VIDEO_SOURCE=video/your_video.mp4
CONF_THRESHOLD=0.30
STATIONARY_SECONDS=5.0
PROXIMITY_PX=120
GROUND_Y_RATIO=0.55
```

**Diqqat:** 
- `STATIONARY_SECONDS=5.0` — trash yerdada **kamida 5 soniya** turishi kerak
- `PROXIMITY_PX=120` — odam va trash **120 piksel** yaqin bo'lsa "qo'lda" deb hisoblaydi
- `GROUND_Y_RATIO=0.55` — kadrdning **55%** pasti "yer" deb hisoblaydi

---

## 8. XATO LAR (XAVF)

| Xato | Tushuntirish |
|------|-------------|
| Video qisqa | 15 soniyadan kam — tizim aniqlay olmaydi |
| FPS past | 15 FPS dan kam — harakat silliq emas |
| Trash ko'rinmaydi | Qorong'i, uzoq, yashirin — tizim topa olmaydi |
| Odam ko'rinmaydi | Faqat qo'l ko'rinishi — tizim aniqlay olmaydi |
| Yer ko'rinmaydi | Kamera juda past yoki yuqori — ground_y_ratio ishlamaydi |
| Video qisqartirilgan | Tezlashtirilgan — stationary_seconds ishlamaydi |

---

**Savol bo'lsa, @Manager_Dilyorbek ga yozing.**
