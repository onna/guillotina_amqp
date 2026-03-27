mkfile_path := $(abspath $(lastword $(MAKEFILE_LIST)))
current_dir := $(notdir $(patsubst %/,%,$(dir $(mkfile_path))))

RABBITMQ_PORT ?= 5672

.PHONY: run-rabbitmq stop-rabbitmq install test lint

run-rabbitmq:
	docker run -d --name guillotina-amqp-rabbitmq -p 127.0.0.1:$(RABBITMQ_PORT):5672 rabbitmq:3-management

stop-rabbitmq:
	docker rm -f guillotina-amqp-rabbitmq

install:
	pip install -e .[test]

test:
	RABBITMQ=localhost:$(RABBITMQ_PORT) pytest --tb=native -v --capture=no guillotina_amqp --cov=guillotina_amqp

lint:
	flake8 guillotina_amqp --config=setup.cfg
	black --check --verbose guillotina_amqp
	mypy -p guillotina_amqp --ignore-missing-imports

