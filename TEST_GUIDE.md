# Predwise — Test Rehberi

Bu rehber sistemi sıfırdan ayağa kaldırıp uçtan uca test etmek için adım adım talimatlar içerir.

---

## 1. Ön Koşullar

```bash
docker --version   # Docker 20+ olmalı
docker compose version  # Compose v2+ olmalı
curl --version
```

---

## 2. Sistemi Başlatma

```bash
cd predwise_task

# İlk kez ya da temiz başlamak istersen:
docker compose down -v   # volume'ları siler, DB'yi sıfırlar
docker compose up --build
```

Başarılı başlangıç logları şöyle görünür:

```
postgres  | database system is ready to accept connections
hub       | INFO:     Application startup complete.
collector | {"event": "collector_started", ...}
collector | {"event": "collector_config_selected", "mode": "accelerated", "hours": 12.0 ...}
```

---

## 3. Temel Sağlık Kontrolleri

Sistem ayaktayken aşağıdaki komutları çalıştır. Her biri `200 OK` dönmeli.

```bash
# Hub sağlık durumu
curl http://localhost:8000/health
# Beklenen: {"status":"ok","service":"hub"}

# Hub paket sayaçları
curl http://localhost:8000/metrics
# Beklenen: {"total_packets":N,"processed_packets":N,"failed_packets":0,"raw_packets":0}

# Hub özet istatistikleri (en az 1 paket işlendikten sonra)
curl http://localhost:8000/summary
# Beklenen: {"ok":true,"summary":{"total_packets":N,"avg_mean_x":...}}
```

---

## 4. Uçtan Uca Akış Testi

### 4.1 İlk Paket İşlendiğini Doğrula

```bash
# Metrics'i izle — processed_packets artmalı
watch -n 2 'curl -s http://localhost:8000/metrics'
```

`processed_packets` değeri 1'e ulaştıktan sonra devam et.

### 4.2 Özet Verilerini Kontrol Et

```bash
curl -s http://localhost:8000/summary | python3 -m json.tool
```

Beklenen çıktı yapısı:
```json
{
  "ok": true,
  "summary": {
    "total_packets": 5,
    "processed_packets": 5,
    "failed_packets": 0,
    "avg_mean_x": 0.123,
    "avg_rms_x": 0.456,
    "max_peak_x": 2.789,
    ...
  }
}
```

### 4.3 Grafik Endpoint'ini Test Et

Önce bir `packet_id` al:
```bash
# DB'den bir packet_id çek
docker compose exec postgres psql -U postgres -d predwise \
  -c "SELECT packet_id FROM packets WHERE status='processed' LIMIT 1;"
```

Çıkan UUID'yi kullan:
```bash
PACKET_ID="buraya-uuid-yaz"

# JSON grafik verisi
curl -s "http://localhost:8000/plot/$PACKET_ID?step=50" | python3 -m json.tool

# PNG grafik — tarayıcıda aç ya da dosyaya kaydet
curl "http://localhost:8000/plot-image/$PACKET_ID?step=50" -o test_plot.png
open test_plot.png   # macOS
```

Beklenenler:
- JSON yanıtında `relative_time_ms`, `x`, `y`, `z` dizileri olmalı
- `downsampled_count` değeri `sample_count / step` olmalı (≈320 eleman, step=100 ise)
- PNG dosyası x/y/z eksenlerini gösteren bir grafik olmalı

---

## 5. Zorlayıcı Şart Testleri

### 5.1 Idempotency (Duplicate Engelleme)

Aynı paketi iki kez gönder — ikinci seferinde duplicate dönmeli, DB'de yeni kayıt oluşmamalı.

```bash
# Gönderilmiş bir paketi ve packet_id'sini bul
docker compose exec postgres psql -U postgres -d predwise \
  -c "SELECT packet_id, file_name FROM packets WHERE status='processed' LIMIT 1;"

# O dosyayı aynı packet_id ile tekrar gönder (collector container'ından)
# /ingest artık hem 'file' hem 'packet_id' form field bekliyor
docker compose exec collector bash -c \
  "curl -v -X POST http://hub:8000/ingest \
   -F 'file=@/app/data/sent/DOSYA_ADI.parquet' \
   -F 'packet_id=BURAYA-UUID-YAZ'"
```




Beklenen yanıt:
```json
{"ok": true, "duplicate": true}
```

DB'deki kayıt sayısı değişmemeli:
```bash
docker compose exec postgres psql -U postgres -d predwise \
  -c "SELECT COUNT(*) FROM packets;"
```

### 5.2 Backpressure (Geri Basınç)

Hub'ı durdur, collector'ın pending kuyruğunu biriktirdiğini gözlemle.

```bash
# Hub'ı durdur
docker compose stop hub

# Collector loglarını izle — backpressure_triggered event'i görünmeli
docker compose logs -f collector | grep -E "backpressure|pending"
```

Beklenen log:
```json
{"event": "backpressure_triggered", "pending_count": 3, "max_pending_packets": 2}
```

Hub'ı tekrar başlat — bekleyen paketler otomatik gönderilmeli:
```bash
docker compose start hub
docker compose logs -f collector | grep -E "packet_sent|pending_flush"
```

### 5.3 Data Corruption Check (SHA256)

Bozuk bir parquet dosyası gönder — validation hatası dönmeli.

```bash
# Sahte bir dosya oluştur
echo "bozuk veri" > /tmp/bozuk_paket.parquet

# /ingest artık packet_id form field'ı zorunlu tutuyor
curl -s -X POST http://localhost:8000/ingest \
  -F "file=@/tmp/bozuk_paket.parquet" \
  -F "packet_id=00000000-0000-0000-0000-000000000001" | python3 -m json.tool
```





Beklenen yanıt:
```json
{
  "ok": false,
  "packet_id": "...",
  "error": "Parquet dosyasi okunamadi: ..."
}
```

Hub DB'de `status='failed'` kaydı oluşmalı:
```bash
docker compose exec postgres psql -U postgres -d predwise \
  -c "SELECT packet_id, status, last_error FROM packets WHERE status='failed';"
```

### 5.4 Observability (Yapısal JSON Log)

```bash
# Hub logları — tüm satırlar JSON formatında olmalı
docker compose logs hub | tail -20

# Collector logları
docker compose logs collector | tail -20

# Sadece belirli event'leri filtrele
docker compose logs hub | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        log = json.loads(line.strip())
        if log.get('event') == 'packet_saved':
            print(json.dumps(log, indent=2))
    except:
        pass
"
```

### 5.5 Data Optimization

Ham verinin DB'ye yazılmadığını, sadece metriklerin gittiğini doğrula:

```bash
docker compose exec postgres psql -U postgres -d predwise -c "
SELECT
    p.packet_id,
    p.status,
    m.downsample_method,
    m.mean_x,
    m.rms_x,
    m.peak_x
FROM packets p
JOIN packet_metrics m ON p.packet_id = m.packet_id
LIMIT 3;
"
```

Beklenen: `downsample_method = 'full_aggregate'` ve sayısal metrik değerleri görünmeli.

Ham parquet dosyaları disk'te olmalı:
```bash
docker compose exec hub ls /app/storage/processed/ | head -5
```

---

## 6. DB Bütünlüğünü Doğrula

```bash
docker compose exec postgres psql -U postgres -d predwise << 'EOF'
-- Paket özeti
SELECT status, COUNT(*) FROM packets GROUP BY status;

-- Her başarılı paketin tam 3 eventi olmalı (received, validated, processed)
SELECT packet_id, COUNT(*) as event_count
FROM packet_events
GROUP BY packet_id
ORDER BY event_count DESC
LIMIT 5;

-- Metrikler var mı?
SELECT COUNT(*) as metric_count FROM packet_metrics;

-- FK bütünlüğü — orphaned event yok olmalı (0 dönmeli)
SELECT COUNT(*) as orphaned_events
FROM packet_events pe
LEFT JOIN packets p ON pe.packet_id = p.packet_id
WHERE p.packet_id IS NULL;
EOF
```

---

## 7. 12 Saatlik Simülasyon Testi

Collector tamamlandıktan sonra toplam üretilen paket sayısını kontrol et:

```bash
# 12 saat × 3600 sn / 10 sn = 4320 paket beklenir
docker compose exec postgres psql -U postgres -d predwise \
  -c "SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE status='processed') as processed FROM packets;"
```

Beklenen: `total = 4320`, `processed = 4320`

Veri hacmini kontrol et:
```bash
# Toplam parquet dosya boyutu
docker compose exec hub du -sh /app/storage/processed/

# Bir paketin boyutu (~250-300 KB beklenir, ham float64 CSV ~1.5 MB olurdu)
docker compose exec hub ls -lh /app/storage/processed/ | head -3
```

---

## 8. Temizlik

```bash
# Servisleri durdur (volume'lar korunur)
docker compose down

# Servisleri durdur ve tüm verileri sil (sıfırdan başlamak için)
docker compose down -v
```




