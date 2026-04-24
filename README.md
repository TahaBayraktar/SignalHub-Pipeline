# Predwise — Sensör Veri Toplama ve İzleme Sistemi

Üretim tesisindeki makinelere takılı sensör kutusundan yüksek frekanslı ivme verisi toplayan,
sıkıştırıp Hub'a ileten, Hub'da ingest edip veritabanına özet olarak kaydeden ve kullanıcıya
grafik sunan uçtan uca veri pipeline sistemi.

---

## İçindekiler

1. [Sistem Mimarisi](#1-sistem-mimarisi)
2. [Mimari Kararlar](#2-mimari-kararlar)
3. [Proje Yapısı](#3-proje-yapısı)
4. [Veri Akışı](#4-veri-akışı)
5. [Veritabanı Şeması](#5-veritabanı-şeması)
6. [Collector Detayları](#6-collector-detayları)
7. [Hub Detayları](#7-hub-detayları)
8. [Zorlayıcı Gerçek Hayat Şartları](#8-zorlayıcı-gerçek-hayat-şartları)
9. [12 Saatlik Test — Hızlandırılmış Simülasyon](#9-12-saatlik-test--hızlandırılmış-simülasyon)
10. [Nasıl Çalıştırılır](#10-nasıl-çalıştırılır)
11. [API Referansı](#11-api-referansı)
12. [Ortam Değişkenleri](#12-ortam-değişkenleri)

---

## 1. Sistem Mimarisi

```
                     ┌──────────────────────────────────────────────┐
                     │              COLLECTOR (Edge)                 │
                     │                                               │
                     │  sensor_sim.read_xyz()                        │
                     │       │                                       │
                     │       ▼                                       │
                     │  3200 Hz örnekleme  ──►  10 sn tampon         │
                     │  (realtime / accelerated)   │                 │
                     │                             ▼                 │
                     │                    Parquet + Snappy           │
                     │                    float32/int32              │
                     │                    SHA256 checksum            │
                     │                             │                 │
                     │           ┌────────────────►│                 │
                     │           │      pending/   ▼                 │
                     │     Retry │      sending/  HTTP multipart     │
                     │     Kuyruk│      sent/    POST /ingest        │
                     │           │      failed/        │             │
                     │           └─────────────────────┘             │
                     │         Backpressure (MAX_PENDING=2)          │
                     │         GET /health  :9000                    │
                     └──────────────────────┬───────────────────────┘
                                            │
                                            │  HTTP multipart upload
                                            │  (sıkıştırılmış .parquet)
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │                 HUB (Server)                  │
                     │                                               │
                     │  POST /ingest  (file + packet_id)             │
                     │    ├─ packet_id → Collector'dan gelir         │
                     │    ├─ SHA256 checksum  → idempotency          │
                     │    ├─ disk'e yaz  (raw/)                      │
                     │    ├─ validation (kolonlar, fs_hz, n_samples) │
                     │    ├─ metrik hesapla (mean/rms/peak)          │
                     │    └─ DB'ye yaz → processed/                  │
                     │                                               │
                     │  GET /summary     →  özet istatistikler       │
                     │  GET /plot/:id    →  downsampled JSON         │
                     │  GET /plot-image/:id → PNG grafik             │
                     │  GET /metrics     →  paket sayaçları          │
                     │  GET /health      →  servis durumu            │
                     │                                               │
                     │           ┌──────────────────┐               │
                     │           │   PostgreSQL DB   │               │
                     │           │  ┌─────────────┐ │               │
                     │           │  │   packets   │ │               │
                     │           │  ├─────────────┤ │               │
                     │           │  │packet_metric│ │               │
                     │           │  ├─────────────┤ │               │
                     │           │  │packet_events│ │               │
                     │           │  └─────────────┘ │               │
                     │           └──────────────────┘               │
                     └──────────────────────────────────────────────┘
```

---

## 2. Mimari Kararlar

### Neden Parquet + Snappy?

Ham ivme verisi `float64` olarak CSV'ye yazılsaydı bir paket (32.000 satır × 6 kolon) yaklaşık
**1.5 MB** olurdu. Parquet kolonar format + Snappy sıkıştırma + `float32`/`int32` tip kısıtlaması
ile aynı veri **~250–300 KB**'a iner. Bu **≥%80 boyut azaltımı** sağlar ve PDF'in istediği %25
sınırını çok aşar. Snappy tercihinin gerekçesi: hız/sıkıştırma oranı dengesi — gzip'e göre çok
daha hızlı açılır, sensör kutusunun CPU'sunu yormaz.

### Neden ham veri DB'ye yazılmıyor?

32.000 satırı her paket için PostgreSQL'e tek tek INSERT etmek hem I/O açısından verimsiz hem de
gereksiz boyut büyümesine yol açar. Bunun yerine:
- **Soğuk depolama (cold storage):** Ham parquet dosyaları diskte `processed/` klasöründe tutulur
- **Sıcak depolama (hot storage):** DB'ye yalnızca 9 özet metrik (mean/rms/peak × x/y/z) yazılır

Bu yaklaşım sorgu performansını korurken disk + DB boyutunu minimize eder.

### Neden PostgreSQL?

Görev SQL veritabanı zorunlu kılıyor. PostgreSQL'in `FILTER` aggregation sözdizimi, `TIMESTAMPTZ`,
`UUID` tipi, `ON DELETE CASCADE` ile bütünleşik FK desteği ve `pg_isready` healthcheck kolaylığı
bu seçimi destekliyor.

### Neden FastAPI?

Async `POST /ingest` ile büyük dosya yükleme, otomatik OpenAPI/Swagger dökümantasyonu (`/docs`),
Pydantic tip doğrulama ve lifespan context manager ile background task yönetimi.

### Neden pending/sending/sent/failed klasörleri?

Collector, ağ kesintisi veya Hub'ın geçici unavailability durumunda veri kaybetmemek için
dosya sistemi tabanlı bir kuyruk kullanır. Stateful: program yeniden başlasa bile
`pending/` klasörü flush edilir, hiçbir paket düşmez. `sending/` klasörü crash sırasında
yarım kalan transferleri recover etmeyi sağlar.

### Neden SHA256 checksum?

İki amaç için kullanılıyor:
1. **Data corruption check:** Ağ üzerinde bozulan payload tespit edilir
2. **Idempotency anahtarı:** Aynı dosya iki kez gelse bile checksum eşleşmesi Hub'ın
   duplicate oluşturmasını engeller

---

## 3. Proje Yapısı

```
predwise_task/
│
├── Collector/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── collector.py        # Ana giriş noktası, CLI argümanları, main loop
│   │   ├── config.py           # Tüm sabitler ve env var okuma
│   │   ├── sampler.py          # sensor_sim.read_xyz() çağrısı, SampleRecord döner
│   │   ├── packet_writer.py    # DataFrame → Parquet yaz, SHA256 hesapla, meta oluştur
│   │   ├── sender.py           # HTTP multipart POST /ingest
│   │   ├── retry_queue.py      # pending klasörünü tara, gönder, kuyruk yönet
│   │   ├── meta_store.py       # Her paket için JSON meta dosyası (retry sayacı vb.)
│   │   ├── counter_store.py    # Paket index kalıcılığı (packet_counter.txt)
│   │   ├── checksum.py         # SHA256 hesaplama (dosyadan)
│   │   ├── packet_id.py        # UUID5 ile deterministik packet_id üretimi
│   │   ├── health_server.py    # FastAPI GET /health — port 9000
│   │   ├── cleanup.py          # sent/ ve failed/ klasör boyutu sınırlama
│   │   ├── logger.py           # JSON structured logging + dosya rotasyonu
│   │   └── models.py           # SampleRecord ve PacketMeta dataclass'ları
│   │
│   ├── sensor_sim.py           # Sensör simülatörü (verilmiş — değiştirilmedi)
│   ├── requirements.txt
│   └── Dockerfile
│
├── Hub/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app, tüm endpoint tanımları
│   │   ├── config.py           # Dizin yapısı + DB bağlantı ayarları (env var)
│   │   ├── validator.py        # Kolon, fs_hz, n_samples doğrulama
│   │   ├── metrics.py          # mean/rms/peak hesaplama, downsample_method
│   │   ├── plot_service.py     # nth-sample downsample + matplotlib PNG
│   │   ├── storage.py          # Tüm DB CRUD fonksiyonları (psycopg2)
│   │   ├── db.py               # psycopg2 bağlantı yönetimi
│   │   ├── cleanup_service.py  # Eski packet_events temizleme (30 gün, async)
│   │   └── logger.py           # JSON structured logging + dosya rotasyonu
│   │
│   ├── requirements.txt
│   └── Dockerfile
│
├── SQL/
│   ├── predwise.sql            # 3 tablo şeması + FK constraint'ler
│   └── predwiseIndex.sql       # 4 performans index'i
│
├── docker-compose.yml          # postgres + hub + collector servisleri
├── README.md
└── TEST_GUIDE.md               # Uçtan uca test senaryoları
```

---

## 4. Veri Akışı

```
sensor_sim.read_xyz()
    │
    │  Her çağrıda (x, y, z) float döner
    ▼
collect_sample(seq)  →  SampleRecord(ts_ns, x, y, z, fs_hz=3200, seq)
    │
    │  3200 Hz hızında 10 saniye → 32.000 örnek tamponlanır
    ▼
write_packet(buffer, packet_index)
    ├─ DataFrame oluştur, dtype'ları zorla:
    │    ts_ns→int64 | x,y,z→float32 | fs_hz→int32 | seq→int64
    ├─ Parquet + Snappy ile pending/ klasörüne yaz
    ├─ SHA256 checksum hesapla
    ├─ UUID5 ile deterministik packet_id üret  ← Collector üretir
    └─ JSON meta dosyasını meta/ klasörüne yaz (packet_id burada saklanır)
    │
    ▼
apply_backpressure_if_needed()
    └─ pending/ > MAX_PENDING_PACKETS (2) ise → flush dene → bekle
    │
    ▼
flush_pending_packets()
    ├─ pending/ → sending/ (atomic move)
    ├─ meta'dan packet_id oku
    ├─ send_packet(file, packet_id) → POST /ingest (multipart: file + packet_id)
    │
    ├─ [BAŞARILI]  → sent/ klasörüne taşı → cleanup (MAX=50)
    └─ [BAŞARISIZ] → retry_count artır
                   ├─ retry < 5  → tekrar pending/'e al
                   └─ retry ≥ 5  → failed/ klasörüne taşı → cleanup (MAX=100)

─────────────────────────────── HTTP ────────────────────────────────

POST /ingest (multipart: file + packet_id form field)
    │
    ├─ packet_id → Collector tarafından üretilmiş UUID5 (deterministik)
    ├─ SHA256 hesapla
    ├─ packet_exists(checksum)?  →  EVET: {"ok":true,"duplicate":true}  STOP
    │
    ├─ raw/ klasörüne yaz
    ├─ packets tablosuna INSERT (status='raw', packet_id=Collector'ın ID'si)
    ├─ packet_events: "received"
    │
    ├─ packet_dogrula()
    │    ├─ kolonlar: [ts_ns, x, y, z, fs_hz, seq]
    │    ├─ n_samples == 32.000
    │    └─ fs_hz == 3200
    │
    ├─ [GEÇERSİZ] → failed/ klasörüne taşı → status='failed' → STOP
    │
    ├─ paket_metriklerini_hesapla()
    │    └─ mean/rms/peak × x,y,z  +  downsample_method='full_aggregate'
    ├─ packet_metrics tablosuna INSERT
    ├─ packet_events: "validated" → "processed"
    ├─ processed/ klasörüne taşı
    └─ status='processed', processed_at=NOW()
       └─ {"ok":true, "packet_id":"...", "n_samples":32000}
```

---

## 5. Veritabanı Şeması

### `packets` — Her paketin yaşam döngüsü

| Kolon | Tip | Açıklama |
|---|---|---|
| `packet_id` | UUID | Collector tarafından UUID5 ile üretilen deterministik kimlik |
| `checksum` | VARCHAR(64) | SHA256 — idempotency anahtarı (`UNIQUE`) |
| `file_name` | TEXT | Orijinal parquet dosya adı |
| `file_path` | TEXT | Güncel disk konumu (raw→processed veya failed) |
| `status` | VARCHAR(20) | `raw` / `processed` / `failed` |
| `retry_count` | INT | Hub tarafındaki yeniden deneme sayısı |
| `created_at` | TIMESTAMPTZ | Paketin alındığı zaman |
| `processed_at` | TIMESTAMPTZ | Başarıyla işlendiği zaman (status=processed ise) |
| `last_error` | TEXT | Son hata mesajı |

### `packet_metrics` — Her paketin özet metrikleri (FK → packets, CASCADE)

| Kolon | Tip | Açıklama |
|---|---|---|
| `packet_id` | UUID | İlgili paket |
| `downsample_method` | VARCHAR(50) | Kullanılan özet yöntemi (`full_aggregate`) |
| `mean_x/y/z` | DOUBLE PRECISION | 32.000 sample ortalaması |
| `rms_x/y/z` | DOUBLE PRECISION | Root Mean Square — titreşim şiddeti |
| `peak_x/y/z` | DOUBLE PRECISION | Maksimum mutlak değer — ani darbeler |

### `packet_events` — Her paketin olay geçmişi (FK → packets, CASCADE)

| Kolon | Tip | Açıklama |
|---|---|---|
| `packet_id` | UUID | İlgili paket |
| `event_type` | VARCHAR(50) | `received` / `validated` / `processed` / `validation_failed` / `failed` |
| `message` | TEXT | Detay mesajı |
| `created_at` | TIMESTAMPTZ | Olayın gerçekleştiği zaman |

### İndeksler (`predwiseIndex.sql`)

```sql
idx_packets_checksum    -- idempotency sorgusu O(log n)
idx_packets_status      -- durum bazlı filtreleme
idx_packets_created_at  -- zaman bazlı sıralama
idx_packet_metrics_packet_id  -- JOIN performansı
```

---

## 6. Collector Detayları

### Örnekleme Döngüsü

```
Hedef:      3200 Hz
Paket süresi:  10 saniye
Paket başına örnek:  32.000
```

Zamanlama `time.perf_counter()` ile yönetilir. Gerçek zamanlı kusursuz timing garantisi
verilmez (gerçek sensör kutusu gibi), ancak **efektif Hz** her paket sonunda hesaplanıp
loglanır:

```python
effective_hz = n_samples / (duration_ns / 1_000_000_000)
```

### Paket Dosya Adı Formatı

```
packet_{index}_{start_ts_ns}_{end_ts_ns}_{created_at}.parquet
```

Örnek: `packet_0_1742903454123456789_1742903464987654321_20260325_143012.parquet`

### Klasör Yapısı (Collector)

```
Collector/data/
├── pending/    # Henüz gönderilmemiş paketler
├── sending/    # Gönderim denemesi süren paket (crash recovery)
├── sent/       # Başarıyla gönderilmiş (max 50 adet tutulur)
├── failed/     # MAX_RETRY (5) aşılan paketler (max 100 adet tutulur)
└── meta/       # Her paket için JSON meta dosyası
```

### Collector CLI Argümanları

```bash
python -m app.collector \
  --mode        realtime|accelerated   # Çalışma modu
  --hours       12                     # Toplam veri süresi (saat)
  --acceleration 100                   # Sadece accelerated modda: hız katsayısı
```

---

## 7. Hub Detayları

### Paket İşleme Adımları

1. Multipart formdan `file` ve `packet_id` al (packet_id Collector'dan gelir)
2. Dosyayı belleğe al → SHA256 hesapla
3. Duplicate kontrol → mevcut checksum varsa dur
4. `raw/` klasörüne yaz → DB'ye Collector'ın `packet_id`'si ile `status='raw'`
5. Validation: kolon sırası, n_samples, fs_hz
6. Metrik hesaplama: mean/rms/peak (x, y, z)
7. `packet_metrics` tablosuna yaz
8. `processed/` klasörüne taşı → `status='processed'`, `processed_at=NOW()`

### Grafik Servisi

Ham 3200 Hz veri grafiğe çizilmez. `nth-sample` yöntemiyle downsample uygulanır:

```
step=100 → 32.000 sample → 320 nokta  (varsayılan)
step=50  → 32.000 sample → 640 nokta
```

`GET /plot/{packet_id}` JSON döner, `GET /plot-image/{packet_id}` doğrudan PNG döner.

### Cleanup Servisi

Arka planda async olarak çalışır. Her **24 saatte bir** 30 günden eski `packet_events`
kayıtlarını siler:

```python
DELETE FROM packet_events
WHERE created_at < NOW() - '30 days'::interval
```

---

## 8. Zorlayıcı Gerçek Hayat Şartları

PDF'de en az 3 tanesi istenmiştir. **Tüm 5 şart uygulanmıştır.**

---

### ✅ 1. Idempotency

> *Aynı packet iki kez gelirse duplicate yaratma*

**Nasıl çalışır:**

Hub, gelen her paketin SHA256 checksumunu hesaplar ve `packets.checksum` kolonunda arar.
Daha önce alınmış bir paketin checksumu eşleşirse yeni kayıt oluşturulmaz:

```python
# Hub/app/main.py
checksum = calculate_sha256_bytes(content)
if packet_exists(checksum):
    return {"ok": True, "duplicate": True}
```

`checksum` kolonunda `UNIQUE` constraint ve index tanımlıdır; eşzamanlı isteklerde de
güvenlidir.

---

### ✅ 2. Backpressure

> *Hub yavaşsa Collector tarafında paket biriktirme + limit + loglama*

**Nasıl çalışır:**

Her yeni paket toplanmadan önce `pending/` klasöründeki bekleyen paket sayısı kontrol edilir.
Limit aşılmışsa collector yeni örnekleme yapmak yerine bekler:

```
pending/ dosya sayısı  ≤ 2  →  normal devam
pending/ dosya sayısı  >  2  →  flush dene → 5 sn bekle → tekrar kontrol
```

Loglanan event: `backpressure_triggered` (WARNING seviyesi)

Bu mekanizma bellek taşmasını ve disk dolmasını engeller. Limit ve bekleme süresi
`config.py`'de `MAX_PENDING_PACKETS` ve `BACKPRESSURE_SLEEP_SEC` ile ayarlanabilir.

---

### ✅ 3. Data Optimization

> *Ham verinin DB üzerinde düşük boyutta tutulmasını sağlamak*

**İki katmanlı yaklaşım:**

**Boyut küçültme (dosya seviyesi):**

| Format | Boyut (1 paket / 32.000 satır) |
|---|---|
| CSV, float64 | ~1.5 MB |
| Parquet + Snappy, float32/int32 | ~250–300 KB |
| Azaltma | **~%80** |

`float32` + `int32` tip kısıtlaması `packet_writer.py`'de DataFrame oluşturulurken
`astype()` ile zorlanır. PDF'in istediği ≥%25 sınırı büyük farkla aşılır.

**Boyut küçültme (DB seviyesi):**

32.000 satır DB'ye hiç yazılmaz. Her paket için sadece 9 float değeri (`packet_metrics`
tablosu) yazılır. Soğuk depolama (parquet dosyaları) yalnızca disktedir.

---

### ✅ 4. Observability

> *Structured log (JSON) + basic metrics endpoint*

**Structured JSON Logging:**

Her iki serviste tüm log satırları makine tarafından parse edilebilir JSON formatındadır:

```json
{
  "timestamp": "2026-03-25T14:30:12.456789",
  "level": "INFO",
  "logger": "hub.ingest",
  "message": "Packet kaydedildi",
  "event": "packet_saved",
  "packet_id": "a1b2c3d4-...",
  "checksum": "e3b0c44...",
  "mean_x": 0.123,
  "rms_x": 0.456,
  "peak_x": 2.789
}
```

Log rotasyonu: gece yarısı, son 7 gün saklanır.

**Metrics Endpoint:**

```
GET /metrics
→ {
    "total_packets": 42,
    "processed_packets": 40,
    "failed_packets": 1,
    "raw_packets": 1
  }
```

**Health Endpoints:**

- Hub: `GET :8000/health` → `{"status": "ok", "service": "hub"}`
- Collector: `GET :9000/health` → pending/sent/failed sayıları + disk durumu + uptime

---

### ✅ 5. Data Corruption Check

> *SHA256 checksum ile payload doğrula*

**Collector tarafı:**

Paket parquet olarak diske yazıldıktan sonra dosya SHA256'sı hesaplanır ve meta dosyasına
kaydedilir. Bu checksum aynı zamanda deterministik `packet_id` üretiminde de kullanılır.

**Hub tarafı:**

Gelen `bytes` payload'dan SHA256 hesaplanır. Bu değer:
1. **Idempotency kontrolü** için `packets.checksum` ile karşılaştırılır
2. Parquet olarak okunamayan payload `validator.py` tarafından tespit edilir, `failed/`
   klasörüne taşınır ve DB'de `status='failed'` olarak işaretlenir

---

## 9. 12 Saatlik Test — Hızlandırılmış Simülasyon

Gerçek zamanlı 12 saat beklemek yerine **time dilation** (zaman genişletme) kullanılır.
Bu yaklaşım README'de açıkça belgelenmiştir.

### Hesap

```
12 saat  = 43.200 saniye
Paket süresi = 10 saniye
Toplam paket = 43.200 / 10 = 4.320 paket

acceleration = 100 ile:
  Her paketin örnekleme süresi  →  10 sn / 100 = 0.1 sn
  Toplam süre  →  4.320 × 0.1 sn = 432 sn ≈ 7 dakika
```

`docker-compose.yml` içinde collector servisi varsayılan olarak `--acceleration 100`
ile yapılandırılmıştır. Saf örnekleme süresi ~7 dakikadır; ancak parquet yazma ve
HTTP upload overhead'i nedeniyle gerçek çalışma süresi **~10–20 dakika** arasındadır.

### Gerçek Zamanlı Çalıştırma

```bash
docker compose run --rm collector \
  python -m app.collector --mode realtime --hours 12
```

---

## 10. Nasıl Çalıştırılır

### Gereksinimler

- Docker 20+
- Docker Compose v2+

### Port Haritası

| Servis | Host Port | Container Port |
|---|---|---|
| Hub API | `8000` | `8000` |
| PostgreSQL | `5433` | `5432` |
| Collector Health | `9000` | `9000` |

> PostgreSQL host portu `5433`'tür (makinede yerel PostgreSQL kuruluysa 5432 çakışmasını önlemek için).
> pgAdmin veya başka bir DB aracıyla bağlanmak için `localhost:5433` kullan.

### Hızlı Başlangıç

```bash
cd predwise_task

# Tüm servisleri build edip başlat
docker compose up --build
```

Başlatma sırası otomatik olarak yönetilir (healthcheck zinciri):

```
postgres  →  (pg_isready)  →  hub  →  (/health 200)  →  collector
```

### Servis Bazlı Yönetim

```bash
# Sadece altyapıyı başlat (Hub API'yi test etmek için)
docker compose up postgres hub

# Collector'ı farklı parametrelerle çalıştır
docker compose run --rm collector \
  python -m app.collector --mode accelerated --hours 6 --acceleration 50

# Logları takip et
docker compose logs -f hub
docker compose logs -f collector

# Servisleri durdur (veriler korunur)
docker compose down

# Tamamen sıfırla (DB ve tüm veriler silinir)
docker compose down -v
```

---

## 11. API Referansı

Tüm endpointler `http://localhost:8000` üzerinden erişilebilir.
Swagger UI: `http://localhost:8000/docs`

---

### `POST /ingest`

Collector'dan sıkıştırılmış paket alır.

**İstek:** `multipart/form-data`

| Alan | Tip | Açıklama |
|---|---|---|
| `file` | binary | `.parquet` dosyası (Snappy sıkıştırmalı) |
| `packet_id` | string | Collector'ın UUID5 ile ürettiği deterministik ID |

**Başarılı yanıt:**
```json
{
  "ok": true,
  "packet_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "n_samples": 32000
}
```

**Duplicate yanıt:**
```json
{ "ok": true, "duplicate": true }
```

**Validation hatası:**
```json
{ "ok": false, "packet_id": "...", "error": "fs_hz hatali. Beklenen=3200, gelen=1600" }
```

---

### `GET /summary`

Tüm işlenmiş paketlerin istatistiksel özeti.

```json
{
  "ok": true,
  "summary": {
    "total_packets": 4320,
    "processed_packets": 4318,
    "failed_packets": 2,
    "avg_mean_x": 0.0123,
    "avg_rms_x": 0.4567,
    "max_peak_x": 3.2198,
    "avg_mean_y": ...,
    "avg_mean_z": ...
  }
}
```

---

### `GET /plot/{packet_id}?step=100`

Bir paketin downsampled ivme verisini JSON olarak döner.

**Parametreler:**
- `packet_id` — UUID
- `step` — Downsample adımı (varsayılan: 100 → 320 nokta)

```json
{
  "ok": true,
  "packet_id": "...",
  "plot": {
    "relative_time_ms": [0.0, 31.25, 62.5, ...],
    "x": [0.123, 0.145, ...],
    "y": [-0.056, -0.048, ...],
    "z": [0.987, 0.991, ...],
    "sample_count": 32000,
    "downsampled_count": 320,
    "step": 100
  }
}
```

---

### `GET /plot-image/{packet_id}?step=100`

Bir paketin downsampled grafiğini PNG olarak döner. (`Content-Type: image/png`)

---

### `GET /metrics`

Anlık paket sayaçları.

```json
{
  "total_packets": 4320,
  "processed_packets": 4318,
  "failed_packets": 2,
  "raw_packets": 0
}
```

---

### `GET /health`

Servis sağlık durumu.

```json
{ "status": "ok", "service": "hub" }
```

---

### `GET :9000/health` (Collector)

Collector'ın kendi health endpoint'i. Collector container'ı içinden veya port açıksa dışarıdan erişilir.

```json
{
  "status": "ok",
  "uptime_sec": 142,
  "pending_packets": 0,
  "failed_packets": 0,
  "sent_packets": 36,
  "last_packet_age_sec": 3,
  "disk_ok": true
}
```

---

## 12. Ortam Değişkenleri

### Hub

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `predwise` | Veritabanı adı |
| `DB_USER` | `postgres` | Kullanıcı adı |
| `DB_PASSWORD` | *(boş)* | Şifre — production'da mutlaka set edilmeli |

### Collector

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `HUB_INGEST_URL` | `http://127.0.0.1:8000/ingest` | Hub ingest endpoint URL |
