# Usage:
#   make emu-firestore PROJECT=dingdoor-development
#   make run-fn FN=ai_insert_text_assistant_message TARGET=ai_insert_text_assistant_message PORT=8081 PROJECT=dingdoor-development
# Optional:
#   make dev FN=... TARGET=... PORT=... PROJECT=...

PROJECT ?= dingdoor-development
EMU_HOST ?= 127.0.0.1
FIRESTORE_PORT ?= 8080
FN ?=
TARGET ?=
PORT ?= 8081

.PHONY: emu-firestore run-fn dev

emu-firestore:
	@echo "Starting Firestore emulator (project: $(PROJECT)) on $(EMU_HOST):$(FIRESTORE_PORT)..."
	firebase emulators:start --only firestore --project $(PROJECT)

run-fn:
	@if [ -z "$(FN)" ]; then echo "ERROR: set FN=<function_folder>"; exit 1; fi
	@if [ -z "$(TARGET)" ]; then echo "ERROR: set TARGET=<functions_framework_target>"; exit 1; fi
	@echo "Running function $(FN) with target $(TARGET) on port $(PORT) pointing to Firestore emulator..."
	cd functions/$(FN) && \
	FIRESTORE_EMULATOR_HOST="$(EMU_HOST):$(FIRESTORE_PORT)" \
	GCLOUD_PROJECT="$(PROJECT)" \
	functions-framework --target "$(TARGET)" --port "$(PORT)" --debug

# One-command local dev (starts emulator in background, then runs the function in foreground)
dev:
	@if [ -z "$(FN)" ]; then echo "ERROR: set FN=<function_folder>"; exit 1; fi
	@if [ -z "$(TARGET)" ]; then echo "ERROR: set TARGET=<functions_framework_target>"; exit 1; fi
	@echo "Starting Firestore emulator in background..."
	(firebase emulators:start --only firestore --project $(PROJECT)) & \
	EMU_PID=$$!; \
	sleep 2; \
	echo "Starting functions-framework..."; \
	cd functions/$(FN) && \
	FIRESTORE_EMULATOR_HOST="$(EMU_HOST):$(FIRESTORE_PORT)" \
	GCLOUD_PROJ_
