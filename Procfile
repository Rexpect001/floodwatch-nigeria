web: uvicorn execution.api.main:app --host 0.0.0.0 --port $PORT --workers 2 --loop uvloop
ingestion: python -m execution.ingestion.scheduler
alert_orchestrator: python -m execution.alerts.alert_classifier
alert_router: python -m execution.alerts.alert_router
