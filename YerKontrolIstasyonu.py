import socket
import json
import time
import numpy as np
import cv2
from threading import Thread, Event, Lock
import os
import sys

# Simülatörden gelen varsayılan portlar
TELEMETRY_PORT = 14550
VIDEO_PORT = 14551
IP_ADRESI = '127.0.0.1' # Localhost dinle

class YerKontrolIstasyonu:
    """
    İHA Simülatöründen gelen telemetri (JSON) ve video (JPEG) verilerini
    eş zamanlı olarak alan, işleyen ve sunan ana sınıf.
    """
    def __init__(self):
        # --- Veri ve Senkronizasyon ---
        self.telemetri_verisi = {}
        self.durdurma_olayi = Event()
        self.telemetri_lock = Lock() # Telemetri verisine erişimi senkronize etmek için
        
        # --- Ağ Ayarları (Dinleme) ---
        self.telemetri_soket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.telemetri_soket.bind((IP_ADRESI, TELEMETRY_PORT))
        self.telemetri_soket.settimeout(1.0) # Zaman aşımı ayarı

        self.video_soket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.video_soket.bind((IP_ADRESI, VIDEO_PORT))
        self.video_soket.settimeout(1.0)

        # --- Thread'ler ---
        self.telemetri_thread = Thread(target=self._telemetri_dinleyici)
        self.video_thread = Thread(target=self._video_dinleyici)
        self.sunum_thread = Thread(target=self._cli_sunucu)

    # ====================================================================
    # DİNLEYİCİ THREAD 1: TELEMETRİ (JSON)
    # ====================================================================
    
    def _telemetri_dinleyici(self):
        """UDP portundan gelen JSON telemetri verilerini dinler ve işler."""
        print(f"[TH-TELEMETRİ] Dinleme Başlatıldı: UDP {TELEMETRY_PORT}")
        while not self.durdurma_olayi.is_set():
            try:
                # Maksimum 1024 byte'lık veri al
                veri, adres = self.telemetri_soket.recvfrom(1024)
                
                # JSON verisini ayrıştır
                mesaj = veri.decode('utf-8')
                yeni_telemetri = json.loads(mesaj)
                
                # Kritik veriyi kilit altında güncelle
                with self.telemetri_lock:
                    self.telemetri_verisi = yeni_telemetri
                    
            except socket.timeout:
                continue # Zaman aşımında döngüye devam et
            except Exception as e:
                if not self.durdurma_olayi.is_set():
                    print(f"[TH-TELEMETRİ] Hata: {e}")
                
        print("[TH-TELEMETRİ] Dinleyici sonlandırıldı.")

    # ====================================================================
    # DİNLEYİCİ THREAD 2: GÖRÜNTÜ (JPEG)
    # ====================================================================

    def _video_dinleyici(self):
        """UDP portundan gelen JPEG görüntü verilerini dinler ve gösterir."""
        print(f"[TH-VİDEO] Dinleme Başlatıldı: UDP {VIDEO_PORT}")
        
        while not self.durdurma_olayi.is_set():
            try:
                # Video paketleri büyük olabilir, maksimum boyutu biraz daha artır
                veri, adres = self.video_soket.recvfrom(65536) 
                
                # NumPy dizisine dönüştür
                np_veri = np.frombuffer(veri, dtype=np.uint8)
                
                # JPEG'den görüntüye çöz (decode)
                frame = cv2.imdecode(np_veri, cv2.IMREAD_COLOR)

                if frame is not None:
                    cv2.imshow('Canli Video Akisi (GCS)', frame)
                    # 1 ms bekleme süresi
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.durdurma_olayi.set() # 'q' basınca durdur
                
            except socket.timeout:
                continue
            except Exception as e:
                if not self.durdurma_olayi.is_set():
                    print(f"[TH-VİDEO] Hata: {e}")
                
        cv2.destroyAllWindows() # Pencereyi kapat
        print("[TH-VİDEO] Dinleyici sonlandırıldı.")

    # ====================================================================
    # SUNUM THREAD: CLI ARAYÜZÜ
    # ====================================================================

    def _cli_sunucu(self):
        """Telemetri verilerini komut satırında düzenli olarak günceller."""
        print(f"[TH-SUNUM] CLI Sunucusu Başlatıldı.")
        while not self.durdurma_olayi.is_set():
            time.sleep(0.5) # Yarım saniyede bir güncelle
            
            # Ekranı temizle
            os.system('cls' if os.name == 'nt' else 'clear') 
            
            with self.telemetri_lock:
                telemetri = self.telemetri_verisi.copy() # Verinin kopyasını al

            if not telemetri:
                print(">>> İHA TELEMETRİSİ BEKLENİYOR... <<<")
                continue

            # Verileri düzenli formatta göster
            cizgi = "=" * 50
            
            print(cizgi)
            print("         YER KONTROL İSTASYONU (GCS)         ")
            print(cizgi)
            print(f" Durum: {'>> AKTİF AKIŞ <<' if telemetri else 'PASİF / VERİ BEKLENİYOR'}")
            print(f" Son Güncelleme: {time.strftime('%H:%M:%S', time.localtime(telemetri.get('timestamp', time.time())))}")
            print(cizgi)
            print(f" [TEMEL DURUM] ")
            print(f"   Pil Durumu: {telemetri.get('pil_durumu', 'N/A')}%")
            print(f"   Uçuş Durumu: {telemetri.get('durum', 'N/A')}")
            print(f"   Hız: {telemetri.get('hiz', 'N/A')} m/s")
            print(cizgi)
            print(f" [KONUM BİLGİSİ] ")
            print(f"   X Koordinatı: {telemetri.get('konum', {}).get('x', 'N/A')}")
            print(f"   Y Koordinatı: {telemetri.get('konum', {}).get('y', 'N/A')}")
            print(f"   Z (İrtifa): {telemetri.get('konum', {}).get('z', 'N/A')} m")
            print(cizgi)
            print("\n* Çıkış için Canlı Video Penceresinde 'q' tuşuna basın.")
            
        print("[TH-SUNUM] CLI Sunucusu sonlandırıldı.")


    # ====================================================================
    # KONTROL METOTLARI
    # ====================================================================

    def baslat(self):
        """Tüm GCS Thread'lerini başlatır."""
        self.durdurma_olayi.clear()
        
        self.telemetri_thread.start()
        self.video_thread.start()
        self.sunum_thread.start()
        
        print("Yer Kontrol İstasyonu (GCS) başlatıldı. Dinleme aktif.")

    def durdur(self):
        """Tüm thread'leri güvenli şekilde durdurur."""
        self.durdurma_olayi.set()
        
        # Socketleri kapatmak, thread'lerin timeout'tan hemen çıkmasını sağlar
        self.telemetri_soket.close()
        self.video_soket.close()

        # Tüm thread'lerin tamamlanmasını bekle
        self.telemetri_thread.join()
        self.video_thread.join()
        self.sunum_thread.join()
        
        print("Yer Kontrol İstasyonu kapatıldı.")

# ====================================================================
# ANA UYGULAMA ÇALIŞTIRMA BLOĞU
# ====================================================================

if __name__ == '__main__':
    # 1. GCS örneğini oluştur
    gcs = YerKontrolIstasyonu()
    
    # 2. GCS'i başlat
    gcs.baslat()

    # Ana thread'i, diğer thread'lerin sonlanmasını beklerken meşgul et
    try:
        # Programı, durdurma olayı tetiklenene kadar çalışır durumda tut
        while not gcs.durdurma_olayi.is_set():
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nKullanıcı tarafından durdurma sinyali alındı.")
    finally:
        # 3. GCS'i güvenli bir şekilde durdur
        gcs.durdur()
        
    print("GCS Programı başarıyla sonlandı.")