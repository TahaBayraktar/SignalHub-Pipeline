CREATE TABLE packets (
    id BIGSERIAL PRIMARY KEY,
    packet_id UUID NOT NULL UNIQUE,
    checksum VARCHAR(64) NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,

    status VARCHAR(20) NOT NULL,  -- raw / processed / failed
    retry_count INT DEFAULT 0,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    last_error TEXT
);

ALTER TABLE packets
ADD CONSTRAINT unique_checksum UNIQUE (checksum);


CREATE TABLE packet_events (
    id BIGSERIAL PRIMARY KEY,
    packet_id UUID NOT NULL,
    event_type VARCHAR(50),  -- received / validated / processed / failed / retry
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT fk_packet_event
        FOREIGN KEY(packet_id)
        REFERENCES packets(packet_id)
        ON DELETE CASCADE
);


CREATE TABLE packet_metrics (
    id BIGSERIAL PRIMARY KEY,
    packet_id UUID NOT NULL,
    downsample_method VARCHAR(50) NOT NULL DEFAULT 'full_aggregate',
    mean_x DOUBLE PRECISION,
    mean_y DOUBLE PRECISION,
    mean_z DOUBLE PRECISION,
    rms_x DOUBLE PRECISION,
    rms_y DOUBLE PRECISION,
    rms_z DOUBLE PRECISION,
    peak_x DOUBLE PRECISION,
    peak_y DOUBLE PRECISION,
    peak_z DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT fk_packet
        FOREIGN KEY(packet_id)
        REFERENCES packets(packet_id)
        ON DELETE CASCADE
);