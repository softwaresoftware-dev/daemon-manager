.PHONY: test server

test:
	python -m pytest tests/ -v

server:
	python server.py
