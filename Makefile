# owa-tools — convenience targets. The package itself installs via pip/uv;
# this just wires up shell completions, which can't live in a wheel.

COMP := $(CURDIR)/src/completions
ZSH_FPATH ?= $(shell brew --prefix 2>/dev/null)/share/zsh/site-functions
BASH_DIR  ?= $(shell brew --prefix 2>/dev/null)/etc/bash_completion.d
FISH_DIR  ?= $(HOME)/.config/fish/completions

.PHONY: install-completions uninstall-completions

# Symlinks (not copies) so `git pull` updates completions for free.
# Only links the shells whose target dir exists, so it's safe to run anywhere.
install-completions:
	@if [ -d "$(ZSH_FPATH)" ]; then \
		ln -sf "$(COMP)/owa-graph.zsh" "$(ZSH_FPATH)/_owa-graph" && \
		echo "zsh  -> $(ZSH_FPATH)/_owa-graph  (run: autoload -Uz compinit && compinit)"; \
	else echo "zsh  -- skipped, $(ZSH_FPATH) not found"; fi
	@if [ -d "$(BASH_DIR)" ]; then \
		ln -sf "$(COMP)/owa-graph.bash" "$(BASH_DIR)/owa-graph" && \
		echo "bash -> $(BASH_DIR)/owa-graph"; \
	else echo "bash -- skipped, $(BASH_DIR) not found"; fi
	@mkdir -p "$(FISH_DIR)" && ln -sf "$(COMP)/owa-graph.fish" "$(FISH_DIR)/owa-graph.fish" && \
		echo "fish -> $(FISH_DIR)/owa-graph.fish"

uninstall-completions:
	@rm -f "$(ZSH_FPATH)/_owa-graph" "$(BASH_DIR)/owa-graph" "$(FISH_DIR)/owa-graph.fish"
	@echo "removed owa-graph completion symlinks"
