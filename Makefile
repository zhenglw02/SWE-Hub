.PHONY: build install clean format lint

build:
	@poetry build -f wheel
ifeq ($(DEBUG),1)
	@echo "Debug mode ON, renaming .whl file with timestamp..."
	@whl_file=$$(ls -t dist/*.whl | head -n 1); \
	ts=$$(date +%Y%m%d%H%M%S); \
	new_file=$$(echo $$whl_file | sed "s/\.whl$$/+$$ts.whl/"); \
	mv $$whl_file $$new_file; \
	echo "Renamed to: $$new_file"
endif

install:
	poetry install

clean:
	rm -rf build output dist

format: install
	poetry run black ./code_data_agent
	poetry run ruff check --select I --fix ./code_data_agent

lint: install
	poetry run black ./code_data_agent --check 
	poetry run ruff check ./code_data_agent
	poetry run mypy ./code_data_agent --install-types --non-interactive
	
.PHONY: build install uninstall clean lint
