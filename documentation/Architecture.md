# Shoplifting Detection System – MVP Architecture

## Overview

This document describes the workflow and architectural decisions behind the MVP version of the shoplifting detection system.

The MVP is designed to be:

- Functional and usable in real environments  
- Stable and fault-tolerant  
- Non-blocking under load  
- Capable of generating contextual video evidence  
- Architecturally prepared for future scalability  

---

# 1. Video Ingestion Layer

The system receives video streams from a **Digital Video Recorder (DVR)** that aggregates multiple camera channels (CH1–CH...).

Each channel is accessed via **RTSP connection**, which includes:

- Automatic reconnection logic  
- Retry attempts with logging  
- Error tracking for connection failures  

This ensures resilience in real-world environments where streams may temporarily drop.

---

# 2. Ring Buffer (Pre-roll in Memory)

A **ring buffer** maintains the last 10 seconds of video in memory for each camera stream.

Purpose:

- Enables capturing video *before* an event occurs  
- Avoids continuous disk recording  
- Minimizes I/O overhead  
- Reduces latency in clip generation  

The buffer operates in memory using a circular structure, continuously overwriting old frames.

---

# 3. Inference System

The AI model processes frames in real time and produces:

- `score` → probability/confidence of the detected event  

A validation rule is applied:

```
score >= threshold
```

The threshold is configurable depending on deployment conditions.

If the condition is not met, the event is ignored.

---

# 4. Event Deduplication

To prevent repetitive alerts, the system checks whether a similar event has occurred within the last 5 minutes.

The deduplication key is based on:

```
(cameraId + zone + eventType)
```

If a similar event exists within the defined time window:
- The event is ignored.

If not:
- The event proceeds to the alert processing stage.

This significantly improves usability and reduces alert noise.

---

# 5. Job Queue (Clip Processing Decoupling)

When a valid event is detected, a **clip generation job** is pushed into a processing queue.

Purpose:

- Decouple heavy video processing from real-time inference  
- Prevent pipeline blocking  
- Allow future horizontal scaling via multiple workers  

The job contains the necessary metadata to construct the video evidence.

---

# 6. Clip Construction

The system generates a contextual evidence clip consisting of:

- 2 seconds before the event (from the ring buffer)  
- 2 seconds during the event  
- 2 seconds after the event  

The final clip is saved to persistent storage.

---

# 7. Persistence Layer

Two types of data are stored:

## Video File
- Saved to disk (or future object storage such as S3/MinIO)

## Metadata (MongoDB)
Stored fields include:

- cameraId  
- zone  
- eventType  
- score  
- timestamps  
- clip_path or clip_url  

Only metadata is stored in the database to maintain performance and efficiency.

---

# 8. Logging Strategy

The system implements a structured logging mechanism for operational monitoring.

Logs include:

- RTSP connection errors  
- Reconnection attempts  
- Inference failures  
- Clip processing errors  
- System-level warnings  

## Why Plain Text Log Files?

For the MVP, logs are stored in **plain text files** instead of a database or centralized logging system.

This decision was made based on:

- **High write speed** → File appends are significantly faster than database inserts.
- **Lower overhead** → No additional services or infrastructure required.
- **Optimized storage weight** → Text logs consume minimal space compared to structured storage systems.
- **Ease of backup** → Log files can be compressed and backed up easily.
- **Simplicity for MVP** → Reduces system complexity while maintaining observability.

This approach prioritizes performance and operational simplicity.  
In future iterations, logs can be integrated into centralized logging systems (e.g., ELK, Loki, or cloud-based monitoring tools).

---

# 9. Alert Emission

The **Alert Emitter** centralizes the business event by:

- Registering alert metadata  
- Linking the generated clip  
- Preparing the alert for visualization  

---

# 10. Alert Visualization

Alerts are exposed through a dashboard view that allows:

- Viewing alert details  
- Reviewing metadata  
- Downloading the associated video clip  

---

# Design Principles of the MVP

- Fault-tolerant stream handling  
- Memory-based pre-roll capture  
- Configurable detection threshold  
- Event deduplication to prevent spam  
- Asynchronous clip generation  
- Lightweight, high-speed logging strategy  
- Decoupled architecture for scalability  

---