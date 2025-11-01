import random
import time
import json
import socket
import numpy as np
import cv2
from threading import Thread, Event

class IHASimulator:
    """
    Uçan bir İHA'yı taklit eder. Telemetri ve Görüntü akışını (Webcam)
    iki ayrı Thread kullanarak eş zamanlı olarak UDP üzerinden yayınlar.
    """
    
    # Varsayılan Ağ ve Akış Ayarları
    TELEMETRY_PORT = 14550
    VIDEO_PORT = 14551
    HEARTBEAT_ARALIGI = 1  # Telemetri yayın aralığı (saniye)
    
    def __init__(self, ip='127.0.0.1'):
        """
        Başlatıcı metot. Simülatörün temel ayarlarını ve soketleri hazırlar.

        :param ip: Telemetri ve Video verisinin gönderileceği hedef IP adresi.
        """
        self.hedef_ip = ip
        
        # --- Telemetri Verileri ---
        self.konum_x = random.uniform(0.0, 100.0)
        self.konum_y = random.uniform(0.0, 100.0)
        self.irtifa_z = 0.0
        self.hiz = 0.0
        self.pil_durumu = 100
        
        # --- Ağ ve Thread Kontrolü ---
        self.telemetri_soket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.video_soket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.durdurma_olayi = Event()
        
        self.telemetri_thread = None
        self.video_thread = None
        
        # --- Video Yakalama ---
        self.kamera = cv2.VideoCapture(0) # 0, varsayılan web kamerası
        if not self.kamera.isOpened():
            print("HATA: Web kamerası açılamadı!")
            self.kamera = None

        print(f"İHA Simülatörü Hazır. Telemetri: {ip}:{self.TELEMETRY_PORT}, Video: {ip}:{self.VIDEO_PORT}")


    # ====================================================================
    # TEK ÖRNEK İHA TELEMETRİSİ YÖNETİMİ (THREAD 1)
    # ====================================================================

    def _veri_uret_ve_yayinla(self):
        """
        Telemetri verilerini üretir ve UDP üzerinden JSON formatında yayınlar.
        """
        if self.pil_durumu > 0:
            # Konum ve Hız Güncelleme
            self.hiz = random.uniform(0.5, 5.0)
            self.konum_x += self.hiz * random.uniform(-0.5, 0.5) * self.HEARTBEAT_ARALIGI
            self.konum_y += self.hiz * random.uniform(-0.5, 0.5) * self.HEARTBEAT_ARALIGI
            self.irtifa_z += random.uniform(-0.2, 0.3)
            self.irtifa_z = max(0.0, self.irtifa_z)

            # Pil Azaltma (Gerçek zamanlı çalışma maliyetini taklit eder)
            pil_azalma_miktari = random.uniform(0.2, 0.6) * self.HEARTBEAT_ARALIGI
            self.pil_durumu -= pil_azalma_miktari
            self.pil_durumu = max(0, int(self.pil_durumu))
        else:
             # Pil bitti, İHA indi
             self.hiz = 0
             self.irtifa_z = 0

        # JSON olarak paketle
        telemetri_verisi = {
            "timestamp": time.time(),
            "konum": {
                "x": round(self.konum_x, 2),
                "y": round(self.konum_y, 2),
                "z": round(self.irtifa_z, 2)
            },
            "hiz": round(self.hiz, 2),
            "pil_durumu": self.pil_durumu,
            "durum": "Uçuşta" if self.pil_durumu > 5 and self.irtifa_z > 0.5 else "İndi"
        }
        
        mesaj_json = json.dumps(telemetri_verisi)
        mesaj_byte = mesaj_json.encode('utf-8')
        
        # UDP ile yayınla
        self.telemetri_soket.sendto(mesaj_byte, (self.hedef_ip, self.TELEMETRY_PORT))
        print(f"[TELEMETRİ] Yayınlandı. Pil: {self.pil_durumu}%, Durum: {telemetri_verisi['durum']}")

    def _telemetri_dongusu(self):
        """Telemetri yayınını ayrı Thread'de sürekli döngüde tutar."""
        while not self.durdurma_olayi.is_set():
            self._veri_uret_ve_yayinla()
            self.durdurma_olayi.wait(self.HEARTBEAT_ARALIGI)
        print("Telemetri yayını sonlandırıldı.")

    # ====================================================================
    # GÖRÜNTÜ AKIŞI YÖNETİMİ (THREAD 2)
    # ====================================================================

    def _goruntu_akisi_dongusu(self):
        """
        Web kamerasından anlık görüntüleri alır ve UDP üzerinden yayınlar.
        """
        if self.kamera is None:
            print("[VİDEO] Kamera erişilebilir değil, video yayını atlanıyor.")
            return

        # Düşük çözünürlük ve sıkıştırma için bir miktar küçültme
        width = 320
        height = 240
        self.kamera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.kamera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        
        # Video akış hızı (FPS)
        video_fps = 10 
        delay = 1 / video_fps

        while not self.durdurma_olayi.is_set():
            ret, frame = self.kamera.read()
            
            if not ret:
                print("[VİDEO] Kare alınamadı.")
                time.sleep(1)
                continue

            # Kareyi JPEG formatında sıkıştır (UDP üzerinden göndermek için boyut küçültme)
            # JPEG kalitesi 50 olarak ayarlandı (0-100 arasında, düşük değer daha küçük dosya)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
            result, encoded_frame = cv2.imencode('.jpg', frame, encode_param)
            
            if result:
                # Numpy dizisini byte dizisine dönüştür
                data = encoded_frame.tobytes()
                
                try:
                    # UDP ile yayınla. Kare boyutu çok büyükse (65KB'dan fazla),
                    # paketler kaybolabilir. Bu yüzden sıkıştırma önemlidir.
                    self.video_soket.sendto(data, (self.hedef_ip, self.VIDEO_PORT))
                    print(f"[VİDEO] Yayınlandı. Boyut: {len(data)} bayt.")
                except Exception as e:
                    print(f"[VİDEO HATA] Veri gönderilemedi: {e}")

            self.durdurma_olayi.wait(delay)
            
        print("Video akışı sonlandırıldı.")

    # ====================================================================
    # KONTROL METOTLARI
    # ====================================================================

    def baslat(self):
        """Tüm simülasyon Thread'lerini başlatır."""
        if self.telemetri_thread is None or not self.telemetri_thread.is_alive():
            self.durdurma_olayi.clear()
            
            # Thread 1: Telemetri
            self.telemetri_thread = Thread(target=self._telemetri_dongusu)
            self.telemetri_thread.start()
            
            # Thread 2: Video Akışı
            self.video_thread = Thread(target=self._goruntu_akisi_dongusu)
            self.video_thread.start()
            
            print("Simülatör başlatıldı (2 Ayrı Thread).")

    def durdur(self):
        """Tüm Thread'leri güvenli şekilde durdurur ve kaynakları serbest bırakır."""
        self.durdurma_olayi.set()
        
        # Thread'lerin bitmesini bekle
        if self.telemetri_thread and self.telemetri_thread.is_alive():
            self.telemetri_thread.join()
        if self.video_thread and self.video_thread.is_alive():
            self.video_thread.join()

        # Kamera kaynağını serbest bırak
        if self.kamera:
            self.kamera.release()
        
        print("Simülatör kapatıldı ve tüm kaynaklar serbest bırakıldı.")

# ====================================================================
# ANA UYGULAMA ÇALIŞTIRMA BLOĞU
# ====================================================================

if __name__ == '__main__':
    # 1. Simülatör örneğini oluştur
    sim = IHASimulator(ip='127.0.0.1')
    
    # 2. Simülasyonu başlat
    sim.baslat()

    # 3. Belirli bir süre çalıştır
    try:
        print("Simülatör 30 saniye boyunca çalışacak. Durdurmak için Ctrl+C tuşlarına basın.")
        time.sleep(30)
    except KeyboardInterrupt:
        print("\nKullanıcı tarafından durdurma sinyali alındı.")
    finally:
        # 4. Simülasyonu güvenli bir şekilde durdur
        sim.durdur()
        
    print("Program başarıyla sonlandı.")