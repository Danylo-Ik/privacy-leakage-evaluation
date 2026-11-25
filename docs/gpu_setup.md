# GPU setup (vast.ai + vLLM)

For copy-paste commands in order, see `docs/gpu_runbook.md`.

One GPU server runs the model, and everyone in the group uses it through an SSH tunnel. One person holds the vast.ai credit and rents, starts and stops the server. The others only need their own SSH key and the server's API key.

The vast.ai team is shared by the whole course. Other groups can see the instances in it, and possibly stop them, so nothing secret goes into the instance settings, and the instance gets a clear label.

## What runs where

- **GPU:** 1× A100 or H100 with 80 GB, 120 GB of disk.
- **Image:** `vllm/vllm-openai:v0.33.0`.
- **Model:** `google/gemma-4-31B-it` in bf16 (about 62 GB of weights, 16k context).
- **Access:** vLLM listens on `127.0.0.1:8000` inside the instance and is reached only through `ssh -L`.

## 1. Everyone: SSH key

If you don't have a key yet, make one with `ssh-keygen -t ed25519`. Share only the public key, `~/.ssh/id_ed25519.pub` (on a Mac, `pbcopy < ~/.ssh/id_ed25519.pub`). The private key never leaves your laptop. The last part of the public key line is a comment, often your email; you can leave it out when sharing.

The key has to reach the instance:

- **In the console.** Switch to your **personal** view (top-left; if the Keys page says "SSH Keys are only available in personal context", you are still in the team view), open Keys → SSH Keys and add the public key. Keys there are copied only to instances created *after* that, so add them before renting.
- **On a running instance.** Add the key on the instance card in the console, or have someone who can already log in append it to `/root/.ssh/authorized_keys`.

If your key has a passphrase, load it into the macOS agent once so scripts and tunnels can use it:

```
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

## 2. Hugging Face token

Gemma is gated. One person accepts the license at huggingface.co/google/gemma-4-31B-it and creates a **fine-grained, read-only** token (Settings → Access Tokens; tick only "read access to contents of all public gated repos you can access"). The token is only typed into the server's shell. It does not go into the repo, `.env`, the instance settings or chats. Delete it once the model is downloaded.

## 3. Rent the instance (team view)

Filters: 1× A100/H100 80 GB, reliability 98% or higher, download 500 Mbps or more, max CUDA 12.8 or newer. Check the hourly price including storage.

Settings:

- **Image:** `vllm/vllm-openai:v0.33.0`
- **Launch mode:** SSH
- **Docker options, environment variables, on-start script:** all empty
- **Disk:** 120 GB
- **Label:** your group and "do not stop"

When it is running, the Connect button shows a direct command (`ssh -p 34099 root@<ip>`) and a proxy one (`ssh -p 41234 root@ssh5.vast.ai`). Use the direct one; the proxy is a fallback.

## 4. Start vLLM on the instance

```
ssh -p <port> root@<ip>

read -s HF_TOKEN; export HF_TOKEN            # paste the token; nothing is shown
export VLLM_API_KEY=$(openssl rand -hex 24)
echo $VLLM_API_KEY                           # share privately with the group

nohup vllm serve google/gemma-4-31B-it \
  --max-model-len 16384 --gpu-memory-utilization 0.92 \
  --reasoning-parser gemma4 --api-key "$VLLM_API_KEY" \
  --host 127.0.0.1 --port 8000 > /root/vllm.log 2>&1 &

tail -f /root/vllm.log
```

The first start downloads the model (10–20 minutes). It is ready at `Application startup complete`. Ctrl+C stops watching the log, not the server. The session runs in tmux: Ctrl+b then d detaches and leaves everything running.

What the flags do: `--max-model-len` is the longest prompt plus reply (ours need 8–14k tokens), `--gpu-memory-utilization` lets vLLM use 92% of the GPU, `--reasoning-parser gemma4` keeps Gemma's thinking out of the answer, `--api-key` refuses requests without the key, and `--host 127.0.0.1` keeps the server off the internet. If it runs out of memory, add `--max-model-len 12288`; on an H100, `--quantization fp8` halves the weights.

## 5. Connect from the laptop

```
ssh -N -L 8000:localhost:8000 -p <port> root@<ip>     # leave running
```

`.env` in the repo root (gitignored):

```
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=google/gemma-4-31B-it
LLM_API_KEY=<VLLM_API_KEY>
LLM_MAX_TOKENS=8000
```

Check with `python data_understanding/llm.py ping`, then generate. On an A100, 30 documents took about 2.5 minutes with 8 workers.

## Stopping

| | How | Billing |
|---|---|---|
| Close the tunnel | Ctrl+C in its terminal | the server keeps running and costs money |
| Stop the instance | console → Stop | GPU billing stops, disk is still billed, the model stays |
| Destroy the instance | console → Destroy | everything stops and everything on it is deleted |

After a Stop, vLLM has to be started again by hand (step 4; the download is skipped) and the port may change. A stopped instance's GPU can be rented by someone else in the meantime. Only stop or destroy your own, labelled instance. Never leave it running overnight.

## When the work is done

Destroy the instance, delete the Hugging Face token, drop the old `VLLM_API_KEY`, and remove SSH keys that are no longer needed.

## Fallback without a GPU

Google AI Studio's free API serves Gemma 4 as well (about 15k tokens a minute):

```
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemma-4-31b-it
LLM_API_KEY=<AI Studio key>
LLM_NO_SYSTEM=1
LLM_MIN_INTERVAL=20
LLM_MAX_TOKENS=8000
```
