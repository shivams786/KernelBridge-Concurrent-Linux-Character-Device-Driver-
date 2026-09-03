KDIR ?= /lib/modules/$(shell uname -r)/build
PWD := $(CURDIR)

.PHONY: all module userspace test load unload reload clean lint shellcheck cppcheck sparse verify help check-headers

all: module userspace

check-headers:
	@if [ ! -d "$(KDIR)" ]; then \
		echo "Kernel headers were not found at $(KDIR)."; \
		echo "On Ubuntu/Debian, install them with:"; \
		echo "  sudo apt install linux-headers-$$(uname -r)"; \
		exit 1; \
	fi

module: check-headers
	$(MAKE) -C $(KDIR) M=$(PWD) modules

userspace:
	$(MAKE) -C userspace

test: all
	sudo bash tests/run_all_tests.sh

load: module
	sudo bash scripts/load.sh

unload:
	sudo bash scripts/unload.sh

reload: module
	sudo bash scripts/reload.sh

shellcheck:
	shellcheck scripts/*.sh tests/*.sh

cppcheck:
	cppcheck --enable=warning,style,performance,portability --error-exitcode=1 --std=c11 -Iinclude userspace

sparse: check-headers
	$(MAKE) -C $(KDIR) M=$(PWD) C=1 modules

lint: shellcheck cppcheck

verify:
	bash scripts/dev_check.sh

clean:
	$(MAKE) -C userspace clean
	@if [ -d "$(KDIR)" ]; then \
		$(MAKE) -C $(KDIR) M=$(PWD) clean; \
	else \
		rm -f *.o *.ko *.mod *.mod.c *.order *.symvers .*.cmd; \
		rm -rf .tmp_versions; \
	fi
	bash scripts/clean.sh

help:
	@echo "Targets:"
	@echo "  make             Build kernel module and user-space tools"
	@echo "  make module      Build ringbuf_char.ko through kernel Kbuild"
	@echo "  make userspace   Build CLI and concurrency test"
	@echo "  make test        Run integration tests in a privileged Linux VM"
	@echo "  make load        Load the module"
	@echo "  make unload      Unload the module"
	@echo "  make reload      Rebuild and reload the module"
	@echo "  make verify      Run safe local repository checks"
	@echo "  make clean       Remove generated build artifacts"
