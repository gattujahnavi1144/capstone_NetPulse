# Request trace walkthrough

On 2026-11-26, the existing `/docs` routes were available and `RTR-401` was not registered. A Swagger `POST /devices` registered it online with HTTP 201. Existing SQLite data was not reset or deleted.

The first `PATCH /devices/RTR-401/status` sent `{"status":"offline"}` with `X-Request-ID: lab-trace-401`. It returned HTTP 200, an offline device, and `x-request-id: lab-trace-401`. The server emitted:

```json
{"device_id":"RTR-401","event":"device_status_changed","request_id":"lab-trace-401","level":"info","timestamp":"2026-11-26T10:10:26.872391Z"}
{"device_id":"RTR-401","event":"offline_alert_created","request_id":"lab-trace-401","level":"info","timestamp":"2026-11-26T10:10:26.872575Z"}
{"method":"PATCH","path":"/devices/{device_id}/status","status_code":200,"duration_ms":23.636,"event":"request_completed","request_id":"lab-trace-401","level":"info","timestamp":"2026-11-26T10:10:26.889490Z"}
```

`GET /alerts` returned one alert for `RTR-401`. Repeating the PATCH with the same header returned HTTP 200 with the same response header and left the count at one. It emitted only this additional event for that ID:

```json
{"method":"PATCH","path":"/devices/{device_id}/status","status_code":200,"duration_ms":7.802,"event":"request_completed","request_id":"lab-trace-401","level":"info","timestamp":"2026-11-26T10:11:12.047234Z"}
```

`GET /devices/summary` returned one offline router; `GET /devices/RTR-401/probe` returned `{"device_id":"RTR-401","reachable":true,"simulated":true}`.