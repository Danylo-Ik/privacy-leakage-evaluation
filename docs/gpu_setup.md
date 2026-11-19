# GPU setup (vast.ai + vLLM)

One GPU server runs the model, and everyone on the team uses it through an SSH tunnel. Only the person who holds the team's vast.ai credit rents, starts and stops it. Everyone else only needs their own SSH key and the server's API key.

## What runs where

- **GPU:** 1× A100 or H100 with 80 GB, about 120 GB of disk.
- **Image:** `vllm/vllm-openai:v0.33.0`.
- **Model:** `google/gemma-4-31B-it` in bf16 (about 62 GB of weights, 16k context).
- **Access:** port 8000 on the server, reached through `ssh -L`. The port is never opened to the internet.

## 1. Everyone: SSH key

Make a key if you don't have one:

```
ssh-keygen -t ed25519
```

Only the **public** key (`~/.ssh/id_ed25519.pub`) is ever shared. The private key stays on your laptop.

Get it onto the server in one of two ways:

- **Team members (preferred).** Ask the account holder to invite you to the vast.ai team as a Member. Members can use and rent instances but can't see billing. In the console, switch to your **personal** context (top-left), open Keys → SSH Keys and add your public key. Keys on your personal account are added to every team instance created *after* that, so do it before the server is rented. If the Keys page says "SSH Keys are only available in personal context", you are still in the team view: switch to your own account in the top-left, add the key, then switch back to the team to rent.
- **Not on the team.** Send your public key to the account holder, who adds it to the running instance (the instance's SSH key option in the console, or a new line in `/root/.ssh/authorized_keys`).

## 2. Account holder: Hugging Face token

Gemma's weights are gated. Accept the license at huggingface.co/google/gemma-4-31B-it, then create a read token at huggingface.co/settings/tokens. One token is enough for the whole team; it only goes into the instance's environment.

## 3. Account holder: rent the server

In the console, switch to the **team** context and pick a machine: one A100/H100 80 GB, reliability 98% or higher, about 120 GB of disk. Check the hourly price before renting.

Instance settings:

- **Image:** `vllm/vllm-openai:v0.33.0`
- **Launch mode:** SSH. This replaces the image's own start command, so vLLM is started by the on-start script below.
- **Environment variables:**
  - `HF_TOKEN=<token from step 2>`
  - `VLLM_API_KEY=<new random string>`, for example from `openssl rand -hex 24`
- **On-start script:**

  ```
  vllm serve google/gemma-4-31B-it --max-model-len 16384 --reasoning-parser gemma4 \
    --api-key $VLLM_API_KEY --port 8000 > /root/vllm.log 2>&1 &
  ```

The first start downloads the model and takes about 10–20 minutes. To follow it, SSH in and run `tail -f /root/vllm.log`. The server is ready when the log says it is listening on port 8000.

Share two things in the team's private chat, never in git:

- the SSH command from the instance's Connect button, e.g. `ssh -p 12345 root@ssh4.vast.ai`
- the `VLLM_API_KEY`

## 4. Everyone: connect

Open the tunnel and leave it running in its own terminal:

```
ssh -N -L 8000:localhost:8000 -p <port> root@<host>
```

Put this in `.env` in the repo root. `.env` is gitignored, so it never ends up in a commit:

```
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=google/gemma-4-31B-it
LLM_API_KEY=<VLLM_API_KEY>
LLM_MAX_TOKENS=8000
```

Leave `LLM_NO_SYSTEM` and `LLM_MIN_INTERVAL` out; they are only needed for Google's free API. Then check the connection:

```
python data_understanding/llm.py ping
```

## Rules

- **The account holder owns the bill.** They start the server, stop it when nobody is using it, and destroy it when the work is done. A stopped instance still pays a little for disk; a destroyed one pays nothing but has to download the model again on the next start.
- **One server, shared.** vLLM handles requests from several people at once, but two big runs at the same time slow each other down. Say in the chat before starting a long job.
- **One model per server.** If masking or the attacks need a different model (ideally they should, so the generator isn't also the judge), that is a second instance or a planned swap.
- **Run big jobs while the server is up.** Every reply is cached in `data/cache/llm/`, so reruns and analysis don't need the GPU.
- **Keys stay out of the repo.** No SSH keys, tokens or `VLLM_API_KEY` in commits, issues or code.

## When the work is done

1. Destroy the instance.
2. Remove the extra SSH keys from the team and personal accounts if they are no longer needed.
3. Forget the old `VLLM_API_KEY`; the next server gets a new one.

## Fallback without a GPU

Google AI Studio's free API serves Gemma 4 too (about 15k tokens a minute on the free tier):

```
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemma-4-31b-it
LLM_API_KEY=<AI Studio key>
LLM_NO_SYSTEM=1
LLM_MIN_INTERVAL=20
LLM_MAX_TOKENS=8000
```

It is slow, but it is enough for smoke tests and small runs.
