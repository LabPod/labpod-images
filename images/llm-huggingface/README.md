# Hugging Face compatibility boundary

The CUDA 12.1 variant deliberately retains PyTorch 2.5.1; CUDA 12.6/12.9
variants use PyTorch 2.8.0. The second package installation explicitly retains
the installed CUDA-tagged Torch version, rather than letting an application
dependency silently replace it with a different wheel.

`requirements.txt` pins the closely coupled Transformers, PEFT, TRL, Accelerate
and bitsandbytes packages together. Transformers 5.19.0 introduced an
import-time call to `torch.accelerator`, which is absent from Torch 2.5.1
([upstream issue](https://github.com/huggingface/transformers/issues/49380)).
5.18.0 is the preceding release. TRL 1.14.2 retains Python 3.10 support needed
by Ubuntu 22.04; TRL 1.15.0 requires Python 3.11.

Every image build runs `runtime-smoke.py` offline with two CPU threads. It
checks the Torch wheel/CUDA identity, package and trainer imports, and tiny
randomly initialized GPT-2 LoRA generation and backward propagation. It does
not download model weights, require a GPU, or validate CUDA/quantized kernels,
distributed training, activation offloading, or every model architecture.
The existing post-pull smoke still verifies the container and service contract.

When changing the pins, run the build smoke on each supported Python/Torch
pair, then validate all CUDA image variants. For a local CPU-only diagnostic:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
EXPECTED_TORCH_VERSION=2.5.1 EXPECTED_TORCH_CUDA=cpu \
python images/llm-huggingface/runtime-smoke.py
```

This is a compatibility cohort, not a complete transitive lock or a security
guarantee. Load only trusted training checkpoints; do not enable remote code
or optional kernels for untrusted models. Requalify a newer Transformers
release before removing the pin, including its minimum Torch requirement.
