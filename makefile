.PHONY: all personal work setup deps install cli gui app-store osx dock dotfiles git node remote-login remote-login-revoke update packages check

PROFILE ?= personal
export PATH := /opt/homebrew/bin:/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:$(PATH)
WITH_SUDO_ASKPASS = scripts/with-sudo-askpass.sh
PLAYBOOK = $(WITH_SUDO_ASKPASS) ansible-playbook local.yaml -e machine_type=$(PROFILE)

all: personal

personal:
	@./install.sh personal

work:
	@./install.sh work

setup:
	@./install.sh --bootstrap-only

deps:
	@ansible-galaxy collection install -r requirements.yaml

install cli gui app-store osx dock node:
	@$(PLAYBOOK) --tags $@

dotfiles:
	@$(PLAYBOOK) --tags dotfiles -e install_dotfiles=true

git:
	@$(PLAYBOOK) --tags git-personal

remote-login:
	@$(PLAYBOOK) --tags remote-login -e manage_remote_login=true

remote-login-revoke:
	@$(PLAYBOOK) --tags remote-login-revoke -e revoke_remote_login=true

update:
	@$(WITH_SUDO_ASKPASS) ansible-playbook update.yaml -e machine_type=$(PROFILE)

packages:
	@ansible-playbook local.yaml -e machine_type=$(PROFILE) --check --tags packages

check:
	@for script in install.sh new-mac.sh scripts/*.sh; do bash -n "$$script" || exit; done
	@python3 scripts/check-platforms.py
	@python3 scripts/check-safety.py
	@find packages -name 'Brewfile.*' -exec sh -c 'for file do HOMEBREW_NO_AUTO_UPDATE=1 brew bundle list --file="$$file" >/dev/null || exit; done' sh {} +
	@ansible-playbook local.yaml --syntax-check
	@ansible-playbook update.yaml --syntax-check
	@$(MAKE) --no-print-directory packages
