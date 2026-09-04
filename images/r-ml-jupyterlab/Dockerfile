# R machine-learning workspace: R + IRkernel served through the same
# stay-alive JupyterLab shape as the PyTorch demo template. LabPod starts
# JupyterLab (R kernel) and TensorBoard on demand via `podman exec`, while
# `podman run --init` reaps zombies — so the image bakes no init (tini)
# and uses a sleep-infinity entrypoint.
#
# The CPU rocker base supplies R but not the ML package set this template is
# named for, so the recipe installs and load-checks the complete advertised
# stack. The base's CRAN configuration provides binary packages where
# available and falls back to source packages otherwise.
ARG BASE_IMAGE=docker.io/rocker/r-ver:4.4.1
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

# libzmq5 backs pbdZMQ, IRkernel's ZMQ transport. The binary package links
# against it but does not carry it, and the base does not ship it — without
# this the R kernel installs cleanly and then fails to load.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        libzmq5 \
        python3 \
        python3-pip \
        python3-venv \
        tmux \
        vim \
    && rm -rf /var/lib/apt/lists/*

# Keep the historical account cleanup for compatibility with older LabPod
# releases. Current LabPod can also run the unmodified rocker account layout:
# it maps the host owner to a free image-local uid/gid before injecting HOME.
RUN userdel rstudio 2>/dev/null || true; rm -rf /home/rstudio

# One Python interpreter for JupyterLab, the python3 kernel, and reticulate.
# Create it when absent and make the path explicit for both.
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH} \
    RETICULATE_PYTHON=/opt/venv/bin/python

RUN if [ ! -x "$VIRTUAL_ENV/bin/python" ]; then python3 -m venv "$VIRTUAL_ENV"; fi \
    && "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir uv \
    && uv --version

# ipykernel backs the advertised python3 kernel and numpy backs reticulate's
# array bridge. Name every dependency directly so the recipe does not depend
# on a transitive install continuing to provide an advertised launcher.
RUN uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache \
        jupyterlab \
        ipykernel \
        ipywidgets \
        jupyter-resource-usage \
        numpy \
        tensorboard \
    && "$VIRTUAL_ENV/bin/python" -c "import jupyterlab, tensorboard"

RUN Rscript -e 'pkgs <- c("tidyverse", "tidymodels", "caret", "xgboost", \
      "randomForest", "glmnet", "data.table", "reticulate", "IRkernel"); \
      install.packages(pkgs, Ncpus = max(1L, parallel::detectCores(), na.rm = TRUE)); \
      missing <- setdiff(pkgs, rownames(installed.packages())); \
      if (length(missing)) stop("failed to install: ", paste(missing, collapse = ", "))'

# Binary packages link against system libraries they do not carry, so a
# package can install cleanly and still fail to load. Attach each one with
# library(), the way a notebook does.
RUN Rscript -e 'pkgs <- c("tidyverse", "tidymodels", "caret", "xgboost", \
      "randomForest", "glmnet", "data.table", "reticulate", "IRkernel"); \
      ok <- vapply(pkgs, function(p) tryCatch({ \
        library(p, character.only = TRUE); TRUE \
      }, error = function(e) { message(conditionMessage(e)); FALSE }), logical(1)); \
      if (any(!ok)) stop("failed to load: ", paste(pkgs[!ok], collapse = ", "))'

# Register the R kernel system-wide (user=FALSE) so JupyterLab finds it
# regardless of which Linux account owns the workspace.
RUN Rscript -e 'IRkernel::installspec(user = FALSE)'

# The launchers locate these by name on PATH (probe_command), and both
# advertised kernels must resolve against this one interpreter.
RUN command -v jupyter && command -v tensorboard \
    && jupyter kernelspec list --json | "$VIRTUAL_ENV/bin/python" -c \
        'import json, os, sys; ks = json.load(sys.stdin)["kernelspecs"]; missing = [k for k in ("ir", "python3") if k not in ks]; missing and sys.exit("missing kernels: " + ", ".join(missing)); want = os.path.join(os.environ["VIRTUAL_ENV"], "bin", "python"); got = json.load(open(os.path.join(ks["python3"]["resource_dir"], "kernel.json")))["argv"][0]; got in ("python", want) or sys.exit("python3 kernel uses " + got + ", not " + want)'

# Resolve both reticulate and the shell-visible Python against the venv.
RUN [ "$(command -v python)" = "$VIRTUAL_ENV/bin/python" ] \
    && Rscript -e 'py <- reticulate::py_config()$python; \
      want <- file.path(Sys.getenv("VIRTUAL_ENV"), "bin", "python"); \
      if (!identical(py, want)) stop("reticulate python ", py, " is not ", want); \
      invisible(reticulate::import("numpy"))'

WORKDIR /work
EXPOSE 8888 6006

ENTRYPOINT ["sleep", "infinity"]
