import os
import sys
import zipfile
import shutil
from huggingface_hub import hf_hub_download

APPLIO_TARGET_DIR = "C:\\Applio"
APPLIO_BAT = os.path.join(APPLIO_TARGET_DIR, "run-applio.bat")

def setup_applio():
    print("==================================================")
    print("  Applio RVC v2 - Otomatik Kurulum ve Hazırlık   ")
    print("==================================================")
    
    if os.path.exists(APPLIO_BAT):
        print(f"[OK] Applio zaten kurulu: {APPLIO_TARGET_DIR}")
        return True
        
    print(f"\n[1/3] Applio v3.6.5 paketi Hugging Face üzerinden indiriliyor...")
    print("      (Bu işlem internet hızınıza bağlı olarak birkaç dakika sürebilir)")
    
    try:
        downloaded_zip = hf_hub_download(
            repo_id="IAHispano/Applio",
            filename="Compiled/Windows/ApplioV3.6.5.zip",
            repo_type="model",
            local_files_only=False
        )
        print(f"\n[OK] İndirme tamamlandı: {downloaded_zip}")
    except Exception as e:
        print(f"[HATA] İndirme başarısız oldu: {e}")
        return False
        
    print(f"\n[2/3] Paket {APPLIO_TARGET_DIR} konumuna açılıyor...")
    os.makedirs(APPLIO_TARGET_DIR, exist_ok=True)
    
    with zipfile.ZipFile(downloaded_zip, 'r') as zip_ref:
        total_files = len(zip_ref.infolist())
        print(f"      Toplam {total_files} dosya çıkartılıyor...")
        zip_ref.extractall(APPLIO_TARGET_DIR)
        
    # Check if there is an inner Applio folder
    extracted_contents = os.listdir(APPLIO_TARGET_DIR)
    if "run-applio.bat" not in extracted_contents:
        for item in extracted_contents:
            sub = os.path.join(APPLIO_TARGET_DIR, item)
            if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "run-applio.bat")):
                print(f"      İç klasör tespit edildi ({item}), dosyalar ana dizine taşınıyor...")
                for sub_item in os.listdir(sub):
                    shutil.move(os.path.join(sub, sub_item), os.path.join(APPLIO_TARGET_DIR, sub_item))
                os.rmdir(sub)
                break

    if os.path.exists(APPLIO_BAT):
        print(f"\n[OK] [3/3] Applio başarıyla kuruldu!")
        print(f"     Konum: {APPLIO_TARGET_DIR}")
        return True
    else:
        print(f"\n[UYARI] run-applio.bat bulunamadı, lütfen klasörü kontrol edin: {APPLIO_TARGET_DIR}")
        return False

if __name__ == "__main__":
    setup_applio()
