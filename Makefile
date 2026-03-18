ifneq (,$(wildcard .env))
include .env
export
endif

FYERS_BROWSER ?= firefox

.PHONY: fyers-login

fyers-login:
	python scripts/fyers_browser_auth.py
