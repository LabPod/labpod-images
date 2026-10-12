"""Offline CPU diagnostic; does not validate CUDA kernels or container runtime."""
import importlib
import importlib.metadata
import os
import sys
import unittest

import torch

torch.set_num_threads(2)


class HuggingFaceRuntimeTest(unittest.TestCase):
    def test_torch_wheel_identity(self):
        version = os.environ["EXPECTED_TORCH_VERSION"]
        channel = os.environ["EXPECTED_TORCH_CUDA"]
        self.assertEqual(torch.__version__, f"{version}+{channel}")
        expected_cuda = None if channel == "cpu" else channel[2:-1] + "." + channel[-1]
        self.assertEqual(torch.version.cuda, expected_cuda)

    def test_recipe_imports(self):
        for name in ("accelerate", "datasets", "peft", "transformers", "trl",
                     "bitsandbytes", "sentencepiece", "safetensors",
                     "huggingface_hub", "einops", "evaluate", "numpy", "pandas"):
            with self.subTest(package=name):
                importlib.import_module(name)

    def test_trainer_imports(self):
        from transformers import Trainer, TrainingArguments
        from trl import SFTConfig, SFTTrainer
        from accelerate import Accelerator
        self.assertEqual(Accelerator(cpu=True).device.type, "cpu")
        self.assertTrue(all(callable(x) for x in (Trainer, TrainingArguments, SFTConfig, SFTTrainer)))

    def test_tiny_lora_generation_and_backward(self):
        from transformers import GPT2Config, GPT2LMHeadModel
        from peft import LoraConfig, TaskType, get_peft_model
        torch.manual_seed(0)
        config = GPT2Config(vocab_size=32, n_positions=16, n_embd=16,
                            n_layer=1, n_head=2, bos_token_id=1,
                            eos_token_id=2, pad_token_id=0)
        config._attn_implementation = "eager"
        model = get_peft_model(GPT2LMHeadModel(config),
                              LoraConfig(task_type=TaskType.CAUSAL_LM, r=2,
                                         lora_alpha=4, target_modules=["c_attn"],
                                         fan_in_fan_out=True))
        inputs = torch.tensor([[1, 4, 5, 6]])
        mask = torch.ones_like(inputs)
        model.eval()
        with torch.no_grad():
            output = model.generate(input_ids=inputs, attention_mask=mask,
                                    max_new_tokens=2, min_new_tokens=2, do_sample=False)
        self.assertEqual(tuple(output.shape), (1, 6))
        model.train()
        result = model(input_ids=inputs, attention_mask=mask, labels=inputs)
        self.assertTrue(torch.isfinite(result.loss).item())
        result.loss.backward()
        gradients = [p.grad for p in model.parameters() if p.requires_grad and p.grad is not None]
        self.assertTrue(gradients)
        self.assertTrue(all(torch.isfinite(g).all().item() for g in gradients))


if __name__ == "__main__":
    print("Python:", sys.version, flush=True)
    print("Torch:", torch.__version__, "CUDA:", torch.version.cuda, flush=True)
    print({name: importlib.metadata.version(name) for name in
           ("transformers", "peft", "trl", "accelerate", "bitsandbytes")}, flush=True)
    unittest.main(verbosity=2)
