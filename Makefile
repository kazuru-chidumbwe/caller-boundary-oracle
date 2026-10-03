.PHONY: venv vsmartcard dotnet dart test test-dotnet test-dart test-go test-python test-java smoke suite evaluate repro verify-gmrtd-pin verify-manifest

# Python deps live in a project venv so system interpreters (PEP 668) stay untouched.
VENV ?= .venv
PY := $(VENV)/bin/python3
VENV_STAMP := $(VENV)/.deps-installed
GO8 := -modfile=gomod/gmrtd-8fea245.mod -tags gmrtd_8fea245
GO132 := -modfile=gomod/gmrtd-b861835.mod -tags gmrtd_b861835
export GOTOOLCHAIN ?= local

$(VENV_STAMP): classifier/requirements-verify.txt
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -r classifier/requirements-verify.txt
	touch $(VENV_STAMP)

venv: $(VENV_STAMP)

# Independent chip (OpenPACE + vsmartcard) for the positive control and cross-checks.
vsmartcard:
	bash scripts/bootstrap-vsmartcard.sh

# Pinned .NET SDK and emrtd-dotnet.
dotnet:
	bash scripts/bootstrap-dotnet.sh

# Pinned Dart SDK and dmrtd.
dart:
	bash scripts/bootstrap-dart.sh

verify-gmrtd-pin:
	bash scripts/verify_gmrtd_pin.sh

# Go tests run against both gmrtd pins.
test-go:
	go vet ./...
	go test ./...
	go vet $(GO8) ./...
	go test $(GO8) ./...
	go vet $(GO132) ./...
	go test $(GO132) ./...

test-python: $(VENV_STAMP)
	cd classifier && ../$(PY) -m unittest test_schemas test_observability_vectors -v

test-java:
	cd drivers/jmrtd && mvn -q test

# The C# oracle against the shared vectors (uses the SDK from scripts/bootstrap-dotnet.sh).
test-dotnet:
	. ../_vendor/dotnet.env && dotnet build drivers/dotnet -c Release -o drivers/dotnet/bin/out -nologo -v q \
	  && dotnet drivers/dotnet/bin/out/EmrtdDotnetRead.dll -check-vectors testdata/observability-vectors.json

# The Dart oracle against the shared vectors (uses the SDK from scripts/bootstrap-dart.sh).
test-dart:
	. ../_vendor/dart.env && cd drivers/dart && dart pub get > /dev/null && mkdir -p build \
	  && dart compile exe bin/dmrtd_read.dart -o build/dmrtd_read > /dev/null \
	  && cd ../.. && drivers/dart/build/dmrtd_read -check-vectors testdata/observability-vectors.json

test: test-go test-python test-java test-dotnet test-dart

smoke: verify-gmrtd-pin $(VENV_STAMP)
	bash scripts/quick_test.sh

# make suite MANIFEST=suites/pace.json
suite: $(VENV_STAMP)
	bash scripts/run_suite.sh

evaluate: $(VENV_STAMP)
	bash scripts/evaluate.sh

repro:
	bash scripts/independent-repro.sh

verify-manifest: $(VENV_STAMP)
	@test -n "$(LOG_DIR)" -a -n "$(MANIFEST)" || (echo "usage: make verify-manifest LOG_DIR=logs/suite-... MANIFEST=suites/....json" && exit 1)
	$(PY) classifier/verify_manifest.py "$(LOG_DIR)" --manifest "$(MANIFEST)"
