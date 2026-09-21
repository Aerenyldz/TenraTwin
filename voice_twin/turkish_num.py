"""
TENRA Voice Twin - Türkçe Sayı ve Metin Normalizasyonu
Metindeki tüm rakamları, saatleri, kesme işaretli ekleri ve para birimlerini
doğal Türkçe okunuşlarına çevirir. Böylece Fish Audio veya TTS motorları
sayıları asla İngilizce okumaz.
"""
import re

ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]

ORDINALS = {
    1: "birinci", 2: "ikinci", 3: "üçüncü", 4: "dördüncü", 5: "beşinci",
    6: "altıncı", 7: "yedinci", 8: "sekizinci", 9: "dokuzuncu", 10: "onuncu"
}

def int_to_turkish(n: int) -> str:
    """Tam sayıları Türkçe metne çevirir (örn: 125 -> yüz yirmi beş)."""
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi " + int_to_turkish(-n)

    parts = []

    # Milyar
    billions = n // 1000000000
    if billions > 0:
        if billions == 1:
            parts.append("bir milyar")
        else:
            parts.append(int_to_turkish(billions) + " milyar")
        n %= 1000000000

    # Milyon
    millions = n // 1000000
    if millions > 0:
        if millions == 1:
            parts.append("bir milyon")
        else:
            parts.append(int_to_turkish(millions) + " milyon")
        n %= 1000000

    # Bin
    thousands = n // 1000
    if thousands > 0:
        if thousands == 1:
            parts.append("bin")
        else:
            parts.append(int_to_turkish(thousands) + " bin")
        n %= 1000

    # Yüz
    hundreds = n // 100
    if hundreds > 0:
        if hundreds == 1:
            parts.append("yüz")
        else:
            parts.append(ONES[hundreds] + " yüz")
        n %= 100

    # Onluk
    tens = n // 10
    if tens > 0:
        parts.append(TENS[tens])
        n %= 10

    # Birlik
    if n > 0:
        parts.append(ONES[n])

    return " ".join(parts).strip()


def normalize_turkish_numbers(text: str) -> str:
    """
    Metin içindeki tüm sayıları, saatleri ve ekleri Türkçe yazıya döker.
    Örnek:
      "saat 8'de" -> "saat sekizde"
      "20:00" -> "yirmi"
      "14:30" -> "on dört otuz"
      "100 TL" -> "yüz lira"
      "15 dk" -> "on beş dakika"
      "%50" -> "yüzde elli"
    """
    if not text:
        return ""

    # Kısaltmalar
    text = re.sub(r"\b(\d+)\s*(dk|dakika)\b", r"\1 dakika", text, flags=re.I)
    text = re.sub(r"\b(\d+)\s*(sn|saniye)\b", r"\1 saniye", text, flags=re.I)
    text = re.sub(r"\b(\d+)\s*(sa|saat)\b", r"\1 saat", text, flags=re.I)

    # 1. Saat formatı: 14:30, 20:00, 08:00
    def time_repl(m):
        h = int(m.group(1))
        m_part = int(m.group(2))
        h_str = int_to_turkish(h)
        if m_part == 0:
            return h_str
        return f"{h_str} {int_to_turkish(m_part)}"
    text = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", time_repl, text)

    # 2. Para birimleri: 100 TL, 50$, 20€
    text = re.sub(r"\b(\d+)\s*(TL|tl|Tl)\b", lambda m: int_to_turkish(int(m.group(1))) + " lira", text)
    text = re.sub(r"\b(\d+)\s*(\$|dolar|Dolar)\b", lambda m: int_to_turkish(int(m.group(1))) + " dolar", text)
    text = re.sub(r"\b(\d+)\s*(€|euro|Euro)\b", lambda m: int_to_turkish(int(m.group(1))) + " euro", text)

    # 3. Yüzde: %50, % 25
    text = re.sub(r"%\s*(\d+)", lambda m: "yüzde " + int_to_turkish(int(m.group(1))), text)

    # 4. Kesme işaretli sayılar: 8'de, 2024'te, 5'e, 10'uncu, 8'deydi
    def suffix_repl(m):
        num = int(m.group(1))
        suffix = m.group(3)
        num_word = int_to_turkish(num)
        # Eğer ek ncı/nci/üncü/inci ise
        if re.match(r"^(inci|ıncı|uncu|üncü|nci|ncı|ncu|ncü)$", suffix, re.I):
            return ORDINALS.get(num, num_word + "inci")
        return num_word + suffix
    text = re.sub(r"\b(\d+)(['’])([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\b", suffix_repl, text)

    # 5. Sıra sayıları nokta ile: 1., 2. vb. (arkasından harf/kelime geliyorsa)
    text = re.sub(r"\b(\d{1,2})\.(?=\s+[A-ZÇĞİÖŞÜa-zçğıöşü])", lambda m: ORDINALS.get(int(m.group(1)), int_to_turkish(int(m.group(1))) + "inci"), text)

    # 6. Düz tam sayılar: 8, 25, 100, 2024
    text = re.sub(r"\b\d+\b", lambda m: int_to_turkish(int(m.group(0))), text)

    return text
