# yordamchi

Claude sessiyalari uchun yordamchi skript. Hajmi katta matn ishlarini (qisqartirish, ma'lumot ajratish, qoralama) va video tahlilini Google Gemini modellariga beradi. Yakuniy qaror va tekshirish Claude'da qoladi.

Bitta fayl: `yordamchi.py`. Faqat Python standart kutubxonasi kerak. Havoladan video yuklash uchun qo'shimcha `yt-dlp` kerak bo'ladi (YouTube havolalari usiz ham ishlaydi).

## Ishlatish

```bash
python3 yordamchi.py "vazifa"                          # matn ishi (flash darajasi)
python3 yordamchi.py --daraja lite -f log.txt "vazifa" # fayl bilan, arzon model
cat matn.txt | python3 yordamchi.py -f - "vazifa"      # stdin'dan
python3 yordamchi.py --video HAVOLA_YOKI_FAYL          # videoni kadr va ovozi bilan to'liq tahlil
python3 yordamchi.py --video HAVOLA "aniq savol"       # videodan faqat bitta savolga javob
python3 yordamchi.py --holat                           # versiya, kalit holati, bugungi hisob
```

Darajalar va boshqa tafsilotlar skript boshidagi izohda yozilgan.

## Kalit

- **Windows:** `GEMINI_API_KEY` foydalanuvchi o'zgaruvchisi.
- **Linux (masalan, Claude cloud sessiyasi):** "proksi rejimi". Skript so'rovni `x-goog-api-key` header'isiz yuboradi, kalitni tarmoq proksisi qo'shadi (Network secret: host `generativelanguage.googleapis.com`, header `x-goog-api-key`). `GEMINI_API_KEY` o'zgaruvchisi berilgan bo'lsa, o'sha yuboriladi.

Kalit hech qachon bu repo'ga yozilmaydi.

## Xavfsizlik

- `.env` va kalit fayllari, shuningdek matn ichidagi kalit yoki token ko'rinishidagi satrlar yuborilmaydi.
- Nomida `KEY`, `TOKEN`, `SECRET`, `PASSWORD` bor muhit o'zgaruvchilarining qiymati matnda uchrasa, matn yuborilmaydi.
- Bepul API darajasida yuborilgan ma'lumot Google modellarini yaxshilashda ishlatilishi mumkin. Shaxsiy matn va videolarni yubormang.
- Jurnalga matnning o'zi emas, faqat hajm, vaqt va holat yoziladi.

## Linux'ga o'rnatish (namuna)

```bash
curl -fsSL https://raw.githubusercontent.com/qochqorovanvar110-svg/yordamchi/main/yordamchi.py -o /usr/local/bin/yordamchi
chmod +x /usr/local/bin/yordamchi
yordamchi --holat
```
