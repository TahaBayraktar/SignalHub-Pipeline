import hashlib
import shutil
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import Response


from app.cleanup_service import cleanup_loop

from app.config import ensure_directories, RAW_DIR, PROCESSED_DIR, FAILED_DIR
from app.logger import get_logger
from app.metrics import paket_metriklerini_hesapla
from app.plot_service import plot_verisini_hazirla, plot_png_hazirla
from app.storage import (
    packet_exists,
    insert_packet,
    update_packet_status,
    insert_packet_metrics,
    get_summary,
    get_metrics,
    get_packet_file_path,
    update_packet_file_path,
    insert_packet_event,
)
from app.validator import packet_dogrula

logger = get_logger("hub.ingest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories()

    # Cleanup background task başlat
    asyncio.create_task(cleanup_loop())

    yield


app = FastAPI(title="Predwise Hub", lifespan=lifespan)


def calculate_sha256_bytes(data: bytes) -> str:
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


@app.get("/health")
def health():
    return {"status": "ok", "service": "hub"}


@app.get("/metrics")
def metrics():
    try:
        data = get_metrics()

        logger.info(
            "Metrics endpoint cagrildi",
            extra={"event": "metrics_requested"},
        )

        return data

    except Exception as exc:
        logger.error(
            "Metrics endpoint hatasi",
            extra={"event": "metrics_failed", "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Metrics failed")


@app.get("/plot-image/{packet_id}")
def plot_image(packet_id: str, step: int = 100):
    try:
        file_path = get_packet_file_path(packet_id)

        if not file_path:
            raise HTTPException(status_code=404, detail="Packet bulunamadi")

        png_bytes = plot_png_hazirla(file_path, adim=step)

        logger.info(
            "Plot image endpoint cagrildi",
            extra={
                "event": "plot_image_requested",
                "packet_id": packet_id,
                "step": step,
            },
        )

        return Response(content=png_bytes, media_type="image/png")

    except HTTPException:
        raise

    except Exception as exc:
        logger.error(
            "Plot image endpoint hatasi",
            extra={
                "event": "plot_image_failed",
                "packet_id": packet_id,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="Plot image failed")


@app.get("/plot/{packet_id}")
def plot(packet_id: str, step: int = 100):
    try:
        file_path = get_packet_file_path(packet_id)

        if not file_path:
            raise HTTPException(status_code=404, detail="Packet bulunamadi")

        plot_data = plot_verisini_hazirla(file_path, adim=step)

        logger.info(
            "Plot endpoint cagrildi",
            extra={
                "event": "plot_requested",
                "packet_id": packet_id,
                "step": step,
            },
        )

        return {
            "ok": True,
            "packet_id": packet_id,
            "plot": plot_data,
        }

    except HTTPException:
        raise

    except Exception as exc:
        logger.error(
            "Plot endpoint hatasi",
            extra={
                "event": "plot_failed",
                "packet_id": packet_id,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="Plot failed")


@app.get("/summary")
def summary():
    try:
        data = get_summary()

        logger.info(
            "Summary endpoint cagrildi",
            extra={
                "event": "summary_requested",
            },
        )

        return {
            "ok": True,
            "summary": data,
        }

    except Exception as exc:
        logger.error(
            "Summary endpoint hatasi",
            extra={
                "event": "summary_failed",
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="Summary failed")


@app.post("/ingest")
async def ingest(file: UploadFile = File(...), packet_id: str = Form(...)):
    try:
        content = await file.read()
        checksum = calculate_sha256_bytes(content)

        # Aynı packet daha önce geldiyse tekrar işleme
        if packet_exists(checksum):
            logger.warning(
                "Duplicate packet geldi",
                extra={
                    "event": "duplicate_packet",
                    "file_name": file.filename,
                    "checksum": checksum,
                },
            )
            return {"ok": True, "duplicate": True}
        dest_path = RAW_DIR / file.filename

        # Dosyayı raw klasörüne yaz
        with dest_path.open("wb") as buffer:
            buffer.write(content)

        # Önce DB'ye raw olarak kaydet
        insert_packet(packet_id, checksum, file.filename, str(dest_path))
        insert_packet_event(packet_id, "received", "Packet hub tarafindan alindi")

        # Validation
        gecerli_mi, hata = packet_dogrula(dest_path)

        if not gecerli_mi:
            failed_path = FAILED_DIR / file.filename
            shutil.move(str(dest_path), str(failed_path))

            update_packet_file_path(packet_id, str(failed_path))
            update_packet_status(packet_id, "failed", hata)
            insert_packet_event(packet_id, "validation_failed", hata)

            logger.error(
                "Packet validation hatasi ve failed klasorune tasindi",
                extra={
                    "event": "packet_validation_failed",
                    "packet_id": packet_id,
                    "file_name": file.filename,
                    "checksum": checksum,
                    "error": hata,
                },
            )

            return {
                "ok": False,
                "packet_id": packet_id,
                "error": hata,
            }

        insert_packet_event(packet_id, "validated", "Packet validation basarili")

        # Validation başarılıysa metrik hesapla ve ayrı tabloya yaz
        metrics = paket_metriklerini_hesapla(dest_path)
        insert_packet_metrics(packet_id, metrics)
        insert_packet_event(packet_id, "processed", "Packet metrics hesaplandi")

        processed_path = PROCESSED_DIR / file.filename
        shutil.move(str(dest_path), str(processed_path))

        update_packet_file_path(packet_id, str(processed_path))
        update_packet_status(packet_id, "processed", None)

        logger.info(
            "Packet kaydedildi, dogrulandi, metrikleri yazildi ve processed klasorune tasindi",
            extra={
                "event": "packet_saved",
                "packet_id": packet_id,
                "checksum": checksum,
                "file_name": file.filename,
                "mean_x": metrics["mean_x"],
                "rms_x": metrics["rms_x"],
                "peak_x": metrics["peak_x"],
            },
        )

        return {
            "ok": True,
            "packet_id": packet_id,
            "n_samples": metrics["n_samples"],
        }

    except Exception as exc:
        try:
            insert_packet_event(packet_id, "failed", str(exc))
        except Exception:
            pass

        logger.error(
            "Packet ingest hatasi",
            extra={
                "event": "packet_ingest_failed",
                "file_name": getattr(file, "filename", None),
                "packet_id": packet_id,
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="Ingest failed")