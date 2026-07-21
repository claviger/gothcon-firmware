PORT     ?= COM3
FIRMWARE ?= firmware/micropython.bin
PYTHON   := python

.PHONY: help erase flash deploy all

help:
	@echo "ESP32-C3 MicroPython Firmware"
	@echo ""
	@echo "Targets:"
	@echo "  erase   - Erase ESP32-C3 flash"
	@echo "  flash   - Erase + write MicroPython firmware"
	@echo "  deploy  - Copy src/ to device filesystem"
	@echo "  all     - flash + deploy"
	@echo ""
	@echo "Variables:"
	@echo "  PORT=$(PORT)       Serial port (e.g. COM3 or /dev/ttyACM0)"
	@echo "  FIRMWARE=$(FIRMWARE)"

erase:
	$(PYTHON) flash.py --port $(PORT) --erase-only

flash:
	$(PYTHON) flash.py --port $(PORT) --firmware $(FIRMWARE)

deploy:
	$(PYTHON) flash.py --port $(PORT) --deploy

# Single flash.py process so it waits for the post-flash reboot before deploying.
all:
	$(PYTHON) flash.py --port $(PORT) --firmware $(FIRMWARE) --deploy
