.PHONY: load-test load-test-seed

load-test-seed:  ## Seed test data for load tests
	python -m tests.load.seed_data

load-test: load-test-seed  ## Run load tests (50 users, 2 min)
	locust -f tests/load/locustfile.py \
		--host http://localhost:8000 \
		--headless \
		--users 50 \
		--spawn-rate 5 \
		--run-time 2m
