.PHONY: env env-update doctor

env:
	conda env create -f environment.yml

env-update:
	conda env update -f environment.yml --prune

doctor:
	@bash scripts/doctor.sh
