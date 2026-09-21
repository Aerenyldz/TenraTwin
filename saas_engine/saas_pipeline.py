"""
TENRA - SaaS Otomasyon Motoru (Dijital İkiz Üretici)
Herhangi bir kişinin WhatsApp sohbet yedeğini (.txt) alıp;
1. Otomatik kişi ve diyalog analizi yapar
2. Soru-cevap çiftlerini çıkarıp gürültüleri temizler
3. LoRA eğitim veri seti (JSONL) üretir
4. Önemli anıları (RAG için) ayıklar
5. Kişiye özel Ollama Modelfile şablonunu oluşturur

Kullanım:
  python saas_pipeline.py "sohbet.txt" --name "Kişi Adı"
"""
import os
import re
import json
import argparse
import sys
import io
from collections import Counter
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class DigitalTwinCloner:
    def __init__(self, txt_path, target_name=None, output_dir="saas_output"):
        self.txt_path = txt_path
        self.target_name = target_name
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
    def parse_whatsapp(self):
        """WhatsApp metin dosyasını çözümler"""
        if not os.path.exists(self.txt_path):
            alt1 = "\u200e" + self.txt_path
            alt2 = self.txt_path.replace("\u200e", "").replace("\u200f", "")
            if os.path.exists(alt1):
                self.txt_path = alt1
            elif os.path.exists(alt2):
                self.txt_path = alt2
            else:
                import glob
                matches = glob.glob(f"*{self.txt_path}*")
                if matches:
                    self.txt_path = matches[0]
                else:
                    raise FileNotFoundError(f"Dosya bulunamadı: {self.txt_path}")
            
        # Regex formatları:
        # Format 1: 2.05.2022 21:18 - Yunus Berk: Mesaj
        # Format 2: [02.05.2022 21:18:15] Yunus Berk: Mesaj
        p1 = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}\s\d{2}:\d{2}\s-\s([^:]+):\s(.*)")
        p2 = re.compile(r"^\[\d{1,2}\.\d{1,2}\.\d{4},\s\d{2}:\d{2}:\d{2}\]\s([^:]+):\s(.*)")
        
        raw_chats = []
        sender_counts = Counter()
        
        with open(self.txt_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                match = p1.match(line) or p2.match(line)
                if match:
                    sender = match.group(1).strip()
                    msg = match.group(2).strip()
                    
                    if msg in ["<Medya dahil edilmedi>", "Bu mesaj silindi", "Görüntü dahil edilmedi"]:
                        continue
                        
                    sender_counts[sender] += 1
                    
                    if raw_chats and raw_chats[-1]["sender"] == sender:
                        raw_chats[-1]["text"] += " " + msg
                    else:
                        raw_chats.append({"sender": sender, "text": msg})

        # Hedef kişi belirtilmemişse en çok konuşan 2 kişiden birini seç
        if not self.target_name:
            if sender_counts:
                # En çok mesaj atan 1. kişi
                self.target_name = sender_counts.most_common(1)[0][0]
            else:
                self.target_name = "Kullanıcı"

        return raw_chats, sender_counts

    def is_valid_response(self, text):
        """Random karakterleri ve anlamsız spamleri eler"""
        text = text.strip().lower()
        if len(text) < 2:
            return False
        # Random harf yığını (ASDHJASHD)
        if re.match(r'^[A-Z]{4,}$', text.strip()):
            return False
        # Tekrar eden gülmeler (sjsjsj hariç tutulabilir veya elenebilir)
        if len(text) > 6 and len(set(text)) <= 2:
            return False
        return True

    def build_qa_dataset(self, raw_chats):
        """Hedef kişi için diyalog çiftleri oluşturur"""
        qa_pairs = []
        memories = []
        
        memory_keywords = ["proje", "rekor", "okul", "üniversite", "ders", "sınav", "çalışıyor", "spor", "bench", "müzik", "spotify", "favori"]

        for i in range(len(raw_chats) - 1):
            curr_msg = raw_chats[i]
            next_msg = raw_chats[i+1]
            
            # Eğer sonraki mesaj hedef kişiye aitse
            if next_msg["sender"] == self.target_name and curr_msg["sender"] != self.target_name:
                out_text = next_msg["text"]
                if not self.is_valid_response(out_text):
                    continue
                    
                qa_pairs.append({
                    "instruction": f"Sen {self.target_name}'in dijital ikizisin. Karşındaki kişinin mesajlarına kendi doğal yazım tarzınla, espritüel ve samimi bir şekilde yanıt ver.",
                    "input": f"[Soran: {curr_msg['sender']}] {curr_msg['text']}",
                    "output": out_text
                })
                
                # Hafıza adayı cümle tespiti
                if any(k in out_text.lower() for k in memory_keywords) and len(out_text.split()) > 4:
                    memories.append({
                        "category": "otomatik_ani",
                        "content": f"{self.target_name} anısı ({curr_msg['sender']} ile sohbet): {out_text}"
                    })

        return qa_pairs, memories

    def generate_modelfile(self):
        """Kişiye özel Ollama Modelfile üretir"""
        content = f"""FROM llama3

TEMPLATE \"\"\"### Talimat:
{{{{ if .System }}}}{{{{ .System }}}}{{{{ else }}}}Sen {self.target_name}'sin. Karşındaki kişinin mesajlarına kendi doğal yazım tarzınla, espritüel ve samimi bir şekilde yanıt ver.{{{{ end }}}}

### Giris:
[Soran: Kullanıcı] {{{{ .Prompt }}}}

### Yanit:
\"\"\"

SYSTEM \"\"\"Sen {self.target_name}'in dijital ikizisin. Türkçe konuşursun, arkadaşlarınla olan sohbetlerindeki gibi samimi, kısa ve doğal cevaplar verirsin. Asla yapay bir robot gibi resmi yazma.\"\"\"

PARAMETER temperature 0.3
PARAMETER top_p 0.95
PARAMETER top_k 40
PARAMETER repeat_penalty 1.4
PARAMETER stop "###"
PARAMETER stop "Talimat:"
"""
        return content

    def run(self):
        print("=" * 60)
        print("  🚀 TENRA SaaS DİJİTAL İKİZ KLONLAMA MOTORU")
        print("=" * 60)
        print(f"  Girdi Dosyası : {self.txt_path}")
        
        raw_chats, senders = self.parse_whatsapp()
        print(f"  Tespit Edilen Kişi: {self.target_name}")
        print(f"  Toplam Mesaj Sayısı: {len(raw_chats)}")
        print("  Katılımcılar:")
        for s, c in senders.most_common(4):
            print(f"    - {s}: {c} mesaj")
            
        qa_pairs, memories = self.build_qa_dataset(raw_chats)
        print(f"  Üretilen Kaliteli Diyalog Çifti: {len(qa_pairs)}")
        print(f"  Ayıklanan Otomatik Anı Sayısı: {len(memories)}")
        
        # 1. Dataset JSONL kaydet
        safe_name = re.sub(r'\W+', '_', self.target_name).strip('_').lower()
        dataset_path = os.path.join(self.output_dir, f"{safe_name}_dataset.jsonl")
        with open(dataset_path, "w", encoding="utf-8") as f:
            for p in qa_pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
                
        # 2. Memories JSON kaydet
        memories_path = os.path.join(self.output_dir, f"{safe_name}_memories.json")
        with open(memories_path, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
            
        # 3. Modelfile kaydet
        modelfile_path = os.path.join(self.output_dir, f"Modelfile_{safe_name}")
        with open(modelfile_path, "w", encoding="utf-8") as f:
            f.write(self.generate_modelfile())
            
        print("\n" + "=" * 60)
        print("  ✅ DİJİTAL İKİZ PAKETİ HAZIRLANDI!")
        print(f"  1. Eğitim Veri Seti : {dataset_path}")
        print(f"  2. Bellek / Anılar   : {memories_path}")
        print(f"  3. Ollama Modelfile  : {modelfile_path}")
        print("=" * 60)
        
        return {
            "target_name": self.target_name,
            "total_raw_messages": len(raw_chats),
            "qa_pairs_count": len(qa_pairs),
            "memories_count": len(memories),
            "dataset_file": dataset_path,
            "memories_file": memories_path,
            "modelfile": modelfile_path
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WhatsApp Sohbetinden Dijital İkiz Klonlayıcı")
    parser.add_argument("file", help="WhatsApp export .txt dosya yolu")
    parser.add_argument("--name", help="Klonlanacak hedef kişinin adı", default=None)
    parser.add_argument("--out", help="Çıktı klasörü", default="saas_output")
    args = parser.parse_args()
    
    cloner = DigitalTwinCloner(args.file, target_name=args.name, output_dir=args.out)
    cloner.run()
