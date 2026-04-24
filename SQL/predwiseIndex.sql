CREATE INDEX idx_packets_checksum ON packets(checksum);
CREATE INDEX idx_packets_status ON packets(status);
CREATE INDEX idx_packets_created_at ON packets(created_at);
CREATE INDEX idx_packet_metrics_packet_id
ON packet_metrics(packet_id);